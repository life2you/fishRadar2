package results

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/csv"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"regexp"
	"slices"
	"strconv"
	"strings"
	"time"
)

const (
	ResultFileSuffix = "_full_data.jsonl"
)

var (
	ErrInvalidFilename = errors.New("无效的文件名")
	ErrFileNotFound    = errors.New("结果文件未找到")

	asciiTokenKeywordPattern = regexp.MustCompile(`^[a-z0-9 ]+$`)
	keywordSplitPattern      = regexp.MustCompile(`[\n,，]+`)
)

type ScopeKind int

const (
	ScopeGlobal ScopeKind = iota
	ScopeTenant
)

type Scope struct {
	Kind     ScopeKind
	TenantID int64
}

func GlobalScope() Scope {
	return Scope{Kind: ScopeGlobal}
}

func TenantScope(tenantID int64) Scope {
	return Scope{Kind: ScopeTenant, TenantID: tenantID}
}

type Service struct {
	db *sql.DB
}

func NewService(db *sql.DB) *Service {
	return &Service{db: db}
}

type ContentQuery struct {
	Filename               string
	AIRecommendedOnly      bool
	KeywordRecommendedOnly bool
	SortBy                 string
	SortOrder              string
	Page                   int
	Limit                  int
	IncludeHidden          bool
	Scope                  Scope
}

type ContentResult struct {
	TotalItems int              `json:"total_items"`
	Page       int              `json:"page"`
	Limit      int              `json:"limit"`
	Items      []map[string]any `json:"items"`
}

func (s *Service) ListFiles(ctx context.Context, scope Scope) ([]string, error) {
	query := `
SELECT result_filename, MAX(crawl_time) AS latest_crawl_time
FROM result_items
`
	whereClause, args := scopeWhereClause(scope, "WHERE ")
	query += whereClause + `
GROUP BY result_filename
ORDER BY latest_crawl_time DESC, result_filename DESC
`
	rows, err := s.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	files := make([]string, 0)
	for rows.Next() {
		var resultFilename string
		var latestCrawlTime sql.NullString
		if err := rows.Scan(&resultFilename, &latestCrawlTime); err != nil {
			return nil, err
		}
		files = append(files, visibleResultFilename(resultFilename, scope))
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return files, nil
}

func (s *Service) DownloadNDJSON(ctx context.Context, filename string, scope Scope) (string, error) {
	if err := ValidateFilename(filename); err != nil {
		return "", err
	}
	query := `
SELECT raw_json
FROM result_items
WHERE result_filename = ?
`
	args := []any{scopedResultFilename(filename, scope)}
	whereClause, whereArgs := scopeWhereClause(scope, "AND ")
	query += whereClause + `
ORDER BY id ASC
`
	args = append(args, whereArgs...)
	rows, err := s.db.QueryContext(ctx, query, args...)
	if err != nil {
		return "", err
	}
	defer rows.Close()

	lines := make([]string, 0)
	for rows.Next() {
		var raw string
		if err := rows.Scan(&raw); err != nil {
			return "", err
		}
		lines = append(lines, raw)
	}
	if err := rows.Err(); err != nil {
		return "", err
	}
	if len(lines) == 0 {
		exists, err := s.FileExists(ctx, filename, scope)
		if err != nil {
			return "", err
		}
		if !exists {
			return "", ErrFileNotFound
		}
	}
	return strings.Join(lines, "\n"), nil
}

func (s *Service) DeleteFile(ctx context.Context, filename string, scope Scope) (int64, error) {
	if err := ValidateFilename(filename); err != nil {
		return 0, err
	}
	query := `
DELETE FROM result_items
WHERE result_filename = ?
`
	args := []any{scopedResultFilename(filename, scope)}
	whereClause, whereArgs := scopeWhereClause(scope, "AND ")
	query += whereClause
	args = append(args, whereArgs...)
	result, err := s.db.ExecContext(ctx, query, args...)
	if err != nil {
		return 0, err
	}
	affected, err := result.RowsAffected()
	if err != nil {
		return 0, err
	}
	return affected, nil
}

func (s *Service) FileExists(ctx context.Context, filename string, scope Scope) (bool, error) {
	if err := ValidateFilename(filename); err != nil {
		return false, err
	}
	query := `
SELECT 1
FROM result_items
WHERE result_filename = ?
`
	args := []any{scopedResultFilename(filename, scope)}
	whereClause, whereArgs := scopeWhereClause(scope, "AND ")
	query += whereClause + " LIMIT 1"
	args = append(args, whereArgs...)
	var marker int
	err := s.db.QueryRowContext(ctx, query, args...).Scan(&marker)
	if err == nil {
		return true, nil
	}
	if errors.Is(err, sql.ErrNoRows) {
		return false, nil
	}
	return false, err
}

func (s *Service) QueryContent(ctx context.Context, input ContentQuery) (*ContentResult, error) {
	if err := ValidateFilename(input.Filename); err != nil {
		return nil, err
	}
	if input.AIRecommendedOnly && input.KeywordRecommendedOnly {
		return nil, fmt.Errorf("AI推荐筛选与关键词推荐筛选不能同时开启")
	}
	if input.Page <= 0 {
		input.Page = 1
	}
	if input.Limit <= 0 {
		input.Limit = 20
	}
	records, err := s.loadFilteredRecords(ctx, input.Filename, input.Scope, input.AIRecommendedOnly, input.KeywordRecommendedOnly, input.SortBy, input.SortOrder, input.IncludeHidden)
	if err != nil {
		return nil, err
	}
	total := len(records)
	start := (input.Page - 1) * input.Limit
	if start >= total {
		start = total
	}
	end := start + input.Limit
	if end > total {
		end = total
	}
	pageItems := records[start:end]
	enriched, err := s.enrichRecordsWithPriceInsight(ctx, pageItems, input.Filename, input.Scope)
	if err != nil {
		return nil, err
	}
	if total == 0 {
		exists, err := s.FileExists(ctx, input.Filename, input.Scope)
		if err != nil {
			return nil, err
		}
		if !exists {
			return nil, ErrFileNotFound
		}
	}
	return &ContentResult{
		TotalItems: total,
		Page:       input.Page,
		Limit:      input.Limit,
		Items:      enriched,
	}, nil
}

func (s *Service) GetInsights(ctx context.Context, filename string, scope Scope) (map[string]any, error) {
	if err := ValidateFilename(filename); err != nil {
		return nil, err
	}
	visibleItemIDs, err := s.loadVisibleItemIDs(ctx, filename, scope)
	if err != nil {
		return nil, err
	}
	return s.buildPriceHistoryInsights(ctx, normalizeKeywordFromFilename(filename), visibleItemIDs, scope)
}

func (s *Service) ExportCSV(ctx context.Context, input ContentQuery) (string, error) {
	if err := ValidateFilename(input.Filename); err != nil {
		return "", err
	}
	records, err := s.loadFilteredRecords(ctx, input.Filename, input.Scope, input.AIRecommendedOnly, input.KeywordRecommendedOnly, input.SortBy, input.SortOrder, input.IncludeHidden)
	if err != nil {
		return "", err
	}
	if len(records) == 0 {
		exists, err := s.FileExists(ctx, input.Filename, input.Scope)
		if err != nil {
			return "", err
		}
		if !exists {
			return "", ErrFileNotFound
		}
	}
	enriched, err := s.enrichRecordsWithPriceInsight(ctx, records, input.Filename, input.Scope)
	if err != nil {
		return "", err
	}
	return buildResultsCSV(enriched), nil
}

func (s *Service) GetBlacklistKeywords(ctx context.Context, filename string, scope Scope) ([]string, error) {
	if err := ValidateFilename(filename); err != nil {
		return nil, err
	}
	return s.loadBlacklistKeywords(ctx, filename, scope)
}

func (s *Service) SaveBlacklistKeywords(ctx context.Context, filename string, scope Scope, keywords []string) ([]string, error) {
	if err := ValidateFilename(filename); err != nil {
		return nil, err
	}
	normalized := normalizeBlacklistKeywords(keywords)
	payload, err := json.Marshal(normalized)
	if err != nil {
		return nil, err
	}
	now := time.Now().Format(time.RFC3339)
	_, err = s.db.ExecContext(ctx, `
INSERT INTO result_blacklist_rules (result_filename, blacklist_keywords_json, updated_at)
VALUES (?, ?, ?)
ON DUPLICATE KEY UPDATE
  blacklist_keywords_json = VALUES(blacklist_keywords_json),
  updated_at = VALUES(updated_at)
`, blacklistScopeKey(filename, scope), string(payload), now)
	if err != nil {
		return nil, err
	}
	return normalized, nil
}

func (s *Service) UpdateItemStatus(ctx context.Context, filename string, itemID string, status string, scope Scope) (bool, error) {
	if err := ValidateFilename(filename); err != nil {
		return false, err
	}
	switch status {
	case "active", "hidden", "expired":
	default:
		return false, fmt.Errorf("status must be one of {active, hidden, expired}")
	}
	query := `
UPDATE result_items
SET status = ?
WHERE result_filename = ? AND item_id = ?
`
	args := []any{status, scopedResultFilename(filename, scope), itemID}
	whereClause, whereArgs := scopeWhereClause(scope, "AND ")
	query += whereClause
	args = append(args, whereArgs...)
	result, err := s.db.ExecContext(ctx, query, args...)
	if err != nil {
		return false, err
	}
	affected, err := result.RowsAffected()
	if err != nil {
		return false, err
	}
	return affected > 0, nil
}

func ValidateFilename(filename string) error {
	if !strings.HasSuffix(filename, ".jsonl") || strings.Contains(filename, "/") || strings.Contains(filename, "..") {
		return ErrInvalidFilename
	}
	return nil
}

func (s *Service) loadFilteredRecords(ctx context.Context, filename string, scope Scope, aiRecommendedOnly bool, keywordRecommendedOnly bool, sortBy string, sortOrder string, includeHidden bool) ([]map[string]any, error) {
	whereClause, args := buildResultWhereClause(filename, scope, aiRecommendedOnly, keywordRecommendedOnly)
	query := `
SELECT raw_json, status
FROM result_items
WHERE ` + whereClause + `
ORDER BY ` + sortExpression(sortBy, sortOrder)

	rows, err := s.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	blacklistKeywords, err := s.loadBlacklistKeywords(ctx, filename, scope)
	if err != nil {
		return nil, err
	}

	records := make([]map[string]any, 0)
	for rows.Next() {
		var rawJSON string
		var status string
		if err := rows.Scan(&rawJSON, &status); err != nil {
			return nil, err
		}
		record, err := parseRawRecord(rawJSON)
		if err != nil {
			return nil, err
		}
		decorated := decorateRecordVisibility(record, status, blacklistKeywords)
		if includeHidden || isRecordVisible(decorated) {
			records = append(records, decorated)
		}
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return records, nil
}

func buildResultWhereClause(filename string, scope Scope, aiRecommendedOnly bool, keywordRecommendedOnly bool) (string, []any) {
	conditions := []string{"result_filename = ?"}
	args := []any{scopedResultFilename(filename, scope)}
	conditions, args = appendScopeFilter(conditions, args, scope)
	if aiRecommendedOnly {
		conditions = append(conditions, "is_recommended = 1", "analysis_source = ?")
		args = append(args, "ai")
	}
	if keywordRecommendedOnly {
		conditions = append(conditions, "is_recommended = 1", "analysis_source = ?")
		args = append(args, "keyword")
	}
	return strings.Join(conditions, " AND "), args
}

func sortExpression(sortBy string, sortOrder string) string {
	column := map[string]string{
		"crawl_time":        "crawl_time",
		"publish_time":      "COALESCE(publish_time, '')",
		"price":             "COALESCE(price, 0)",
		"keyword_hit_count": "keyword_hit_count",
	}[sortBy]
	if column == "" {
		column = "crawl_time"
	}
	direction := "DESC"
	if strings.EqualFold(sortOrder, "asc") {
		direction = "ASC"
	}
	return fmt.Sprintf("(CASE WHEN status = 'active' THEN 0 ELSE 1 END), %s %s, id %s", column, direction, direction)
}

func parseRawRecord(rawJSON string) (map[string]any, error) {
	record := make(map[string]any)
	if err := json.Unmarshal([]byte(rawJSON), &record); err != nil {
		return nil, err
	}
	return record, nil
}

func decorateRecordVisibility(record map[string]any, status string, blacklistKeywords []string) map[string]any {
	matched := matchBlacklistKeywords(record, blacklistKeywords)
	hiddenReason := any(nil)
	switch {
	case status == "expired":
		hiddenReason = "expired"
	case status != "" && status != "active":
		hiddenReason = "manual"
	case len(matched) > 0:
		hiddenReason = "rule"
	}
	record["_status"] = statusOrDefault(status, "active")
	record["_matched_blacklist_keywords"] = matched
	record["_hidden_reason"] = hiddenReason
	record["_effective_hidden"] = hiddenReason != nil
	return record
}

func isRecordVisible(record map[string]any) bool {
	value, ok := record["_effective_hidden"].(bool)
	return !ok || !value
}

func (s *Service) loadBlacklistKeywords(ctx context.Context, filename string, scope Scope) ([]string, error) {
	var payload string
	err := s.db.QueryRowContext(ctx, `
SELECT blacklist_keywords_json
FROM result_blacklist_rules
WHERE result_filename = ?
LIMIT 1
`, blacklistScopeKey(filename, scope)).Scan(&payload)
	if err == nil {
		var values []string
		if jsonErr := json.Unmarshal([]byte(payload), &values); jsonErr == nil {
			return normalizeBlacklistKeywords(values), nil
		}
		return []string{}, nil
	}
	if errors.Is(err, sql.ErrNoRows) {
		return []string{}, nil
	}
	return nil, err
}

func normalizeBlacklistKeywords(values []string) []string {
	normalized := make([]string, 0)
	seen := make(map[string]struct{})
	for _, raw := range values {
		parts := keywordSplitPattern.Split(strings.TrimSpace(raw), -1)
		for _, part := range parts {
			sourceText := strings.TrimSpace(part)
			if sourceText == "" {
				continue
			}
			text := strings.ToLower(strings.TrimSpace(sourceText))
			if strings.HasPrefix(text, "re:") {
				pattern := strings.TrimSpace(sourceText[len("re:"):])
				if pattern == "" {
					continue
				}
				text = "re:" + pattern
			} else {
				text = normalizeText(sourceText)
			}
			if text == "" {
				continue
			}
			if _, exists := seen[text]; exists {
				continue
			}
			seen[text] = struct{}{}
			normalized = append(normalized, text)
		}
	}
	return normalized
}

func matchBlacklistKeywords(record map[string]any, keywords []string) []string {
	normalizedKeywords := normalizeBlacklistKeywords(keywords)
	if len(normalizedKeywords) == 0 {
		return []string{}
	}
	searchText := normalizeText(buildSearchText(record))
	if searchText == "" {
		return []string{}
	}
	matched := make([]string, 0)
	for _, keyword := range normalizedKeywords {
		if keywordMatches(keyword, searchText) {
			matched = append(matched, keyword)
		}
	}
	return matched
}

func normalizeText(value string) string {
	return strings.Join(strings.Fields(strings.ToLower(value)), " ")
}

func buildSearchText(record map[string]any) string {
	fragments := make([]string, 0)
	collectTextFragments(productInfo(record)["商品标题"], &fragments)
	collectTextFragments(productInfo(record), &fragments)
	collectTextFragments(sellerInfo(record), &fragments)
	return normalizeText(strings.Join(fragments, " "))
}

func collectTextFragments(value any, bucket *[]string) {
	switch typed := value.(type) {
	case nil:
		return
	case string:
		text := strings.TrimSpace(typed)
		if text != "" {
			*bucket = append(*bucket, text)
		}
	case bool, int, int64, float64, float32:
		*bucket = append(*bucket, fmt.Sprintf("%v", typed))
	case map[string]any:
		for _, item := range typed {
			collectTextFragments(item, bucket)
		}
	case []any:
		for _, item := range typed {
			collectTextFragments(item, bucket)
		}
	}
}

func keywordMatches(keyword string, normalizedText string) bool {
	lowered := strings.ToLower(keyword)
	if strings.HasPrefix(lowered, "re:") {
		pattern := keyword[len("re:"):]
		re, err := regexp.Compile("(?i)" + pattern)
		if err != nil {
			return false
		}
		return re.MatchString(normalizedText)
	}
	if !asciiTokenKeywordPattern.MatchString(keyword) {
		return strings.Contains(normalizedText, keyword)
	}
	pattern := regexp.MustCompile(`(^|[^a-z0-9])` + regexp.QuoteMeta(keyword) + `([^a-z0-9]|$)`)
	return pattern.MatchString(normalizedText)
}

func (s *Service) enrichRecordsWithPriceInsight(ctx context.Context, records []map[string]any, filename string, scope Scope) ([]map[string]any, error) {
	snapshots, err := s.loadPriceSnapshots(ctx, normalizeKeywordFromFilename(filename), scope)
	if err != nil {
		return nil, err
	}
	if len(snapshots) == 0 {
		return records, nil
	}
	visibleItemIDs, err := s.loadVisibleItemIDs(ctx, filename, scope)
	if err != nil {
		return nil, err
	}
	visibleSnapshots := make([]snapshotRecord, 0)
	for _, snapshot := range snapshots {
		if _, ok := visibleItemIDs[snapshot.ItemID]; ok {
			visibleSnapshots = append(visibleSnapshots, snapshot)
		}
	}
	enriched := make([]map[string]any, 0, len(records))
	for _, record := range records {
		clone := shallowCloneMap(record)
		product := productInfo(record)
		itemID := strings.TrimSpace(asString(product["商品ID"]))
		clone["price_insight"] = buildItemPriceContext(snapshots, itemID, parsePriceValue(product["当前售价"]), visibleSnapshots)
		enriched = append(enriched, clone)
	}
	return enriched, nil
}

func (s *Service) loadVisibleItemIDs(ctx context.Context, filename string, scope Scope) (map[string]struct{}, error) {
	records, err := s.loadFilteredRecords(ctx, filename, scope, false, false, "crawl_time", "desc", false)
	if err != nil {
		return nil, err
	}
	itemIDs := make(map[string]struct{})
	for _, record := range records {
		itemID := strings.TrimSpace(asString(productInfo(record)["商品ID"]))
		if itemID != "" {
			itemIDs[itemID] = struct{}{}
		}
	}
	return itemIDs, nil
}

type snapshotRecord struct {
	SnapshotTime string
	SnapshotDay  string
	RunID        string
	ItemID       string
	Price        float64
}

func (s *Service) loadPriceSnapshots(ctx context.Context, keyword string, scope Scope) ([]snapshotRecord, error) {
	query := `
SELECT snapshot_time, snapshot_day, run_id, item_id, price
FROM price_snapshots
WHERE keyword_slug = ?
`
	args := []any{scopedKeywordSlug(keyword, scope)}
	whereClause, whereArgs := scopeWhereClause(scope, "AND ")
	query += whereClause + `
ORDER BY snapshot_time ASC, id ASC
`
	args = append(args, whereArgs...)
	rows, err := s.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	snapshots := make([]snapshotRecord, 0)
	for rows.Next() {
		var record snapshotRecord
		if err := rows.Scan(&record.SnapshotTime, &record.SnapshotDay, &record.RunID, &record.ItemID, &record.Price); err != nil {
			return nil, err
		}
		snapshots = append(snapshots, record)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return snapshots, nil
}

func (s *Service) buildPriceHistoryInsights(ctx context.Context, keyword string, visibleItemIDs map[string]struct{}, scope Scope) (map[string]any, error) {
	snapshots, err := s.loadPriceSnapshots(ctx, keyword, scope)
	if err != nil {
		return nil, err
	}
	filtered := make([]snapshotRecord, 0)
	for _, snapshot := range snapshots {
		if _, ok := visibleItemIDs[snapshot.ItemID]; ok {
			filtered = append(filtered, snapshot)
		}
	}
	if len(filtered) == 0 {
		return map[string]any{
			"market_summary": map[string]any{
				"sample_count":  0,
				"avg_price":     nil,
				"median_price":  nil,
				"min_price":     nil,
				"max_price":     nil,
				"snapshot_time": nil,
			},
			"history_summary": map[string]any{
				"unique_items": 0,
				"sample_count": 0,
				"avg_price":    nil,
				"median_price": nil,
				"min_price":    nil,
				"max_price":    nil,
			},
			"daily_trend":        []map[string]any{},
			"latest_snapshot_at": nil,
		}, nil
	}
	recentSnapshots := recentWindowSnapshots(filtered, 30)
	latestRunID := filtered[len(filtered)-1].RunID
	latestRunSnapshots := dedupeLatestSnapshots(filterSnapshotsByRunID(filtered, latestRunID))
	latestRecordsByItem := dedupeLatestSnapshots(recentSnapshots)
	return map[string]any{
		"market_summary":     withSnapshotTime(summarizePrices(latestRunSnapshots), filtered[len(filtered)-1].SnapshotTime),
		"history_summary":    withUniqueItems(summarizePrices(latestRecordsByItem), len(latestRecordsByItem)),
		"daily_trend":        buildDailyTrend(recentSnapshots),
		"latest_snapshot_at": filtered[len(filtered)-1].SnapshotTime,
	}, nil
}

func withSnapshotTime(summary map[string]any, snapshotTime string) map[string]any {
	clone := shallowCloneMap(summary)
	clone["snapshot_time"] = snapshotTime
	return clone
}

func withUniqueItems(summary map[string]any, uniqueItems int) map[string]any {
	clone := shallowCloneMap(summary)
	clone["unique_items"] = uniqueItems
	return clone
}

func buildDailyTrend(snapshots []snapshotRecord) []map[string]any {
	grouped := make(map[string][]snapshotRecord)
	for _, snapshot := range snapshots {
		grouped[snapshot.SnapshotDay] = append(grouped[snapshot.SnapshotDay], snapshot)
	}
	days := make([]string, 0, len(grouped))
	for day := range grouped {
		days = append(days, day)
	}
	slices.Sort(days)
	points := make([]map[string]any, 0, len(days))
	for _, day := range days {
		summary := summarizePrices(dedupeLatestSnapshots(grouped[day]))
		summary["day"] = day
		points = append(points, summary)
	}
	return points
}

func recentWindowSnapshots(snapshots []snapshotRecord, windowDays int) []snapshotRecord {
	if len(snapshots) == 0 {
		return []snapshotRecord{}
	}
	latestTime := parseTimestamp(snapshots[len(snapshots)-1].SnapshotTime)
	filtered := make([]snapshotRecord, 0)
	for _, snapshot := range snapshots {
		current := parseTimestamp(snapshot.SnapshotTime)
		if latestTime.IsZero() || current.IsZero() || int(latestTime.Sub(current).Hours()/24) <= max(windowDays, 0) {
			filtered = append(filtered, snapshot)
		}
	}
	return filtered
}

func filterSnapshotsByRunID(snapshots []snapshotRecord, runID string) []snapshotRecord {
	filtered := make([]snapshotRecord, 0)
	for _, snapshot := range snapshots {
		if snapshot.RunID == runID {
			filtered = append(filtered, snapshot)
		}
	}
	return filtered
}

func dedupeLatestSnapshots(snapshots []snapshotRecord) []snapshotRecord {
	latest := make(map[string]snapshotRecord)
	for _, snapshot := range snapshots {
		latest[snapshot.ItemID] = snapshot
	}
	deduped := make([]snapshotRecord, 0, len(latest))
	for _, snapshot := range latest {
		deduped = append(deduped, snapshot)
	}
	return deduped
}

func summarizePrices(snapshots []snapshotRecord) map[string]any {
	prices := make([]float64, 0)
	for _, snapshot := range snapshots {
		prices = append(prices, snapshot.Price)
	}
	if len(prices) == 0 {
		return map[string]any{
			"sample_count": 0,
			"avg_price":    nil,
			"median_price": nil,
			"min_price":    nil,
			"max_price":    nil,
		}
	}
	slices.Sort(prices)
	sum := 0.0
	for _, price := range prices {
		sum += price
	}
	medianValue := prices[len(prices)/2]
	if len(prices)%2 == 0 {
		medianValue = (prices[len(prices)/2-1] + prices[len(prices)/2]) / 2
	}
	return map[string]any{
		"sample_count": len(prices),
		"avg_price":    round2(sum / float64(len(prices))),
		"median_price": round2(medianValue),
		"min_price":    round2(prices[0]),
		"max_price":    round2(prices[len(prices)-1]),
	}
}

func buildItemPriceContext(snapshots []snapshotRecord, itemID string, currentPrice *float64, marketSnapshots []snapshotRecord) map[string]any {
	if strings.TrimSpace(itemID) == "" {
		return map[string]any{"observation_count": 0, "deal_score": nil, "deal_label": "暂无数据"}
	}
	itemSnapshots := make([]snapshotRecord, 0)
	for _, snapshot := range snapshots {
		if snapshot.ItemID == itemID {
			itemSnapshots = append(itemSnapshots, snapshot)
		}
	}
	if len(itemSnapshots) == 0 {
		return map[string]any{"observation_count": 0, "deal_score": nil, "deal_label": "暂无数据"}
	}
	latestItemSnapshot := itemSnapshots[len(itemSnapshots)-1]
	priceNow := currentPrice
	if priceNow == nil {
		priceCopy := latestItemSnapshot.Price
		priceNow = &priceCopy
	}
	historicalPrices := make([]float64, 0, len(itemSnapshots))
	for _, snapshot := range itemSnapshots {
		historicalPrices = append(historicalPrices, snapshot.Price)
	}
	sourceSnapshots := marketSnapshots
	if len(sourceSnapshots) == 0 {
		sourceSnapshots = snapshots
	}
	latestRunID := ""
	if len(sourceSnapshots) > 0 {
		latestRunID = sourceSnapshots[len(sourceSnapshots)-1].RunID
	}
	latestMarket := dedupeLatestSnapshots(filterSnapshotsByRunID(sourceSnapshots, latestRunID))
	marketSummary := summarizePrices(latestMarket)
	marketAvg, _ := marketSummary["avg_price"].(float64)
	marketMedian, _ := marketSummary["median_price"].(float64)
	score := 50
	if priceNow != nil && marketAvg > 0 {
		score += int(((marketAvg - *priceNow) / marketAvg) * 60)
	}
	if priceNow != nil && len(historicalPrices) > 0 {
		maxHistorical := maxFloat(historicalPrices)
		if maxHistorical > 0 {
			score += int(((maxHistorical - *priceNow) / maxHistorical) * 20)
		}
		if nearlyEqual(*priceNow, minFloat(historicalPrices)) {
			score += 8
		}
	}
	if score < 0 {
		score = 0
	}
	if score > 100 {
		score = 100
	}
	var changeAmount any
	var changePercent any
	if len(historicalPrices) >= 2 && priceNow != nil {
		previous := historicalPrices[len(historicalPrices)-2]
		change := round2(*priceNow - previous)
		changeAmount = change
		if previous != 0 {
			changePercent = round2(change / previous * 100)
		}
	}
	sum := 0.0
	for _, price := range historicalPrices {
		sum += price
	}
	sortedPrices := slices.Clone(historicalPrices)
	slices.Sort(sortedPrices)
	medianValue := sortedPrices[len(sortedPrices)/2]
	if len(sortedPrices)%2 == 0 {
		medianValue = (sortedPrices[len(sortedPrices)/2-1] + sortedPrices[len(sortedPrices)/2]) / 2
	}
	return map[string]any{
		"observation_count":    len(historicalPrices),
		"current_price":        derefFloat(priceNow),
		"avg_price":            round2(sum / float64(len(historicalPrices))),
		"median_price":         round2(medianValue),
		"min_price":            round2(sortedPrices[0]),
		"max_price":            round2(sortedPrices[len(sortedPrices)-1]),
		"first_seen_at":        itemSnapshots[0].SnapshotTime,
		"last_seen_at":         latestItemSnapshot.SnapshotTime,
		"market_avg_price":     nullableFloatFromZero(marketAvg, marketSummary["avg_price"]),
		"market_median_price":  nullableFloatFromZero(marketMedian, marketSummary["median_price"]),
		"price_change_amount":  changeAmount,
		"price_change_percent": changePercent,
		"deal_score":           score,
		"deal_label":           resolveDealLabel(score),
	}
}

func buildResultsCSV(records []map[string]any) string {
	headers := []string{
		"任务名称", "搜索关键字", "商品ID", "商品标题", "当前售价", "发布时间", "卖家昵称", "AI是否推荐",
		"分析来源", "原因", "价格观察次数", "价格最低值", "价格最高值", "市场均价", "性价比分数", "性价比标签", "商品链接",
	}
	buffer := &bytes.Buffer{}
	writer := csv.NewWriter(buffer)
	_ = writer.Write(headers)
	for _, record := range records {
		item := productInfo(record)
		seller := sellerInfo(record)
		analysis := analysisInfo(record)
		priceInsight, _ := record["price_insight"].(map[string]any)
		row := []string{
			asString(record["任务名称"]),
			asString(record["搜索关键字"]),
			asString(item["商品ID"]),
			asString(item["商品标题"]),
			asString(item["当前售价"]),
			asString(item["发布时间"]),
			firstNonEmpty(asString(seller["卖家昵称"]), asString(item["卖家昵称"])),
			boolLabel(asBool(analysis["is_recommended"])),
			asString(analysis["analysis_source"]),
			asString(analysis["reason"]),
			asString(priceInsight["observation_count"]),
			asString(priceInsight["min_price"]),
			asString(priceInsight["max_price"]),
			asString(priceInsight["market_avg_price"]),
			asString(firstNonNil(analysis["value_score"], priceInsight["deal_score"])),
			asString(firstNonNil(analysis["value_summary"], priceInsight["deal_label"])),
			asString(item["商品链接"]),
		}
		_ = writer.Write(row)
	}
	writer.Flush()
	return buffer.String()
}

func scopeWhereClause(scope Scope, prefix string) (string, []any) {
	switch scope.Kind {
	case ScopeTenant:
		return prefix + "tenant_id = ?", []any{scope.TenantID}
	default:
		return prefix + "tenant_id IS NULL", nil
	}
}

func appendScopeFilter(conditions []string, args []any, scope Scope) ([]string, []any) {
	switch scope.Kind {
	case ScopeTenant:
		return append(conditions, "tenant_id = ?"), append(args, scope.TenantID)
	default:
		return append(conditions, "tenant_id IS NULL"), args
	}
}

func blacklistScopeKey(filename string, scope Scope) string {
	switch scope.Kind {
	case ScopeTenant:
		return fmt.Sprintf("tenant:%d:%s", scope.TenantID, filename)
	default:
		return "global:" + filename
	}
}

func scopedResultFilename(filename string, scope Scope) string {
	switch scope.Kind {
	case ScopeTenant:
		return fmt.Sprintf("tenant:%d:%s", scope.TenantID, filename)
	default:
		return filename
	}
}

func visibleResultFilename(storedFilename string, scope Scope) string {
	if scope.Kind != ScopeTenant {
		return storedFilename
	}
	prefix := fmt.Sprintf("tenant:%d:", scope.TenantID)
	return strings.TrimPrefix(storedFilename, prefix)
}

func normalizeKeywordFromFilename(filename string) string {
	return strings.TrimSuffix(filename, ResultFileSuffix)
}

func scopedKeywordSlug(keyword string, scope Scope) string {
	baseSlug := normalizeKeywordSlug(keyword)
	if scope.Kind != ScopeTenant {
		return baseSlug
	}
	return fmt.Sprintf("tenant_%d__%s", scope.TenantID, baseSlug)
}

func normalizeKeywordSlug(keyword string) string {
	var builder strings.Builder
	source := strings.ToLower(strings.ReplaceAll(keyword, " ", "_"))
	for _, char := range source {
		if (char >= 'a' && char <= 'z') || (char >= '0' && char <= '9') || char == '_' || char == '-' {
			builder.WriteRune(char)
		}
	}
	text := strings.TrimRight(builder.String(), "_")
	if text == "" {
		return "unknown"
	}
	return text
}

func statusOrDefault(value string, fallback string) string {
	if strings.TrimSpace(value) == "" {
		return fallback
	}
	return value
}

func productInfo(record map[string]any) map[string]any {
	if value, ok := record["商品信息"].(map[string]any); ok {
		return value
	}
	return map[string]any{}
}

func sellerInfo(record map[string]any) map[string]any {
	if value, ok := record["卖家信息"].(map[string]any); ok {
		return value
	}
	return map[string]any{}
}

func analysisInfo(record map[string]any) map[string]any {
	if value, ok := record["ai_analysis"].(map[string]any); ok {
		return value
	}
	return map[string]any{}
}

func shallowCloneMap(source map[string]any) map[string]any {
	clone := make(map[string]any, len(source))
	for key, value := range source {
		clone[key] = value
	}
	return clone
}

func asString(value any) string {
	switch typed := value.(type) {
	case nil:
		return ""
	case string:
		return typed
	case float64:
		return strconv.FormatFloat(typed, 'f', -1, 64)
	case float32:
		return strconv.FormatFloat(float64(typed), 'f', -1, 64)
	case int:
		return strconv.Itoa(typed)
	case int64:
		return strconv.FormatInt(typed, 10)
	case bool:
		if typed {
			return "true"
		}
		return "false"
	default:
		return fmt.Sprintf("%v", typed)
	}
}

func asBool(value any) bool {
	switch typed := value.(type) {
	case bool:
		return typed
	case float64:
		return typed != 0
	case int:
		return typed != 0
	default:
		return false
	}
}

func parsePriceValue(value any) *float64 {
	if value == nil {
		return nil
	}
	switch typed := value.(type) {
	case float64:
		rounded := round2(typed)
		return &rounded
	case int:
		rounded := round2(float64(typed))
		return &rounded
	case string:
		text := strings.TrimSpace(strings.ReplaceAll(strings.ReplaceAll(typed, "¥", ""), ",", ""))
		if text == "" || text == "价格异常" || text == "暂无" || text == "-" || text == "N/A" {
			return nil
		}
		if strings.HasSuffix(text, "万") {
			base, err := strconv.ParseFloat(strings.TrimSuffix(text, "万"), 64)
			if err != nil {
				return nil
			}
			rounded := round2(base * 10000)
			return &rounded
		}
		number, err := strconv.ParseFloat(text, 64)
		if err != nil {
			return nil
		}
		rounded := round2(number)
		return &rounded
	}
	return nil
}

func parseTimestamp(value string) time.Time {
	if value == "" {
		return time.Time{}
	}
	if parsed, err := time.Parse(time.RFC3339, value); err == nil {
		return parsed
	}
	if parsed, err := time.Parse("2006-01-02T15:04:05", value); err == nil {
		return parsed
	}
	return time.Time{}
}

func round2(value float64) float64 {
	return math.Round(value*100) / 100
}

func maxFloat(values []float64) float64 {
	maximum := values[0]
	for _, value := range values[1:] {
		if value > maximum {
			maximum = value
		}
	}
	return maximum
}

func minFloat(values []float64) float64 {
	minimum := values[0]
	for _, value := range values[1:] {
		if value < minimum {
			minimum = value
		}
	}
	return minimum
}

func nearlyEqual(left float64, right float64) bool {
	return math.Abs(left-right) <= 0.001
}

func resolveDealLabel(score int) string {
	switch {
	case score >= 65:
		return "高性价比"
	case score >= 50:
		return "值得关注"
	case score >= 40:
		return "价格正常"
	default:
		return "价格偏高"
	}
}

func derefFloat(value *float64) any {
	if value == nil {
		return nil
	}
	return *value
}

func nullableFloatFromZero(numeric float64, fallback any) any {
	if fallback == nil {
		return nil
	}
	return numeric
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return value
		}
	}
	return ""
}

func firstNonNil(values ...any) any {
	for _, value := range values {
		if value == nil {
			continue
		}
		if text, ok := value.(string); ok && strings.TrimSpace(text) == "" {
			continue
		}
		return value
	}
	return nil
}

func boolLabel(value bool) string {
	if value {
		return "是"
	}
	return "否"
}

func max(left int, right int) int {
	if left > right {
		return left
	}
	return right
}
