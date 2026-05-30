package httpapi

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"

	"github.com/life2you/fishRadar2/services/radar-control/internal/aiaccounts"
	"github.com/life2you/fishRadar2/services/radar-control/internal/config"
)

type aiAccountTestPayload struct {
	APIKey    *string `json:"api_key"`
	BaseURL   string  `json:"base_url"`
	ModelName string  `json:"model_name"`
}

func handleNotificationTest(cfg config.Config) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if requireAdminUser(w, r) == nil {
			return
		}
		var payload map[string]any
		if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
			writeError(w, http.StatusBadRequest, "请求体无效")
			return
		}
		result, err := runJSONBridge(r.Context(), cfg, "tools/notification_test_bridge.py", map[string]any{
			"scope":    "platform",
			"channel":  payload["channel"],
			"settings": payload["settings"],
		})
		if err != nil {
			writeError(w, http.StatusUnprocessableEntity, err.Error())
			return
		}
		writeJSON(w, http.StatusOK, result)
	}
}

func handleTenantNotificationTest(cfg config.Config) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		user := requireWorkspaceUser(w, r)
		if user == nil || user.Role != "tenant" || user.TenantID == nil {
			writeError(w, http.StatusForbidden, "当前账号无权访问该资源")
			return
		}
		var payload map[string]any
		if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
			writeError(w, http.StatusBadRequest, "请求体无效")
			return
		}
		result, err := runJSONBridge(r.Context(), cfg, "tools/notification_test_bridge.py", map[string]any{
			"scope":     "tenant",
			"tenant_id": *user.TenantID,
			"channel":   payload["channel"],
			"settings":  payload["settings"],
		})
		if err != nil {
			writeError(w, http.StatusUnprocessableEntity, err.Error())
			return
		}
		writeJSON(w, http.StatusOK, result)
	}
}

func handleAIAccountTest(cfg config.Config) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if requireAdminUser(w, r) == nil {
			return
		}
		var payload aiAccountTestPayload
		if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
			writeError(w, http.StatusBadRequest, "请求体无效")
			return
		}
		result, err := runJSONBridge(r.Context(), cfg, "tools/ai_account_test_bridge.py", map[string]any{
			"api_key":    payload.APIKey,
			"base_url":   payload.BaseURL,
			"model_name": payload.ModelName,
		})
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		writeJSON(w, http.StatusOK, result)
	}
}

func handleExistingAIAccountTest(cfg config.Config, service *aiaccounts.Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if requireAdminUser(w, r) == nil {
			return
		}
		id, err := accountIDFromTestPath(r.URL.Path)
		if err != nil {
			writeError(w, http.StatusBadRequest, "AI账号ID无效")
			return
		}
		testConfig, err := service.GetTestConfig(r.Context(), id)
		if err != nil {
			writeError(w, http.StatusNotFound, "AI账号未找到")
			return
		}
		result, err := runJSONBridge(r.Context(), cfg, "tools/ai_account_test_bridge.py", map[string]any{
			"account_id": testConfig.AccountID,
			"api_key":    testConfig.APIKey,
			"base_url":   testConfig.BaseURL,
			"model_name": testConfig.ModelName,
		})
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		updated, _ := service.Get(r.Context(), id)
		if updated != nil {
			result["item"] = updated
		}
		writeJSON(w, http.StatusOK, result)
	}
}

func runJSONBridge(ctx context.Context, cfg config.Config, script string, payload map[string]any) (map[string]any, error) {
	workerRoot, err := filepath.Abs(cfg.WorkerPyRoot)
	if err != nil {
		return nil, err
	}
	command := exec.CommandContext(ctx, cfg.PythonBin, script)
	command.Dir = workerRoot
	command.Env = append(command.Environ(), "PYTHONIOENCODING=utf-8", "PYTHONUNBUFFERED=1")
	stdin, err := command.StdinPipe()
	if err != nil {
		return nil, err
	}
	stdout, err := command.StdoutPipe()
	if err != nil {
		return nil, err
	}
	command.Stderr = command.Stdout
	if err := command.Start(); err != nil {
		return nil, err
	}
	go func() {
		defer stdin.Close()
		_ = json.NewEncoder(stdin).Encode(payload)
	}()
	scanner := bufio.NewScanner(stdout)
	for scanner.Scan() {
		var event map[string]json.RawMessage
		if err := json.Unmarshal(scanner.Bytes(), &event); err != nil {
			continue
		}
		var eventType string
		if err := json.Unmarshal(event["type"], &eventType); err != nil {
			continue
		}
		switch eventType {
		case "result":
			var wrapper struct {
				Payload map[string]any `json:"payload"`
			}
			if err := json.Unmarshal(scanner.Bytes(), &wrapper); err == nil {
				if err := command.Wait(); err != nil {
					return nil, err
				}
				return wrapper.Payload, nil
			}
		case "error":
			var wrapper struct {
				Error string `json:"error"`
			}
			_ = json.Unmarshal(scanner.Bytes(), &wrapper)
			_ = command.Wait()
			if wrapper.Error == "" {
				wrapper.Error = "桥接调用失败"
			}
			return nil, fmt.Errorf("%s", wrapper.Error)
		}
	}
	if err := scanner.Err(); err != nil {
		return nil, err
	}
	if err := command.Wait(); err != nil {
		return nil, err
	}
	return nil, fmt.Errorf("桥接调用未返回结果")
}

func accountIDFromTestPath(path string) (int64, error) {
	value := strings.TrimSuffix(strings.TrimPrefix(path, "/api/settings/ai-accounts/"), "/test")
	return strconv.ParseInt(strings.TrimSpace(value), 10, 64)
}
