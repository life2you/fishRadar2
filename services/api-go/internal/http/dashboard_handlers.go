package httpapi

import (
	"net/http"

	"github.com/life2you/fishRadar2/services/api-go/internal/dashboard"
)

func handleDashboardSummary(service *dashboard.Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		snapshot, err := service.BuildSnapshot(r.Context())
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		writeJSON(w, http.StatusOK, snapshot)
	}
}
