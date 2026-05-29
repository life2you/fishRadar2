package httpapi

import (
	"database/sql"
	"encoding/json"
	"errors"
	"net/http"
	"net/url"
	"strings"

	"github.com/life2you/fishRadar2/services/api-go/internal/prompts"
)

type promptUpdatePayload struct {
	Content string `json:"content"`
}

func handlePrompts(service *prompts.Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if requireAdminUser(w, r) == nil {
			return
		}
		if r.Method != http.MethodGet {
			writeError(w, http.StatusMethodNotAllowed, "方法不支持")
			return
		}
		items, err := service.List(r.Context())
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		writeJSON(w, http.StatusOK, items)
	}
}

func handlePromptByFilename(service *prompts.Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if requireAdminUser(w, r) == nil {
			return
		}
		filename, err := promptFilenameFromPath(r.URL.Path)
		if err != nil {
			writeError(w, http.StatusBadRequest, err.Error())
			return
		}
		switch r.Method {
		case http.MethodGet:
			document, err := service.Get(r.Context(), filename)
			if err != nil {
				if errors.Is(err, sql.ErrNoRows) {
					writeError(w, http.StatusNotFound, "Prompt 文件未找到")
					return
				}
				writeError(w, http.StatusInternalServerError, err.Error())
				return
			}
			writeJSON(w, http.StatusOK, map[string]any{"filename": document.Filename, "content": document.Content})
		case http.MethodPut:
			var payload promptUpdatePayload
			if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
				writeError(w, http.StatusBadRequest, "请求体无效")
				return
			}
			document, err := service.Update(r.Context(), filename, payload.Content)
			if err != nil {
				if errors.Is(err, sql.ErrNoRows) {
					writeError(w, http.StatusNotFound, "Prompt 文件未找到")
					return
				}
				writeError(w, http.StatusBadRequest, err.Error())
				return
			}
			writeJSON(w, http.StatusOK, map[string]any{"message": "Prompt 文件 '" + document.Filename + "' 更新成功", "updated_at": document.UpdatedAt})
		default:
			writeError(w, http.StatusMethodNotAllowed, "方法不支持")
		}
	}
}

func promptFilenameFromPath(path string) (string, error) {
	value := strings.TrimPrefix(path, "/api/prompts/")
	value = strings.TrimSpace(value)
	if decoded, err := url.PathUnescape(value); err == nil {
		value = decoded
	}
	return prompts.NormalizeFilename(value)
}
