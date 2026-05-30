package httpapi

import (
	"context"
	"encoding/json"
	"net/http"
	"strings"
	"time"

	"github.com/life2you/fishRadar2/services/radar-control/internal/accounts"
	"github.com/life2you/fishRadar2/services/radar-control/internal/aiaccounts"
	"github.com/life2you/fishRadar2/services/radar-control/internal/announcements"
	"github.com/life2you/fishRadar2/services/radar-control/internal/auth"
	"github.com/life2you/fishRadar2/services/radar-control/internal/config"
	"github.com/life2you/fishRadar2/services/radar-control/internal/dashboard"
	"github.com/life2you/fishRadar2/services/radar-control/internal/generation"
	"github.com/life2you/fishRadar2/services/radar-control/internal/http/handlers"
	"github.com/life2you/fishRadar2/services/radar-control/internal/logs"
	"github.com/life2you/fishRadar2/services/radar-control/internal/prompts"
	"github.com/life2you/fishRadar2/services/radar-control/internal/realtime"
	"github.com/life2you/fishRadar2/services/radar-control/internal/reanalysis"
	"github.com/life2you/fishRadar2/services/radar-control/internal/results"
	runtimeworker "github.com/life2you/fishRadar2/services/radar-control/internal/runtime"
	"github.com/life2you/fishRadar2/services/radar-control/internal/settings"
	"github.com/life2you/fishRadar2/services/radar-control/internal/storage"
	"github.com/life2you/fishRadar2/services/radar-control/internal/tasks"
	"github.com/life2you/fishRadar2/services/radar-control/internal/tenants"
	"github.com/life2you/fishRadar2/services/radar-control/internal/workerqueue"
)

func NewRouter(cfg config.Config) http.Handler {
	mux := http.NewServeMux()

	mux.HandleFunc("/health", handlers.Health)
	mux.HandleFunc("/api/v1/health", handlers.Health)
	mux.HandleFunc("/api/v1/meta/services", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]any{
			"app":        "fishRadar2-radar-control",
			"env":        cfg.Env,
			"serverTime": time.Now().Format(time.RFC3339),
			"services": []map[string]string{
				{"name": "radar-control", "role": "api"},
				{"name": "radar-probe", "role": "worker"},
				{"name": "radar-portal", "role": "frontend"},
			},
		})
	})

	if strings.TrimSpace(cfg.DatabaseURL) == "" {
		return withCommonMiddleware(mux)
	}

	db, err := storage.OpenMySQL(cfg.DatabaseURL)
	if err != nil {
		panic(err)
	}

	authService := auth.NewService(db)
	accountService := accounts.NewService(db)
	announcementService := announcements.NewService(db)
	aiAccountService := aiaccounts.NewService(db)
	dashboardService := dashboard.NewService(db)
	promptService := prompts.NewService(db)
	taskService := tasks.NewService(db)
	logService := logs.NewService(taskService)
	resultService := results.NewService(db)
	queueService := workerqueue.NewService(db, cfg)
	generationService := generation.NewService(cfg, taskService, queueService)
	reanalysisService := reanalysis.NewService(queueService)
	runtimeManager := runtimeworker.NewWorkerManager(taskService, queueService)
	realtimeHub := realtime.NewHub(cfg)
	realtimeHub.Start()
	settingsService := settings.NewService(db)
	tenantService := tenants.NewService(db)
	if err := runtimeManager.ResetState(context.Background()); err != nil {
		panic(err)
	}

	mux.Handle("/auth/login", handleLogin(authService, cfg))
	mux.Handle("/auth/status", handleLogin(authService, cfg))
	mux.Handle("/auth/me", withSessionUser(authService, cfg, true, handleMe()))
	mux.Handle("/auth/logout", handleLogout(authService, cfg))
	mux.Handle("/ws", handleWebSocket(authService, cfg, realtimeHub))

	mux.Handle("/api/announcements", withSessionUser(authService, cfg, true, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.Method {
		case http.MethodGet:
			user := currentUser(r.Context())
			includeInactive := user != nil && user.Role == "admin"
			handleAnnouncements(announcementService, includeInactive).ServeHTTP(w, r)
		case http.MethodPost:
			handleAnnouncementCreate(announcementService).ServeHTTP(w, r)
		default:
			writeError(w, http.StatusMethodNotAllowed, "方法不支持")
		}
	})))
	mux.Handle("/api/announcements/active", withSessionUser(authService, cfg, true, handleAnnouncements(announcementService, false)))
	mux.Handle("/api/announcements/", withSessionUser(authService, cfg, true, handleAnnouncementByID(announcementService)))
	mux.Handle("/api/dashboard/summary", withSessionUser(authService, cfg, true, handleDashboardSummary(dashboardService)))
	mux.Handle("/api/accounts", withSessionUser(authService, cfg, true, handleAccounts(accountService)))
	mux.Handle("/api/accounts/", withSessionUser(authService, cfg, true, handleAccountByName(accountService)))
	mux.Handle("/api/tasks", withSessionUser(authService, cfg, true, handleTasks(taskService, generationService, realtimeHub)))
	mux.Handle("/api/tasks/generate", withSessionUser(authService, cfg, true, handleTaskGenerate(taskService, generationService, realtimeHub)))
	mux.Handle("/api/tasks/generate-jobs/", withSessionUser(authService, cfg, true, handleTaskGenerateJob(generationService)))
	mux.Handle("/api/tasks/start/", withSessionUser(authService, cfg, true, handleTaskStart(taskService, runtimeManager)))
	mux.Handle("/api/tasks/stop/", withSessionUser(authService, cfg, true, handleTaskStop(taskService, runtimeManager)))
	mux.Handle("/api/tasks/", withSessionUser(authService, cfg, true, handleTaskByID(taskService, generationService, realtimeHub)))
	mux.Handle("/api/prompts", withSessionUser(authService, cfg, true, handlePrompts(promptService)))
	mux.Handle("/api/prompts/", withSessionUser(authService, cfg, true, handlePromptByFilename(promptService)))
	mux.Handle("/api/results/files", withSessionUser(authService, cfg, true, handleResultFiles(resultService)))
	mux.Handle("/api/results/files/", withSessionUser(authService, cfg, true, handleResultFileDownloadOrDelete(resultService, realtimeHub)))
	mux.Handle("/api/results/", withSessionUser(authService, cfg, true, handleResultByFilename(resultService, reanalysisService, realtimeHub)))
	mux.Handle("/api/login-state", withSessionUser(authService, cfg, true, handleLoginState(accountService)))
	mux.Handle("/api/logs", withSessionUser(authService, cfg, true, handleLogs(logService)))
	mux.Handle("/api/logs/tail", withSessionUser(authService, cfg, true, handleLogTail(logService)))
	mux.Handle("/api/tenant-settings/notifications", withSessionUser(authService, cfg, true, handleTenantNotificationSettings(settingsService)))
	mux.Handle("/api/tenant-settings/notifications/test", withSessionUser(authService, cfg, true, handleTenantNotificationTest(cfg)))
	mux.Handle("/api/settings/status", withSessionUser(authService, cfg, true, handleSettingsStatus(settingsService)))
	mux.Handle("/api/settings/notifications", withSessionUser(authService, cfg, true, handleNotificationSettings(settingsService)))
	mux.Handle("/api/settings/notifications/test", withSessionUser(authService, cfg, true, handleNotificationTest(cfg)))
	mux.Handle("/api/settings/tenant-notification-channels", withSessionUser(authService, cfg, true, handleTenantNotificationChannels(settingsService)))
	mux.Handle("/api/settings/rotation", withSessionUser(authService, cfg, true, handleRotationSettings(settingsService)))
	mux.Handle("/api/settings/ai-runtime", withSessionUser(authService, cfg, true, handleAIRuntimeSettings(settingsService)))
	mux.Handle("/api/settings/failure-guard", withSessionUser(authService, cfg, true, handleFailureGuardSettings(settingsService)))
	mux.Handle("/api/settings/activation-codes", withSessionUser(authService, cfg, true, handleActivationCodes(settingsService)))
	mux.Handle("/api/settings/ai-accounts/test", withSessionUser(authService, cfg, true, handleAIAccountTest(cfg)))
	mux.Handle("/api/settings/ai-accounts", withSessionUser(authService, cfg, true, handleAIAccounts(aiAccountService)))
	mux.Handle("/api/settings/ai-accounts/", withSessionUser(authService, cfg, true, handleAIAccountByID(aiAccountService, cfg)))
	mux.Handle("/api/settings/tenants", withSessionUser(authService, cfg, true, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.Method {
		case http.MethodGet:
			handleTenantList(tenantService).ServeHTTP(w, r)
		default:
			writeError(w, http.StatusMethodNotAllowed, "方法不支持")
		}
	})))
	mux.Handle("/api/settings/tenants/", withSessionUser(authService, cfg, true, handleTenantByID(tenantService)))

	return withCommonMiddleware(mux)
}

func withCommonMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if strings.EqualFold(strings.TrimSpace(r.Header.Get("Upgrade")), "websocket") {
			next.ServeHTTP(w, r)
			return
		}
		w.Header().Set("Content-Type", "application/json; charset=utf-8")
		w.Header().Set("X-Content-Type-Options", "nosniff")
		next.ServeHTTP(w, r)
	})
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func writeError(w http.ResponseWriter, status int, detail string) {
	writeJSON(w, status, map[string]string{"detail": detail})
}

func withSessionUser(authService *auth.Service, cfg config.Config, required bool, next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		cookie, err := r.Cookie(cfg.AuthCookieName)
		if err != nil || strings.TrimSpace(cookie.Value) == "" {
			if required {
				writeError(w, http.StatusUnauthorized, "未登录或登录已过期")
				return
			}
			next.ServeHTTP(w, r)
			return
		}
		user, err := authService.GetUserBySession(r.Context(), cookie.Value)
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		if user == nil {
			if required {
				writeError(w, http.StatusUnauthorized, "未登录或登录已过期")
				return
			}
			next.ServeHTTP(w, r)
			return
		}
		next.ServeHTTP(w, r.WithContext(withUserContext(r.Context(), user)))
	})
}
