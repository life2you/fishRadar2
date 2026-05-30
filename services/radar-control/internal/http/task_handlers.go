package httpapi

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"strings"

	"github.com/life2you/fishRadar2/services/radar-control/internal/auth"
	"github.com/life2you/fishRadar2/services/radar-control/internal/generation"
	"github.com/life2you/fishRadar2/services/radar-control/internal/realtime"
	runtimeworker "github.com/life2you/fishRadar2/services/radar-control/internal/runtime"
	"github.com/life2you/fishRadar2/services/radar-control/internal/tasks"
)

func handleTasks(service *tasks.Service, generationService *generation.Service, realtimeHub *realtime.Hub) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		user := requireWorkspaceUser(w, r)
		if user == nil {
			return
		}

		switch r.Method {
		case http.MethodGet:
			tenantID, err := tenantScopeFromTaskQuery(user, r.URL.Query().Get("tenant_id"))
			if err != nil {
				writeError(w, http.StatusBadRequest, "租户ID无效")
				return
			}
			items, err := service.List(r.Context(), tenantID)
			if err != nil {
				writeError(w, http.StatusInternalServerError, err.Error())
				return
			}
			writeJSON(w, http.StatusOK, items)
		case http.MethodPost:
			var payload tasks.CreateInput
			if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
				writeError(w, http.StatusBadRequest, "请求体无效")
				return
			}
			if user.Role == "tenant" {
				payload.TenantID = user.TenantID
			}
			item, err := service.Create(r.Context(), payload)
			if err != nil {
				writeTaskError(w, err)
				return
			}
			publishTaskRefresh(r.Context(), realtimeHub, item.TenantID)
			writeJSON(w, http.StatusOK, map[string]any{"message": "任务创建成功", "task": item})
		default:
			writeError(w, http.StatusMethodNotAllowed, "方法不支持")
		}
	}
}

func handleTaskGenerate(service *tasks.Service, generationService *generation.Service, realtimeHub *realtime.Hub) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		user := requireWorkspaceUser(w, r)
		if user == nil {
			return
		}
		if r.Method != http.MethodPost {
			writeError(w, http.StatusMethodNotAllowed, "方法不支持")
			return
		}
		var payload generation.GenerateRequest
		if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
			writeError(w, http.StatusBadRequest, "请求体无效")
			return
		}
		if payload.DecisionMode == "" {
			payload.DecisionMode = "ai"
		}
		if user.Role == "tenant" {
			payload.TenantID = user.TenantID
			if payload.DecisionMode == "ai" && !user.CanUseAI {
				writeError(w, http.StatusForbidden, "当前租户未开通 AI 分析能力")
				return
			}
		}
		if payload.DecisionMode != "ai" {
			task, err := service.Create(r.Context(), tasks.CreateInput{
				TenantID:         payload.TenantID,
				TaskName:         payload.TaskName,
				Enabled:          true,
				Keyword:          payload.Keyword,
				Description:      payload.Description,
				AnalyzeImages:    payload.AnalyzeImages,
				MaxPages:         payload.MaxPages,
				PersonalOnly:     payload.PersonalOnly,
				MinPrice:         payload.MinPrice,
				MaxPrice:         payload.MaxPrice,
				Cron:             payload.Cron,
				AIPromptBaseFile: "prompts/base_prompt.txt",
				AccountStateFile: payload.AccountStateFile,
				AccountStrategy:  payload.AccountStrategy,
				FreeShipping:     payload.FreeShipping,
				NewPublishOption: payload.NewPublishOption,
				Region:           payload.Region,
				DecisionMode:     payload.DecisionMode,
				KeywordRules:     payload.KeywordRules,
			})
			if err != nil {
				writeTaskError(w, err)
				return
			}
			publishTaskRefresh(r.Context(), realtimeHub, task.TenantID)
			writeJSON(w, http.StatusOK, map[string]any{"message": "任务创建成功。", "task": task})
			return
		}

		var requestedByUserID *int64
		if user != nil {
			requestedByUserID = &user.UserID
		}
		job, err := generationService.CreateJob(r.Context(), payload, requestedByUserID)
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		writeJSON(w, http.StatusAccepted, map[string]any{
			"message": "AI 任务生成已开始。",
			"job":     job,
		})
	}
}

func handleTaskGenerateJob(generationService *generation.Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if requireWorkspaceUser(w, r) == nil {
			return
		}
		if r.Method != http.MethodGet {
			writeError(w, http.StatusMethodNotAllowed, "方法不支持")
			return
		}
		jobID := strings.TrimPrefix(r.URL.Path, "/api/tasks/generate-jobs/")
		jobID = strings.TrimSpace(jobID)
		job, err := generationService.GetJob(r.Context(), jobID)
		if err != nil {
			if errors.Is(err, sql.ErrNoRows) {
				writeError(w, http.StatusNotFound, "任务生成作业未找到")
				return
			}
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		if job == nil {
			writeError(w, http.StatusNotFound, "任务生成作业未找到")
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"job": job})
	}
}

func handleTaskStart(service *tasks.Service, runtimeManager *runtimeworker.WorkerManager) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		user := requireWorkspaceUser(w, r)
		if user == nil {
			return
		}
		if r.Method != http.MethodPost {
			writeError(w, http.StatusMethodNotAllowed, "方法不支持")
			return
		}
		taskID, err := taskIDFromActionPath(r.URL.Path, "/api/tasks/start/")
		if err != nil {
			writeError(w, http.StatusBadRequest, "任务ID无效")
			return
		}
		item, err := service.Get(r.Context(), taskID)
		if err != nil {
			if errors.Is(err, sql.ErrNoRows) {
				writeError(w, http.StatusNotFound, "任务未找到")
				return
			}
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		if !canAccessTask(user, item) {
			writeError(w, http.StatusNotFound, "任务未找到")
			return
		}
		if user.Role == "tenant" && item.DecisionMode == "ai" && !user.CanUseAI {
			writeError(w, http.StatusForbidden, "当前租户未开通 AI 分析能力")
			return
		}
		var requestedByUserID *int64
		if user != nil {
			requestedByUserID = &user.UserID
		}
		if err := runtimeManager.StartTask(r.Context(), taskID, requestedByUserID); err != nil {
			writeError(w, http.StatusBadRequest, err.Error())
			return
		}
		writeJSON(w, http.StatusOK, map[string]string{"message": "任务 '" + item.TaskName + "' 启动请求已入队"})
	}
}

func handleTaskStop(service *tasks.Service, runtimeManager *runtimeworker.WorkerManager) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		user := requireWorkspaceUser(w, r)
		if user == nil {
			return
		}
		if r.Method != http.MethodPost {
			writeError(w, http.StatusMethodNotAllowed, "方法不支持")
			return
		}
		taskID, err := taskIDFromActionPath(r.URL.Path, "/api/tasks/stop/")
		if err != nil {
			writeError(w, http.StatusBadRequest, "任务ID无效")
			return
		}
		item, err := service.Get(r.Context(), taskID)
		if err != nil {
			if errors.Is(err, sql.ErrNoRows) {
				writeError(w, http.StatusNotFound, "任务未找到")
				return
			}
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		if !canAccessTask(user, item) {
			writeError(w, http.StatusNotFound, "任务未找到")
			return
		}
		var requestedByUserID *int64
		if user != nil {
			requestedByUserID = &user.UserID
		}
		if err := runtimeManager.StopTask(r.Context(), taskID, requestedByUserID); err != nil {
			writeError(w, http.StatusBadRequest, err.Error())
			return
		}
		writeJSON(w, http.StatusOK, map[string]string{"message": "任务ID " + strconv.FormatInt(taskID, 10) + " 停止请求已入队"})
	}
}

func handleTaskByID(service *tasks.Service, generationService *generation.Service, realtimeHub *realtime.Hub) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		user := requireWorkspaceUser(w, r)
		if user == nil {
			return
		}
		taskID, err := taskIDFromPath(r.URL.Path)
		if err != nil {
			writeError(w, http.StatusBadRequest, "任务ID无效")
			return
		}
		switch r.Method {
		case http.MethodGet:
			item, err := service.Get(r.Context(), taskID)
			if err != nil {
				if errors.Is(err, sql.ErrNoRows) {
					writeError(w, http.StatusNotFound, "任务未找到")
					return
				}
				writeError(w, http.StatusInternalServerError, err.Error())
				return
			}
			if !canAccessTask(user, item) {
				writeError(w, http.StatusNotFound, "任务未找到")
				return
			}
			writeJSON(w, http.StatusOK, item)
		case http.MethodPatch:
			item, err := service.Get(r.Context(), taskID)
			if err != nil {
				if errors.Is(err, sql.ErrNoRows) {
					writeError(w, http.StatusNotFound, "任务未找到")
					return
				}
				writeError(w, http.StatusInternalServerError, err.Error())
				return
			}
			if !canAccessTask(user, item) {
				writeError(w, http.StatusNotFound, "任务未找到")
				return
			}
			var payload tasks.UpdateInput
			if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
				writeError(w, http.StatusBadRequest, "请求体无效")
				return
			}
			if user.Role == "tenant" {
				payload.TenantID = user.TenantID
			}
			targetMode := item.DecisionMode
			if payload.DecisionMode != nil && strings.TrimSpace(*payload.DecisionMode) != "" {
				targetMode = strings.TrimSpace(*payload.DecisionMode)
			}
			descriptionChanged := payload.Description != nil && strings.TrimSpace(*payload.Description) != strings.TrimSpace(item.Description)
			keywordChanged := payload.Keyword != nil && strings.TrimSpace(*payload.Keyword) != strings.TrimSpace(item.Keyword)
			taskNameChanged := payload.TaskName != nil && strings.TrimSpace(*payload.TaskName) != strings.TrimSpace(item.TaskName)
			switchedToAI := item.DecisionMode != "ai" && targetMode == "ai"
			if targetMode == "ai" && (descriptionChanged || keywordChanged || taskNameChanged || switchedToAI) {
				descriptionForAI := item.Description
				if payload.Description != nil {
					descriptionForAI = *payload.Description
				}
				keywordForAI := item.Keyword
				if payload.Keyword != nil {
					keywordForAI = *payload.Keyword
				}
				taskNameForAI := item.TaskName
				if payload.TaskName != nil {
					taskNameForAI = *payload.TaskName
				}
				promptPayload, err := generationService.RefreshPrompt(r.Context(), generation.RefreshPromptRequest{
					TaskName:       taskNameForAI,
					Keyword:        keywordForAI,
					Description:    descriptionForAI,
					BasePromptFile: item.AIPromptBaseFile,
				})
				if err != nil {
					writeError(w, http.StatusBadRequest, err.Error())
					return
				}
				payload.AIPromptBaseFile = &promptPayload.AIPromptBaseFile
				payload.AIPromptCriteriaFile = &promptPayload.AIPromptCriteriaFile
				payload.AIPromptBaseText = &promptPayload.AIPromptBaseText
				payload.AIPromptCriteriaText = &promptPayload.AIPromptCriteriaText
				payload.AIPromptText = &promptPayload.AIPromptText
			}
			updated, err := service.Update(r.Context(), taskID, payload)
			if err != nil {
				writeTaskError(w, err)
				return
			}
			publishTaskRefresh(r.Context(), realtimeHub, updated.TenantID)
			writeJSON(w, http.StatusOK, map[string]any{"message": "任务更新成功", "task": updated})
		case http.MethodDelete:
			item, err := service.Get(r.Context(), taskID)
			if err != nil {
				if errors.Is(err, sql.ErrNoRows) {
					writeError(w, http.StatusNotFound, "任务未找到")
					return
				}
				writeError(w, http.StatusInternalServerError, err.Error())
				return
			}
			if !canAccessTask(user, item) {
				writeError(w, http.StatusNotFound, "任务未找到")
				return
			}
			if item.IsRunning {
				_ = service.SetRunning(r.Context(), taskID, false)
			}
			deleted, err := service.Delete(r.Context(), taskID)
			if err != nil {
				writeError(w, http.StatusInternalServerError, err.Error())
				return
			}
			if !deleted {
				writeError(w, http.StatusNotFound, "任务未找到")
				return
			}
			publishTaskRefresh(r.Context(), realtimeHub, item.TenantID)
			writeJSON(w, http.StatusOK, map[string]string{"message": "任务删除成功"})
		default:
			writeError(w, http.StatusMethodNotAllowed, "方法不支持")
		}
	}
}

func publishTaskRefresh(ctx context.Context, realtimeHub *realtime.Hub, tenantID *int64) {
	realtime.PublishTasksUpdated(ctx, realtimeHub, tenantID)
}

func tenantScopeFromTaskQuery(user *auth.UserContext, rawTenantID string) (*int64, error) {
	if user.Role == "tenant" {
		return user.TenantID, nil
	}
	rawTenantID = strings.TrimSpace(rawTenantID)
	if rawTenantID == "" {
		return nil, nil
	}
	parsed, err := strconv.ParseInt(rawTenantID, 10, 64)
	if err != nil {
		return nil, err
	}
	return &parsed, nil
}

func canAccessTask(user *auth.UserContext, item *tasks.Item) bool {
	if user.Role == "admin" {
		return true
	}
	if item == nil || item.TenantID == nil || user.TenantID == nil {
		return false
	}
	return *item.TenantID == *user.TenantID
}

func writeTaskError(w http.ResponseWriter, err error) {
	var validationErr tasks.ValidationError
	switch {
	case errors.As(err, &validationErr):
		writeError(w, http.StatusBadRequest, validationErr.Error())
	case errors.Is(err, sql.ErrNoRows):
		writeError(w, http.StatusNotFound, "任务未找到")
	default:
		writeError(w, http.StatusInternalServerError, err.Error())
	}
}

func taskIDFromPath(path string) (int64, error) {
	idText := strings.TrimPrefix(path, "/api/tasks/")
	idText = strings.TrimSpace(idText)
	return strconv.ParseInt(idText, 10, 64)
}

func taskIDFromActionPath(path string, prefix string) (int64, error) {
	idText := strings.TrimPrefix(path, prefix)
	idText = strings.TrimSpace(idText)
	return strconv.ParseInt(idText, 10, 64)
}
