package main

import (
	"log"
	"net/http"

	"github.com/life2you/fishRadar2/services/radar-control/internal/config"
	httpapi "github.com/life2you/fishRadar2/services/radar-control/internal/http"
)

func main() {
	cfg := config.Load()
	server := &http.Server{
		Addr:    cfg.ListenAddr(),
		Handler: httpapi.NewRouter(cfg),
	}

	log.Printf("api-go listening on %s", cfg.ListenAddr())
	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatalf("api-go failed: %v", err)
	}
}
