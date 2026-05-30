package httpapi

import (
	"net/http"

	"github.com/gorilla/websocket"
	"github.com/life2you/fishRadar2/services/radar-control/internal/auth"
	"github.com/life2you/fishRadar2/services/radar-control/internal/config"
	"github.com/life2you/fishRadar2/services/radar-control/internal/realtime"
)

var websocketUpgrader = websocket.Upgrader{
	CheckOrigin: func(r *http.Request) bool {
		return true
	},
}

func handleWebSocket(authService *auth.Service, cfg config.Config, hub *realtime.Hub) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if hub == nil {
			writeError(w, http.StatusServiceUnavailable, "实时服务未启用")
			return
		}
		cookie, err := r.Cookie(cfg.AuthCookieName)
		if err != nil || cookie == nil || cookie.Value == "" {
			writeError(w, http.StatusUnauthorized, "未登录或登录已过期")
			return
		}
		user, err := authService.GetUserBySession(r.Context(), cookie.Value)
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		if user == nil {
			writeError(w, http.StatusUnauthorized, "未登录或登录已过期")
			return
		}
		if user.Role == "tenant" && !user.WorkspaceEnabled {
			writeError(w, http.StatusForbidden, "当前租户工作台不可用")
			return
		}

		conn, err := websocketUpgrader.Upgrade(w, r, nil)
		if err != nil {
			return
		}
		client := hub.Register(conn, user)
		defer hub.Unregister(client)

		for {
			if _, _, err := conn.ReadMessage(); err != nil {
				return
			}
		}
	}
}
