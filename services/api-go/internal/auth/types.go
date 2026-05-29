package auth

import "time"

type UserContext struct {
	UserID                   int64    `json:"-"`
	Username                 string   `json:"username"`
	DisplayName              *string  `json:"display_name"`
	Role                     string   `json:"role"`
	TenantID                 *int64   `json:"tenant_id"`
	TenantName               *string  `json:"tenant_name"`
	TenantStatus             *string  `json:"tenant_status"`
	WorkspaceEnabled         bool     `json:"workspace_enabled"`
	TenantAIEnabled          bool     `json:"tenant_ai_enabled"`
	TenantActivationRequired bool     `json:"tenant_activation_required"`
	TenantActivated          bool     `json:"tenant_activated"`
	TenantActivatedAt        *string  `json:"tenant_activated_at"`
	TenantAccessExpiresAt    *string  `json:"tenant_access_expires_at"`
	TenantAccessExpired      bool     `json:"tenant_access_expired"`
	CanUseAI                 bool     `json:"can_use_ai"`
	AllowedRoutes            []string `json:"allowed_routes"`
	SessionToken             *string  `json:"-"`
}

func (u UserContext) AuthPayload() map[string]any {
	return map[string]any{
		"authenticated":              true,
		"username":                   u.Username,
		"display_name":               u.DisplayName,
		"role":                       u.Role,
		"tenant_id":                  u.TenantID,
		"tenant_name":                u.TenantName,
		"tenant_status":              u.TenantStatus,
		"workspace_enabled":          u.WorkspaceEnabled,
		"tenant_ai_enabled":          u.TenantAIEnabled,
		"tenant_activation_required": u.TenantActivationRequired,
		"tenant_activated":           u.TenantActivated,
		"tenant_activated_at":        u.TenantActivatedAt,
		"tenant_access_expires_at":   u.TenantAccessExpiresAt,
		"tenant_access_expired":      u.TenantAccessExpired,
		"can_use_ai":                 u.CanUseAI,
		"allowed_routes":             u.AllowedRoutes,
	}
}

func computeWorkspaceEnabled(role string, tenantStatus *string, activationRequired bool, activatedAt *string, accessExpiresAt *string) (bool, bool) {
	if role != "tenant" {
		return true, false
	}
	activated := !activationRequired || (activatedAt != nil && *activatedAt != "")
	expired := false
	if accessExpiresAt != nil && *accessExpiresAt != "" {
		if dt, err := time.Parse(time.RFC3339, *accessExpiresAt); err == nil {
			expired = !dt.After(time.Now())
		} else if dt, err := time.Parse("2006-01-02T15:04:05", *accessExpiresAt); err == nil {
			expired = !dt.After(time.Now())
		}
	}
	if tenantStatus == nil || *tenantStatus != "active" {
		return false, expired
	}
	return activated && !expired, expired
}

func allowedRoutes(role string, workspaceEnabled bool) []string {
	if role == "admin" {
		return []string{"dashboard", "tasks", "accounts", "results", "logs", "settings"}
	}
	if !workspaceEnabled {
		return []string{"activate"}
	}
	return []string{"tasks", "results", "notifications"}
}
