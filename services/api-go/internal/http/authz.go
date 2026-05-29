package httpapi

import (
	"net/http"

	"github.com/life2you/fishRadar2/services/api-go/internal/auth"
)

func requireAuthenticatedUser(w http.ResponseWriter, r *http.Request) *auth.UserContext {
	user := currentUser(r.Context())
	if user == nil {
		writeError(w, http.StatusUnauthorized, "未登录或登录已过期")
		return nil
	}
	return user
}

func requireWorkspaceUser(w http.ResponseWriter, r *http.Request) *auth.UserContext {
	user := requireAuthenticatedUser(w, r)
	if user == nil {
		return nil
	}
	if user.Role == "tenant" && !user.WorkspaceEnabled {
		writeError(w, http.StatusForbidden, "租户工作台尚未开通或已过期，请先使用卡密激活")
		return nil
	}
	return user
}

func requireAdminUser(w http.ResponseWriter, r *http.Request) *auth.UserContext {
	user := requireAuthenticatedUser(w, r)
	if user == nil {
		return nil
	}
	if user.Role != "admin" {
		writeError(w, http.StatusForbidden, "当前账号无权访问该资源")
		return nil
	}
	return user
}
