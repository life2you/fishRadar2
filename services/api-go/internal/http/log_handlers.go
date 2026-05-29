package httpapi

import (
	"database/sql"
	"net/http"
	"strconv"

	"github.com/life2you/fishRadar2/services/api-go/internal/logs"
)

func handleLogs(service *logs.Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if requireAdminUser(w, r) == nil {
			return
		}
		taskID, ok := queryInt64(r, "task_id")
		switch r.Method {
		case http.MethodGet:
			if !ok {
				writeJSON(w, http.StatusOK, map[string]any{"new_content": "请选择任务后查看日志。", "new_pos": 0})
				return
			}
			fromPos := queryInt64Or(r, "from_pos", 0)
			content, newPos, err := service.ReadIncremental(r.Context(), taskID, fromPos)
			if err != nil {
				if err == sql.ErrNoRows {
					writeJSON(w, http.StatusNotFound, map[string]any{"new_content": "任务不存在或已删除。", "new_pos": 0})
					return
				}
				writeJSON(w, http.StatusInternalServerError, map[string]any{"new_content": "\n读取日志文件时出错: " + err.Error(), "new_pos": fromPos})
				return
			}
			writeJSON(w, http.StatusOK, map[string]any{"new_content": content, "new_pos": newPos})
		case http.MethodDelete:
			if !ok {
				writeJSON(w, http.StatusOK, map[string]any{"message": "未指定任务，无法清空日志。"})
				return
			}
			if err := service.Clear(r.Context(), taskID); err != nil {
				if err == sql.ErrNoRows {
					writeJSON(w, http.StatusOK, map[string]any{"message": "任务不存在或已删除。"})
					return
				}
				writeJSON(w, http.StatusInternalServerError, map[string]any{"message": "清空日志文件时出错: " + err.Error()})
				return
			}
			writeJSON(w, http.StatusOK, map[string]any{"message": "日志已成功清空。"})
		default:
			writeError(w, http.StatusMethodNotAllowed, "方法不支持")
		}
	}
}

func handleLogTail(service *logs.Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if requireAdminUser(w, r) == nil {
			return
		}
		taskID, ok := queryInt64(r, "task_id")
		if !ok {
			writeJSON(w, http.StatusOK, map[string]any{"content": "", "has_more": false, "next_offset": 0, "new_pos": 0})
			return
		}
		offsetLines := int(queryInt64Or(r, "offset_lines", 0))
		limitLines := int(queryInt64Or(r, "limit_lines", 50))
		content, hasMore, nextOffset, newPos, err := service.Tail(r.Context(), taskID, offsetLines, limitLines)
		if err != nil {
			if err == sql.ErrNoRows {
				writeJSON(w, http.StatusNotFound, map[string]any{"content": "", "has_more": false, "next_offset": 0, "new_pos": 0})
				return
			}
			writeJSON(w, http.StatusInternalServerError, map[string]any{"content": "读取日志文件时出错: " + err.Error(), "has_more": false, "next_offset": offsetLines, "new_pos": 0})
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"content": content, "has_more": hasMore, "next_offset": nextOffset, "new_pos": newPos})
	}
}

func queryInt64(r *http.Request, key string) (int64, bool) {
	raw := r.URL.Query().Get(key)
	if raw == "" {
		return 0, false
	}
	value, err := strconv.ParseInt(raw, 10, 64)
	if err != nil {
		return 0, false
	}
	return value, true
}

func queryInt64Or(r *http.Request, key string, fallback int64) int64 {
	value, ok := queryInt64(r, key)
	if !ok {
		return fallback
	}
	return value
}
