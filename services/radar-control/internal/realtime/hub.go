package realtime

import (
	"context"
	"encoding/json"
	"log"
	"strings"
	"sync"
	"time"

	"github.com/gorilla/websocket"
	"github.com/life2you/fishRadar2/services/radar-control/internal/auth"
	"github.com/life2you/fishRadar2/services/radar-control/internal/config"
	"github.com/redis/go-redis/v9"
)

type EventEnvelope struct {
	Type        string          `json:"type"`
	Data        json.RawMessage `json:"data"`
	TenantScope *int64          `json:"tenant_scope,omitempty"`
}

type client struct {
	conn *websocket.Conn
	user *auth.UserContext
	mu   sync.Mutex
}

type Hub struct {
	redisClient  *redis.Client
	redisChannel string

	mu      sync.RWMutex
	clients map[*client]struct{}

	startOnce sync.Once
}

func NewHub(cfg config.Config) *Hub {
	hub := &Hub{
		redisChannel: strings.TrimSpace(cfg.RedisEventChannel),
		clients:      make(map[*client]struct{}),
	}
	if hub.redisChannel == "" {
		hub.redisChannel = "fishradar2:events"
	}
	if redisURL := strings.TrimSpace(cfg.RedisURL); redisURL != "" {
		if options, err := redis.ParseURL(redisURL); err == nil {
			hub.redisClient = redis.NewClient(options)
		}
	}
	return hub
}

func (h *Hub) Start() {
	h.startOnce.Do(func() {
		if h.redisClient == nil {
			return
		}
		go h.subscribeLoop()
	})
}

func (h *Hub) Publish(ctx context.Context, eventType string, data any, tenantScope *int64) error {
	payload, err := buildEnvelope(eventType, data, tenantScope)
	if err != nil {
		return err
	}
	if h.redisClient != nil {
		return h.redisClient.Publish(ctx, h.redisChannel, payload).Err()
	}
	h.dispatch(payload, tenantScope)
	return nil
}

func (h *Hub) Register(conn *websocket.Conn, user *auth.UserContext) *client {
	entry := &client{conn: conn, user: user}
	h.mu.Lock()
	h.clients[entry] = struct{}{}
	h.mu.Unlock()
	return entry
}

func (h *Hub) Unregister(entry *client) {
	if entry == nil {
		return
	}
	h.mu.Lock()
	delete(h.clients, entry)
	h.mu.Unlock()
	_ = entry.conn.Close()
}

func (h *Hub) subscribeLoop() {
	for {
		if h.redisClient == nil {
			return
		}
		pubsub := h.redisClient.Subscribe(context.Background(), h.redisChannel)
		channel := pubsub.Channel()
		for message := range channel {
			var envelope EventEnvelope
			if err := json.Unmarshal([]byte(message.Payload), &envelope); err != nil {
				log.Printf("realtime: failed to decode event payload: %v", err)
				continue
			}
			h.dispatch([]byte(message.Payload), envelope.TenantScope)
		}
		_ = pubsub.Close()
		time.Sleep(2 * time.Second)
	}
}

func (h *Hub) dispatch(payload []byte, tenantScope *int64) {
	h.mu.RLock()
	clients := make([]*client, 0, len(h.clients))
	for entry := range h.clients {
		clients = append(clients, entry)
	}
	h.mu.RUnlock()

	for _, entry := range clients {
		if !shouldDeliver(entry.user, tenantScope) {
			continue
		}
		entry.mu.Lock()
		err := entry.conn.WriteMessage(websocket.TextMessage, payload)
		entry.mu.Unlock()
		if err != nil {
			h.Unregister(entry)
		}
	}
}

func buildEnvelope(eventType string, data any, tenantScope *int64) ([]byte, error) {
	encodedData, err := json.Marshal(data)
	if err != nil {
		return nil, err
	}
	return json.Marshal(EventEnvelope{
		Type:        eventType,
		Data:        encodedData,
		TenantScope: tenantScope,
	})
}

func shouldDeliver(user *auth.UserContext, tenantScope *int64) bool {
	if user == nil {
		return false
	}
	if user.Role == "admin" {
		return true
	}
	if tenantScope == nil || user.TenantID == nil {
		return false
	}
	return *tenantScope == *user.TenantID
}
