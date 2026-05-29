package runtime

import (
	"context"
	"fmt"

	"github.com/life2you/fishRadar2/services/api-go/internal/tasks"
	"github.com/life2you/fishRadar2/services/api-go/internal/workerqueue"
)

type WorkerManager struct {
	taskService *tasks.Service
	queue       *workerqueue.Service
}

func NewWorkerManager(taskService *tasks.Service, queue *workerqueue.Service) *WorkerManager {
	return &WorkerManager{
		taskService: taskService,
		queue:       queue,
	}
}

func (m *WorkerManager) ResetState(ctx context.Context) error {
	if m.queue == nil {
		return nil
	}
	return m.queue.EnsureSchema(ctx)
}

func (m *WorkerManager) StartTask(ctx context.Context, taskID int64, requestedByUserID *int64) error {
	task, err := m.taskService.Get(ctx, taskID)
	if err != nil {
		return err
	}
	if !task.Enabled {
		return fmt.Errorf("任务已被禁用，无法启动")
	}
	if task.IsRunning {
		return fmt.Errorf("任务已在运行中")
	}
	return m.queue.EnqueueStartTask(ctx, taskID, requestedByUserID, "api-go")
}

func (m *WorkerManager) StopTask(ctx context.Context, taskID int64, requestedByUserID *int64) error {
	task, err := m.taskService.Get(ctx, taskID)
	if err != nil {
		return err
	}
	if !task.IsRunning {
		return fmt.Errorf("任务当前未在运行")
	}
	return m.queue.EnqueueStopTask(ctx, taskID, requestedByUserID, "api-go")
}
