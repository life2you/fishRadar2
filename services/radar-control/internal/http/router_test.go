package httpapi

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/life2you/fishRadar2/services/radar-control/internal/config"
)

func TestHealthRoute(t *testing.T) {
	router := NewRouter(config.Config{
		Host: "127.0.0.1",
		Port: "8080",
		Env:  "test",
	})

	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
}
