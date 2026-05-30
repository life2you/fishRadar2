package settings

import (
	"context"
	"crypto/rand"
	"database/sql"
	"encoding/hex"
	"fmt"
	"strings"
	"time"
)

type ActivationCodeItem struct {
	ID                 int64   `json:"id"`
	Code               string  `json:"code"`
	Status             string  `json:"status"`
	DurationMinutes    int     `json:"duration_minutes"`
	Note               *string `json:"note"`
	CreatedByUserID    *int64  `json:"created_by_user_id"`
	RedeemedByTenantID *int64  `json:"redeemed_by_tenant_id"`
	RedeemedByUserID   *int64  `json:"redeemed_by_user_id"`
	RedeemedAt         *string `json:"redeemed_at"`
	CreatedAt          string  `json:"created_at"`
	RedeemedTenantName *string `json:"redeemed_tenant_name"`
}

func (s *Service) ListActivationCodes(ctx context.Context) ([]ActivationCodeItem, error) {
	rows, err := s.db.QueryContext(ctx, `
SELECT
	c.id,
	c.code,
	c.status,
	c.duration_minutes,
	c.note,
	c.created_by_user_id,
	c.redeemed_by_tenant_id,
	c.redeemed_by_user_id,
	c.redeemed_at,
	c.created_at,
	t.name AS redeemed_tenant_name
FROM activation_codes AS c
LEFT JOIN tenants AS t ON t.id = c.redeemed_by_tenant_id
ORDER BY c.id DESC
`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	items := make([]ActivationCodeItem, 0)
	for rows.Next() {
		var (
			item               ActivationCodeItem
			note               sql.NullString
			createdByUserID    sql.NullInt64
			redeemedByTenantID sql.NullInt64
			redeemedByUserID   sql.NullInt64
			redeemedAt         sql.NullString
			redeemedTenantName sql.NullString
		)
		if err := rows.Scan(
			&item.ID,
			&item.Code,
			&item.Status,
			&item.DurationMinutes,
			&note,
			&createdByUserID,
			&redeemedByTenantID,
			&redeemedByUserID,
			&redeemedAt,
			&item.CreatedAt,
			&redeemedTenantName,
		); err != nil {
			return nil, err
		}
		item.Note = nullableString(note)
		item.CreatedByUserID = nullableInt64(createdByUserID)
		item.RedeemedByTenantID = nullableInt64(redeemedByTenantID)
		item.RedeemedByUserID = nullableInt64(redeemedByUserID)
		item.RedeemedAt = nullableString(redeemedAt)
		item.RedeemedTenantName = nullableString(redeemedTenantName)
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s *Service) CreateActivationCodes(ctx context.Context, quantity int, durationMinutes int, note *string, createdByUserID int64) ([]ActivationCodeItem, error) {
	normalizedQuantity := maxInt(1, minInt(quantity, 100))
	normalizedDuration := maxInt(1, minInt(durationMinutes, 60*24*365))
	normalizedNote := normalizeOptionalText(note)
	createdAt := time.Now().Format(time.RFC3339)
	items := make([]ActivationCodeItem, 0, normalizedQuantity)

	for i := 0; i < normalizedQuantity; i++ {
		code, err := s.nextActivationCode(ctx)
		if err != nil {
			return nil, err
		}
		if _, err := s.db.ExecContext(ctx, `
INSERT INTO activation_codes (
	code, status, duration_minutes, note, created_by_user_id, redeemed_by_tenant_id,
	redeemed_by_user_id, redeemed_at, created_at
) VALUES (?, 'unused', ?, ?, ?, NULL, NULL, NULL, ?)
`, code, normalizedDuration, normalizedNote, createdByUserID, createdAt); err != nil {
			return nil, err
		}
		items = append(items, ActivationCodeItem{
			Code:            code,
			Status:          "unused",
			DurationMinutes: normalizedDuration,
			Note:            normalizedNote,
			CreatedByUserID: &createdByUserID,
			CreatedAt:       createdAt,
		})
	}
	return items, nil
}

func (s *Service) nextActivationCode(ctx context.Context) (string, error) {
	for {
		code, err := generateActivationCode()
		if err != nil {
			return "", err
		}
		var existingID int64
		err = s.db.QueryRowContext(ctx, `
SELECT id
FROM activation_codes
WHERE code = ?
LIMIT 1
`, code).Scan(&existingID)
		if err == sql.ErrNoRows {
			return code, nil
		}
		if err != nil {
			return "", err
		}
	}
}

func generateActivationCode() (string, error) {
	parts := make([]string, 0, 3)
	for range 3 {
		buffer := make([]byte, 4)
		if _, err := rand.Read(buffer); err != nil {
			return "", err
		}
		part := strings.ToUpper(hex.EncodeToString(buffer))
		if len(part) > 8 {
			part = part[:8]
		}
		parts = append(parts, part)
	}
	return strings.Join(parts, "-"), nil
}

func nullableInt64(value sql.NullInt64) *int64 {
	if !value.Valid {
		return nil
	}
	number := value.Int64
	return &number
}

func nullableString(value sql.NullString) *string {
	if !value.Valid {
		return nil
	}
	text := value.String
	return &text
}

func normalizeOptionalText(value *string) *string {
	if value == nil {
		return nil
	}
	text := strings.TrimSpace(*value)
	if text == "" {
		return nil
	}
	return &text
}

func minInt(left int, right int) int {
	if left < right {
		return left
	}
	return right
}

func activationCodeValidationError(message string) error {
	return fmt.Errorf("%s", message)
}
