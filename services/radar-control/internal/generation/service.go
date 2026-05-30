package generation

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/google/uuid"
	"github.com/life2you/fishRadar2/services/radar-control/internal/config"
	"github.com/life2you/fishRadar2/services/radar-control/internal/tasks"
	"github.com/life2you/fishRadar2/services/radar-control/internal/workerqueue"
)

type Service struct {
	cfg         config.Config
	taskService *tasks.Service
	queue       *workerqueue.Service
}

func NewService(cfg config.Config, taskService *tasks.Service, queue *workerqueue.Service) *Service {
	return &Service{
		cfg:         cfg,
		taskService: taskService,
		queue:       queue,
	}
}

type JobStatus string
type StepStatus string

const (
	JobQueued    JobStatus = "queued"
	JobRunning   JobStatus = "running"
	JobCompleted JobStatus = "completed"
	JobFailed    JobStatus = "failed"

	StepPending   StepStatus = "pending"
	StepRunning   StepStatus = "running"
	StepCompleted StepStatus = "completed"
	StepFailed    StepStatus = "failed"
)

var defaultSteps = []Step{
	{Key: "prepare", Label: "接收创建请求", Status: StepPending},
	{Key: "reference", Label: "读取参考文件", Status: StepPending},
	{Key: "prompt", Label: "构建提示词", Status: StepPending},
	{Key: "llm", Label: "调用 AI 生成标准", Status: StepPending},
	{Key: "persist", Label: "保存分析标准", Status: StepPending},
	{Key: "task", Label: "创建任务记录", Status: StepPending},
}

type Step struct {
	Key     string     `json:"key"`
	Label   string     `json:"label"`
	Status  StepStatus `json:"status"`
	Message string     `json:"message"`
}

type Job struct {
	JobID       string      `json:"job_id"`
	TaskName    string      `json:"task_name"`
	Status      JobStatus   `json:"status"`
	Message     string      `json:"message"`
	CurrentStep *string     `json:"current_step"`
	Steps       []Step      `json:"steps"`
	Task        *tasks.Item `json:"task"`
	Error       *string     `json:"error"`
}

type GenerateRequest struct {
	TenantID         *int64   `json:"tenant_id,omitempty"`
	TaskName         string   `json:"task_name"`
	Keyword          string   `json:"keyword"`
	Description      string   `json:"description"`
	AnalyzeImages    bool     `json:"analyze_images"`
	PersonalOnly     bool     `json:"personal_only"`
	MinPrice         *string  `json:"min_price"`
	MaxPrice         *string  `json:"max_price"`
	MaxPages         int      `json:"max_pages"`
	Cron             *string  `json:"cron"`
	AccountStateFile *string  `json:"account_state_file"`
	AccountStrategy  string   `json:"account_strategy"`
	FreeShipping     bool     `json:"free_shipping"`
	NewPublishOption *string  `json:"new_publish_option"`
	Region           *string  `json:"region"`
	DecisionMode     string   `json:"decision_mode"`
	KeywordRules     []string `json:"keyword_rules"`
}

func (s *Service) CreateJob(ctx context.Context, payload GenerateRequest, requestedByUserID *int64) (*Job, error) {
	jobID := uuid.NewString()
	stepsJSON, err := json.Marshal(cloneSteps(defaultSteps))
	if err != nil {
		return nil, err
	}
	if err := s.queue.EnqueueGenerateTask(
		ctx,
		jobID,
		payload.TaskName,
		payload,
		requestedByUserID,
		"radar-control",
		string(stepsJSON),
	); err != nil {
		return nil, err
	}
	return s.GetJob(ctx, jobID)
}

func (s *Service) GetJob(ctx context.Context, jobID string) (*Job, error) {
	queuedJob, err := s.queue.GetByJobKey(ctx, jobID)
	if err != nil {
		return nil, err
	}
	return s.fromQueuedJob(ctx, queuedJob)
}

func (s *Service) fromQueuedJob(ctx context.Context, queuedJob *workerqueue.QueuedJob) (*Job, error) {
	if queuedJob == nil {
		return nil, nil
	}

	job := &Job{
		JobID:       queuedJob.JobKeyOrDefault(),
		TaskName:    queuedJob.TaskNameOrDefault(),
		Status:      normalizeJobStatus(queuedJob.Status),
		Message:     queuedJob.MessageOrDefault(),
		CurrentStep: queuedJob.CurrentStep,
		Steps:       cloneSteps(defaultSteps),
	}

	if queuedJob.StepsJSON != nil && *queuedJob.StepsJSON != "" {
		var steps []Step
		if err := json.Unmarshal([]byte(*queuedJob.StepsJSON), &steps); err == nil && len(steps) > 0 {
			job.Steps = steps
		}
	}

	if queuedJob.ResultJSON != nil && *queuedJob.ResultJSON != "" {
		var task tasks.Item
		if err := json.Unmarshal([]byte(*queuedJob.ResultJSON), &task); err == nil && task.ID > 0 {
			job.Task = &task
		}
	}
	if job.Task == nil && queuedJob.TaskID > 0 && queuedJob.Status == "completed" {
		task, err := s.taskService.Get(ctx, queuedJob.TaskID)
		if err == nil {
			job.Task = task
		}
	}

	if queuedJob.ErrorMessage != nil && *queuedJob.ErrorMessage != "" {
		job.Error = queuedJob.ErrorMessage
		job.Message = *queuedJob.ErrorMessage
	}

	return job, nil
}

func cloneSteps(source []Step) []Step {
	cloned := make([]Step, len(source))
	copy(cloned, source)
	return cloned
}

func normalizeJobStatus(status string) JobStatus {
	switch status {
	case "claimed", "running":
		return JobRunning
	case "completed":
		return JobCompleted
	case "failed":
		return JobFailed
	default:
		return JobQueued
	}
}

func (j *Job) String() string {
	return fmt.Sprintf("Job<%s %s>", j.JobID, j.Status)
}
