package httpapi

import (
	"database/sql"
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"strings"

	"github.com/life2you/fishRadar2/services/api-go/internal/tenants"
)

func handleTenantList(service *tenants.Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		user := currentUser(r.Context())
		if user == nil || user.Role != "admin" {
			writeError(w, http.StatusForbidden, "无权访问该资源")
			return
		}
		items, err := service.List(r.Context())
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"items": items})
	}
}

func handleTenantByID(service *tenants.Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		user := currentUser(r.Context())
		if user == nil || user.Role != "admin" {
			writeError(w, http.StatusForbidden, "无权访问该资源")
			return
		}
		id, err := tenantIDFromPath(r.URL.Path)
		if err != nil {
			writeError(w, http.StatusBadRequest, "租户ID无效")
			return
		}

		switch r.Method {
		case http.MethodGet:
			detail, err := service.GetDetail(r.Context(), id)
			if err != nil {
				if errors.Is(err, sql.ErrNoRows) {
					writeError(w, http.StatusNotFound, "租户不存在")
					return
				}
				writeError(w, http.StatusInternalServerError, err.Error())
				return
			}
			writeJSON(w, http.StatusOK, detail)
		case http.MethodPatch:
			var payload tenants.UpdateInput
			if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
				writeError(w, http.StatusBadRequest, "请求体无效")
				return
			}
			item, err := service.UpdateAccess(r.Context(), id, payload)
			if err != nil {
				if errors.Is(err, sql.ErrNoRows) {
					writeError(w, http.StatusNotFound, "租户不存在")
					return
				}
				var validationErr tenants.ValidationError
				if errors.As(err, &validationErr) {
					writeError(w, http.StatusBadRequest, validationErr.Error())
					return
				}
				writeError(w, http.StatusInternalServerError, err.Error())
				return
			}
			writeJSON(w, http.StatusOK, map[string]any{"message": "租户权限已更新", "item": item})
		default:
			writeError(w, http.StatusMethodNotAllowed, "方法不支持")
		}
	}
}

func tenantIDFromPath(path string) (int64, error) {
	idText := strings.TrimPrefix(path, "/api/settings/tenants/")
	idText = strings.TrimSpace(idText)
	return strconv.ParseInt(idText, 10, 64)
}
