package accounts

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"regexp"
	"strings"
	"time"
)

const (
	accountStateKindAccount = "account"
	accountStateKindDefault = "default"
	defaultLoginStateName   = "__default__"
)

var accountNamePattern = regexp.MustCompile(`^[a-zA-Z0-9_-]{1,50}$`)

type Service struct {
	db *sql.DB
}

func NewService(db *sql.DB) *Service {
	return &Service{db: db}
}

type Item struct {
	Name      string  `json:"name"`
	Path      string  `json:"path"`
	Content   *string `json:"content,omitempty"`
	UpdatedAt *string `json:"updated_at,omitempty"`
}

func (s *Service) List(ctx context.Context) ([]Item, error) {
	rows, err := s.db.QueryContext(ctx, `
SELECT name, updated_at
FROM account_states
WHERE kind = ?
ORDER BY name ASC
`, accountStateKindAccount)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	items := make([]Item, 0)
	for rows.Next() {
		var (
			name      string
			updatedAt sql.NullString
		)
		if err := rows.Scan(&name, &updatedAt); err != nil {
			return nil, err
		}
		items = append(items, Item{
			Name:      name,
			Path:      buildAccountReference(name),
			UpdatedAt: nullableString(updatedAt),
		})
	}
	return items, rows.Err()
}

func (s *Service) Get(ctx context.Context, name string) (*Item, error) {
	normalized, err := ValidateAccountName(name)
	if err != nil {
		return nil, err
	}
	row := s.db.QueryRowContext(ctx, `
SELECT name, state_json, updated_at
FROM account_states
WHERE kind = ? AND name = ?
LIMIT 1
`, accountStateKindAccount, normalized)

	var (
		item      Item
		content   string
		updatedAt sql.NullString
	)
	if err := row.Scan(&item.Name, &content, &updatedAt); err != nil {
		return nil, err
	}
	item.Path = buildAccountReference(item.Name)
	item.Content = &content
	item.UpdatedAt = nullableString(updatedAt)
	return &item, nil
}

func (s *Service) Create(ctx context.Context, name string, content string) (*Item, error) {
	normalized, err := ValidateAccountName(name)
	if err != nil {
		return nil, err
	}
	validated, err := ValidateStateJSON(content)
	if err != nil {
		return nil, err
	}
	if existing, err := s.Get(ctx, normalized); err == nil && existing != nil {
		return nil, fmt.Errorf("账号已存在")
	} else if err != nil && err != sql.ErrNoRows {
		return nil, err
	}
	return s.upsert(ctx, normalized, validated, accountStateKindAccount, buildAccountReference(normalized))
}

func (s *Service) Update(ctx context.Context, name string, content string) (*Item, error) {
	normalized, err := ValidateAccountName(name)
	if err != nil {
		return nil, err
	}
	validated, err := ValidateStateJSON(content)
	if err != nil {
		return nil, err
	}
	if _, err := s.Get(ctx, normalized); err != nil {
		return nil, err
	}
	return s.upsert(ctx, normalized, validated, accountStateKindAccount, buildAccountReference(normalized))
}

func (s *Service) Delete(ctx context.Context, name string) (bool, error) {
	normalized, err := ValidateAccountName(name)
	if err != nil {
		return false, err
	}
	result, err := s.db.ExecContext(ctx, `
DELETE FROM account_states
WHERE kind = ? AND name = ?
`, accountStateKindAccount, normalized)
	if err != nil {
		return false, err
	}
	affected, err := result.RowsAffected()
	if err != nil {
		return false, err
	}
	return affected > 0, nil
}

func (s *Service) UpsertDefaultLoginState(ctx context.Context, content string) error {
	validated, err := ValidateStateJSON(content)
	if err != nil {
		return err
	}
	_, err = s.upsert(ctx, defaultLoginStateName, validated, accountStateKindDefault, "xianyu_state.json")
	return err
}

func (s *Service) DeleteDefaultLoginState(ctx context.Context) (bool, error) {
	result, err := s.db.ExecContext(ctx, `
DELETE FROM account_states
WHERE kind = ? AND name = ?
`, accountStateKindDefault, defaultLoginStateName)
	if err != nil {
		return false, err
	}
	affected, err := result.RowsAffected()
	if err != nil {
		return false, err
	}
	return affected > 0, nil
}

func (s *Service) upsert(ctx context.Context, name string, content string, kind string, path string) (*Item, error) {
	now := time.Now().Format(time.RFC3339)
	_, err := s.db.ExecContext(ctx, `
INSERT INTO account_states (name, kind, state_json, created_at, updated_at)
VALUES (?, ?, ?, ?, ?)
ON DUPLICATE KEY UPDATE
	state_json = VALUES(state_json),
	updated_at = VALUES(updated_at)
`, name, kind, content, now, now)
	if err != nil {
		return nil, err
	}

	item := &Item{
		Name:      name,
		Path:      path,
		Content:   &content,
		UpdatedAt: &now,
	}
	return item, nil
}

func ValidateAccountName(name string) (string, error) {
	trimmed := strings.TrimSpace(name)
	if trimmed == "" || !accountNamePattern.MatchString(trimmed) {
		return "", fmt.Errorf("账号名称只能包含字母、数字、下划线或短横线")
	}
	return trimmed, nil
}

func ValidateStateJSON(content string) (string, error) {
	text := strings.TrimSpace(content)
	if text == "" {
		return "", fmt.Errorf("登录态内容不能为空")
	}
	var payload any
	if err := json.Unmarshal([]byte(text), &payload); err != nil {
		return "", fmt.Errorf("提供的内容不是有效的JSON格式")
	}
	normalized, err := json.Marshal(payload)
	if err != nil {
		return "", err
	}
	return string(normalized), nil
}

func buildAccountReference(name string) string {
	return "state/" + name + ".json"
}

func nullableString(value sql.NullString) *string {
	if !value.Valid {
		return nil
	}
	text := value.String
	return &text
}
