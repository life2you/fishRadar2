package logs

import (
	"context"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"

	"github.com/life2you/fishRadar2/services/api-go/internal/tasks"
)

type Service struct {
	taskService *tasks.Service
}

func NewService(taskService *tasks.Service) *Service {
	return &Service{taskService: taskService}
}

func (s *Service) ReadIncremental(ctx context.Context, taskID int64, fromPos int64) (string, int64, error) {
	task, path, err := s.resolveTaskPath(ctx, taskID)
	if err != nil {
		return "", 0, err
	}
	_ = task
	file, err := os.Open(path)
	if err != nil {
		if os.IsNotExist(err) {
			return "", 0, nil
		}
		return "", 0, err
	}
	defer file.Close()
	info, err := file.Stat()
	if err != nil {
		return "", 0, err
	}
	size := info.Size()
	if fromPos >= size {
		return "", size, nil
	}
	if _, err := file.Seek(fromPos, io.SeekStart); err != nil {
		return "", fromPos, err
	}
	content, err := io.ReadAll(file)
	if err != nil {
		return "", fromPos, err
	}
	return string(content), size, nil
}

func (s *Service) Tail(ctx context.Context, taskID int64, offsetLines int, limitLines int) (string, bool, int, int64, error) {
	_, path, err := s.resolveTaskPath(ctx, taskID)
	if err != nil {
		return "", false, 0, 0, err
	}
	content, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return "", false, 0, 0, nil
		}
		return "", false, 0, 0, err
	}
	text := strings.ReplaceAll(string(content), "\r\n", "\n")
	lines := strings.Split(text, "\n")
	if len(lines) > 0 && lines[len(lines)-1] == "" {
		lines = lines[:len(lines)-1]
	}
	if offsetLines < 0 {
		offsetLines = 0
	}
	if limitLines <= 0 {
		limitLines = 50
	}
	total := len(lines)
	end := total - offsetLines
	if end < 0 {
		end = 0
	}
	start := end - limitLines
	if start < 0 {
		start = 0
	}
	selected := lines[start:end]
	hasMore := start > 0
	nextOffset := offsetLines + len(selected)
	return strings.Join(selected, "\n"), hasMore, nextOffset, int64(len(content)), nil
}

func (s *Service) Clear(ctx context.Context, taskID int64) error {
	_, path, err := s.resolveTaskPath(ctx, taskID)
	if err != nil {
		return err
	}
	file, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0o644)
	if err != nil {
		return err
	}
	return file.Close()
}

func (s *Service) resolveTaskPath(ctx context.Context, taskID int64) (*tasks.Item, string, error) {
	task, err := s.taskService.Get(ctx, taskID)
	if err != nil {
		return nil, "", err
	}
	path := buildTaskLogPath(taskID, task.TaskName)
	if _, err := os.Stat(path); err == nil {
		return task, path, nil
	}
	matches, err := filepath.Glob(filepath.Join("logs", fmt.Sprintf("*_%d.log", taskID)))
	if err == nil && len(matches) > 0 {
		return task, matches[0], nil
	}
	return task, path, nil
}

func buildTaskLogPath(taskID int64, taskName string) string {
	return filepath.Join("logs", fmt.Sprintf("%s_%d.log", sanitizeFilename(taskName), taskID))
}

func sanitizeFilename(value string) string {
	cleaned := strings.TrimSpace(value)
	if cleaned == "" {
		return "task"
	}
	builder := strings.Builder{}
	lastUnderscore := false
	for _, char := range cleaned {
		valid := (char >= 'a' && char <= 'z') || (char >= 'A' && char <= 'Z') || (char >= '0' && char <= '9') || char == '_' || char == '-'
		if valid {
			builder.WriteRune(char)
			lastUnderscore = false
			continue
		}
		if !lastUnderscore {
			builder.WriteRune('_')
			lastUnderscore = true
		}
	}
	result := strings.Trim(builder.String(), "_")
	if result == "" {
		return "task"
	}
	return result
}
