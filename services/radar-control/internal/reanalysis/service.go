package reanalysis

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/life2you/fishRadar2/services/radar-control/internal/results"
	"github.com/life2you/fishRadar2/services/radar-control/internal/workerqueue"
)

type Service struct {
	queue *workerqueue.Service
}

func NewService(queue *workerqueue.Service) *Service {
	return &Service{queue: queue}
}

func (s *Service) Reanalyze(ctx context.Context, filename string, scope results.Scope, requestedByUserID *int64) (map[string]any, error) {
	jobID := uuid.NewString()
	var tenantScope *int64
	if scope.Kind == results.ScopeTenant {
		tenantScope = &scope.TenantID
	}
	if err := s.queue.EnqueueReanalyzeResult(ctx, jobID, filename, tenantScope, requestedByUserID, "radar-control"); err != nil {
		return nil, err
	}
	return s.waitForCompletion(ctx, jobID)
}

func (s *Service) waitForCompletion(ctx context.Context, jobID string) (map[string]any, error) {
	ticker := time.NewTicker(750 * time.Millisecond)
	defer ticker.Stop()

	for {
		job, err := s.queue.GetByJobKey(ctx, jobID)
		if err != nil {
			if err == sql.ErrNoRows {
				return nil, fmt.Errorf("重分析作业未找到")
			}
			return nil, err
		}
		switch job.Status {
		case "completed":
			if job.ResultJSON == nil || *job.ResultJSON == "" {
				return map[string]any{"message": "结果集已完成重新分析"}, nil
			}
			var payload map[string]any
			if err := json.Unmarshal([]byte(*job.ResultJSON), &payload); err != nil {
				return nil, err
			}
			return payload, nil
		case "failed":
			if job.ErrorMessage != nil && *job.ErrorMessage != "" {
				return nil, fmt.Errorf("%s", *job.ErrorMessage)
			}
			if job.Message != nil && *job.Message != "" {
				return nil, fmt.Errorf("%s", *job.Message)
			}
			return nil, fmt.Errorf("结果重分析失败")
		}

		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		case <-ticker.C:
		}
	}
}
