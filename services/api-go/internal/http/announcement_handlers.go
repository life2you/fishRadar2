package httpapi

import (
	"database/sql"
	"encoding/json"
	"net/http"
	"strconv"
	"strings"

	"github.com/life2you/fishRadar2/services/api-go/internal/announcements"
)

func handleAnnouncements(service *announcements.Service, includeInactive bool) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		items, err := service.List(r.Context(), includeInactive)
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"items": items})
	}
}

func handleAnnouncementCreate(service *announcements.Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		user := currentUser(r.Context())
		if user == nil || user.Role != "admin" {
			writeError(w, http.StatusForbidden, "无权访问该资源")
			return
		}
		var payload announcements.SaveInput
		if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
			writeError(w, http.StatusBadRequest, "请求体无效")
			return
		}
		payload.CreatedByUserID = &user.UserID
		item, err := service.Create(r.Context(), payload)
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"message": "公告已创建", "item": item, "notification_result": nil})
	}
}

func handleAnnouncementByID(service *announcements.Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		user := currentUser(r.Context())
		if user == nil || user.Role != "admin" {
			writeError(w, http.StatusForbidden, "无权访问该资源")
			return
		}
		idText := strings.TrimPrefix(r.URL.Path, "/api/announcements/")
		idText = strings.TrimSpace(idText)
		id, err := strconv.ParseInt(idText, 10, 64)
		if err != nil {
			writeError(w, http.StatusBadRequest, "公告ID无效")
			return
		}

		switch r.Method {
		case http.MethodPatch:
			var payload announcements.SaveInput
			if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
				writeError(w, http.StatusBadRequest, "请求体无效")
				return
			}
			item, err := service.Update(r.Context(), id, payload)
			if err != nil {
				if err == sql.ErrNoRows {
					writeError(w, http.StatusNotFound, "公告不存在")
					return
				}
				writeError(w, http.StatusInternalServerError, err.Error())
				return
			}
			writeJSON(w, http.StatusOK, map[string]any{"message": "公告已更新", "item": item, "notification_result": nil})
		case http.MethodDelete:
			if err := service.Delete(r.Context(), id); err != nil {
				writeError(w, http.StatusInternalServerError, err.Error())
				return
			}
			writeJSON(w, http.StatusOK, map[string]any{"message": "公告已删除"})
		default:
			writeError(w, http.StatusMethodNotAllowed, "方法不支持")
		}
	}
}
