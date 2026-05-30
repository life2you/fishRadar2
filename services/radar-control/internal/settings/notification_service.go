package settings

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"strings"
	"time"
)

const defaultTelegramAPIBaseURL = "https://api.telegram.org"

var (
	notificationFieldMap = map[string]string{
		"NTFY_TOPIC_URL":           "ntfy_topic_url",
		"GOTIFY_URL":               "gotify_url",
		"GOTIFY_TOKEN":             "gotify_token",
		"BARK_URL":                 "bark_url",
		"WX_BOT_URL":               "wx_bot_url",
		"TELEGRAM_BOT_TOKEN":       "telegram_bot_token",
		"TELEGRAM_CHAT_ID":         "telegram_chat_id",
		"TELEGRAM_API_BASE_URL":    "telegram_api_base_url",
		"WEBHOOK_URL":              "webhook_url",
		"WEBHOOK_METHOD":           "webhook_method",
		"WEBHOOK_HEADERS":          "webhook_headers",
		"WEBHOOK_CONTENT_TYPE":     "webhook_content_type",
		"WEBHOOK_QUERY_PARAMETERS": "webhook_query_parameters",
		"WEBHOOK_BODY":             "webhook_body",
		"PCURL_TO_MOBILE":          "pcurl_to_mobile",
	}
	channelNotificationFields = map[string][]string{
		"ntfy":     {"NTFY_TOPIC_URL"},
		"bark":     {"BARK_URL"},
		"gotify":   {"GOTIFY_URL", "GOTIFY_TOKEN"},
		"wecom":    {"WX_BOT_URL"},
		"telegram": {"TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "TELEGRAM_API_BASE_URL"},
		"webhook":  {"WEBHOOK_URL", "WEBHOOK_METHOD", "WEBHOOK_HEADERS", "WEBHOOK_CONTENT_TYPE", "WEBHOOK_QUERY_PARAMETERS", "WEBHOOK_BODY"},
	}
)

type NotificationSettingsPatch map[string]any

func (s *Service) GetNotificationSettings(ctx context.Context) (map[string]any, error) {
	values, err := s.loadSection(ctx, platformNotificationSettingsKey, notificationDefaults(), notificationEnvSeed(), normalizeNotificationValues)
	if err != nil {
		return nil, err
	}
	return buildNotificationResponse(values), nil
}

func (s *Service) SaveNotificationSettings(ctx context.Context, patch map[string]any) (map[string]any, error) {
	values, err := s.loadSection(ctx, platformNotificationSettingsKey, notificationDefaults(), notificationEnvSeed(), normalizeNotificationValues)
	if err != nil {
		return nil, err
	}
	merged, err := mergeNotificationPatch(values, patch, nil)
	if err != nil {
		return nil, err
	}
	if err := s.writeMetadataJSON(ctx, platformNotificationSettingsKey, merged); err != nil {
		return nil, err
	}
	return map[string]any{
		"message":             "通知设置已成功更新",
		"configured_channels": configuredNotificationChannelsMap(merged),
	}, nil
}

func (s *Service) GetTenantNotificationSettings(ctx context.Context, tenantID int64) (map[string]any, error) {
	availableChannels, err := s.GetTenantNotificationChannels(ctx)
	if err != nil {
		return nil, err
	}
	values, err := s.loadTenantNotificationValues(ctx, tenantID)
	if err != nil {
		return nil, err
	}
	response := buildNotificationResponse(values)
	response["AVAILABLE_CHANNELS"] = availableChannels
	return response, nil
}

func (s *Service) SaveTenantNotificationSettings(ctx context.Context, tenantID int64, patch map[string]any, allowedChannels []string) (map[string]any, error) {
	values, err := s.loadTenantNotificationValues(ctx, tenantID)
	if err != nil {
		return nil, err
	}
	merged, err := mergeNotificationPatch(values, patch, allowedChannels)
	if err != nil {
		return nil, err
	}
	serialized, err := json.Marshal(tenantSettingsStoragePayload(merged))
	if err != nil {
		return nil, err
	}
	_, err = s.db.ExecContext(ctx, `
INSERT INTO tenant_notification_settings (tenant_id, settings_json, updated_at)
VALUES (?, ?, ?)
ON DUPLICATE KEY UPDATE
	settings_json = VALUES(settings_json),
	updated_at = VALUES(updated_at)
`, tenantID, string(serialized), time.Now().Format(time.RFC3339))
	if err != nil {
		return nil, err
	}
	return map[string]any{
		"message":             "租户通知设置已更新",
		"configured_channels": configuredNotificationChannelsMap(merged),
	}, nil
}

func (s *Service) loadTenantNotificationValues(ctx context.Context, tenantID int64) (map[string]any, error) {
	values := notificationDefaults()
	var raw sql.NullString
	err := s.db.QueryRowContext(ctx, `
SELECT settings_json
FROM tenant_notification_settings
WHERE tenant_id = ?
LIMIT 1
`, tenantID).Scan(&raw)
	if err != nil {
		if err == sql.ErrNoRows {
			return values, nil
		}
		return nil, err
	}
	if !raw.Valid || strings.TrimSpace(raw.String) == "" {
		return values, nil
	}
	var payload map[string]any
	if err := json.Unmarshal([]byte(raw.String), &payload); err != nil {
		return values, nil
	}
	for key, value := range payload {
		values[key] = value
	}
	return normalizeNotificationValues(values), nil
}

func notificationDefaults() map[string]any {
	return map[string]any{
		"ntfy_topic_url":           "",
		"gotify_url":               "",
		"gotify_token":             "",
		"bark_url":                 "",
		"wx_bot_url":               "",
		"telegram_bot_token":       "",
		"telegram_chat_id":         "",
		"telegram_api_base_url":    defaultTelegramAPIBaseURL,
		"webhook_url":              "",
		"webhook_method":           "POST",
		"webhook_headers":          "",
		"webhook_content_type":     "JSON",
		"webhook_query_parameters": "",
		"webhook_body":             "",
		"pcurl_to_mobile":          true,
	}
}

func notificationEnvSeed() map[string]any {
	return map[string]any{
		"ntfy_topic_url":           envString("NTFY_TOPIC_URL", ""),
		"gotify_url":               envString("GOTIFY_URL", ""),
		"gotify_token":             envString("GOTIFY_TOKEN", ""),
		"bark_url":                 envString("BARK_URL", ""),
		"wx_bot_url":               envString("WX_BOT_URL", ""),
		"telegram_bot_token":       envString("TELEGRAM_BOT_TOKEN", ""),
		"telegram_chat_id":         envString("TELEGRAM_CHAT_ID", ""),
		"telegram_api_base_url":    envString("TELEGRAM_API_BASE_URL", defaultTelegramAPIBaseURL),
		"webhook_url":              envString("WEBHOOK_URL", ""),
		"webhook_method":           envString("WEBHOOK_METHOD", "POST"),
		"webhook_headers":          envString("WEBHOOK_HEADERS", ""),
		"webhook_content_type":     envString("WEBHOOK_CONTENT_TYPE", "JSON"),
		"webhook_query_parameters": envString("WEBHOOK_QUERY_PARAMETERS", ""),
		"webhook_body":             envString("WEBHOOK_BODY", ""),
		"pcurl_to_mobile":          envBool("PCURL_TO_MOBILE", true),
	}
}

func normalizeNotificationValues(values map[string]any) map[string]any {
	return map[string]any{
		"ntfy_topic_url":           envStringFromAny(values["ntfy_topic_url"], ""),
		"gotify_url":               envStringFromAny(values["gotify_url"], ""),
		"gotify_token":             envStringFromAny(values["gotify_token"], ""),
		"bark_url":                 envStringFromAny(values["bark_url"], ""),
		"wx_bot_url":               envStringFromAny(values["wx_bot_url"], ""),
		"telegram_bot_token":       envStringFromAny(values["telegram_bot_token"], ""),
		"telegram_chat_id":         envStringFromAny(values["telegram_chat_id"], ""),
		"telegram_api_base_url":    envStringFromAny(values["telegram_api_base_url"], defaultTelegramAPIBaseURL),
		"webhook_url":              envStringFromAny(values["webhook_url"], ""),
		"webhook_method":           strings.ToUpper(envStringFromAny(values["webhook_method"], "POST")),
		"webhook_headers":          envStringFromAny(values["webhook_headers"], ""),
		"webhook_content_type":     strings.ToUpper(envStringFromAny(values["webhook_content_type"], "JSON")),
		"webhook_query_parameters": envStringFromAny(values["webhook_query_parameters"], ""),
		"webhook_body":             envStringFromAny(values["webhook_body"], ""),
		"pcurl_to_mobile":          boolValue(values["pcurl_to_mobile"], true),
	}
}

func buildNotificationResponse(values map[string]any) map[string]any {
	return map[string]any{
		"NTFY_TOPIC_URL":           textOr(values["ntfy_topic_url"], ""),
		"GOTIFY_URL":               textOr(values["gotify_url"], ""),
		"GOTIFY_TOKEN":             "",
		"BARK_URL":                 "",
		"WX_BOT_URL":               "",
		"TELEGRAM_BOT_TOKEN":       "",
		"TELEGRAM_CHAT_ID":         textOr(values["telegram_chat_id"], ""),
		"TELEGRAM_API_BASE_URL":    textOr(values["telegram_api_base_url"], defaultTelegramAPIBaseURL),
		"WEBHOOK_URL":              "",
		"WEBHOOK_METHOD":           textOr(values["webhook_method"], "POST"),
		"WEBHOOK_HEADERS":          "",
		"WEBHOOK_CONTENT_TYPE":     textOr(values["webhook_content_type"], "JSON"),
		"WEBHOOK_QUERY_PARAMETERS": textOr(values["webhook_query_parameters"], ""),
		"WEBHOOK_BODY":             textOr(values["webhook_body"], ""),
		"PCURL_TO_MOBILE":          boolValue(values["pcurl_to_mobile"], true),
		"BARK_URL_SET":             textSet(values["bark_url"]),
		"GOTIFY_TOKEN_SET":         textSet(values["gotify_token"]),
		"WX_BOT_URL_SET":           textSet(values["wx_bot_url"]),
		"TELEGRAM_BOT_TOKEN_SET":   textSet(values["telegram_bot_token"]),
		"WEBHOOK_URL_SET":          textSet(values["webhook_url"]),
		"WEBHOOK_HEADERS_SET":      textSet(values["webhook_headers"]),
		"CONFIGURED_CHANNELS":      configuredNotificationChannelsMap(values),
	}
}

func mergeNotificationPatch(current map[string]any, patch map[string]any, allowedChannels []string) (map[string]any, error) {
	merged := mergeMaps(current, map[string]any{})
	allowedFields := allowedNotificationFields(allowedChannels)
	for field, rawValue := range patch {
		attr, exists := notificationFieldMap[field]
		if !exists {
			continue
		}
		if allowedChannels != nil && !allowedFields[field] {
			return nil, fmt.Errorf("以下通知字段未向租户开放: %s", field)
		}
		switch field {
		case "PCURL_TO_MOBILE":
			merged[attr] = boolValue(rawValue, true)
		default:
			merged[attr] = strings.TrimSpace(fmt.Sprintf("%v", rawValue))
		}
	}
	normalized := normalizeNotificationValues(merged)
	return normalized, nil
}

func allowedNotificationFields(channels []string) map[string]bool {
	fields := map[string]bool{"PCURL_TO_MOBILE": true}
	for _, channel := range channels {
		for _, field := range channelNotificationFields[channel] {
			fields[field] = true
		}
	}
	return fields
}

func configuredNotificationChannelsMap(values map[string]any) []string {
	channels := make([]string, 0, 6)
	if textSet(values["ntfy_topic_url"]) {
		channels = append(channels, "ntfy")
	}
	if textSet(values["bark_url"]) {
		channels = append(channels, "bark")
	}
	if textSet(values["gotify_url"]) && textSet(values["gotify_token"]) {
		channels = append(channels, "gotify")
	}
	if textSet(values["wx_bot_url"]) {
		channels = append(channels, "wecom")
	}
	if textSet(values["telegram_bot_token"]) && textSet(values["telegram_chat_id"]) {
		channels = append(channels, "telegram")
	}
	if textSet(values["webhook_url"]) {
		channels = append(channels, "webhook")
	}
	return channels
}

func tenantSettingsStoragePayload(values map[string]any) map[string]any {
	return map[string]any{
		"ntfy_topic_url":           textOr(values["ntfy_topic_url"], ""),
		"gotify_url":               textOr(values["gotify_url"], ""),
		"gotify_token":             textOr(values["gotify_token"], ""),
		"bark_url":                 textOr(values["bark_url"], ""),
		"wx_bot_url":               textOr(values["wx_bot_url"], ""),
		"telegram_bot_token":       textOr(values["telegram_bot_token"], ""),
		"telegram_chat_id":         textOr(values["telegram_chat_id"], ""),
		"telegram_api_base_url":    textOr(values["telegram_api_base_url"], defaultTelegramAPIBaseURL),
		"webhook_url":              textOr(values["webhook_url"], ""),
		"webhook_method":           textOr(values["webhook_method"], "POST"),
		"webhook_headers":          textOr(values["webhook_headers"], ""),
		"webhook_content_type":     textOr(values["webhook_content_type"], "JSON"),
		"webhook_query_parameters": textOr(values["webhook_query_parameters"], ""),
		"webhook_body":             textOr(values["webhook_body"], ""),
		"pcurl_to_mobile":          boolValue(values["pcurl_to_mobile"], true),
	}
}
