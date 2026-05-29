package httpapi

import (
	"encoding/json"
	"net/http"

	"github.com/life2you/fishRadar2/services/api-go/internal/settings"
)

func handleNotificationSettings(service *settings.Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if requireAdminUser(w, r) == nil {
			return
		}
		switch r.Method {
		case http.MethodGet:
			payload, err := service.GetNotificationSettings(r.Context())
			if err != nil {
				writeError(w, http.StatusInternalServerError, err.Error())
				return
			}
			writeJSON(w, http.StatusOK, payload)
		case http.MethodPut:
			var payload map[string]any
			if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
				writeError(w, http.StatusBadRequest, "请求体无效")
				return
			}
			result, err := service.SaveNotificationSettings(r.Context(), payload)
			if err != nil {
				writeError(w, http.StatusUnprocessableEntity, err.Error())
				return
			}
			writeJSON(w, http.StatusOK, result)
		default:
			writeError(w, http.StatusMethodNotAllowed, "方法不支持")
		}
	}
}

func handleTenantNotificationSettings(service *settings.Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		user := requireWorkspaceUser(w, r)
		if user == nil || user.Role != "tenant" || user.TenantID == nil {
			writeError(w, http.StatusForbidden, "当前账号无权访问该资源")
			return
		}
		switch r.Method {
		case http.MethodGet:
			payload, err := service.GetTenantNotificationSettings(r.Context(), *user.TenantID)
			if err != nil {
				writeError(w, http.StatusInternalServerError, err.Error())
				return
			}
			writeJSON(w, http.StatusOK, payload)
		case http.MethodPut:
			var payload map[string]any
			if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
				writeError(w, http.StatusBadRequest, "请求体无效")
				return
			}
			channels, err := service.GetTenantNotificationChannels(r.Context())
			if err != nil {
				writeError(w, http.StatusInternalServerError, err.Error())
				return
			}
			result, err := service.SaveTenantNotificationSettings(r.Context(), *user.TenantID, payload, channels)
			if err != nil {
				writeError(w, http.StatusUnprocessableEntity, err.Error())
				return
			}
			writeJSON(w, http.StatusOK, result)
		default:
			writeError(w, http.StatusMethodNotAllowed, "方法不支持")
		}
	}
}
