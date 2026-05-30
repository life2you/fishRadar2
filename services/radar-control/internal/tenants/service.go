package tenants

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"strings"
	"time"
)

const defaultAdminTenantSlug = "platform-admin"

type ValidationError string

func (e ValidationError) Error() string {
	return string(e)
}

type Item struct {
	ID                 int64   `json:"id"`
	Name               string  `json:"name"`
	Slug               string  `json:"slug"`
	Status             string  `json:"status"`
	AIEnabled          bool    `json:"ai_enabled"`
	ActivationRequired bool    `json:"activation_required"`
	ActivatedAt        *string `json:"activated_at"`
	AccessExpiresAt    *string `json:"access_expires_at"`
	AccessExpired      bool    `json:"access_expired"`
	WorkspaceEnabled   bool    `json:"workspace_enabled"`
	CanUseAI           bool    `json:"can_use_ai"`
	CreatedAt          string  `json:"created_at"`
	MemberCount        int64   `json:"member_count"`
}

type Metrics struct {
	TaskCount                   int64   `json:"task_count"`
	EnabledTaskCount            int64   `json:"enabled_task_count"`
	RunningTaskCount            int64   `json:"running_task_count"`
	ResultFileCount             int64   `json:"result_file_count"`
	ScannedItemCount            int64   `json:"scanned_item_count"`
	AIRecommendedItemCount      int64   `json:"ai_recommended_item_count"`
	KeywordRecommendedItemCount int64   `json:"keyword_recommended_item_count"`
	RecommendedItemCount        int64   `json:"recommended_item_count"`
	LatestCrawlTime             *string `json:"latest_crawl_time"`
}

type ActivationCodeSummary struct {
	Code            string  `json:"code"`
	Status          string  `json:"status"`
	DurationMinutes int64   `json:"duration_minutes"`
	Note            *string `json:"note"`
	CreatedAt       string  `json:"created_at"`
	RedeemedAt      *string `json:"redeemed_at"`
}

type Detail struct {
	Tenant               Item                   `json:"tenant"`
	Metrics              Metrics                `json:"metrics"`
	LatestActivationCode *ActivationCodeSummary `json:"latest_activation_code"`
}

type UpdateInput struct {
	Status              *string `json:"status"`
	AIEnabled           *bool   `json:"ai_enabled"`
	ActivationRequired  *bool   `json:"activation_required"`
	ExtendAccessMinutes *int    `json:"extend_access_minutes"`
}

type Service struct {
	db *sql.DB
}

func NewService(db *sql.DB) *Service {
	return &Service{db: db}
}

func (s *Service) List(ctx context.Context) ([]Item, error) {
	rows, err := s.db.QueryContext(ctx, `
		SELECT
			t.id,
			t.name,
			t.slug,
			t.status,
			t.ai_enabled,
			t.activation_required,
			t.activated_at,
			t.access_expires_at,
			t.created_at,
			COUNT(m.id) AS member_count
		FROM tenants AS t
		LEFT JOIN user_tenant_memberships AS m ON m.tenant_id = t.id
		GROUP BY
			t.id,
			t.name,
			t.slug,
			t.status,
			t.ai_enabled,
			t.activation_required,
			t.activated_at,
			t.access_expires_at,
			t.created_at
		ORDER BY t.id DESC
	`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	items := make([]Item, 0)
	for rows.Next() {
		record, err := scanTenantRecord(rows)
		if err != nil {
			return nil, err
		}
		items = append(items, record.toItem())
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return items, nil
}

func (s *Service) GetDetail(ctx context.Context, tenantID int64) (*Detail, error) {
	record, err := s.fetchTenantRecord(ctx, tenantID)
	if err != nil {
		return nil, err
	}

	var (
		taskCount                   sql.NullInt64
		enabledTaskCount            sql.NullInt64
		runningTaskCount            sql.NullInt64
		resultFileCount             sql.NullInt64
		scannedItemCount            sql.NullInt64
		aiRecommendedItemCount      sql.NullInt64
		keywordRecommendedItemCount sql.NullInt64
		latestCrawlTime             sql.NullString
	)
	if err := s.db.QueryRowContext(ctx, `
		SELECT
			COUNT(1) AS total_tasks,
			SUM(CASE WHEN enabled = 1 THEN 1 ELSE 0 END) AS enabled_tasks,
			SUM(CASE WHEN is_running = 1 THEN 1 ELSE 0 END) AS running_tasks
		FROM tasks
		WHERE tenant_id = ?
	`, tenantID).Scan(&taskCount, &enabledTaskCount, &runningTaskCount); err != nil {
		return nil, err
	}

	if err := s.db.QueryRowContext(ctx, `
		SELECT
			COUNT(DISTINCT result_filename) AS result_files,
			COUNT(1) AS scanned_items,
			SUM(CASE WHEN is_recommended = 1 AND analysis_source = 'ai' THEN 1 ELSE 0 END) AS ai_recommended_items,
			SUM(CASE WHEN is_recommended = 1 AND analysis_source = 'keyword' THEN 1 ELSE 0 END) AS keyword_recommended_items,
			MAX(crawl_time) AS latest_crawl_time
		FROM result_items
		WHERE tenant_id = ?
	`, tenantID).Scan(
		&resultFileCount,
		&scannedItemCount,
		&aiRecommendedItemCount,
		&keywordRecommendedItemCount,
		&latestCrawlTime,
	); err != nil {
		return nil, err
	}

	var latestCode *ActivationCodeSummary
	row := s.db.QueryRowContext(ctx, `
		SELECT
			code,
			status,
			duration_minutes,
			note,
			created_at,
			redeemed_at
		FROM activation_codes
		WHERE redeemed_by_tenant_id = ?
		ORDER BY redeemed_at DESC, id DESC
		LIMIT 1
	`, tenantID)
	var (
		codeValue     string
		statusValue   string
		durationValue sql.NullInt64
		noteValue     sql.NullString
		createdValue  string
		redeemedValue sql.NullString
	)
	switch err := row.Scan(&codeValue, &statusValue, &durationValue, &noteValue, &createdValue, &redeemedValue); {
	case errors.Is(err, sql.ErrNoRows):
		latestCode = nil
	case err != nil:
		return nil, err
	default:
		latestCode = &ActivationCodeSummary{
			Code:            codeValue,
			Status:          statusValue,
			DurationMinutes: nullInt64(durationValue),
			Note:            nullableString(noteValue),
			CreatedAt:       createdValue,
			RedeemedAt:      nullableString(redeemedValue),
		}
	}

	aiRecommended := nullInt64(aiRecommendedItemCount)
	keywordRecommended := nullInt64(keywordRecommendedItemCount)
	return &Detail{
		Tenant: record.toItem(),
		Metrics: Metrics{
			TaskCount:                   nullInt64(taskCount),
			EnabledTaskCount:            nullInt64(enabledTaskCount),
			RunningTaskCount:            nullInt64(runningTaskCount),
			ResultFileCount:             nullInt64(resultFileCount),
			ScannedItemCount:            nullInt64(scannedItemCount),
			AIRecommendedItemCount:      aiRecommended,
			KeywordRecommendedItemCount: keywordRecommended,
			RecommendedItemCount:        aiRecommended + keywordRecommended,
			LatestCrawlTime:             nullableString(latestCrawlTime),
		},
		LatestActivationCode: latestCode,
	}, nil
}

func (s *Service) UpdateAccess(ctx context.Context, tenantID int64, input UpdateInput) (*Item, error) {
	if input.Status != nil {
		normalized := strings.TrimSpace(*input.Status)
		if normalized != "active" && normalized != "disabled" {
			return nil, ValidationError("租户状态仅支持 active 或 disabled")
		}
		input.Status = &normalized
	}
	if input.ExtendAccessMinutes != nil && (*input.ExtendAccessMinutes < 1 || *input.ExtendAccessMinutes > 525600) {
		return nil, ValidationError("续期时长必须在 1 到 525600 分钟之间")
	}
	if input.Status == nil && input.AIEnabled == nil && input.ActivationRequired == nil && input.ExtendAccessMinutes == nil {
		return nil, ValidationError("没有可更新的租户字段")
	}

	record, err := s.fetchTenantRecord(ctx, tenantID)
	if err != nil {
		return nil, err
	}
	if record.Slug == defaultAdminTenantSlug && input.ActivationRequired != nil && *input.ActivationRequired {
		return nil, ValidationError("管理员租户不能开启激活限制")
	}
	if record.Slug == defaultAdminTenantSlug && input.Status != nil && *input.Status == "disabled" {
		return nil, ValidationError("管理员租户不能被停用")
	}

	now := time.Now()
	nowText := now.Format(time.RFC3339)
	finalStatus := input.Status
	needActivatedAt := false
	clearAccessExpires := false
	var accessExpiresAtValue *string

	if input.ActivationRequired != nil && !*input.ActivationRequired {
		needActivatedAt = true
		clearAccessExpires = true
	}

	if input.ExtendAccessMinutes != nil {
		baseTime := now
		if currentExpires, ok := parseOptionalTime(record.AccessExpiresAt); ok && currentExpires.After(baseTime) {
			baseTime = currentExpires
		}
		nextExpiry := baseTime.Add(time.Duration(*input.ExtendAccessMinutes) * time.Minute).Format(time.RFC3339)
		accessExpiresAtValue = &nextExpiry
		clearAccessExpires = false
		needActivatedAt = true
		if record.ActivationRequired && (finalStatus == nil || *finalStatus != "disabled") {
			statusValue := "active"
			finalStatus = &statusValue
		}
	}

	updates := make([]string, 0, 6)
	params := make([]any, 0, 8)
	if finalStatus != nil {
		updates = append(updates, "status = ?")
		params = append(params, *finalStatus)
	}
	if input.AIEnabled != nil {
		updates = append(updates, "ai_enabled = ?")
		params = append(params, boolAsInt(*input.AIEnabled))
	}
	if input.ActivationRequired != nil {
		updates = append(updates, "activation_required = ?")
		params = append(params, boolAsInt(*input.ActivationRequired))
	}
	if needActivatedAt {
		updates = append(updates, "activated_at = COALESCE(activated_at, ?)")
		params = append(params, nowText)
	}
	if clearAccessExpires {
		updates = append(updates, "access_expires_at = NULL")
	}
	if accessExpiresAtValue != nil {
		updates = append(updates, "access_expires_at = ?")
		params = append(params, *accessExpiresAtValue)
	}
	if len(updates) == 0 {
		return nil, ValidationError("没有可更新的租户字段")
	}

	if _, err := s.db.ExecContext(
		ctx,
		fmt.Sprintf("UPDATE tenants SET %s WHERE id = ?", strings.Join(updates, ", ")),
		append(params, tenantID)...,
	); err != nil {
		return nil, err
	}

	updated, err := s.fetchTenantRecord(ctx, tenantID)
	if err != nil {
		return nil, err
	}
	item := updated.toItem()
	return &item, nil
}

func (s *Service) fetchTenantRecord(ctx context.Context, tenantID int64) (*tenantRecord, error) {
	row := s.db.QueryRowContext(ctx, `
		SELECT
			t.id,
			t.name,
			t.slug,
			t.status,
			t.ai_enabled,
			t.activation_required,
			t.activated_at,
			t.access_expires_at,
			t.created_at,
			COUNT(m.id) AS member_count
		FROM tenants AS t
		LEFT JOIN user_tenant_memberships AS m ON m.tenant_id = t.id
		WHERE t.id = ?
		GROUP BY
			t.id,
			t.name,
			t.slug,
			t.status,
			t.ai_enabled,
			t.activation_required,
			t.activated_at,
			t.access_expires_at,
			t.created_at
		LIMIT 1
	`, tenantID)

	record, err := scanTenantRecord(row)
	if err != nil {
		return nil, err
	}
	return &record, nil
}

type scanner interface {
	Scan(dest ...any) error
}

type tenantRecord struct {
	ID                 int64
	Name               string
	Slug               string
	Status             string
	AIEnabled          bool
	ActivationRequired bool
	ActivatedAt        *string
	AccessExpiresAt    *string
	CreatedAt          string
	MemberCount        int64
}

func scanTenantRecord(source scanner) (tenantRecord, error) {
	var (
		record             tenantRecord
		aiEnabled          sql.NullBool
		activationRequired sql.NullBool
		activatedAt        sql.NullString
		accessExpiresAt    sql.NullString
		memberCount        sql.NullInt64
	)
	if err := source.Scan(
		&record.ID,
		&record.Name,
		&record.Slug,
		&record.Status,
		&aiEnabled,
		&activationRequired,
		&activatedAt,
		&accessExpiresAt,
		&record.CreatedAt,
		&memberCount,
	); err != nil {
		return tenantRecord{}, err
	}
	record.AIEnabled = aiEnabled.Valid && aiEnabled.Bool
	record.ActivationRequired = activationRequired.Valid && activationRequired.Bool
	record.ActivatedAt = nullableString(activatedAt)
	record.AccessExpiresAt = nullableString(accessExpiresAt)
	record.MemberCount = nullInt64(memberCount)
	return record, nil
}

func (record tenantRecord) toItem() Item {
	accessExpired := false
	if expiresAt, ok := parseOptionalTime(record.AccessExpiresAt); ok {
		accessExpired = !expiresAt.After(time.Now())
	}
	activated := record.ActivatedAt != nil && strings.TrimSpace(*record.ActivatedAt) != ""
	workspaceEnabled := record.Status == "active" && (!record.ActivationRequired || activated) && !accessExpired
	return Item{
		ID:                 record.ID,
		Name:               record.Name,
		Slug:               record.Slug,
		Status:             record.Status,
		AIEnabled:          record.AIEnabled,
		ActivationRequired: record.ActivationRequired,
		ActivatedAt:        record.ActivatedAt,
		AccessExpiresAt:    record.AccessExpiresAt,
		AccessExpired:      accessExpired,
		WorkspaceEnabled:   workspaceEnabled,
		CanUseAI:           workspaceEnabled && record.AIEnabled,
		CreatedAt:          record.CreatedAt,
		MemberCount:        record.MemberCount,
	}
}

func parseOptionalTime(value *string) (time.Time, bool) {
	if value == nil || strings.TrimSpace(*value) == "" {
		return time.Time{}, false
	}
	text := strings.TrimSpace(*value)
	if parsed, err := time.Parse(time.RFC3339, text); err == nil {
		return parsed, true
	}
	if parsed, err := time.Parse("2006-01-02T15:04:05", text); err == nil {
		return parsed, true
	}
	return time.Time{}, false
}

func nullableString(value sql.NullString) *string {
	if !value.Valid {
		return nil
	}
	text := value.String
	return &text
}

func nullInt64(value sql.NullInt64) int64 {
	if !value.Valid {
		return 0
	}
	return value.Int64
}

func boolAsInt(value bool) int {
	if value {
		return 1
	}
	return 0
}
