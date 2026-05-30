package aiaccounts

import (
	"context"
	"database/sql"
	"strings"
	"time"
)

type Item struct {
	ID              int64   `json:"id"`
	Name            string  `json:"name"`
	APIKey          string  `json:"api_key"`
	APIKeySet       bool    `json:"api_key_set"`
	BaseURL         string  `json:"base_url"`
	ModelName       string  `json:"model_name"`
	SupportsImage   bool    `json:"supports_image"`
	SupportsText    bool    `json:"supports_text"`
	Enabled         bool    `json:"enabled"`
	Priority        int     `json:"priority"`
	Notes           *string `json:"notes"`
	CreatedAt       *string `json:"created_at"`
	UpdatedAt       *string `json:"updated_at"`
	LastTestStatus  *string `json:"last_test_status"`
	LastTestMessage *string `json:"last_test_message"`
	LastTestedAt    *string `json:"last_tested_at"`
}

type CreateInput struct {
	Name          string  `json:"name"`
	APIKey        *string `json:"api_key"`
	BaseURL       string  `json:"base_url"`
	ModelName     string  `json:"model_name"`
	SupportsImage bool    `json:"supports_image"`
	SupportsText  bool    `json:"supports_text"`
	Enabled       bool    `json:"enabled"`
	Priority      int     `json:"priority"`
	Notes         *string `json:"notes"`
}

type UpdateInput struct {
	Name          *string `json:"name"`
	APIKey        *string `json:"api_key"`
	BaseURL       *string `json:"base_url"`
	ModelName     *string `json:"model_name"`
	SupportsImage *bool   `json:"supports_image"`
	SupportsText  *bool   `json:"supports_text"`
	Enabled       *bool   `json:"enabled"`
	Priority      *int    `json:"priority"`
	Notes         *string `json:"notes"`
}

type ValidationError string

func (e ValidationError) Error() string {
	return string(e)
}

type Service struct {
	db *sql.DB
}

type TestConfig struct {
	AccountID int64
	APIKey    string
	BaseURL   string
	ModelName string
}

func NewService(db *sql.DB) *Service {
	return &Service{db: db}
}

func (s *Service) List(ctx context.Context, includeDisabled bool) ([]Item, error) {
	query := `
		SELECT id, name, api_key, base_url, model_name, supports_image, supports_text,
		       enabled, priority, notes, last_test_status, last_test_message,
		       last_tested_at, created_at, updated_at
		FROM ai_accounts
	`
	if !includeDisabled {
		query += " WHERE enabled = 1"
	}
	query += " ORDER BY enabled DESC, priority ASC, id ASC"

	rows, err := s.db.QueryContext(ctx, query)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	items := make([]Item, 0)
	for rows.Next() {
		item, err := scanAccount(rows)
		if err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s *Service) Get(ctx context.Context, accountID int64) (*Item, error) {
	row := s.db.QueryRowContext(ctx, `
		SELECT id, name, api_key, base_url, model_name, supports_image, supports_text,
		       enabled, priority, notes, last_test_status, last_test_message,
		       last_tested_at, created_at, updated_at
		FROM ai_accounts
		WHERE id = ?
		LIMIT 1
	`, accountID)
	item, err := scanAccount(row)
	if err != nil {
		return nil, err
	}
	return &item, nil
}

func (s *Service) Create(ctx context.Context, input CreateInput) (*Item, error) {
	if err := validateCreateInput(input); err != nil {
		return nil, err
	}
	now := nowISO()
	_, err := s.db.ExecContext(ctx, `
		INSERT INTO ai_accounts (
			name, api_key, base_url, model_name, supports_image, supports_text,
			enabled, priority, notes, last_test_status, last_test_message,
			last_tested_at, created_at, updated_at
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
	`,
		strings.TrimSpace(input.Name),
		nullableTrimmed(input.APIKey),
		strings.TrimSpace(input.BaseURL),
		strings.TrimSpace(input.ModelName),
		boolAsInt(input.SupportsImage),
		boolAsInt(input.SupportsText),
		boolAsInt(input.Enabled),
		input.Priority,
		nullableTrimmed(input.Notes),
		nil,
		nil,
		nil,
		now,
		now,
	)
	if err != nil {
		return nil, err
	}
	var createdID int64
	if err := s.db.QueryRowContext(ctx, `SELECT LAST_INSERT_ID()`).Scan(&createdID); err != nil {
		return nil, err
	}
	return s.Get(ctx, createdID)
}

func (s *Service) Update(ctx context.Context, accountID int64, input UpdateInput) (*Item, error) {
	existing, err := s.Get(ctx, accountID)
	if err != nil {
		return nil, err
	}

	finalSupportsImage := existing.SupportsImage
	if input.SupportsImage != nil {
		finalSupportsImage = *input.SupportsImage
	}
	finalSupportsText := existing.SupportsText
	if input.SupportsText != nil {
		finalSupportsText = *input.SupportsText
	}
	if !finalSupportsImage && !finalSupportsText {
		return nil, ValidationError("至少需要开启一种能力：图片分析或文本分析")
	}

	updates := make([]string, 0, 10)
	params := make([]any, 0, 12)
	if input.Name != nil {
		updates = append(updates, "name = ?")
		params = append(params, strings.TrimSpace(*input.Name))
	}
	if input.APIKey != nil {
		updates = append(updates, "api_key = ?")
		params = append(params, nullableTrimmed(input.APIKey))
	}
	if input.BaseURL != nil {
		updates = append(updates, "base_url = ?")
		params = append(params, strings.TrimSpace(*input.BaseURL))
	}
	if input.ModelName != nil {
		updates = append(updates, "model_name = ?")
		params = append(params, strings.TrimSpace(*input.ModelName))
	}
	if input.SupportsImage != nil {
		updates = append(updates, "supports_image = ?")
		params = append(params, boolAsInt(*input.SupportsImage))
	}
	if input.SupportsText != nil {
		updates = append(updates, "supports_text = ?")
		params = append(params, boolAsInt(*input.SupportsText))
	}
	if input.Enabled != nil {
		updates = append(updates, "enabled = ?")
		params = append(params, boolAsInt(*input.Enabled))
	}
	if input.Priority != nil {
		updates = append(updates, "priority = ?")
		params = append(params, *input.Priority)
	}
	if input.Notes != nil {
		updates = append(updates, "notes = ?")
		params = append(params, nullableTrimmed(input.Notes))
	}
	if len(updates) == 0 {
		item := *existing
		return &item, nil
	}
	updates = append(updates, "updated_at = ?")
	params = append(params, nowISO(), accountID)

	_, err = s.db.ExecContext(
		ctx,
		"UPDATE ai_accounts SET "+strings.Join(updates, ", ")+" WHERE id = ?",
		params...,
	)
	if err != nil {
		return nil, err
	}
	return s.Get(ctx, accountID)
}

func (s *Service) Delete(ctx context.Context, accountID int64) (bool, error) {
	result, err := s.db.ExecContext(ctx, `DELETE FROM ai_accounts WHERE id = ?`, accountID)
	if err != nil {
		return false, err
	}
	affected, err := result.RowsAffected()
	if err != nil {
		return false, err
	}
	return affected > 0, nil
}

func (s *Service) GetTestConfig(ctx context.Context, accountID int64) (*TestConfig, error) {
	var (
		config    TestConfig
		apiKey    sql.NullString
		baseURL   sql.NullString
		modelName sql.NullString
	)
	if err := s.db.QueryRowContext(ctx, `
		SELECT id, api_key, base_url, model_name
		FROM ai_accounts
		WHERE id = ?
		LIMIT 1
	`, accountID).Scan(&config.AccountID, &apiKey, &baseURL, &modelName); err != nil {
		return nil, err
	}
	config.APIKey = strings.TrimSpace(apiKey.String)
	config.BaseURL = strings.TrimSpace(baseURL.String)
	config.ModelName = strings.TrimSpace(modelName.String)
	return &config, nil
}

func validateCreateInput(input CreateInput) error {
	if strings.TrimSpace(input.Name) == "" {
		return ValidationError("AI账号名称不能为空")
	}
	if strings.TrimSpace(input.BaseURL) == "" {
		return ValidationError("API Base URL 不能为空")
	}
	if strings.TrimSpace(input.ModelName) == "" {
		return ValidationError("模型名称不能为空")
	}
	if !input.SupportsImage && !input.SupportsText {
		return ValidationError("至少需要开启一种能力：图片分析或文本分析")
	}
	return nil
}

type accountScanner interface {
	Scan(dest ...any) error
}

func scanAccount(source accountScanner) (Item, error) {
	var (
		item            Item
		apiKey          sql.NullString
		supportsImage   sql.NullBool
		supportsText    sql.NullBool
		enabled         sql.NullBool
		notes           sql.NullString
		lastTestStatus  sql.NullString
		lastTestMessage sql.NullString
		lastTestedAt    sql.NullString
		createdAt       sql.NullString
		updatedAt       sql.NullString
	)
	if err := source.Scan(
		&item.ID,
		&item.Name,
		&apiKey,
		&item.BaseURL,
		&item.ModelName,
		&supportsImage,
		&supportsText,
		&enabled,
		&item.Priority,
		&notes,
		&lastTestStatus,
		&lastTestMessage,
		&lastTestedAt,
		&createdAt,
		&updatedAt,
	); err != nil {
		return Item{}, err
	}
	item.APIKey = ""
	item.APIKeySet = strings.TrimSpace(apiKey.String) != ""
	item.SupportsImage = supportsImage.Valid && supportsImage.Bool
	item.SupportsText = supportsText.Valid && supportsText.Bool
	item.Enabled = enabled.Valid && enabled.Bool
	item.Notes = nullableString(notes)
	item.LastTestStatus = nullableString(lastTestStatus)
	item.LastTestMessage = nullableString(lastTestMessage)
	item.LastTestedAt = nullableString(lastTestedAt)
	item.CreatedAt = nullableString(createdAt)
	item.UpdatedAt = nullableString(updatedAt)
	return item, nil
}

func nullableString(value sql.NullString) *string {
	if !value.Valid {
		return nil
	}
	text := value.String
	return &text
}

func nullableTrimmed(value *string) any {
	if value == nil {
		return nil
	}
	text := strings.TrimSpace(*value)
	if text == "" {
		return nil
	}
	return text
}

func boolAsInt(value bool) int {
	if value {
		return 1
	}
	return 0
}

func nowISO() string {
	return time.Now().Format(time.RFC3339)
}
