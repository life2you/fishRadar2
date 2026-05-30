package tasks

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"slices"
	"strings"
)

type Service struct {
	db *sql.DB
}

func NewService(db *sql.DB) *Service {
	return &Service{db: db}
}

type Item struct {
	ID                   int64    `json:"id"`
	TenantID             *int64   `json:"tenant_id,omitempty"`
	TaskName             string   `json:"task_name"`
	Enabled              bool     `json:"enabled"`
	Keyword              string   `json:"keyword"`
	Description          string   `json:"description"`
	AnalyzeImages        bool     `json:"analyze_images"`
	MaxPages             int      `json:"max_pages"`
	PersonalOnly         bool     `json:"personal_only"`
	MinPrice             *string  `json:"min_price"`
	MaxPrice             *string  `json:"max_price"`
	Cron                 *string  `json:"cron"`
	NextRunAt            *string  `json:"next_run_at"`
	AIPromptBaseFile     string   `json:"ai_prompt_base_file"`
	AIPromptCriteriaFile string   `json:"ai_prompt_criteria_file"`
	AIPromptBaseText     *string  `json:"ai_prompt_base_text"`
	AIPromptCriteriaText *string  `json:"ai_prompt_criteria_text"`
	AIPromptText         *string  `json:"ai_prompt_text"`
	AccountStateFile     *string  `json:"account_state_file"`
	AccountStrategy      string   `json:"account_strategy"`
	FreeShipping         bool     `json:"free_shipping"`
	NewPublishOption     *string  `json:"new_publish_option"`
	Region               *string  `json:"region"`
	DecisionMode         string   `json:"decision_mode"`
	KeywordRules         []string `json:"keyword_rules"`
	IsRunning            bool     `json:"is_running"`
}

func (s *Service) List(ctx context.Context, tenantID *int64) ([]Item, error) {
	query := `
SELECT id, tenant_id, task_name, enabled, keyword, description, analyze_images, max_pages,
       personal_only, min_price, max_price, cron, ai_prompt_base_file, ai_prompt_criteria_file,
       ai_prompt_base_text, ai_prompt_criteria_text, ai_prompt_text,
       account_state_file, account_strategy, free_shipping, new_publish_option, region,
       decision_mode, keyword_rules_json, is_running
FROM tasks
`
	args := []any{}
	if tenantID != nil {
		query += "WHERE tenant_id = ? "
		args = append(args, *tenantID)
	}
	query += "ORDER BY id DESC"

	rows, err := s.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	items := make([]Item, 0)
	for rows.Next() {
		item, err := scanTask(rows)
		if err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return items, nil
}

func (s *Service) Get(ctx context.Context, taskID int64) (*Item, error) {
	row := s.db.QueryRowContext(ctx, `
SELECT id, tenant_id, task_name, enabled, keyword, description, analyze_images, max_pages,
       personal_only, min_price, max_price, cron, ai_prompt_base_file, ai_prompt_criteria_file,
       ai_prompt_base_text, ai_prompt_criteria_text, ai_prompt_text,
       account_state_file, account_strategy, free_shipping, new_publish_option, region,
       decision_mode, keyword_rules_json, is_running
FROM tasks
WHERE id = ?
LIMIT 1
`, taskID)
	item, err := scanTaskScanner(row)
	if err != nil {
		return nil, err
	}
	return &item, nil
}

type CreateInput struct {
	TenantID             *int64   `json:"tenant_id"`
	TaskName             string   `json:"task_name"`
	Enabled              bool     `json:"enabled"`
	Keyword              string   `json:"keyword"`
	Description          string   `json:"description"`
	AnalyzeImages        bool     `json:"analyze_images"`
	MaxPages             int      `json:"max_pages"`
	PersonalOnly         bool     `json:"personal_only"`
	MinPrice             *string  `json:"min_price"`
	MaxPrice             *string  `json:"max_price"`
	Cron                 *string  `json:"cron"`
	AIPromptBaseFile     string   `json:"ai_prompt_base_file"`
	AIPromptCriteriaFile string   `json:"ai_prompt_criteria_file"`
	AIPromptBaseText     *string  `json:"ai_prompt_base_text"`
	AIPromptCriteriaText *string  `json:"ai_prompt_criteria_text"`
	AIPromptText         *string  `json:"ai_prompt_text"`
	AccountStateFile     *string  `json:"account_state_file"`
	AccountStrategy      string   `json:"account_strategy"`
	FreeShipping         bool     `json:"free_shipping"`
	NewPublishOption     *string  `json:"new_publish_option"`
	Region               *string  `json:"region"`
	DecisionMode         string   `json:"decision_mode"`
	KeywordRules         []string `json:"keyword_rules"`
}

type UpdateInput struct {
	TenantID             *int64    `json:"tenant_id"`
	TaskName             *string   `json:"task_name"`
	Enabled              *bool     `json:"enabled"`
	Keyword              *string   `json:"keyword"`
	Description          *string   `json:"description"`
	AnalyzeImages        *bool     `json:"analyze_images"`
	MaxPages             *int      `json:"max_pages"`
	PersonalOnly         *bool     `json:"personal_only"`
	MinPrice             **string  `json:"min_price"`
	MaxPrice             **string  `json:"max_price"`
	Cron                 **string  `json:"cron"`
	AIPromptBaseFile     *string   `json:"ai_prompt_base_file"`
	AIPromptCriteriaFile *string   `json:"ai_prompt_criteria_file"`
	AIPromptBaseText     **string  `json:"ai_prompt_base_text"`
	AIPromptCriteriaText **string  `json:"ai_prompt_criteria_text"`
	AIPromptText         **string  `json:"ai_prompt_text"`
	AccountStateFile     **string  `json:"account_state_file"`
	AccountStrategy      *string   `json:"account_strategy"`
	FreeShipping         *bool     `json:"free_shipping"`
	NewPublishOption     **string  `json:"new_publish_option"`
	Region               **string  `json:"region"`
	DecisionMode         *string   `json:"decision_mode"`
	KeywordRules         *[]string `json:"keyword_rules"`
	IsRunning            *bool     `json:"is_running"`
}

type ValidationError struct {
	Message string
}

func (e ValidationError) Error() string {
	return e.Message
}

func (s *Service) Create(ctx context.Context, input CreateInput) (*Item, error) {
	if err := validateCreateInput(input); err != nil {
		return nil, err
	}
	taskID, err := s.nextTaskID(ctx)
	if err != nil {
		return nil, err
	}
	if err := s.save(ctx, taskID, input, false); err != nil {
		return nil, err
	}
	return s.Get(ctx, taskID)
}

func (s *Service) Update(ctx context.Context, taskID int64, input UpdateInput) (*Item, error) {
	current, err := s.Get(ctx, taskID)
	if err != nil {
		return nil, err
	}
	merged, err := mergeTaskUpdate(*current, input)
	if err != nil {
		return nil, err
	}
	if err := validateCreateInput(merged); err != nil {
		return nil, err
	}
	isRunning := current.IsRunning
	if input.IsRunning != nil {
		isRunning = *input.IsRunning
	}
	if err := s.save(ctx, taskID, merged, isRunning); err != nil {
		return nil, err
	}
	return s.Get(ctx, taskID)
}

func (s *Service) Delete(ctx context.Context, taskID int64) (bool, error) {
	result, err := s.db.ExecContext(ctx, "DELETE FROM tasks WHERE id = ?", taskID)
	if err != nil {
		return false, err
	}
	affected, err := result.RowsAffected()
	if err != nil {
		return false, err
	}
	return affected > 0, nil
}

func (s *Service) SetRunning(ctx context.Context, taskID int64, isRunning bool) error {
	result, err := s.db.ExecContext(ctx, "UPDATE tasks SET is_running = ? WHERE id = ?", isRunning, taskID)
	if err != nil {
		return err
	}
	affected, err := result.RowsAffected()
	if err != nil {
		return err
	}
	if affected == 0 {
		return sql.ErrNoRows
	}
	return nil
}

func (s *Service) ResetAllRunningFlags(ctx context.Context) error {
	_, err := s.db.ExecContext(ctx, "UPDATE tasks SET is_running = 0 WHERE is_running <> 0")
	return err
}

type taskScanner interface {
	Scan(dest ...any) error
}

func scanTask(scanner taskScanner) (Item, error) {
	return scanTaskScanner(scanner)
}

func scanTaskScanner(scanner taskScanner) (Item, error) {
	var (
		item                 Item
		tenantID             sql.NullInt64
		description          sql.NullString
		minPrice             sql.NullString
		maxPrice             sql.NullString
		cron                 sql.NullString
		aiPromptBaseText     sql.NullString
		aiPromptCriteriaText sql.NullString
		aiPromptText         sql.NullString
		accountStateFile     sql.NullString
		newPublishOption     sql.NullString
		region               sql.NullString
		keywordRulesJSON     string
	)
	if err := scanner.Scan(
		&item.ID,
		&tenantID,
		&item.TaskName,
		&item.Enabled,
		&item.Keyword,
		&description,
		&item.AnalyzeImages,
		&item.MaxPages,
		&item.PersonalOnly,
		&minPrice,
		&maxPrice,
		&cron,
		&item.AIPromptBaseFile,
		&item.AIPromptCriteriaFile,
		&aiPromptBaseText,
		&aiPromptCriteriaText,
		&aiPromptText,
		&accountStateFile,
		&item.AccountStrategy,
		&item.FreeShipping,
		&newPublishOption,
		&region,
		&item.DecisionMode,
		&keywordRulesJSON,
		&item.IsRunning,
	); err != nil {
		return Item{}, err
	}

	if tenantID.Valid {
		item.TenantID = &tenantID.Int64
	}
	item.Description = description.String
	item.MinPrice = nullableString(minPrice)
	item.MaxPrice = nullableString(maxPrice)
	item.Cron = nullableString(cron)
	item.AIPromptBaseText = nullableString(aiPromptBaseText)
	item.AIPromptCriteriaText = nullableString(aiPromptCriteriaText)
	item.AIPromptText = nullableString(aiPromptText)
	item.AccountStateFile = nullableString(accountStateFile)
	item.NewPublishOption = nullableString(newPublishOption)
	item.Region = nullableString(region)
	item.NextRunAt = nil

	if err := json.Unmarshal([]byte(keywordRulesJSON), &item.KeywordRules); err != nil {
		return Item{}, fmt.Errorf("解析任务关键词规则失败: %w", err)
	}
	if item.KeywordRules == nil {
		item.KeywordRules = []string{}
	}

	return item, nil
}

func nullableString(value sql.NullString) *string {
	if !value.Valid {
		return nil
	}
	text := value.String
	return &text
}

func validateCreateInput(input CreateInput) error {
	if input.TaskName == "" {
		return ValidationError{Message: "任务名称不能为空"}
	}
	if input.Keyword == "" {
		return ValidationError{Message: "搜索关键词不能为空"}
	}
	if input.MaxPages <= 0 {
		return ValidationError{Message: "最大页数必须大于 0"}
	}
	if input.AIPromptBaseFile == "" {
		input.AIPromptBaseFile = "prompts/base_prompt.txt"
	}
	if input.DecisionMode == "" {
		input.DecisionMode = "ai"
	}
	switch input.DecisionMode {
	case "ai":
		if strings.TrimSpace(input.Description) == "" {
			return ValidationError{Message: "AI 判断模式下，详细需求(description)不能为空。"}
		}
	case "keyword":
		if len(normalizeKeywordRules(input.KeywordRules)) == 0 {
			return ValidationError{Message: "关键词判断模式下，至少需要一个关键词。"}
		}
	default:
		return ValidationError{Message: "决策模式无效"}
	}
	if input.AccountStrategy == "" {
		input.AccountStrategy = "auto"
	}
	switch input.AccountStrategy {
	case "auto", "fixed", "rotate":
	default:
		return ValidationError{Message: "账号策略无效"}
	}
	if input.AccountStrategy == "fixed" && (input.AccountStateFile == nil || strings.TrimSpace(*input.AccountStateFile) == "") {
		return ValidationError{Message: "固定账号模式下必须选择账号。"}
	}
	return nil
}

func normalizeKeywordRules(values []string) []string {
	seen := make(map[string]struct{})
	normalized := make([]string, 0, len(values))
	for _, raw := range values {
		text := strings.TrimSpace(raw)
		if text == "" {
			continue
		}
		key := strings.ToLower(text)
		if _, exists := seen[key]; exists {
			continue
		}
		seen[key] = struct{}{}
		normalized = append(normalized, text)
	}
	return normalized
}

func (s *Service) nextTaskID(ctx context.Context) (int64, error) {
	var maxID int64
	err := s.db.QueryRowContext(ctx, "SELECT COALESCE(MAX(id), -1) FROM tasks").Scan(&maxID)
	if err != nil {
		return 0, err
	}
	if maxID < 1 {
		return 1, nil
	}
	return maxID + 1, nil
}

func (s *Service) save(ctx context.Context, taskID int64, input CreateInput, isRunning bool) error {
	keywordRulesJSON, err := json.Marshal(normalizeKeywordRules(input.KeywordRules))
	if err != nil {
		return err
	}
	_, err = s.db.ExecContext(ctx, `
INSERT INTO tasks (
	id, tenant_id, task_name, enabled, keyword, description, analyze_images,
	max_pages, personal_only, min_price, max_price, cron,
	ai_prompt_base_file, ai_prompt_criteria_file, ai_prompt_base_text,
	ai_prompt_criteria_text, ai_prompt_text, account_state_file,
	account_strategy, free_shipping, new_publish_option, region,
	decision_mode, keyword_rules_json, is_running
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON DUPLICATE KEY UPDATE
	tenant_id = VALUES(tenant_id),
	task_name = VALUES(task_name),
	enabled = VALUES(enabled),
	keyword = VALUES(keyword),
	description = VALUES(description),
	analyze_images = VALUES(analyze_images),
	max_pages = VALUES(max_pages),
	personal_only = VALUES(personal_only),
	min_price = VALUES(min_price),
	max_price = VALUES(max_price),
	cron = VALUES(cron),
	ai_prompt_base_file = VALUES(ai_prompt_base_file),
	ai_prompt_criteria_file = VALUES(ai_prompt_criteria_file),
	ai_prompt_base_text = VALUES(ai_prompt_base_text),
	ai_prompt_criteria_text = VALUES(ai_prompt_criteria_text),
	ai_prompt_text = VALUES(ai_prompt_text),
	account_state_file = VALUES(account_state_file),
	account_strategy = VALUES(account_strategy),
	free_shipping = VALUES(free_shipping),
	new_publish_option = VALUES(new_publish_option),
	region = VALUES(region),
	decision_mode = VALUES(decision_mode),
	keyword_rules_json = VALUES(keyword_rules_json),
	is_running = VALUES(is_running)
`, taskID, input.TenantID, input.TaskName, input.Enabled, input.Keyword, input.Description, input.AnalyzeImages,
		input.MaxPages, input.PersonalOnly, input.MinPrice, input.MaxPrice, input.Cron,
		coalesceString(input.AIPromptBaseFile, "prompts/base_prompt.txt"), input.AIPromptCriteriaFile, input.AIPromptBaseText,
		input.AIPromptCriteriaText, input.AIPromptText, input.AccountStateFile,
		input.AccountStrategy, input.FreeShipping, input.NewPublishOption, input.Region,
		input.DecisionMode, string(keywordRulesJSON), isRunning)
	return err
}

func mergeTaskUpdate(current Item, update UpdateInput) (CreateInput, error) {
	merged := CreateInput{
		TenantID:             current.TenantID,
		TaskName:             current.TaskName,
		Enabled:              current.Enabled,
		Keyword:              current.Keyword,
		Description:          current.Description,
		AnalyzeImages:        current.AnalyzeImages,
		MaxPages:             current.MaxPages,
		PersonalOnly:         current.PersonalOnly,
		MinPrice:             current.MinPrice,
		MaxPrice:             current.MaxPrice,
		Cron:                 current.Cron,
		AIPromptBaseFile:     current.AIPromptBaseFile,
		AIPromptCriteriaFile: current.AIPromptCriteriaFile,
		AIPromptBaseText:     current.AIPromptBaseText,
		AIPromptCriteriaText: current.AIPromptCriteriaText,
		AIPromptText:         current.AIPromptText,
		AccountStateFile:     current.AccountStateFile,
		AccountStrategy:      current.AccountStrategy,
		FreeShipping:         current.FreeShipping,
		NewPublishOption:     current.NewPublishOption,
		Region:               current.Region,
		DecisionMode:         current.DecisionMode,
		KeywordRules:         slices.Clone(current.KeywordRules),
	}
	if update.TenantID != nil {
		merged.TenantID = update.TenantID
	}
	if update.TaskName != nil {
		merged.TaskName = *update.TaskName
	}
	if update.Enabled != nil {
		merged.Enabled = *update.Enabled
	}
	if update.Keyword != nil {
		merged.Keyword = *update.Keyword
	}
	if update.Description != nil {
		merged.Description = *update.Description
	}
	if update.AnalyzeImages != nil {
		merged.AnalyzeImages = *update.AnalyzeImages
	}
	if update.MaxPages != nil {
		merged.MaxPages = *update.MaxPages
	}
	if update.PersonalOnly != nil {
		merged.PersonalOnly = *update.PersonalOnly
	}
	if update.MinPrice != nil {
		merged.MinPrice = *update.MinPrice
	}
	if update.MaxPrice != nil {
		merged.MaxPrice = *update.MaxPrice
	}
	if update.Cron != nil {
		merged.Cron = *update.Cron
	}
	if update.AIPromptBaseFile != nil {
		merged.AIPromptBaseFile = *update.AIPromptBaseFile
	}
	if update.AIPromptCriteriaFile != nil {
		merged.AIPromptCriteriaFile = *update.AIPromptCriteriaFile
	}
	if update.AIPromptBaseText != nil {
		merged.AIPromptBaseText = *update.AIPromptBaseText
	}
	if update.AIPromptCriteriaText != nil {
		merged.AIPromptCriteriaText = *update.AIPromptCriteriaText
	}
	if update.AIPromptText != nil {
		merged.AIPromptText = *update.AIPromptText
	}
	if update.AccountStateFile != nil {
		merged.AccountStateFile = *update.AccountStateFile
	}
	if update.AccountStrategy != nil {
		merged.AccountStrategy = *update.AccountStrategy
	}
	if update.FreeShipping != nil {
		merged.FreeShipping = *update.FreeShipping
	}
	if update.NewPublishOption != nil {
		merged.NewPublishOption = *update.NewPublishOption
	}
	if update.Region != nil {
		merged.Region = *update.Region
	}
	if update.DecisionMode != nil {
		merged.DecisionMode = *update.DecisionMode
	}
	if update.KeywordRules != nil {
		merged.KeywordRules = normalizeKeywordRules(*update.KeywordRules)
	}
	return merged, nil
}

func coalesceString(value string, fallback string) string {
	if strings.TrimSpace(value) == "" {
		return fallback
	}
	return value
}
