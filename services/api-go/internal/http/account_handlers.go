package httpapi

import (
	"database/sql"
	"encoding/json"
	"errors"
	"net/http"
	"net/url"
	"strings"

	"github.com/life2you/fishRadar2/services/api-go/internal/accounts"
)

type accountPayload struct {
	Name    string `json:"name"`
	Content string `json:"content"`
}

func handleAccounts(service *accounts.Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if requireAdminUser(w, r) == nil {
			return
		}
		switch r.Method {
		case http.MethodGet:
			items, err := service.List(r.Context())
			if err != nil {
				writeError(w, http.StatusInternalServerError, err.Error())
				return
			}
			writeJSON(w, http.StatusOK, items)
		case http.MethodPost:
			var payload accountPayload
			if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
				writeError(w, http.StatusBadRequest, "请求体无效")
				return
			}
			item, err := service.Create(r.Context(), payload.Name, payload.Content)
			if err != nil {
				writeAccountError(w, err)
				return
			}
			writeJSON(w, http.StatusOK, map[string]any{"message": "账号已添加", "name": item.Name, "path": item.Path, "content": item.Content, "updated_at": item.UpdatedAt})
		default:
			writeError(w, http.StatusMethodNotAllowed, "方法不支持")
		}
	}
}

func handleAccountByName(service *accounts.Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if requireAdminUser(w, r) == nil {
			return
		}
		name, err := accountNameFromPath(r.URL.Path)
		if err != nil {
			writeError(w, http.StatusBadRequest, err.Error())
			return
		}
		switch r.Method {
		case http.MethodGet:
			item, err := service.Get(r.Context(), name)
			if err != nil {
				writeAccountError(w, err)
				return
			}
			writeJSON(w, http.StatusOK, item)
		case http.MethodPut:
			var payload accountPayload
			if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
				writeError(w, http.StatusBadRequest, "请求体无效")
				return
			}
			item, err := service.Update(r.Context(), name, payload.Content)
			if err != nil {
				writeAccountError(w, err)
				return
			}
			writeJSON(w, http.StatusOK, map[string]any{"message": "账号已更新", "name": item.Name, "path": item.Path, "content": item.Content, "updated_at": item.UpdatedAt})
		case http.MethodDelete:
			deleted, err := service.Delete(r.Context(), name)
			if err != nil {
				writeAccountError(w, err)
				return
			}
			if !deleted {
				writeError(w, http.StatusNotFound, "账号不存在")
				return
			}
			writeJSON(w, http.StatusOK, map[string]string{"message": "账号已删除"})
		default:
			writeError(w, http.StatusMethodNotAllowed, "方法不支持")
		}
	}
}

func handleLoginState(service *accounts.Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if requireAdminUser(w, r) == nil {
			return
		}
		switch r.Method {
		case http.MethodPost:
			var payload accountPayload
			if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
				writeError(w, http.StatusBadRequest, "请求体无效")
				return
			}
			if err := service.UpsertDefaultLoginState(r.Context(), payload.Content); err != nil {
				writeAccountError(w, err)
				return
			}
			writeJSON(w, http.StatusOK, map[string]string{"message": "默认登录状态已成功更新。"})
		case http.MethodDelete:
			deleted, err := service.DeleteDefaultLoginState(r.Context())
			if err != nil {
				writeError(w, http.StatusInternalServerError, err.Error())
				return
			}
			if deleted {
				writeJSON(w, http.StatusOK, map[string]string{"message": "默认登录状态已成功删除。"})
				return
			}
			writeJSON(w, http.StatusOK, map[string]string{"message": "默认登录状态不存在，无需删除。"})
		default:
			writeError(w, http.StatusMethodNotAllowed, "方法不支持")
		}
	}
}

func accountNameFromPath(path string) (string, error) {
	value := strings.TrimPrefix(path, "/api/accounts/")
	value = strings.TrimSpace(value)
	if decoded, err := url.PathUnescape(value); err == nil {
		value = decoded
	}
	return accounts.ValidateAccountName(value)
}

func writeAccountError(w http.ResponseWriter, err error) {
	switch {
	case errors.Is(err, sql.ErrNoRows):
		writeError(w, http.StatusNotFound, "账号不存在")
	case err != nil && strings.Contains(err.Error(), "账号已存在"):
		writeError(w, http.StatusConflict, err.Error())
	default:
		writeError(w, http.StatusBadRequest, err.Error())
	}
}
