package httpapi

import (
	"context"

	"github.com/life2you/fishRadar2/services/api-go/internal/auth"
)

type contextKey string

const userContextKey contextKey = "user"

func withUserContext(ctx context.Context, user *auth.UserContext) context.Context {
	return context.WithValue(ctx, userContextKey, user)
}

func currentUser(ctx context.Context) *auth.UserContext {
	value := ctx.Value(userContextKey)
	if value == nil {
		return nil
	}
	user, _ := value.(*auth.UserContext)
	return user
}
