package realtime

import "context"

func PublishTasksUpdated(ctx context.Context, hub *Hub, tenantScope *int64) {
	publish(ctx, hub, "tasks_updated", map[string]any{"tenant_id": tenantScope}, tenantScope)
}

func PublishResultsUpdated(ctx context.Context, hub *Hub, tenantScope *int64, data map[string]any) {
	if data == nil {
		data = map[string]any{}
	}
	if _, ok := data["tenant_id"]; !ok && tenantScope != nil {
		data["tenant_id"] = *tenantScope
	}
	publish(ctx, hub, "results_updated", data, tenantScope)
}

func PublishTaskStatusChanged(ctx context.Context, hub *Hub, taskID int64, isRunning bool, tenantScope *int64) {
	publish(ctx, hub, "task_status_changed", map[string]any{
		"id":         taskID,
		"is_running": isRunning,
		"tenant_id":  tenantScope,
	}, tenantScope)
}

func publish(ctx context.Context, hub *Hub, eventType string, data any, tenantScope *int64) {
	if hub == nil {
		return
	}
	if err := hub.Publish(ctx, eventType, data, tenantScope); err != nil {
		// 实时事件只做增强体验，不影响主流程。
	}
}
