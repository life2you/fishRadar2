package announcements

import (
	"context"
	"database/sql"
	"time"
)

type Item struct {
	ID              int64   `json:"id"`
	Title           string  `json:"title"`
	Content         string  `json:"content"`
	Level           string  `json:"level"`
	Status          string  `json:"status"`
	Dismissible     bool    `json:"dismissible"`
	PublishedAt     *string `json:"published_at"`
	ExpiresAt       *string `json:"expires_at"`
	CreatedAt       string  `json:"created_at"`
	UpdatedAt       string  `json:"updated_at"`
	CreatedByUserID *int64  `json:"created_by_user_id"`
}

type Service struct {
	db *sql.DB
}

type SaveInput struct {
	Title           string  `json:"title"`
	Content         string  `json:"content"`
	Level           string  `json:"level"`
	Status          string  `json:"status"`
	Dismissible     bool    `json:"dismissible"`
	NotifyTenants   bool    `json:"notify_tenants"`
	PublishedAt     *string `json:"published_at"`
	ExpiresAt       *string `json:"expires_at"`
	CreatedByUserID *int64  `json:"-"`
}

func NewService(db *sql.DB) *Service {
	return &Service{db: db}
}

func (s *Service) List(ctx context.Context, includeInactive bool) ([]Item, error) {
	query := `
		SELECT id, title, content, level, status, dismissible, published_at, expires_at,
		       created_at, updated_at, created_by_user_id
		FROM announcements
	`
	args := []any{}
	if includeInactive {
		query += `
		ORDER BY
		    CASE WHEN status = 'active' THEN 0 ELSE 1 END,
		    COALESCE(published_at, updated_at) DESC,
		    id DESC`
	} else {
		now := time.Now().Format(time.RFC3339)
		query += `
		WHERE status = 'active'
		  AND (published_at IS NULL OR published_at <= ?)
		  AND (expires_at IS NULL OR expires_at > ?)
		ORDER BY COALESCE(published_at, updated_at) DESC, id DESC`
		args = append(args, now, now)
	}

	rows, err := s.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	items := make([]Item, 0)
	for rows.Next() {
		var (
			item            Item
			dismissible     int
			publishedAt     sql.NullString
			expiresAt       sql.NullString
			createdByUserID sql.NullInt64
		)
		if err := rows.Scan(
			&item.ID,
			&item.Title,
			&item.Content,
			&item.Level,
			&item.Status,
			&dismissible,
			&publishedAt,
			&expiresAt,
			&item.CreatedAt,
			&item.UpdatedAt,
			&createdByUserID,
		); err != nil {
			return nil, err
		}
		item.Dismissible = dismissible != 0
		if publishedAt.Valid {
			item.PublishedAt = &publishedAt.String
		}
		if expiresAt.Valid {
			item.ExpiresAt = &expiresAt.String
		}
		if createdByUserID.Valid {
			v := createdByUserID.Int64
			item.CreatedByUserID = &v
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s *Service) Create(ctx context.Context, input SaveInput) (*Item, error) {
	now := time.Now().Format(time.RFC3339)
	publishedAt := normalizeOptionalText(input.PublishedAt)
	if input.Status == "active" && publishedAt == nil {
		publishedAt = &now
	}

	result, err := s.db.ExecContext(ctx, `
		INSERT INTO announcements (
			title, content, level, status, dismissible,
			published_at, expires_at, created_at, updated_at, created_by_user_id
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
	`,
		input.Title,
		input.Content,
		normalizeLevel(input.Level),
		normalizeStatus(input.Status),
		boolToInt(input.Dismissible),
		publishedAt,
		normalizeOptionalText(input.ExpiresAt),
		now,
		now,
		input.CreatedByUserID,
	)
	if err != nil {
		return nil, err
	}
	id, err := result.LastInsertId()
	if err != nil {
		return nil, err
	}
	return s.GetByID(ctx, id)
}

func (s *Service) Update(ctx context.Context, id int64, input SaveInput) (*Item, error) {
	existing, err := s.GetByID(ctx, id)
	if err != nil {
		return nil, err
	}
	if existing == nil {
		return nil, sql.ErrNoRows
	}

	publishedAt := normalizeOptionalText(input.PublishedAt)
	if input.Status == "active" && publishedAt == nil {
		if existing.PublishedAt != nil {
			publishedAt = existing.PublishedAt
		} else {
			now := time.Now().Format(time.RFC3339)
			publishedAt = &now
		}
	}

	_, err = s.db.ExecContext(ctx, `
		UPDATE announcements
		SET title = ?,
		    content = ?,
		    level = ?,
		    status = ?,
		    dismissible = ?,
		    published_at = ?,
		    expires_at = ?,
		    updated_at = ?
		WHERE id = ?
	`,
		input.Title,
		input.Content,
		normalizeLevel(input.Level),
		normalizeStatus(input.Status),
		boolToInt(input.Dismissible),
		publishedAt,
		normalizeOptionalText(input.ExpiresAt),
		time.Now().Format(time.RFC3339),
		id,
	)
	if err != nil {
		return nil, err
	}
	return s.GetByID(ctx, id)
}

func (s *Service) Delete(ctx context.Context, id int64) error {
	_, err := s.db.ExecContext(ctx, `DELETE FROM announcements WHERE id = ?`, id)
	return err
}

func (s *Service) GetByID(ctx context.Context, id int64) (*Item, error) {
	row := s.db.QueryRowContext(ctx, `
		SELECT id, title, content, level, status, dismissible, published_at, expires_at,
		       created_at, updated_at, created_by_user_id
		FROM announcements
		WHERE id = ?
		LIMIT 1
	`, id)
	var (
		item            Item
		dismissible     int
		publishedAt     sql.NullString
		expiresAt       sql.NullString
		createdByUserID sql.NullInt64
	)
	if err := row.Scan(
		&item.ID,
		&item.Title,
		&item.Content,
		&item.Level,
		&item.Status,
		&dismissible,
		&publishedAt,
		&expiresAt,
		&item.CreatedAt,
		&item.UpdatedAt,
		&createdByUserID,
	); err != nil {
		if err == sql.ErrNoRows {
			return nil, nil
		}
		return nil, err
	}
	item.Dismissible = dismissible != 0
	if publishedAt.Valid {
		item.PublishedAt = &publishedAt.String
	}
	if expiresAt.Valid {
		item.ExpiresAt = &expiresAt.String
	}
	if createdByUserID.Valid {
		v := createdByUserID.Int64
		item.CreatedByUserID = &v
	}
	return &item, nil
}

func normalizeOptionalText(value *string) *string {
	if value == nil {
		return nil
	}
	text := *value
	if text == "" {
		return nil
	}
	return &text
}

func normalizeLevel(level string) string {
	if level == "" {
		return "info"
	}
	return level
}

func normalizeStatus(status string) string {
	if status == "" {
		return "draft"
	}
	return status
}

func boolToInt(value bool) int {
	if value {
		return 1
	}
	return 0
}
