package dashboard

import (
	"context"
	"database/sql"
)

type Summary struct {
	EnabledTasks            int     `json:"enabled_tasks"`
	RunningTasks            int     `json:"running_tasks"`
	ResultFiles             int     `json:"result_files"`
	ScannedItems            int     `json:"scanned_items"`
	RecommendedItems        int     `json:"recommended_items"`
	AIRecommendedItems      int     `json:"ai_recommended_items"`
	KeywordRecommendedItems int     `json:"keyword_recommended_items"`
	LastUpdatedAt           *string `json:"last_updated_at"`
}

type Snapshot struct {
	Summary          Summary `json:"summary"`
	TaskSummaries    []any   `json:"task_summaries"`
	RecentActivities []any   `json:"recent_activities"`
	FocusFile        *string `json:"focus_file"`
}

type Service struct {
	db *sql.DB
}

func NewService(db *sql.DB) *Service {
	return &Service{db: db}
}

func (s *Service) BuildSnapshot(ctx context.Context) (Snapshot, error) {
	summary := Summary{}
	if err := s.db.QueryRowContext(ctx, `
		SELECT
			COALESCE(SUM(CASE WHEN enabled = 1 THEN 1 ELSE 0 END), 0) AS enabled_tasks,
			COALESCE(SUM(CASE WHEN is_running = 1 THEN 1 ELSE 0 END), 0) AS running_tasks
		FROM tasks
	`).Scan(&summary.EnabledTasks, &summary.RunningTasks); err != nil {
		return Snapshot{}, err
	}

	if err := s.db.QueryRowContext(ctx, `
		SELECT
			COUNT(DISTINCT result_filename) AS result_files,
			COUNT(1) AS scanned_items,
			COALESCE(SUM(CASE WHEN is_recommended = 1 THEN 1 ELSE 0 END), 0) AS recommended_items,
			COALESCE(SUM(CASE WHEN is_recommended = 1 AND analysis_source = 'ai' THEN 1 ELSE 0 END), 0) AS ai_recommended_items,
			COALESCE(SUM(CASE WHEN is_recommended = 1 AND analysis_source = 'keyword' THEN 1 ELSE 0 END), 0) AS keyword_recommended_items,
			MAX(crawl_time) AS last_updated_at
		FROM result_items
	`).Scan(
		&summary.ResultFiles,
		&summary.ScannedItems,
		&summary.RecommendedItems,
		&summary.AIRecommendedItems,
		&summary.KeywordRecommendedItems,
		&summary.LastUpdatedAt,
	); err != nil {
		return Snapshot{}, err
	}

	var focusFile *string
	var nullableFocus sql.NullString
	if err := s.db.QueryRowContext(ctx, `
		SELECT result_filename
		FROM result_items
		WHERE result_filename IS NOT NULL AND result_filename != ''
		ORDER BY crawl_time DESC, id DESC
		LIMIT 1
	`).Scan(&nullableFocus); err == nil && nullableFocus.Valid {
		focusFile = &nullableFocus.String
	}

	return Snapshot{
		Summary:          summary,
		TaskSummaries:    []any{},
		RecentActivities: []any{},
		FocusFile:        focusFile,
	}, nil
}
