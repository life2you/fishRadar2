package auth

import (
	"context"
	"database/sql"
	"fmt"
	"strings"
	"time"

	"github.com/google/uuid"
)

const sessionTTLDays = 7

type Service struct {
	db *sql.DB
}

func NewService(db *sql.DB) *Service {
	return &Service{db: db}
}

func (s *Service) Authenticate(ctx context.Context, username string, password string) (*UserContext, error) {
	row := s.db.QueryRowContext(ctx, `
		SELECT id, username, password_hash, role, status, display_name
		FROM users
		WHERE username = ?
		LIMIT 1
	`, strings.TrimSpace(username))

	var (
		id           int64
		foundUser    string
		passwordHash string
		role         string
		status       string
		displayName  sql.NullString
	)
	if err := row.Scan(&id, &foundUser, &passwordHash, &role, &status, &displayName); err != nil {
		if err == sql.ErrNoRows {
			return nil, nil
		}
		return nil, err
	}
	if status != "active" || !VerifyPassword(password, passwordHash) {
		return nil, nil
	}

	user, err := s.buildUserContext(ctx, id, foundUser, role, nullableString(displayName))
	if err != nil {
		return nil, err
	}
	if role == "tenant" && !user.WorkspaceEnabled {
		return nil, nil
	}
	return user, nil
}

func (s *Service) CreateSession(ctx context.Context, user *UserContext) (string, error) {
	token := uuid.NewString()
	expiresAt := time.Now().Add(sessionTTLDays * 24 * time.Hour).Format(time.RFC3339)
	createdAt := time.Now().Format(time.RFC3339)
	_, err := s.db.ExecContext(ctx, `
		INSERT INTO auth_sessions (session_token, user_id, tenant_id, expires_at, created_at)
		VALUES (?, ?, ?, ?, ?)
		ON DUPLICATE KEY UPDATE
			user_id = VALUES(user_id),
			tenant_id = VALUES(tenant_id),
			expires_at = VALUES(expires_at),
			created_at = VALUES(created_at)
	`, token, user.UserID, user.TenantID, expiresAt, createdAt)
	if err != nil {
		return "", err
	}
	return token, nil
}

func (s *Service) GetUserBySession(ctx context.Context, sessionToken string) (*UserContext, error) {
	row := s.db.QueryRowContext(ctx, `
		SELECT s.session_token, s.expires_at, u.id, u.username, u.role, u.status, u.display_name
		FROM auth_sessions AS s
		JOIN users AS u ON u.id = s.user_id
		WHERE s.session_token = ?
		LIMIT 1
	`, sessionToken)

	var (
		token       string
		expiresAt   string
		userID      int64
		username    string
		role        string
		status      string
		displayName sql.NullString
	)
	if err := row.Scan(&token, &expiresAt, &userID, &username, &role, &status, &displayName); err != nil {
		if err == sql.ErrNoRows {
			return nil, nil
		}
		return nil, err
	}
	if status != "active" {
		return nil, nil
	}
	if isExpired(expiresAt) {
		_ = s.DeleteSession(ctx, sessionToken)
		return nil, nil
	}

	user, err := s.buildUserContext(ctx, userID, username, role, nullableString(displayName))
	if err != nil {
		return nil, err
	}
	user.SessionToken = &token
	if role == "tenant" && !user.WorkspaceEnabled {
		return nil, nil
	}
	return user, nil
}

func (s *Service) DeleteSession(ctx context.Context, sessionToken string) error {
	_, err := s.db.ExecContext(ctx, `DELETE FROM auth_sessions WHERE session_token = ?`, sessionToken)
	return err
}

func (s *Service) buildUserContext(ctx context.Context, userID int64, username string, role string, displayName *string) (*UserContext, error) {
	row := s.db.QueryRowContext(ctx, `
		SELECT
			m.tenant_id,
			t.name AS tenant_name,
			t.status AS tenant_status,
			t.ai_enabled AS tenant_ai_enabled,
			t.activation_required AS tenant_activation_required,
			t.activated_at AS tenant_activated_at,
			t.access_expires_at AS tenant_access_expires_at
		FROM user_tenant_memberships AS m
		JOIN tenants AS t ON t.id = m.tenant_id
		WHERE m.user_id = ?
		ORDER BY m.id ASC
		LIMIT 1
	`, userID)

	var (
		tenantID                 sql.NullInt64
		tenantName               sql.NullString
		tenantStatus             sql.NullString
		tenantAIEnabled          sql.NullBool
		tenantActivationRequired sql.NullBool
		tenantActivatedAt        sql.NullString
		tenantAccessExpiresAt    sql.NullString
	)
	err := row.Scan(
		&tenantID,
		&tenantName,
		&tenantStatus,
		&tenantAIEnabled,
		&tenantActivationRequired,
		&tenantActivatedAt,
		&tenantAccessExpiresAt,
	)
	if err != nil && err != sql.ErrNoRows {
		return nil, err
	}

	var tenantIDPtr *int64
	if tenantID.Valid {
		v := tenantID.Int64
		tenantIDPtr = &v
	}
	tenantStatusPtr := nullableString(tenantStatus)
	tenantActivatedAtPtr := nullableString(tenantActivatedAt)
	tenantAccessExpiresAtPtr := nullableString(tenantAccessExpiresAt)
	workspaceEnabled, accessExpired := computeWorkspaceEnabled(
		role,
		tenantStatusPtr,
		tenantActivationRequired.Valid && tenantActivationRequired.Bool,
		tenantActivatedAtPtr,
		tenantAccessExpiresAtPtr,
	)

	context := &UserContext{
		UserID:                   userID,
		Username:                 username,
		DisplayName:              displayName,
		Role:                     role,
		TenantID:                 tenantIDPtr,
		TenantName:               nullableString(tenantName),
		TenantStatus:             tenantStatusPtr,
		WorkspaceEnabled:         workspaceEnabled,
		TenantAIEnabled:          tenantAIEnabled.Valid && tenantAIEnabled.Bool,
		TenantActivationRequired: tenantActivationRequired.Valid && tenantActivationRequired.Bool,
		TenantActivated:          role != "tenant" || !(tenantActivationRequired.Valid && tenantActivationRequired.Bool) || (tenantActivatedAtPtr != nil && *tenantActivatedAtPtr != ""),
		TenantActivatedAt:        tenantActivatedAtPtr,
		TenantAccessExpiresAt:    tenantAccessExpiresAtPtr,
		TenantAccessExpired:      accessExpired,
	}
	context.CanUseAI = role == "admin" || (context.WorkspaceEnabled && context.TenantAIEnabled)
	context.AllowedRoutes = allowedRoutes(role, context.WorkspaceEnabled)
	return context, nil
}

func nullableString(value sql.NullString) *string {
	if !value.Valid {
		return nil
	}
	v := value.String
	return &v
}

func isExpired(value string) bool {
	parsed, err := time.Parse(time.RFC3339, value)
	if err == nil {
		return !parsed.After(time.Now())
	}
	parsed, err = time.Parse("2006-01-02T15:04:05", value)
	if err == nil {
		return !parsed.After(time.Now())
	}
	return false
}

func (s *Service) RequireAdmin(ctx context.Context, sessionToken string) (*UserContext, error) {
	user, err := s.GetUserBySession(ctx, sessionToken)
	if err != nil {
		return nil, err
	}
	if user == nil {
		return nil, nil
	}
	if user.Role != "admin" {
		return nil, fmt.Errorf("forbidden")
	}
	return user, nil
}
