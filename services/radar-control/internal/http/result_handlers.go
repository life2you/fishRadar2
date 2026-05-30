package httpapi

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/url"
	"strconv"
	"strings"

	"github.com/life2you/fishRadar2/services/radar-control/internal/auth"
	"github.com/life2you/fishRadar2/services/radar-control/internal/realtime"
	"github.com/life2you/fishRadar2/services/radar-control/internal/reanalysis"
	"github.com/life2you/fishRadar2/services/radar-control/internal/results"
)

type blacklistRulesRequest struct {
	Keywords []string `json:"keywords"`
}

type updateItemStatusRequest struct {
	Status string `json:"status"`
}

func handleResultFiles(service *results.Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		user := requireWorkspaceUser(w, r)
		if user == nil {
			return
		}
		switch r.Method {
		case http.MethodGet:
			scope, err := resolveResultsScope(user, r.URL.Query().Get("tenant_id"))
			if err != nil {
				writeError(w, http.StatusBadRequest, err.Error())
				return
			}
			files, err := service.ListFiles(r.Context(), scope)
			if err != nil {
				writeError(w, http.StatusInternalServerError, err.Error())
				return
			}
			writeJSON(w, http.StatusOK, map[string]any{"files": files})
		default:
			writeError(w, http.StatusMethodNotAllowed, "方法不支持")
		}
	}
}

func handleResultFileDownloadOrDelete(service *results.Service, realtimeHub *realtime.Hub) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		user := requireWorkspaceUser(w, r)
		if user == nil {
			return
		}
		filename, err := resultFilenameFromPath(r.URL.Path, "/api/results/files/")
		if err != nil {
			writeError(w, http.StatusBadRequest, err.Error())
			return
		}
		scope, err := resolveResultsScope(user, r.URL.Query().Get("tenant_id"))
		if err != nil {
			writeError(w, http.StatusBadRequest, err.Error())
			return
		}
		switch r.Method {
		case http.MethodGet:
			content, err := service.DownloadNDJSON(r.Context(), filename, scope)
			if err != nil {
				writeResultError(w, err)
				return
			}
			w.Header().Set("Content-Type", "application/x-ndjson")
			w.Header().Set("Content-Disposition", `attachment; filename="`+filename+`"`)
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(content))
		case http.MethodDelete:
			deleted, err := service.DeleteFile(r.Context(), filename, scope)
			if err != nil {
				writeResultError(w, err)
				return
			}
			if deleted <= 0 {
				writeError(w, http.StatusNotFound, "文件不存在")
				return
			}
			publishResultsRefresh(r.Context(), realtimeHub, scope, map[string]any{"filename": filename, "deleted": true})
			writeJSON(w, http.StatusOK, map[string]string{"message": "文件 " + filename + " 已成功删除"})
		default:
			writeError(w, http.StatusMethodNotAllowed, "方法不支持")
		}
	}
}

func handleResultByFilename(service *results.Service, reanalysisService *reanalysis.Service, realtimeHub *realtime.Hub) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		user := requireWorkspaceUser(w, r)
		if user == nil {
			return
		}
		filename, suffix, err := splitResultPath(r.URL.Path)
		if err != nil {
			writeError(w, http.StatusBadRequest, err.Error())
			return
		}
		scope, err := resolveResultsScope(user, r.URL.Query().Get("tenant_id"))
		if err != nil {
			writeError(w, http.StatusBadRequest, err.Error())
			return
		}

		switch {
		case suffix == "":
			if r.Method != http.MethodGet {
				writeError(w, http.StatusMethodNotAllowed, "方法不支持")
				return
			}
			payload, err := service.QueryContent(r.Context(), results.ContentQuery{
				Filename:               filename,
				AIRecommendedOnly:      queryBool(r.URL.Query(), "ai_recommended_only") || (queryBool(r.URL.Query(), "recommended_only") && !queryBool(r.URL.Query(), "keyword_recommended_only")),
				KeywordRecommendedOnly: queryBool(r.URL.Query(), "keyword_recommended_only"),
				SortBy:                 defaultString(r.URL.Query().Get("sort_by"), "crawl_time"),
				SortOrder:              defaultString(r.URL.Query().Get("sort_order"), "desc"),
				Page:                   queryInt(r.URL.Query(), "page", 1),
				Limit:                  queryInt(r.URL.Query(), "limit", 20),
				IncludeHidden:          queryBool(r.URL.Query(), "include_hidden"),
				Scope:                  scope,
			})
			if err != nil {
				writeResultError(w, err)
				return
			}
			writeJSON(w, http.StatusOK, payload)
		case suffix == "/insights":
			if r.Method != http.MethodGet {
				writeError(w, http.StatusMethodNotAllowed, "方法不支持")
				return
			}
			payload, err := service.GetInsights(r.Context(), filename, scope)
			if err != nil {
				writeResultError(w, err)
				return
			}
			writeJSON(w, http.StatusOK, payload)
		case suffix == "/export":
			if r.Method != http.MethodGet {
				writeError(w, http.StatusMethodNotAllowed, "方法不支持")
				return
			}
			csvText, err := service.ExportCSV(r.Context(), results.ContentQuery{
				Filename:               filename,
				AIRecommendedOnly:      queryBool(r.URL.Query(), "ai_recommended_only") || (queryBool(r.URL.Query(), "recommended_only") && !queryBool(r.URL.Query(), "keyword_recommended_only")),
				KeywordRecommendedOnly: queryBool(r.URL.Query(), "keyword_recommended_only"),
				SortBy:                 defaultString(r.URL.Query().Get("sort_by"), "crawl_time"),
				SortOrder:              defaultString(r.URL.Query().Get("sort_order"), "desc"),
				IncludeHidden:          queryBool(r.URL.Query(), "include_hidden"),
				Scope:                  scope,
			})
			if err != nil {
				writeResultError(w, err)
				return
			}
			exportName := strings.TrimSuffix(filename, ".jsonl") + ".csv"
			w.Header().Set("Content-Type", "text/csv; charset=utf-8")
			w.Header().Set("Content-Disposition", buildDownloadDisposition(exportName))
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(csvText))
		case suffix == "/reanalyze":
			admin := requireAdminUser(w, r)
			if admin == nil {
				return
			}
			if r.Method != http.MethodPost {
				writeError(w, http.StatusMethodNotAllowed, "方法不支持")
				return
			}
			var requestedByUserID *int64
			if admin != nil {
				requestedByUserID = &admin.UserID
			}
			payload, err := reanalysisService.Reanalyze(r.Context(), filename, scope, requestedByUserID)
			if err != nil {
				writeError(w, http.StatusInternalServerError, err.Error())
				return
			}
			if payload == nil {
				payload = map[string]any{}
			}
			if _, exists := payload["message"]; !exists {
				payload["message"] = "结果集已完成重新分析"
			}
			writeJSON(w, http.StatusOK, payload)
		case suffix == "/blacklist-rules":
			switch r.Method {
			case http.MethodGet:
				keywords, err := service.GetBlacklistKeywords(r.Context(), filename, scope)
				if err != nil {
					writeResultError(w, err)
					return
				}
				writeJSON(w, http.StatusOK, map[string]any{"keywords": keywords})
			case http.MethodPut:
				var payload blacklistRulesRequest
				if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
					writeError(w, http.StatusBadRequest, "请求体无效")
					return
				}
				keywords, err := service.SaveBlacklistKeywords(r.Context(), filename, scope, payload.Keywords)
				if err != nil {
					writeResultError(w, err)
					return
				}
				publishResultsRefresh(r.Context(), realtimeHub, scope, map[string]any{"filename": filename, "blacklist_updated": true})
				writeJSON(w, http.StatusOK, map[string]any{
					"message":  "黑名单规则已更新",
					"keywords": keywords,
				})
			default:
				writeError(w, http.StatusMethodNotAllowed, "方法不支持")
			}
		case strings.Contains(suffix, "/items/") && strings.HasSuffix(suffix, "/status"):
			if r.Method != http.MethodPatch {
				writeError(w, http.StatusMethodNotAllowed, "方法不支持")
				return
			}
			itemID, err := itemIDFromResultSuffix(suffix)
			if err != nil {
				writeError(w, http.StatusBadRequest, "商品ID无效")
				return
			}
			var payload updateItemStatusRequest
			if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
				writeError(w, http.StatusBadRequest, "请求体无效")
				return
			}
			updated, err := service.UpdateItemStatus(r.Context(), filename, itemID, payload.Status, scope)
			if err != nil {
				writeResultError(w, err)
				return
			}
			if !updated {
				writeError(w, http.StatusNotFound, "商品未找到")
				return
			}
			publishResultsRefresh(r.Context(), realtimeHub, scope, map[string]any{
				"filename": filename,
				"item_id":  itemID,
				"status":   payload.Status,
			})
			writeJSON(w, http.StatusOK, map[string]any{"message": "状态已更新", "status": payload.Status})
		default:
			writeError(w, http.StatusNotFound, "资源不存在")
		}
	}
}

func publishResultsRefresh(ctx context.Context, realtimeHub *realtime.Hub, scope results.Scope, data map[string]any) {
	realtime.PublishResultsUpdated(ctx, realtimeHub, scopeTenantID(scope), data)
}

func scopeTenantID(scope results.Scope) *int64 {
	if scope.Kind != results.ScopeTenant {
		return nil
	}
	tenantID := scope.TenantID
	return &tenantID
}

func resolveResultsScope(user *auth.UserContext, rawTenantID string) (results.Scope, error) {
	if user.Role == "tenant" {
		if user.TenantID == nil {
			return results.GlobalScope(), nil
		}
		return results.TenantScope(*user.TenantID), nil
	}
	if strings.TrimSpace(rawTenantID) == "" {
		return results.GlobalScope(), nil
	}
	tenantID, err := strconv.ParseInt(strings.TrimSpace(rawTenantID), 10, 64)
	if err != nil {
		return results.GlobalScope(), errors.New("租户ID无效")
	}
	return results.TenantScope(tenantID), nil
}

func resultFilenameFromPath(path string, prefix string) (string, error) {
	filename := strings.TrimPrefix(path, prefix)
	filename = strings.TrimSpace(filename)
	if decoded, err := url.PathUnescape(filename); err == nil {
		filename = decoded
	}
	if err := results.ValidateFilename(filename); err != nil {
		return "", err
	}
	return filename, nil
}

func splitResultPath(path string) (string, string, error) {
	trimmed := strings.TrimPrefix(path, "/api/results/")
	if decoded, err := url.PathUnescape(trimmed); err == nil {
		trimmed = decoded
	}
	for _, suffix := range []string{"/insights", "/export", "/blacklist-rules", "/reanalyze"} {
		if strings.HasSuffix(trimmed, suffix) {
			filename := strings.TrimSuffix(trimmed, suffix)
			if err := results.ValidateFilename(filename); err != nil {
				return "", "", err
			}
			return filename, suffix, nil
		}
	}
	if idx := strings.Index(trimmed, "/items/"); idx >= 0 && strings.HasSuffix(trimmed, "/status") {
		filename := trimmed[:idx]
		if err := results.ValidateFilename(filename); err != nil {
			return "", "", err
		}
		return filename, trimmed[idx:], nil
	}
	if err := results.ValidateFilename(trimmed); err != nil {
		return "", "", err
	}
	return trimmed, "", nil
}

func itemIDFromResultSuffix(suffix string) (string, error) {
	trimmed := strings.TrimPrefix(suffix, "/items/")
	trimmed = strings.TrimSuffix(trimmed, "/status")
	if decoded, err := url.PathUnescape(trimmed); err == nil {
		trimmed = decoded
	}
	if strings.TrimSpace(trimmed) == "" {
		return "", errors.New("empty item id")
	}
	return trimmed, nil
}

func buildDownloadDisposition(exportName string) string {
	asciiName := exportName
	for _, char := range exportName {
		if char > 127 {
			asciiName = "export.csv"
			break
		}
	}
	encoded := url.PathEscape(exportName)
	return `attachment; filename="` + asciiName + `"; filename*=UTF-8''` + encoded
}

func queryBool(values url.Values, key string) bool {
	raw := strings.TrimSpace(values.Get(key))
	return raw == "1" || strings.EqualFold(raw, "true")
}

func queryInt(values url.Values, key string, fallback int) int {
	raw := strings.TrimSpace(values.Get(key))
	if raw == "" {
		return fallback
	}
	parsed, err := strconv.Atoi(raw)
	if err != nil {
		return fallback
	}
	return parsed
}

func defaultString(value string, fallback string) string {
	if strings.TrimSpace(value) == "" {
		return fallback
	}
	return value
}

func writeResultError(w http.ResponseWriter, err error) {
	switch {
	case errors.Is(err, results.ErrInvalidFilename):
		writeError(w, http.StatusBadRequest, err.Error())
	case errors.Is(err, results.ErrFileNotFound):
		writeError(w, http.StatusNotFound, err.Error())
	default:
		writeError(w, http.StatusInternalServerError, err.Error())
	}
}
