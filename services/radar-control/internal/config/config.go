package config

import (
	"os"
	"strings"
)

type Config struct {
	Host              string
	Port              string
	Env               string
	DatabaseURL       string
	AuthCookieName    string
	AuthCookieSecure  bool
	QueueBackend      string
	RedisURL          string
	RedisQueueName    string
	RedisEventChannel string
	PythonBin         string
	WorkerPyRoot      string
}

func Load() Config {
	return Config{
		Host:              getEnv("API_HOST", "0.0.0.0"),
		Port:              getEnv("API_PORT", "8080"),
		Env:               getEnv("APP_ENV", "development"),
		DatabaseURL:       getEnv("APP_DATABASE_URL", ""),
		AuthCookieName:    getEnv("AUTH_SESSION_COOKIE_NAME", "auth_session"),
		AuthCookieSecure:  getEnvBool("AUTH_COOKIE_SECURE", false),
		QueueBackend:      getEnv("QUEUE_BACKEND", "mysql"),
		RedisURL:          getEnv("REDIS_URL", "redis://127.0.0.1:6379/0"),
		RedisQueueName:    getEnv("REDIS_QUEUE_NAME", "fishradar2:worker_jobs"),
		RedisEventChannel: getEnv("REDIS_EVENT_CHANNEL", "fishradar2:events"),
		PythonBin:         getEnv("PYTHON_BIN", "python3"),
		WorkerPyRoot:      getEnv("WORKER_PY_ROOT", "../worker-py"),
	}
}

func (c Config) ListenAddr() string {
	return c.Host + ":" + c.Port
}

func getEnv(key string, fallback string) string {
	value := os.Getenv(key)
	if value == "" {
		return fallback
	}
	return value
}

func getEnvBool(key string, fallback bool) bool {
	value := strings.TrimSpace(strings.ToLower(os.Getenv(key)))
	if value == "" {
		return fallback
	}
	return value == "1" || value == "true" || value == "yes" || value == "on"
}
