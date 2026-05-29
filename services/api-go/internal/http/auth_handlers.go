package httpapi

import (
	"encoding/json"
	"net/http"

	"github.com/life2you/fishRadar2/services/api-go/internal/auth"
	"github.com/life2you/fishRadar2/services/api-go/internal/config"
)

type loginRequest struct {
	Username string `json:"username"`
	Password string `json:"password"`
}

const sessionMaxAgeSeconds = 7 * 24 * 60 * 60

func handleLogin(authService *auth.Service, cfg config.Config) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var payload loginRequest
		if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
			writeError(w, http.StatusBadRequest, "请求体无效")
			return
		}
		user, err := authService.Authenticate(r.Context(), payload.Username, payload.Password)
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		if user == nil {
			writeError(w, http.StatusUnauthorized, "认证失败")
			return
		}
		sessionToken, err := authService.CreateSession(r.Context(), user)
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		http.SetCookie(w, &http.Cookie{
			Name:     cfg.AuthCookieName,
			Value:    sessionToken,
			Path:     "/",
			HttpOnly: true,
			SameSite: http.SameSiteLaxMode,
			Secure:   cfg.AuthCookieSecure,
			MaxAge:   sessionMaxAgeSeconds,
		})
		writeJSON(w, http.StatusOK, user.AuthPayload())
	}
}

func handleMe() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		user := currentUser(r.Context())
		if user == nil {
			writeError(w, http.StatusUnauthorized, "未登录或登录已过期")
			return
		}
		writeJSON(w, http.StatusOK, user.AuthPayload())
	}
}

func handleLogout(authService *auth.Service, cfg config.Config) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		cookie, err := r.Cookie(cfg.AuthCookieName)
		if err == nil && cookie.Value != "" {
			_ = authService.DeleteSession(r.Context(), cookie.Value)
		}
		http.SetCookie(w, &http.Cookie{
			Name:     cfg.AuthCookieName,
			Value:    "",
			Path:     "/",
			HttpOnly: true,
			SameSite: http.SameSiteLaxMode,
			Secure:   cfg.AuthCookieSecure,
			MaxAge:   -1,
		})
		writeJSON(w, http.StatusOK, map[string]string{"message": "已退出登录"})
	}
}
