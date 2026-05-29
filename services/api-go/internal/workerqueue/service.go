package workerqueue

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/life2you/fishRadar2/services/api-go/internal/config"
	"github.com/redis/go-redis/v9"
)

const (
	jobTypeStartTask    = "start_task"
	jobTypeStopTask     = "stop_task"
	jobTypeGenerateTask = "generate_task"
	jobTypeReanalyze    = "reanalyze_result"
)

type Service struct {
	db            *sql.DB
	queueBackend  string
	redisQueueKey string
	redisClient   *redis.Client
}

type queueMessage struct {
	JobID  int64   `json:"job_id"`
	JobKey *string `json:"job_key,omitempty"`
}

func NewService(db *sql.DB, cfg config.Config) *Service {
	service := &Service{
		db:            db,
		queueBackend:  strings.ToLower(strings.TrimSpace(cfg.QueueBackend)),
		redisQueueKey: strings.TrimSpace(cfg.RedisQueueName),
	}
	if service.redisQueueKey == "" {
		service.redisQueueKey = "fishradar2:worker_jobs"
	}
	if service.queueBackend == "redis" {
		options, err := redis.ParseURL(strings.TrimSpace(cfg.RedisURL))
		if err == nil {
			service.redisClient = redis.NewClient(options)
		}
	}
	return service
}

func (s *Service) EnsureSchema(ctx context.Context) error {
	createTableStatement := `
CREATE TABLE IF NOT EXISTS worker_jobs (
	id BIGINT PRIMARY KEY AUTO_INCREMENT,
	job_key VARCHAR(64) NULL,
	job_type VARCHAR(64) NOT NULL,
	task_id BIGINT NOT NULL,
	task_name VARCHAR(255) NULL,
	status VARCHAR(32) NOT NULL DEFAULT 'pending',
	current_step VARCHAR(64) NULL,
	message TEXT NULL,
	steps_json LONGTEXT NULL,
	result_json LONGTEXT NULL,
	payload_json LONGTEXT NULL,
	requested_by_user_id BIGINT NULL,
	source VARCHAR(64) NOT NULL DEFAULT 'api',
	worker_id VARCHAR(128) NULL,
	process_id BIGINT NULL,
	created_at VARCHAR(64) NOT NULL,
	claimed_at VARCHAR(64) NULL,
	finished_at VARCHAR(64) NULL,
	error_message TEXT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Worker执行任务队列表'
`
	if _, err := s.db.ExecContext(ctx, createTableStatement); err != nil {
		return err
	}

	columnDefinitions := map[string]string{
		"job_key":      "VARCHAR(64) NULL",
		"task_name":    "VARCHAR(255) NULL",
		"current_step": "VARCHAR(64) NULL",
		"message":      "TEXT NULL",
		"steps_json":   "LONGTEXT NULL",
		"result_json":  "LONGTEXT NULL",
	}
	for columnName, columnSQL := range columnDefinitions {
		exists, err := s.columnExists(ctx, "worker_jobs", columnName)
		if err != nil {
			return err
		}
		if exists {
			continue
		}
		if _, err := s.db.ExecContext(ctx, fmt.Sprintf("ALTER TABLE worker_jobs ADD COLUMN %s %s", columnName, columnSQL)); err != nil {
			return err
		}
	}

	indexStatements := map[string]string{
		"idx_worker_jobs_status_created": "CREATE INDEX idx_worker_jobs_status_created ON worker_jobs(status, created_at)",
		"idx_worker_jobs_task_status":    "CREATE INDEX idx_worker_jobs_task_status ON worker_jobs(task_id, status)",
		"uniq_worker_jobs_job_key":       "CREATE UNIQUE INDEX uniq_worker_jobs_job_key ON worker_jobs(job_key)",
	}
	for indexName, statement := range indexStatements {
		exists, err := s.indexExists(ctx, "worker_jobs", indexName)
		if err != nil {
			return err
		}
		if exists {
			continue
		}
		if _, err := s.db.ExecContext(ctx, statement); err != nil {
			return err
		}
	}

	return nil
}

func (s *Service) columnExists(ctx context.Context, tableName string, columnName string) (bool, error) {
	var count int
	if err := s.db.QueryRowContext(ctx, `
SELECT COUNT(1)
FROM information_schema.columns
WHERE table_schema = DATABASE()
  AND table_name = ?
  AND column_name = ?
`, tableName, columnName).Scan(&count); err != nil {
		return false, err
	}
	return count > 0, nil
}

func (s *Service) indexExists(ctx context.Context, tableName string, indexName string) (bool, error) {
	var count int
	if err := s.db.QueryRowContext(ctx, `
SELECT COUNT(1)
FROM information_schema.statistics
WHERE table_schema = DATABASE()
  AND table_name = ?
  AND index_name = ?
`, tableName, indexName).Scan(&count); err != nil {
		return false, err
	}
	return count > 0, nil
}

func (s *Service) EnqueueStartTask(ctx context.Context, taskID int64, requestedByUserID *int64, source string) error {
	return s.enqueueTaskJob(ctx, jobTypeStartTask, taskID, requestedByUserID, source, nil)
}

func (s *Service) EnqueueStopTask(ctx context.Context, taskID int64, requestedByUserID *int64, source string) error {
	return s.enqueueTaskJob(ctx, jobTypeStopTask, taskID, requestedByUserID, source, nil)
}

func (s *Service) EnqueueGenerateTask(ctx context.Context, jobKey string, taskName string, payload any, requestedByUserID *int64, source string, stepsJSON string) error {
	if strings.TrimSpace(jobKey) == "" {
		return fmt.Errorf("生成作业标识不能为空")
	}
	if strings.TrimSpace(taskName) == "" {
		taskName = "未命名任务"
	}
	serializedPayload := "{}"
	if payload != nil {
		encoded, err := json.Marshal(payload)
		if err != nil {
			return err
		}
		serializedPayload = string(encoded)
	}
	result, err := s.db.ExecContext(ctx, `
INSERT INTO worker_jobs (
	job_key, job_type, task_id, task_name, status, current_step, message, steps_json, payload_json,
	requested_by_user_id, source, created_at
) VALUES (?, ?, 0, ?, 'pending', NULL, ?, ?, ?, ?, ?, ?)
`, jobKey, jobTypeGenerateTask, taskName, "任务已排队，等待开始。", stepsJSON, serializedPayload, nullableInt64(requestedByUserID), sourceOrDefault(source), nowISO())
	if err != nil {
		return err
	}
	return s.enqueueDelivery(ctx, result, &jobKey)
}

func (s *Service) EnqueueReanalyzeResult(ctx context.Context, jobKey string, filename string, tenantScope *int64, requestedByUserID *int64, source string) error {
	if strings.TrimSpace(jobKey) == "" {
		return fmt.Errorf("重分析作业标识不能为空")
	}
	payload := map[string]any{"filename": filename}
	if tenantScope != nil {
		payload["tenant_scope"] = *tenantScope
	}
	serializedPayload, err := json.Marshal(payload)
	if err != nil {
		return err
	}
	taskName := strings.TrimSpace(filename)
	if taskName == "" {
		taskName = "结果重分析"
	}
	result, err := s.db.ExecContext(ctx, `
INSERT INTO worker_jobs (
	job_key, job_type, task_id, task_name, status, current_step, message, payload_json,
	requested_by_user_id, source, created_at
) VALUES (?, ?, 0, ?, 'pending', NULL, ?, ?, ?, ?, ?)
`, jobKey, jobTypeReanalyze, taskName, "结果集已排队，等待重新分析。", string(serializedPayload), nullableInt64(requestedByUserID), sourceOrDefault(source), nowISO())
	if err != nil {
		return err
	}
	return s.enqueueDelivery(ctx, result, &jobKey)
}

func (s *Service) enqueueTaskJob(ctx context.Context, jobType string, taskID int64, requestedByUserID *int64, source string, payload map[string]any) error {
	if taskID <= 0 {
		return fmt.Errorf("任务ID无效")
	}
	source = sourceOrDefault(source)
	active, err := s.hasActiveJob(ctx, taskID, jobType)
	if err != nil {
		return err
	}
	if active {
		switch jobType {
		case jobTypeStartTask:
			return fmt.Errorf("任务启动请求已在队列中")
		case jobTypeStopTask:
			return fmt.Errorf("任务停止请求已在队列中")
		default:
			return fmt.Errorf("任务队列请求已存在")
		}
	}
	serializedPayload := "{}"
	if payload != nil {
		encoded, err := json.Marshal(payload)
		if err != nil {
			return err
		}
		serializedPayload = string(encoded)
	}
	result, err := s.db.ExecContext(ctx, `
INSERT INTO worker_jobs (
	job_type, task_id, status, payload_json, requested_by_user_id, source, created_at
) VALUES (?, ?, 'pending', ?, ?, ?, ?)
`, jobType, taskID, serializedPayload, nullableInt64(requestedByUserID), source, nowISO())
	if err != nil {
		return err
	}
	return s.enqueueDelivery(ctx, result, nil)
}

type QueuedJob struct {
	ID           int64
	JobKey       *string
	JobType      string
	TaskID       int64
	Status       string
	CurrentStep  *string
	Message      *string
	StepsJSON    *string
	ResultJSON   *string
	PayloadJSON  *string
	TaskName     *string
	ErrorMessage *string
}

func (s *Service) GetByJobKey(ctx context.Context, jobKey string) (*QueuedJob, error) {
	row := s.db.QueryRowContext(ctx, `
SELECT id, job_key, job_type, task_id, status, current_step, message, steps_json, result_json, payload_json, task_name, error_message
FROM worker_jobs
WHERE job_key = ?
LIMIT 1
`, jobKey)
	return scanQueuedJob(row)
}

func (s *Service) hasActiveJob(ctx context.Context, taskID int64, jobType string) (bool, error) {
	var count int
	if err := s.db.QueryRowContext(ctx, `
SELECT COUNT(1)
FROM worker_jobs
WHERE task_id = ?
  AND job_type = ?
  AND status IN ('pending', 'claimed')
`, taskID, jobType).Scan(&count); err != nil {
		return false, err
	}
	return count > 0, nil
}

func nullableInt64(value *int64) any {
	if value == nil {
		return nil
	}
	return *value
}

func (s *Service) enqueueDelivery(ctx context.Context, result sql.Result, jobKey *string) error {
	if s.queueBackend != "redis" || s.redisClient == nil {
		return nil
	}
	jobID, err := result.LastInsertId()
	if err != nil {
		return err
	}
	payload, err := json.Marshal(queueMessage{
		JobID:  jobID,
		JobKey: jobKey,
	})
	if err != nil {
		return err
	}
	return s.redisClient.RPush(ctx, s.redisQueueKey, payload).Err()
}

func nullableString(value sql.NullString) *string {
	if !value.Valid {
		return nil
	}
	text := value.String
	return &text
}

type queueScanner interface {
	Scan(dest ...any) error
}

func scanQueuedJob(scanner queueScanner) (*QueuedJob, error) {
	var (
		item         QueuedJob
		jobKey       sql.NullString
		currentStep  sql.NullString
		message      sql.NullString
		stepsJSON    sql.NullString
		resultJSON   sql.NullString
		payloadJSON  sql.NullString
		taskName     sql.NullString
		errorMessage sql.NullString
	)
	if err := scanner.Scan(
		&item.ID,
		&jobKey,
		&item.JobType,
		&item.TaskID,
		&item.Status,
		&currentStep,
		&message,
		&stepsJSON,
		&resultJSON,
		&payloadJSON,
		&taskName,
		&errorMessage,
	); err != nil {
		return nil, err
	}
	item.JobKey = nullableString(jobKey)
	item.CurrentStep = nullableString(currentStep)
	item.Message = nullableString(message)
	item.StepsJSON = nullableString(stepsJSON)
	item.ResultJSON = nullableString(resultJSON)
	item.PayloadJSON = nullableString(payloadJSON)
	item.TaskName = nullableString(taskName)
	item.ErrorMessage = nullableString(errorMessage)
	return &item, nil
}

func (q *QueuedJob) JobKeyOrDefault() string {
	if q == nil || q.JobKey == nil || strings.TrimSpace(*q.JobKey) == "" {
		return ""
	}
	return *q.JobKey
}

func (q *QueuedJob) TaskNameOrDefault() string {
	if q == nil || q.TaskName == nil || strings.TrimSpace(*q.TaskName) == "" {
		return "未命名任务"
	}
	return *q.TaskName
}

func (q *QueuedJob) MessageOrDefault() string {
	if q == nil || q.Message == nil || strings.TrimSpace(*q.Message) == "" {
		switch q.Status {
		case "completed":
			return "任务执行完成。"
		case "failed":
			if q.ErrorMessage != nil && strings.TrimSpace(*q.ErrorMessage) != "" {
				return *q.ErrorMessage
			}
			return "任务执行失败。"
		case "claimed", "running":
			return "任务正在处理中。"
		default:
			return "任务已排队，等待开始。"
		}
	}
	return *q.Message
}

func sourceOrDefault(source string) string {
	if strings.TrimSpace(source) == "" {
		return "api"
	}
	return source
}

func nowISO() string {
	return time.Now().Format(time.RFC3339)
}

var ErrJobAlreadyQueued = errors.New("worker job already queued")
