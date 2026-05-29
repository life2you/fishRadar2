package settings

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"os"
	"strings"
)

const (
	platformNotificationSettingsKey = "platform:notification_settings"
	platformFailureGuardSettingsKey = "platform:failure_guard_settings"
)

type NotificationFlags struct {
	Exists              bool `json:"exists"`
	NtfyTopicURLSet     bool `json:"ntfy_topic_url_set"`
	GotifyURLSet        bool `json:"gotify_url_set"`
	GotifyTokenSet      bool `json:"gotify_token_set"`
	BarkURLSet          bool `json:"bark_url_set"`
	WxBotURLSet         bool `json:"wx_bot_url_set"`
	TelegramBotTokenSet bool `json:"telegram_bot_token_set"`
	TelegramChatIDSet   bool `json:"telegram_chat_id_set"`
	WebhookURLSet       bool `json:"webhook_url_set"`
	WebhookHeadersSet   bool `json:"webhook_headers_set"`
}

type LoginStateFileStatus struct {
	Exists bool   `json:"exists"`
	Path   string `json:"path"`
}

type SystemStatus struct {
	ScraperRunning                 bool                 `json:"scraper_running"`
	RunningTaskIDs                 []int64              `json:"running_task_ids"`
	AIConfigured                   bool                 `json:"ai_configured"`
	NotificationConfigured         bool                 `json:"notification_configured"`
	HeadlessMode                   bool                 `json:"headless_mode"`
	RunningInDocker                bool                 `json:"running_in_docker"`
	LoginStateFile                 LoginStateFileStatus `json:"login_state_file"`
	EnvFile                        NotificationFlags    `json:"env_file"`
	FailureGuard                   map[string]any       `json:"failure_guard"`
	ConfiguredNotificationChannels []string             `json:"configured_notification_channels"`
}

type Service struct {
	db *sql.DB
}

func NewService(db *sql.DB) *Service {
	return &Service{db: db}
}

func (s *Service) BuildStatus(ctx context.Context) (*SystemStatus, error) {
	runningTaskIDs, err := s.runningTaskIDs(ctx)
	if err != nil {
		return nil, err
	}
	aiConfigured, err := s.hasEnabledAIAccount(ctx)
	if err != nil {
		return nil, err
	}
	loginStateExists, err := s.hasDefaultLoginState(ctx)
	if err != nil {
		return nil, err
	}

	notificationValues, _ := s.loadMetadataJSON(ctx, platformNotificationSettingsKey)
	configuredChannels := configuredNotificationChannels(notificationValues)
	notificationFlags := buildNotificationFlags(notificationValues)
	notificationFlags.Exists = fileExists(".env")

	failureGuardValues, _ := s.loadMetadataJSON(ctx, platformFailureGuardSettingsKey)

	return &SystemStatus{
		ScraperRunning:                 len(runningTaskIDs) > 0,
		RunningTaskIDs:                 runningTaskIDs,
		AIConfigured:                   aiConfigured,
		NotificationConfigured:         len(configuredChannels) > 0,
		HeadlessMode:                   envBool("RUN_HEADLESS", true),
		RunningInDocker:                fileExists("/.dockerenv"),
		LoginStateFile:                 LoginStateFileStatus{Exists: loginStateExists, Path: "xianyu_state.json"},
		EnvFile:                        notificationFlags,
		FailureGuard:                   normalizeFailureGuardValues(failureGuardValues),
		ConfiguredNotificationChannels: configuredChannels,
	}, nil
}

func (s *Service) runningTaskIDs(ctx context.Context) ([]int64, error) {
	rows, err := s.db.QueryContext(ctx, `SELECT id FROM tasks WHERE is_running = 1 ORDER BY id ASC`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var ids []int64
	for rows.Next() {
		var id int64
		if err := rows.Scan(&id); err != nil {
			return nil, err
		}
		ids = append(ids, id)
	}
	return ids, rows.Err()
}

func (s *Service) hasEnabledAIAccount(ctx context.Context) (bool, error) {
	var count int64
	if err := s.db.QueryRowContext(ctx, `SELECT COUNT(1) FROM ai_accounts WHERE enabled = 1`).Scan(&count); err != nil {
		return false, err
	}
	return count > 0, nil
}

func (s *Service) hasDefaultLoginState(ctx context.Context) (bool, error) {
	var count int64
	if err := s.db.QueryRowContext(
		ctx,
		`SELECT COUNT(1) FROM account_states WHERE kind = 'default' AND name = '__default__'`,
	).Scan(&count); err != nil {
		return false, err
	}
	return count > 0, nil
}

func (s *Service) loadMetadataJSON(ctx context.Context, key string) (map[string]any, error) {
	value, err := s.loadMetadataValue(ctx, key)
	if err != nil {
		return nil, err
	}
	payload, ok := value.(map[string]any)
	if !ok {
		return nil, nil
	}
	return payload, nil
}

func (s *Service) loadMetadataValue(ctx context.Context, key string) (any, error) {
	var raw sql.NullString
	if err := s.db.QueryRowContext(ctx, "SELECT value FROM app_metadata WHERE `key` = ? LIMIT 1", key).Scan(&raw); err != nil {
		if err == sql.ErrNoRows {
			return nil, nil
		}
		return nil, err
	}
	if !raw.Valid || strings.TrimSpace(raw.String) == "" {
		return nil, nil
	}
	var payload any
	if err := json.Unmarshal([]byte(raw.String), &payload); err != nil {
		return nil, nil
	}
	return payload, nil
}

func buildNotificationFlags(values map[string]any) NotificationFlags {
	return NotificationFlags{
		NtfyTopicURLSet:     textSet(notificationValue(values, "NTFY_TOPIC_URL", "ntfy_topic_url")),
		GotifyURLSet:        textSet(notificationValue(values, "GOTIFY_URL", "gotify_url")),
		GotifyTokenSet:      textSet(notificationValue(values, "GOTIFY_TOKEN", "gotify_token")),
		BarkURLSet:          textSet(notificationValue(values, "BARK_URL", "bark_url")),
		WxBotURLSet:         textSet(notificationValue(values, "WX_BOT_URL", "wx_bot_url")),
		TelegramBotTokenSet: textSet(notificationValue(values, "TELEGRAM_BOT_TOKEN", "telegram_bot_token")),
		TelegramChatIDSet:   textSet(notificationValue(values, "TELEGRAM_CHAT_ID", "telegram_chat_id")),
		WebhookURLSet:       textSet(notificationValue(values, "WEBHOOK_URL", "webhook_url")),
		WebhookHeadersSet:   textSet(notificationValue(values, "WEBHOOK_HEADERS", "webhook_headers")),
	}
}

func configuredNotificationChannels(values map[string]any) []string {
	channels := make([]string, 0, 6)
	if textSet(notificationValue(values, "NTFY_TOPIC_URL", "ntfy_topic_url")) {
		channels = append(channels, "ntfy")
	}
	if textSet(notificationValue(values, "BARK_URL", "bark_url")) {
		channels = append(channels, "bark")
	}
	if textSet(notificationValue(values, "GOTIFY_URL", "gotify_url")) && textSet(notificationValue(values, "GOTIFY_TOKEN", "gotify_token")) {
		channels = append(channels, "gotify")
	}
	if textSet(notificationValue(values, "WX_BOT_URL", "wx_bot_url")) {
		channels = append(channels, "wecom")
	}
	if textSet(notificationValue(values, "TELEGRAM_BOT_TOKEN", "telegram_bot_token")) && textSet(notificationValue(values, "TELEGRAM_CHAT_ID", "telegram_chat_id")) {
		channels = append(channels, "telegram")
	}
	if textSet(notificationValue(values, "WEBHOOK_URL", "webhook_url")) {
		channels = append(channels, "webhook")
	}
	return channels
}

func notificationValue(values map[string]any, primary string, fallback string) any {
	if value, ok := values[primary]; ok {
		return value
	}
	return values[fallback]
}

func normalizeFailureGuardValues(values map[string]any) map[string]any {
	return map[string]any{
		"TASK_FAILURE_THRESHOLD":     intFromAny(values["TASK_FAILURE_THRESHOLD"], 3),
		"TASK_FAILURE_PAUSE_SECONDS": intFromAny(values["TASK_FAILURE_PAUSE_SECONDS"], 24*60*60),
		"TASK_FAILURE_TZ":            textOr(values["TASK_FAILURE_TZ"], "Asia/Shanghai"),
	}
}

func envBool(key string, fallback bool) bool {
	value := strings.TrimSpace(os.Getenv(key))
	if value == "" {
		return fallback
	}
	switch strings.ToLower(value) {
	case "1", "true", "yes", "y", "on":
		return true
	case "0", "false", "no", "n", "off":
		return false
	default:
		return fallback
	}
}

func intFromAny(value any, fallback int) int {
	switch typed := value.(type) {
	case float64:
		return int(typed)
	case int:
		return typed
	case int64:
		return int(typed)
	case string:
		typed = strings.TrimSpace(typed)
		if typed == "" {
			return fallback
		}
		var parsed int
		if _, err := fmt.Sscanf(typed, "%d", &parsed); err == nil {
			return parsed
		}
	}
	return fallback
}

func textOr(value any, fallback string) string {
	text := strings.TrimSpace(fmt.Sprintf("%v", value))
	if text == "" || text == "<nil>" {
		return fallback
	}
	return text
}

func textSet(value any) bool {
	text := strings.TrimSpace(fmt.Sprintf("%v", value))
	return text != "" && text != "<nil>"
}

func fileExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}
