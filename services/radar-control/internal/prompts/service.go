package prompts

import (
	"context"
	"database/sql"
	"fmt"
	"strings"
	"time"
)

const sourceManual = "manual"

type Service struct {
	db *sql.DB
}

func NewService(db *sql.DB) *Service {
	return &Service{db: db}
}

type Document struct {
	Filename  string  `json:"filename"`
	Content   string  `json:"content"`
	Source    *string `json:"source,omitempty"`
	CreatedAt *string `json:"created_at,omitempty"`
	UpdatedAt *string `json:"updated_at,omitempty"`
}

func (s *Service) List(ctx context.Context) ([]string, error) {
	rows, err := s.db.QueryContext(ctx, `
SELECT filename
FROM prompt_documents
ORDER BY filename ASC
`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	filenames := make([]string, 0)
	for rows.Next() {
		var filename string
		if err := rows.Scan(&filename); err != nil {
			return nil, err
		}
		filenames = append(filenames, basePromptName(filename))
	}
	return filenames, rows.Err()
}

func (s *Service) Get(ctx context.Context, filename string) (*Document, error) {
	normalized, err := NormalizeFilename(filename)
	if err != nil {
		return nil, err
	}
	row := s.db.QueryRowContext(ctx, `
SELECT filename, content, source, created_at, updated_at
FROM prompt_documents
WHERE filename = ?
LIMIT 1
`, normalized)

	var (
		document  Document
		source    sql.NullString
		createdAt sql.NullString
		updatedAt sql.NullString
	)
	if err := row.Scan(&document.Filename, &document.Content, &source, &createdAt, &updatedAt); err != nil {
		return nil, err
	}
	document.Filename = basePromptName(document.Filename)
	document.Source = nullableString(source)
	document.CreatedAt = nullableString(createdAt)
	document.UpdatedAt = nullableString(updatedAt)
	return &document, nil
}

func (s *Service) Update(ctx context.Context, filename string, content string) (*Document, error) {
	normalized, err := NormalizeFilename(filename)
	if err != nil {
		return nil, err
	}
	if strings.TrimSpace(content) == "" {
		return nil, fmt.Errorf("Prompt 内容不能为空")
	}

	var createdAt sql.NullString
	if err := s.db.QueryRowContext(ctx, `
SELECT created_at
FROM prompt_documents
WHERE filename = ?
LIMIT 1
`, normalized).Scan(&createdAt); err != nil {
		if err == sql.ErrNoRows {
			return nil, sql.ErrNoRows
		}
		return nil, err
	}
	createdValue := time.Now().Format(time.RFC3339)
	if createdAt.Valid && strings.TrimSpace(createdAt.String) != "" {
		createdValue = createdAt.String
	}
	updatedValue := time.Now().Format(time.RFC3339)
	_, err = s.db.ExecContext(ctx, `
INSERT INTO prompt_documents (filename, content, source, created_at, updated_at)
VALUES (?, ?, ?, ?, ?)
ON DUPLICATE KEY UPDATE
	content = VALUES(content),
	source = VALUES(source),
	updated_at = VALUES(updated_at)
`, normalized, content, sourceManual, createdValue, updatedValue)
	if err != nil {
		return nil, err
	}
	return s.Get(ctx, normalized)
}

func NormalizeFilename(filename string) (string, error) {
	normalized := strings.TrimSpace(strings.ReplaceAll(filename, "\\", "/"))
	if normalized == "" || strings.Contains(normalized, "..") || strings.HasPrefix(normalized, "/") {
		return "", fmt.Errorf("无效的文件名")
	}
	if !strings.Contains(normalized, "/") {
		normalized = "prompts/" + normalized
	}
	return normalized, nil
}

func basePromptName(filename string) string {
	parts := strings.Split(strings.ReplaceAll(filename, "\\", "/"), "/")
	return parts[len(parts)-1]
}

func nullableString(value sql.NullString) *string {
	if !value.Valid {
		return nil
	}
	text := value.String
	return &text
}
