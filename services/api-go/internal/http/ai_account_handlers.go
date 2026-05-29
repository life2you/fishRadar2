package httpapi

import (
	"database/sql"
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"strings"

	"github.com/life2you/fishRadar2/services/api-go/internal/aiaccounts"
	"github.com/life2you/fishRadar2/services/api-go/internal/config"
)

func handleAIAccounts(service *aiaccounts.Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		user := currentUser(r.Context())
		if user == nil || user.Role != "admin" {
			writeError(w, http.StatusForbidden, "无权访问该资源")
			return
		}
		switch r.Method {
		case http.MethodGet:
			items, err := service.List(r.Context(), true)
			if err != nil {
				writeError(w, http.StatusInternalServerError, err.Error())
				return
			}
			writeJSON(w, http.StatusOK, map[string]any{"items": items})
		case http.MethodPost:
			var payload aiaccounts.CreateInput
			if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
				writeError(w, http.StatusBadRequest, "请求体无效")
				return
			}
			item, err := service.Create(r.Context(), payload)
			if err != nil {
				var validationErr aiaccounts.ValidationError
				if errors.As(err, &validationErr) {
					writeError(w, http.StatusBadRequest, validationErr.Error())
					return
				}
				writeError(w, http.StatusInternalServerError, err.Error())
				return
			}
			writeJSON(w, http.StatusOK, map[string]any{"message": "AI账号已创建", "item": item})
		default:
			writeError(w, http.StatusMethodNotAllowed, "方法不支持")
		}
	}
}

func handleAIAccountByID(service *aiaccounts.Service, cfg config.Config) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		user := currentUser(r.Context())
		if user == nil || user.Role != "admin" {
			writeError(w, http.StatusForbidden, "无权访问该资源")
			return
		}
		if r.Method == http.MethodPost && strings.HasSuffix(r.URL.Path, "/test") {
			handleExistingAIAccountTest(cfg, service).ServeHTTP(w, r)
			return
		}
		id, err := accountIDFromPath(r.URL.Path)
		if err != nil {
			writeError(w, http.StatusBadRequest, "AI账号ID无效")
			return
		}
		switch r.Method {
		case http.MethodPatch:
			var payload aiaccounts.UpdateInput
			if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
				writeError(w, http.StatusBadRequest, "请求体无效")
				return
			}
			item, err := service.Update(r.Context(), id, payload)
			if err != nil {
				if errors.Is(err, sql.ErrNoRows) {
					writeError(w, http.StatusNotFound, "AI账号未找到")
					return
				}
				var validationErr aiaccounts.ValidationError
				if errors.As(err, &validationErr) {
					writeError(w, http.StatusBadRequest, validationErr.Error())
					return
				}
				writeError(w, http.StatusInternalServerError, err.Error())
				return
			}
			writeJSON(w, http.StatusOK, map[string]any{"message": "AI账号已更新", "item": item})
		case http.MethodDelete:
			deleted, err := service.Delete(r.Context(), id)
			if err != nil {
				writeError(w, http.StatusInternalServerError, err.Error())
				return
			}
			if !deleted {
				writeError(w, http.StatusNotFound, "AI账号未找到")
				return
			}
			writeJSON(w, http.StatusOK, map[string]any{"message": "AI账号已删除"})
		default:
			writeError(w, http.StatusMethodNotAllowed, "方法不支持")
		}
	}
}

func accountIDFromPath(path string) (int64, error) {
	idText := strings.TrimPrefix(path, "/api/settings/ai-accounts/")
	idText = strings.TrimSpace(idText)
	return strconv.ParseInt(idText, 10, 64)
}
