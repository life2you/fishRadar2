package httpapi

import (
	"net/http"

	"github.com/life2you/fishRadar2/services/api-go/internal/settings"
)

func handleSettingsStatus(service *settings.Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		user := currentUser(r.Context())
		if user == nil || user.Role != "admin" {
			writeError(w, http.StatusForbidden, "无权访问该资源")
			return
		}
		status, err := service.BuildStatus(r.Context())
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		writeJSON(w, http.StatusOK, status)
	}
}
