package settings

import (
	"context"
	"encoding/json"
	"os"
	"strings"
)

const (
	tenantNotificationChannelsKey = "tenant_notification_channels"
	platformRotationSettingsKey   = "platform:rotation_settings"
	platformAIRuntimeSettingsKey  = "platform:ai_runtime_settings"
)

type TenantNotificationChannels struct {
	Channels []string `json:"channels"`
}

type RotationSettings struct {
	AccountRotationEnabled    bool   `json:"ACCOUNT_ROTATION_ENABLED"`
	AccountRotationMode       string `json:"ACCOUNT_ROTATION_MODE"`
	AccountRotationRetryLimit int    `json:"ACCOUNT_ROTATION_RETRY_LIMIT"`
	AccountBlacklistTTL       int    `json:"ACCOUNT_BLACKLIST_TTL"`
	ProxyRotationEnabled      bool   `json:"PROXY_ROTATION_ENABLED"`
	ProxyRotationMode         string `json:"PROXY_ROTATION_MODE"`
	ProxyPool                 string `json:"PROXY_POOL"`
	ProxyRotationRetryLimit   int    `json:"PROXY_ROTATION_RETRY_LIMIT"`
	ProxyBlacklistTTL         int    `json:"PROXY_BLACKLIST_TTL"`
}

type RotationSettingsPatch struct {
	AccountRotationEnabled    *bool   `json:"ACCOUNT_ROTATION_ENABLED"`
	AccountRotationMode       *string `json:"ACCOUNT_ROTATION_MODE"`
	AccountRotationRetryLimit *int    `json:"ACCOUNT_ROTATION_RETRY_LIMIT"`
	AccountBlacklistTTL       *int    `json:"ACCOUNT_BLACKLIST_TTL"`
	ProxyRotationEnabled      *bool   `json:"PROXY_ROTATION_ENABLED"`
	ProxyRotationMode         *string `json:"PROXY_ROTATION_MODE"`
	ProxyPool                 *string `json:"PROXY_POOL"`
	ProxyRotationRetryLimit   *int    `json:"PROXY_ROTATION_RETRY_LIMIT"`
	ProxyBlacklistTTL         *int    `json:"PROXY_BLACKLIST_TTL"`
}

type AIRuntimeSettings struct {
	ProxyURL              string `json:"PROXY_URL"`
	AIDebugMode           bool   `json:"AI_DEBUG_MODE"`
	EnableResponseFormat  bool   `json:"ENABLE_RESPONSE_FORMAT"`
	EnableThinking        bool   `json:"ENABLE_THINKING"`
	SkipAIAnalysis        bool   `json:"SKIP_AI_ANALYSIS"`
	AIAnalysisConcurrency int    `json:"AI_ANALYSIS_CONCURRENCY"`
	SellerProfileCacheTTL int    `json:"SELLER_PROFILE_CACHE_TTL"`
}

type AIRuntimeSettingsPatch struct {
	ProxyURL              *string `json:"PROXY_URL"`
	AIDebugMode           *bool   `json:"AI_DEBUG_MODE"`
	EnableResponseFormat  *bool   `json:"ENABLE_RESPONSE_FORMAT"`
	EnableThinking        *bool   `json:"ENABLE_THINKING"`
	SkipAIAnalysis        *bool   `json:"SKIP_AI_ANALYSIS"`
	AIAnalysisConcurrency *int    `json:"AI_ANALYSIS_CONCURRENCY"`
	SellerProfileCacheTTL *int    `json:"SELLER_PROFILE_CACHE_TTL"`
}

type FailureGuardSettings struct {
	TaskFailureThreshold    int    `json:"TASK_FAILURE_THRESHOLD"`
	TaskFailurePauseSeconds int    `json:"TASK_FAILURE_PAUSE_SECONDS"`
	TaskFailureTZ           string `json:"TASK_FAILURE_TZ"`
}

type FailureGuardSettingsPatch struct {
	TaskFailureThreshold    *int    `json:"TASK_FAILURE_THRESHOLD"`
	TaskFailurePauseSeconds *int    `json:"TASK_FAILURE_PAUSE_SECONDS"`
	TaskFailureTZ           *string `json:"TASK_FAILURE_TZ"`
}

func (s *Service) GetTenantNotificationChannels(ctx context.Context) ([]string, error) {
	values, err := s.loadMetadataValue(ctx, tenantNotificationChannelsKey)
	if err != nil {
		return nil, err
	}
	if values == nil {
		notificationValues, _ := s.loadMetadataJSON(ctx, platformNotificationSettingsKey)
		return configuredNotificationChannels(notificationValues), nil
	}
	if objectValue, ok := values.(map[string]any); ok {
		if rawChannels, exists := objectValue["channels"]; exists {
			return normalizeNotificationChannels(rawChannels), nil
		}
	}
	return normalizeNotificationChannels(values), nil
}

func (s *Service) SaveTenantNotificationChannels(ctx context.Context, channels []string) ([]string, error) {
	normalized := normalizeNotificationChannels(channels)
	if err := s.writeMetadataJSON(ctx, tenantNotificationChannelsKey, normalized); err != nil {
		return nil, err
	}
	return normalized, nil
}

func (s *Service) GetRotationSettings(ctx context.Context) (RotationSettings, error) {
	values, err := s.loadSection(ctx, platformRotationSettingsKey, rotationDefaults(), rotationEnvSeed(), normalizeRotationValues)
	if err != nil {
		return RotationSettings{}, err
	}
	return toRotationSettings(values), nil
}

func (s *Service) SaveRotationSettings(ctx context.Context, patch RotationSettingsPatch) (RotationSettings, error) {
	current, err := s.GetRotationSettings(ctx)
	if err != nil {
		return RotationSettings{}, err
	}
	values := current.toMap()
	mergeRotationPatch(values, patch)
	normalized := normalizeRotationValues(values)
	if err := s.writeMetadataJSON(ctx, platformRotationSettingsKey, normalized); err != nil {
		return RotationSettings{}, err
	}
	return toRotationSettings(normalized), nil
}

func (s *Service) GetAIRuntimeSettings(ctx context.Context) (AIRuntimeSettings, error) {
	values, err := s.loadSection(ctx, platformAIRuntimeSettingsKey, aiRuntimeDefaults(), aiRuntimeEnvSeed(), normalizeAIRuntimeValues)
	if err != nil {
		return AIRuntimeSettings{}, err
	}
	return toAIRuntimeSettings(values), nil
}

func (s *Service) SaveAIRuntimeSettings(ctx context.Context, patch AIRuntimeSettingsPatch) (AIRuntimeSettings, error) {
	current, err := s.GetAIRuntimeSettings(ctx)
	if err != nil {
		return AIRuntimeSettings{}, err
	}
	values := current.toMap()
	mergeAIRuntimePatch(values, patch)
	normalized := normalizeAIRuntimeValues(values)
	if err := s.writeMetadataJSON(ctx, platformAIRuntimeSettingsKey, normalized); err != nil {
		return AIRuntimeSettings{}, err
	}
	return toAIRuntimeSettings(normalized), nil
}

func (s *Service) GetFailureGuardSettings(ctx context.Context) (FailureGuardSettings, error) {
	values, err := s.loadSection(ctx, platformFailureGuardSettingsKey, failureGuardDefaults(), failureGuardEnvSeed(), normalizeFailureGuardValues)
	if err != nil {
		return FailureGuardSettings{}, err
	}
	return toFailureGuardSettings(values), nil
}

func (s *Service) SaveFailureGuardSettings(ctx context.Context, patch FailureGuardSettingsPatch) (FailureGuardSettings, error) {
	current, err := s.GetFailureGuardSettings(ctx)
	if err != nil {
		return FailureGuardSettings{}, err
	}
	values := current.toMap()
	mergeFailureGuardPatch(values, patch)
	normalized := normalizeFailureGuardValues(values)
	if err := s.writeMetadataJSON(ctx, platformFailureGuardSettingsKey, normalized); err != nil {
		return FailureGuardSettings{}, err
	}
	return toFailureGuardSettings(normalized), nil
}

func (s *Service) loadSection(
	ctx context.Context,
	key string,
	defaults map[string]any,
	seed map[string]any,
	normalizer func(map[string]any) map[string]any,
) (map[string]any, error) {
	stored, err := s.loadMetadataJSON(ctx, key)
	if err != nil {
		return nil, err
	}
	if stored == nil {
		normalized := normalizer(mergeMaps(defaults, seed))
		if err := s.writeMetadataJSON(ctx, key, normalized); err != nil {
			return nil, err
		}
		return normalized, nil
	}
	return normalizer(mergeMaps(defaults, stored)), nil
}

func (s *Service) writeMetadataJSON(ctx context.Context, key string, payload any) error {
	serialized, err := json.Marshal(payload)
	if err != nil {
		return err
	}
	_, err = s.db.ExecContext(
		ctx,
		"INSERT INTO app_metadata(`key`, value) VALUES(?, ?) ON DUPLICATE KEY UPDATE value = VALUES(value)",
		key,
		string(serialized),
	)
	return err
}

func rotationDefaults() map[string]any {
	return map[string]any{
		"ACCOUNT_ROTATION_ENABLED":     false,
		"ACCOUNT_ROTATION_MODE":        "per_task",
		"ACCOUNT_ROTATION_RETRY_LIMIT": 2,
		"ACCOUNT_BLACKLIST_TTL":        300,
		"PROXY_ROTATION_ENABLED":       false,
		"PROXY_ROTATION_MODE":          "per_task",
		"PROXY_POOL":                   "",
		"PROXY_ROTATION_RETRY_LIMIT":   2,
		"PROXY_BLACKLIST_TTL":          300,
	}
}

func aiRuntimeDefaults() map[string]any {
	return map[string]any{
		"PROXY_URL":                "",
		"AI_DEBUG_MODE":            false,
		"ENABLE_RESPONSE_FORMAT":   true,
		"ENABLE_THINKING":          false,
		"SKIP_AI_ANALYSIS":         false,
		"AI_ANALYSIS_CONCURRENCY":  2,
		"SELLER_PROFILE_CACHE_TTL": 1800,
	}
}

func failureGuardDefaults() map[string]any {
	return map[string]any{
		"TASK_FAILURE_THRESHOLD":     3,
		"TASK_FAILURE_PAUSE_SECONDS": 24 * 60 * 60,
		"TASK_FAILURE_TZ":            "Asia/Shanghai",
	}
}

func rotationEnvSeed() map[string]any {
	return map[string]any{
		"ACCOUNT_ROTATION_ENABLED":     envBool("ACCOUNT_ROTATION_ENABLED", false),
		"ACCOUNT_ROTATION_MODE":        envString("ACCOUNT_ROTATION_MODE", "per_task"),
		"ACCOUNT_ROTATION_RETRY_LIMIT": envInt("ACCOUNT_ROTATION_RETRY_LIMIT", 2),
		"ACCOUNT_BLACKLIST_TTL":        envInt("ACCOUNT_BLACKLIST_TTL", 300),
		"PROXY_ROTATION_ENABLED":       envBool("PROXY_ROTATION_ENABLED", false),
		"PROXY_ROTATION_MODE":          envString("PROXY_ROTATION_MODE", "per_task"),
		"PROXY_POOL":                   envString("PROXY_POOL", ""),
		"PROXY_ROTATION_RETRY_LIMIT":   envInt("PROXY_ROTATION_RETRY_LIMIT", 2),
		"PROXY_BLACKLIST_TTL":          envInt("PROXY_BLACKLIST_TTL", 300),
	}
}

func aiRuntimeEnvSeed() map[string]any {
	return map[string]any{
		"PROXY_URL":                envString("PROXY_URL", ""),
		"AI_DEBUG_MODE":            envBool("AI_DEBUG_MODE", false),
		"ENABLE_RESPONSE_FORMAT":   envBool("ENABLE_RESPONSE_FORMAT", true),
		"ENABLE_THINKING":          envBool("ENABLE_THINKING", false),
		"SKIP_AI_ANALYSIS":         envBool("SKIP_AI_ANALYSIS", false),
		"AI_ANALYSIS_CONCURRENCY":  envInt("AI_ANALYSIS_CONCURRENCY", 2),
		"SELLER_PROFILE_CACHE_TTL": envInt("SELLER_PROFILE_CACHE_TTL", 1800),
	}
}

func failureGuardEnvSeed() map[string]any {
	return map[string]any{
		"TASK_FAILURE_THRESHOLD":     envInt("TASK_FAILURE_THRESHOLD", 3),
		"TASK_FAILURE_PAUSE_SECONDS": envInt("TASK_FAILURE_PAUSE_SECONDS", 24*60*60),
		"TASK_FAILURE_TZ":            envString("TASK_FAILURE_TZ", "Asia/Shanghai"),
	}
}

func normalizeNotificationChannels(values any) []string {
	allowed := map[string]struct{}{
		"ntfy":     {},
		"bark":     {},
		"gotify":   {},
		"wecom":    {},
		"telegram": {},
		"webhook":  {},
	}
	items := make([]string, 0, 6)
	seen := make(map[string]struct{})
	switch typed := values.(type) {
	case []string:
		for _, item := range typed {
			item = strings.TrimSpace(item)
			if _, ok := allowed[item]; ok {
				if _, exists := seen[item]; !exists {
					seen[item] = struct{}{}
					items = append(items, item)
				}
			}
		}
	case []any:
		for _, raw := range typed {
			item := strings.TrimSpace(textOr(raw, ""))
			if _, ok := allowed[item]; ok {
				if _, exists := seen[item]; !exists {
					seen[item] = struct{}{}
					items = append(items, item)
				}
			}
		}
	}
	return items
}

func normalizeRotationValues(values map[string]any) map[string]any {
	defaults := rotationDefaults()
	return map[string]any{
		"ACCOUNT_ROTATION_ENABLED":     boolValue(values["ACCOUNT_ROTATION_ENABLED"], defaults["ACCOUNT_ROTATION_ENABLED"].(bool)),
		"ACCOUNT_ROTATION_MODE":        strings.ToLower(envStringFromAny(values["ACCOUNT_ROTATION_MODE"], defaults["ACCOUNT_ROTATION_MODE"].(string))),
		"ACCOUNT_ROTATION_RETRY_LIMIT": maxInt(1, intFromAny(values["ACCOUNT_ROTATION_RETRY_LIMIT"], defaults["ACCOUNT_ROTATION_RETRY_LIMIT"].(int))),
		"ACCOUNT_BLACKLIST_TTL":        maxInt(0, intFromAny(values["ACCOUNT_BLACKLIST_TTL"], defaults["ACCOUNT_BLACKLIST_TTL"].(int))),
		"PROXY_ROTATION_ENABLED":       boolValue(values["PROXY_ROTATION_ENABLED"], defaults["PROXY_ROTATION_ENABLED"].(bool)),
		"PROXY_ROTATION_MODE":          strings.ToLower(envStringFromAny(values["PROXY_ROTATION_MODE"], defaults["PROXY_ROTATION_MODE"].(string))),
		"PROXY_POOL":                   envStringFromAny(values["PROXY_POOL"], defaults["PROXY_POOL"].(string)),
		"PROXY_ROTATION_RETRY_LIMIT":   maxInt(1, intFromAny(values["PROXY_ROTATION_RETRY_LIMIT"], defaults["PROXY_ROTATION_RETRY_LIMIT"].(int))),
		"PROXY_BLACKLIST_TTL":          maxInt(0, intFromAny(values["PROXY_BLACKLIST_TTL"], defaults["PROXY_BLACKLIST_TTL"].(int))),
	}
}

func normalizeAIRuntimeValues(values map[string]any) map[string]any {
	defaults := aiRuntimeDefaults()
	return map[string]any{
		"PROXY_URL":                envStringFromAny(values["PROXY_URL"], defaults["PROXY_URL"].(string)),
		"AI_DEBUG_MODE":            boolValue(values["AI_DEBUG_MODE"], defaults["AI_DEBUG_MODE"].(bool)),
		"ENABLE_RESPONSE_FORMAT":   boolValue(values["ENABLE_RESPONSE_FORMAT"], defaults["ENABLE_RESPONSE_FORMAT"].(bool)),
		"ENABLE_THINKING":          boolValue(values["ENABLE_THINKING"], defaults["ENABLE_THINKING"].(bool)),
		"SKIP_AI_ANALYSIS":         boolValue(values["SKIP_AI_ANALYSIS"], defaults["SKIP_AI_ANALYSIS"].(bool)),
		"AI_ANALYSIS_CONCURRENCY":  maxInt(1, intFromAny(values["AI_ANALYSIS_CONCURRENCY"], defaults["AI_ANALYSIS_CONCURRENCY"].(int))),
		"SELLER_PROFILE_CACHE_TTL": maxInt(0, intFromAny(values["SELLER_PROFILE_CACHE_TTL"], defaults["SELLER_PROFILE_CACHE_TTL"].(int))),
	}
}

func toRotationSettings(values map[string]any) RotationSettings {
	return RotationSettings{
		AccountRotationEnabled:    boolValue(values["ACCOUNT_ROTATION_ENABLED"], false),
		AccountRotationMode:       envStringFromAny(values["ACCOUNT_ROTATION_MODE"], "per_task"),
		AccountRotationRetryLimit: intFromAny(values["ACCOUNT_ROTATION_RETRY_LIMIT"], 2),
		AccountBlacklistTTL:       intFromAny(values["ACCOUNT_BLACKLIST_TTL"], 300),
		ProxyRotationEnabled:      boolValue(values["PROXY_ROTATION_ENABLED"], false),
		ProxyRotationMode:         envStringFromAny(values["PROXY_ROTATION_MODE"], "per_task"),
		ProxyPool:                 envStringFromAny(values["PROXY_POOL"], ""),
		ProxyRotationRetryLimit:   intFromAny(values["PROXY_ROTATION_RETRY_LIMIT"], 2),
		ProxyBlacklistTTL:         intFromAny(values["PROXY_BLACKLIST_TTL"], 300),
	}
}

func toAIRuntimeSettings(values map[string]any) AIRuntimeSettings {
	return AIRuntimeSettings{
		ProxyURL:              envStringFromAny(values["PROXY_URL"], ""),
		AIDebugMode:           boolValue(values["AI_DEBUG_MODE"], false),
		EnableResponseFormat:  boolValue(values["ENABLE_RESPONSE_FORMAT"], true),
		EnableThinking:        boolValue(values["ENABLE_THINKING"], false),
		SkipAIAnalysis:        boolValue(values["SKIP_AI_ANALYSIS"], false),
		AIAnalysisConcurrency: intFromAny(values["AI_ANALYSIS_CONCURRENCY"], 2),
		SellerProfileCacheTTL: intFromAny(values["SELLER_PROFILE_CACHE_TTL"], 1800),
	}
}

func toFailureGuardSettings(values map[string]any) FailureGuardSettings {
	return FailureGuardSettings{
		TaskFailureThreshold:    intFromAny(values["TASK_FAILURE_THRESHOLD"], 3),
		TaskFailurePauseSeconds: intFromAny(values["TASK_FAILURE_PAUSE_SECONDS"], 24*60*60),
		TaskFailureTZ:           envStringFromAny(values["TASK_FAILURE_TZ"], "Asia/Shanghai"),
	}
}

func (value RotationSettings) toMap() map[string]any {
	return map[string]any{
		"ACCOUNT_ROTATION_ENABLED":     value.AccountRotationEnabled,
		"ACCOUNT_ROTATION_MODE":        value.AccountRotationMode,
		"ACCOUNT_ROTATION_RETRY_LIMIT": value.AccountRotationRetryLimit,
		"ACCOUNT_BLACKLIST_TTL":        value.AccountBlacklistTTL,
		"PROXY_ROTATION_ENABLED":       value.ProxyRotationEnabled,
		"PROXY_ROTATION_MODE":          value.ProxyRotationMode,
		"PROXY_POOL":                   value.ProxyPool,
		"PROXY_ROTATION_RETRY_LIMIT":   value.ProxyRotationRetryLimit,
		"PROXY_BLACKLIST_TTL":          value.ProxyBlacklistTTL,
	}
}

func (value AIRuntimeSettings) toMap() map[string]any {
	return map[string]any{
		"PROXY_URL":                value.ProxyURL,
		"AI_DEBUG_MODE":            value.AIDebugMode,
		"ENABLE_RESPONSE_FORMAT":   value.EnableResponseFormat,
		"ENABLE_THINKING":          value.EnableThinking,
		"SKIP_AI_ANALYSIS":         value.SkipAIAnalysis,
		"AI_ANALYSIS_CONCURRENCY":  value.AIAnalysisConcurrency,
		"SELLER_PROFILE_CACHE_TTL": value.SellerProfileCacheTTL,
	}
}

func (value FailureGuardSettings) toMap() map[string]any {
	return map[string]any{
		"TASK_FAILURE_THRESHOLD":     value.TaskFailureThreshold,
		"TASK_FAILURE_PAUSE_SECONDS": value.TaskFailurePauseSeconds,
		"TASK_FAILURE_TZ":            value.TaskFailureTZ,
	}
}

func mergeRotationPatch(values map[string]any, patch RotationSettingsPatch) {
	if patch.AccountRotationEnabled != nil {
		values["ACCOUNT_ROTATION_ENABLED"] = *patch.AccountRotationEnabled
	}
	if patch.AccountRotationMode != nil {
		values["ACCOUNT_ROTATION_MODE"] = *patch.AccountRotationMode
	}
	if patch.AccountRotationRetryLimit != nil {
		values["ACCOUNT_ROTATION_RETRY_LIMIT"] = *patch.AccountRotationRetryLimit
	}
	if patch.AccountBlacklistTTL != nil {
		values["ACCOUNT_BLACKLIST_TTL"] = *patch.AccountBlacklistTTL
	}
	if patch.ProxyRotationEnabled != nil {
		values["PROXY_ROTATION_ENABLED"] = *patch.ProxyRotationEnabled
	}
	if patch.ProxyRotationMode != nil {
		values["PROXY_ROTATION_MODE"] = *patch.ProxyRotationMode
	}
	if patch.ProxyPool != nil {
		values["PROXY_POOL"] = *patch.ProxyPool
	}
	if patch.ProxyRotationRetryLimit != nil {
		values["PROXY_ROTATION_RETRY_LIMIT"] = *patch.ProxyRotationRetryLimit
	}
	if patch.ProxyBlacklistTTL != nil {
		values["PROXY_BLACKLIST_TTL"] = *patch.ProxyBlacklistTTL
	}
}

func mergeAIRuntimePatch(values map[string]any, patch AIRuntimeSettingsPatch) {
	if patch.ProxyURL != nil {
		values["PROXY_URL"] = *patch.ProxyURL
	}
	if patch.AIDebugMode != nil {
		values["AI_DEBUG_MODE"] = *patch.AIDebugMode
	}
	if patch.EnableResponseFormat != nil {
		values["ENABLE_RESPONSE_FORMAT"] = *patch.EnableResponseFormat
	}
	if patch.EnableThinking != nil {
		values["ENABLE_THINKING"] = *patch.EnableThinking
	}
	if patch.SkipAIAnalysis != nil {
		values["SKIP_AI_ANALYSIS"] = *patch.SkipAIAnalysis
	}
	if patch.AIAnalysisConcurrency != nil {
		values["AI_ANALYSIS_CONCURRENCY"] = *patch.AIAnalysisConcurrency
	}
	if patch.SellerProfileCacheTTL != nil {
		values["SELLER_PROFILE_CACHE_TTL"] = *patch.SellerProfileCacheTTL
	}
}

func mergeFailureGuardPatch(values map[string]any, patch FailureGuardSettingsPatch) {
	if patch.TaskFailureThreshold != nil {
		values["TASK_FAILURE_THRESHOLD"] = *patch.TaskFailureThreshold
	}
	if patch.TaskFailurePauseSeconds != nil {
		values["TASK_FAILURE_PAUSE_SECONDS"] = *patch.TaskFailurePauseSeconds
	}
	if patch.TaskFailureTZ != nil {
		values["TASK_FAILURE_TZ"] = *patch.TaskFailureTZ
	}
}

func envString(key string, fallback string) string {
	value := strings.TrimSpace(os.Getenv(key))
	if value == "" {
		return fallback
	}
	return value
}

func envInt(key string, fallback int) int {
	return intFromAny(os.Getenv(key), fallback)
}

func envStringFromAny(value any, fallback string) string {
	text := strings.TrimSpace(textOr(value, fallback))
	if text == "" {
		return fallback
	}
	return text
}

func boolValue(value any, fallback bool) bool {
	switch typed := value.(type) {
	case bool:
		return typed
	case string:
		switch strings.ToLower(strings.TrimSpace(typed)) {
		case "1", "true", "yes", "y", "on":
			return true
		case "0", "false", "no", "n", "off":
			return false
		}
	}
	return fallback
}

func mergeMaps(base map[string]any, override map[string]any) map[string]any {
	merged := make(map[string]any, len(base)+len(override))
	for key, value := range base {
		merged[key] = value
	}
	for key, value := range override {
		merged[key] = value
	}
	return merged
}

func maxInt(left int, right int) int {
	if left > right {
		return left
	}
	return right
}
