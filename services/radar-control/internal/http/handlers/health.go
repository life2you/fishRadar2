package handlers

import (
	"encoding/json"
	"net/http"
)

func Health(w http.ResponseWriter, _ *http.Request) {
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(map[string]string{
		"status":  "ok",
		"service": "radar-control",
	})
}
