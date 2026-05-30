package httpapi

import (
	"encoding/json"
	"net/http"

	"github.com/life2you/fishRadar2/services/radar-control/internal/settings"
)

type activationCodeCreatePayload struct {
	Quantity        int     `json:"quantity"`
	DurationMinutes int     `json:"duration_minutes"`
	Note            *string `json:"note"`
}

func handleTenantNotificationChannels(service *settings.Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		user := currentUser(r.Context())
		if user == nil || user.Role != "admin" {
			writeError(w, http.StatusForbidden, "无权访问该资源")
			return
		}
		switch r.Method {
		case http.MethodGet:
			channels, err := service.GetTenantNotificationChannels(r.Context())
			if err != nil {
				writeError(w, http.StatusInternalServerError, err.Error())
				return
			}
			writeJSON(w, http.StatusOK, map[string]any{"channels": channels})
		case http.MethodPut:
			var payload settings.TenantNotificationChannels
			if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
				writeError(w, http.StatusBadRequest, "请求体无效")
				return
			}
			channels, err := service.SaveTenantNotificationChannels(r.Context(), payload.Channels)
			if err != nil {
				writeError(w, http.StatusInternalServerError, err.Error())
				return
			}
			writeJSON(w, http.StatusOK, map[string]any{"message": "租户可用通知方式已更新", "channels": channels})
		default:
			writeError(w, http.StatusMethodNotAllowed, "方法不支持")
		}
	}
}

func handleRotationSettings(service *settings.Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		user := currentUser(r.Context())
		if user == nil || user.Role != "admin" {
			writeError(w, http.StatusForbidden, "无权访问该资源")
			return
		}
		switch r.Method {
		case http.MethodGet:
			value, err := service.GetRotationSettings(r.Context())
			if err != nil {
				writeError(w, http.StatusInternalServerError, err.Error())
				return
			}
			writeJSON(w, http.StatusOK, value)
		case http.MethodPut:
			var payload settings.RotationSettingsPatch
			if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
				writeError(w, http.StatusBadRequest, "请求体无效")
				return
			}
			value, err := service.SaveRotationSettings(r.Context(), payload)
			if err != nil {
				writeError(w, http.StatusInternalServerError, err.Error())
				return
			}
			writeJSON(w, http.StatusOK, map[string]any{"message": "轮换设置已成功更新", "settings": value})
		default:
			writeError(w, http.StatusMethodNotAllowed, "方法不支持")
		}
	}
}

func handleAIRuntimeSettings(service *settings.Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		user := currentUser(r.Context())
		if user == nil || user.Role != "admin" {
			writeError(w, http.StatusForbidden, "无权访问该资源")
			return
		}
		switch r.Method {
		case http.MethodGet:
			value, err := service.GetAIRuntimeSettings(r.Context())
			if err != nil {
				writeError(w, http.StatusInternalServerError, err.Error())
				return
			}
			writeJSON(w, http.StatusOK, value)
		case http.MethodPut:
			var payload settings.AIRuntimeSettingsPatch
			if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
				writeError(w, http.StatusBadRequest, "请求体无效")
				return
			}
			value, err := service.SaveAIRuntimeSettings(r.Context(), payload)
			if err != nil {
				writeError(w, http.StatusInternalServerError, err.Error())
				return
			}
			writeJSON(w, http.StatusOK, map[string]any{"message": "AI 运行参数已成功更新", "settings": value})
		default:
			writeError(w, http.StatusMethodNotAllowed, "方法不支持")
		}
	}
}

func handleFailureGuardSettings(service *settings.Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		user := currentUser(r.Context())
		if user == nil || user.Role != "admin" {
			writeError(w, http.StatusForbidden, "无权访问该资源")
			return
		}
		switch r.Method {
		case http.MethodGet:
			value, err := service.GetFailureGuardSettings(r.Context())
			if err != nil {
				writeError(w, http.StatusInternalServerError, err.Error())
				return
			}
			writeJSON(w, http.StatusOK, value)
		case http.MethodPut:
			var payload settings.FailureGuardSettingsPatch
			if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
				writeError(w, http.StatusBadRequest, "请求体无效")
				return
			}
			value, err := service.SaveFailureGuardSettings(r.Context(), payload)
			if err != nil {
				writeError(w, http.StatusInternalServerError, err.Error())
				return
			}
			writeJSON(w, http.StatusOK, map[string]any{"message": "失败熔断设置已成功更新", "settings": value})
		default:
			writeError(w, http.StatusMethodNotAllowed, "方法不支持")
		}
	}
}

func handleActivationCodes(service *settings.Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		user := currentUser(r.Context())
		if user == nil || user.Role != "admin" {
			writeError(w, http.StatusForbidden, "无权访问该资源")
			return
		}
		switch r.Method {
		case http.MethodGet:
			items, err := service.ListActivationCodes(r.Context())
			if err != nil {
				writeError(w, http.StatusInternalServerError, err.Error())
				return
			}
			writeJSON(w, http.StatusOK, map[string]any{"items": items})
		case http.MethodPost:
			var payload activationCodeCreatePayload
			if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
				writeError(w, http.StatusBadRequest, "请求体无效")
				return
			}
			items, err := service.CreateActivationCodes(r.Context(), payload.Quantity, payload.DurationMinutes, payload.Note, user.UserID)
			if err != nil {
				writeError(w, http.StatusBadRequest, err.Error())
				return
			}
			writeJSON(w, http.StatusOK, map[string]any{"message": "卡密已生成", "items": items})
		default:
			writeError(w, http.StatusMethodNotAllowed, "方法不支持")
		}
	}
}
