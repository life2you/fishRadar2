"""
结果数据的数据库读写服务。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime

from src.infrastructure.persistence.mysql_bootstrap import bootstrap_mysql_storage
from src.infrastructure.persistence.mysql_connection import mysql_connection
from src.infrastructure.persistence.storage_names import build_result_filename
from src.services.price_history_service import parse_price_value
from src.services.result_blacklist_service import (
    match_blacklist_keywords,
    normalize_blacklist_keywords,
)


SORT_COLUMN_MAP = {
    "crawl_time": "crawl_time",
    "publish_time": "COALESCE(publish_time, '')",
    "price": "COALESCE(price, 0)",
    "keyword_hit_count": "keyword_hit_count",
}
GLOBAL_TENANT_SCOPE = "__global__"


def _get_link_unique_key(link: str) -> str:
    return link.split("&", 1)[0]


def _fallback_unique_key(record: dict, item: dict) -> str:
    item_id = str(item.get("商品ID") or "").strip()
    if item_id:
        return f"item:{item_id}"
    digest = hashlib.sha1(
        json.dumps(record, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return f"hash:{digest}"


def _parse_raw_record(raw_json: str, *, status: str | None = None) -> dict:
    record = json.loads(raw_json)
    if status is not None:
        record["_status"] = status
    return record


def _append_tenant_filter(conditions: list[str], params: list, tenant_scope) -> None:
    if tenant_scope is None:
        return
    if tenant_scope == GLOBAL_TENANT_SCOPE:
        conditions.append("tenant_id IS NULL")
        return
    conditions.append("tenant_id = ?")
    params.append(int(tenant_scope))


def _tenant_scope_to_db_value(tenant_scope):
    if tenant_scope in {None, GLOBAL_TENANT_SCOPE}:
        return None
    return int(tenant_scope)


def _blacklist_scope_key(filename: str, tenant_scope) -> str:
    if tenant_scope is None:
        return filename
    if tenant_scope == GLOBAL_TENANT_SCOPE:
        return f"global:{filename}"
    return f"tenant:{int(tenant_scope)}:{filename}"


def _scoped_result_filename(filename: str, tenant_scope) -> str:
    if tenant_scope in {None, GLOBAL_TENANT_SCOPE}:
        return filename
    return f"tenant:{int(tenant_scope)}:{filename}"


def _visible_result_filename(stored_filename: str, tenant_scope) -> str:
    if tenant_scope in {None, GLOBAL_TENANT_SCOPE}:
        return stored_filename
    prefix = f"tenant:{int(tenant_scope)}:"
    if stored_filename.startswith(prefix):
        return stored_filename[len(prefix):]
    return stored_filename


def _build_query_conditions(
    *,
    filename: str,
    ai_recommended_only: bool,
    keyword_recommended_only: bool,
    tenant_scope=None,
) -> tuple[str, list]:
    conditions = ["result_filename = ?"]
    params: list = [_scoped_result_filename(filename, tenant_scope)]
    _append_tenant_filter(conditions, params, tenant_scope)
    if ai_recommended_only:
        conditions.append("is_recommended = 1")
        conditions.append("analysis_source = ?")
        params.append("ai")
    if keyword_recommended_only:
        conditions.append("is_recommended = 1")
        conditions.append("analysis_source = ?")
        params.append("keyword")
    return " AND ".join(conditions), params


def _sort_expression(sort_by: str, sort_order: str) -> str:
    column = SORT_COLUMN_MAP.get(sort_by, SORT_COLUMN_MAP["crawl_time"])
    direction = "ASC" if sort_order == "asc" else "DESC"
    return f"(CASE WHEN status = 'active' THEN 0 ELSE 1 END), {column} {direction}, id {direction}"


def _load_blacklist_keywords_from_conn(conn, filename: str, tenant_scope=None) -> list[str]:
    row = conn.execute(
        """
        SELECT blacklist_keywords_json
        FROM result_blacklist_rules
        WHERE result_filename = ?
        """,
        (_blacklist_scope_key(filename, tenant_scope),),
    ).fetchone()
    if row is None:
        return []
    try:
        payload = json.loads(row["blacklist_keywords_json"] or "[]")
    except json.JSONDecodeError:
        return []
    return normalize_blacklist_keywords(payload)


def _decorate_record_visibility(record: dict, status: str | None, blacklist_keywords: list[str]) -> dict:
    matched_keywords = match_blacklist_keywords(record, blacklist_keywords)
    hidden_reason = None
    if status == "expired":
        hidden_reason = "expired"
    elif status and status != "active":
        hidden_reason = "manual"
    elif matched_keywords:
        hidden_reason = "rule"

    record["_status"] = status or "active"
    record["_matched_blacklist_keywords"] = matched_keywords
    record["_hidden_reason"] = hidden_reason
    record["_effective_hidden"] = hidden_reason is not None
    return record


def _is_record_visible(record: dict) -> bool:
    return record.get("_effective_hidden") is not True


def _load_filtered_records_from_conn(
    conn,
    *,
    filename: str,
    ai_recommended_only: bool,
    keyword_recommended_only: bool,
    sort_by: str,
    sort_order: str,
    include_hidden: bool,
    tenant_scope=None,
) -> list[dict]:
    where_clause, params = _build_query_conditions(
        filename=filename,
        ai_recommended_only=ai_recommended_only,
        keyword_recommended_only=keyword_recommended_only,
        tenant_scope=tenant_scope,
    )
    order_clause = _sort_expression(sort_by, sort_order)
    rows = conn.execute(
        f"""
        SELECT raw_json, status
        FROM result_items
        WHERE {where_clause}
        ORDER BY {order_clause}
        """,
        tuple(params),
    ).fetchall()
    blacklist_keywords = _load_blacklist_keywords_from_conn(conn, filename, tenant_scope)

    records: list[dict] = []
    for row in rows:
        record = _parse_raw_record(str(row["raw_json"]), status=row["status"])
        decorated = _decorate_record_visibility(record, row["status"], blacklist_keywords)
        if include_hidden or _is_record_visible(decorated):
            records.append(decorated)
    return records


async def save_result_record(record: dict, keyword: str, tenant_scope=None) -> bool:
    return await asyncio.to_thread(_save_result_record_sync, record, keyword, tenant_scope)


def _save_result_record_sync(record: dict, keyword: str, tenant_scope=None) -> bool:
    bootstrap_mysql_storage()
    item = record.get("商品信息", {}) or {}
    analysis = record.get("ai_analysis", {}) or {}
    link = str(item.get("商品链接") or "")
    link_unique_key = _get_link_unique_key(link) if link else _fallback_unique_key(record, item)
    keyword_hit_count = analysis.get("keyword_hit_count", 0)
    try:
        keyword_hit_count = int(keyword_hit_count)
    except (TypeError, ValueError):
        keyword_hit_count = 0

    with mysql_connection() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO result_items (
                tenant_id, result_filename, keyword, task_name, crawl_time, publish_time, price,
                price_display, item_id, title, link, link_unique_key, seller_nickname,
                is_recommended, analysis_source, keyword_hit_count, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _tenant_scope_to_db_value(tenant_scope),
                _scoped_result_filename(build_result_filename(keyword), tenant_scope),
                record.get("搜索关键字", keyword),
                record.get("任务名称", ""),
                record.get("爬取时间", ""),
                item.get("发布时间"),
                parse_price_value(item.get("当前售价")),
                item.get("当前售价"),
                item.get("商品ID"),
                item.get("商品标题"),
                link,
                link_unique_key,
                (record.get("卖家信息", {}) or {}).get("卖家昵称") or item.get("卖家昵称"),
                1 if analysis.get("is_recommended") else 0,
                analysis.get("analysis_source"),
                keyword_hit_count,
                json.dumps(record, ensure_ascii=False),
            ),
        )
        conn.commit()
    return True


def load_processed_link_keys(keyword: str, tenant_scope=None) -> set[str]:
    bootstrap_mysql_storage()
    filename = _scoped_result_filename(build_result_filename(keyword), tenant_scope)
    conditions = ["result_filename = ?"]
    params: list = [filename]
    _append_tenant_filter(conditions, params, tenant_scope)
    with mysql_connection() as conn:
        rows = conn.execute(
            f"SELECT link_unique_key FROM result_items WHERE {' AND '.join(conditions)}",
            tuple(params),
        ).fetchall()
    return {str(row["link_unique_key"]) for row in rows if row["link_unique_key"]}


async def list_result_filenames(tenant_scope=None) -> list[str]:
    return await asyncio.to_thread(_list_result_filenames_sync, tenant_scope)


def _list_result_filenames_sync(tenant_scope=None) -> list[str]:
    bootstrap_mysql_storage()
    where_clause = ""
    params: list = []
    if tenant_scope is not None:
        conditions: list[str] = []
        _append_tenant_filter(conditions, params, tenant_scope)
        where_clause = f"WHERE {' AND '.join(conditions)}"
    with mysql_connection() as conn:
        rows = conn.execute(
            """
            SELECT result_filename, MAX(crawl_time) AS latest_crawl_time
            FROM result_items
            """
            + where_clause
            + """
            GROUP BY result_filename
            ORDER BY latest_crawl_time DESC, result_filename DESC
            """,
            tuple(params),
        ).fetchall()
    return [
        _visible_result_filename(str(row["result_filename"]), tenant_scope)
        for row in rows
    ]


async def result_file_exists(filename: str, tenant_scope=None) -> bool:
    return await asyncio.to_thread(_result_file_exists_sync, filename, tenant_scope)


def _result_file_exists_sync(filename: str, tenant_scope=None) -> bool:
    bootstrap_mysql_storage()
    conditions = ["result_filename = ?"]
    params: list = [_scoped_result_filename(filename, tenant_scope)]
    _append_tenant_filter(conditions, params, tenant_scope)
    with mysql_connection() as conn:
        row = conn.execute(
            f"SELECT 1 FROM result_items WHERE {' AND '.join(conditions)} LIMIT 1",
            tuple(params),
        ).fetchone()
    return row is not None


async def delete_result_file_records(filename: str, tenant_scope=None) -> int:
    return await asyncio.to_thread(_delete_result_file_records_sync, filename, tenant_scope)


def _delete_result_file_records_sync(filename: str, tenant_scope=None) -> int:
    bootstrap_mysql_storage()
    conditions = ["result_filename = ?"]
    params: list = [_scoped_result_filename(filename, tenant_scope)]
    _append_tenant_filter(conditions, params, tenant_scope)
    with mysql_connection() as conn:
        cursor = conn.execute(
            f"DELETE FROM result_items WHERE {' AND '.join(conditions)}",
            tuple(params),
        )
        conn.commit()
    return int(cursor.rowcount or 0)


async def query_result_records(
    filename: str,
    *,
    ai_recommended_only: bool,
    keyword_recommended_only: bool,
    sort_by: str,
    sort_order: str,
    page: int,
    limit: int,
    include_hidden: bool = False,
    tenant_scope=None,
) -> tuple[int, list[dict]]:
    return await asyncio.to_thread(
        _query_result_records_sync,
        filename,
        ai_recommended_only,
        keyword_recommended_only,
        sort_by,
        sort_order,
        page,
        limit,
        include_hidden,
        tenant_scope,
    )


def _query_result_records_sync(
    filename: str,
    ai_recommended_only: bool,
    keyword_recommended_only: bool,
    sort_by: str,
    sort_order: str,
    page: int,
    limit: int,
    include_hidden: bool,
    tenant_scope=None,
) -> tuple[int, list[dict]]:
    bootstrap_mysql_storage()
    offset = max(page - 1, 0) * limit
    with mysql_connection() as conn:
        records = _load_filtered_records_from_conn(
            conn,
            filename=filename,
            ai_recommended_only=ai_recommended_only,
            keyword_recommended_only=keyword_recommended_only,
            sort_by=sort_by,
            sort_order=sort_order,
            include_hidden=include_hidden,
            tenant_scope=tenant_scope,
        )
    total = len(records)
    return total, records[offset: offset + limit]


async def load_all_result_records(
    filename: str,
    *,
    ai_recommended_only: bool,
    keyword_recommended_only: bool,
    sort_by: str,
    sort_order: str,
    include_hidden: bool = False,
    tenant_scope=None,
) -> list[dict]:
    return await asyncio.to_thread(
        _load_all_result_records_sync,
        filename,
        ai_recommended_only,
        keyword_recommended_only,
        sort_by,
        sort_order,
        include_hidden,
        tenant_scope,
    )


def _load_all_result_records_sync(
    filename: str,
    ai_recommended_only: bool,
    keyword_recommended_only: bool,
    sort_by: str,
    sort_order: str,
    include_hidden: bool,
    tenant_scope=None,
) -> list[dict]:
    bootstrap_mysql_storage()
    with mysql_connection() as conn:
        return _load_filtered_records_from_conn(
            conn,
            filename=filename,
            ai_recommended_only=ai_recommended_only,
            keyword_recommended_only=keyword_recommended_only,
            sort_by=sort_by,
            sort_order=sort_order,
            include_hidden=include_hidden,
            tenant_scope=tenant_scope,
        )


async def build_result_ndjson(filename: str, tenant_scope=None) -> str:
    return await asyncio.to_thread(_build_result_ndjson_sync, filename, tenant_scope)


def _build_result_ndjson_sync(filename: str, tenant_scope=None) -> str:
    bootstrap_mysql_storage()
    conditions = ["result_filename = ?"]
    params: list = [_scoped_result_filename(filename, tenant_scope)]
    _append_tenant_filter(conditions, params, tenant_scope)
    with mysql_connection() as conn:
        rows = conn.execute(
            f"SELECT raw_json FROM result_items WHERE {' AND '.join(conditions)} ORDER BY id ASC",
            tuple(params),
        ).fetchall()
    return "\n".join(str(row["raw_json"]) for row in rows)


async def load_result_summary(filename: str, tenant_scope=None) -> dict | None:
    return await asyncio.to_thread(_load_result_summary_sync, filename, tenant_scope)


def _load_result_summary_sync(filename: str, tenant_scope=None) -> dict | None:
    bootstrap_mysql_storage()
    with mysql_connection() as conn:
        visible_records = _load_filtered_records_from_conn(
            conn,
            filename=filename,
            ai_recommended_only=False,
            keyword_recommended_only=False,
            sort_by="crawl_time",
            sort_order="desc",
            include_hidden=False,
            tenant_scope=tenant_scope,
        )
    if not visible_records:
        return None

    recommended_records = [
        record
        for record in visible_records
        if (record.get("ai_analysis", {}) or {}).get("is_recommended") is True
    ]
    ai_recommended_items = 0
    keyword_recommended_items = 0
    for record in recommended_records:
        source = (record.get("ai_analysis", {}) or {}).get("analysis_source")
        if source == "ai":
            ai_recommended_items += 1
        elif source == "keyword":
            keyword_recommended_items += 1

    return {
        "total_items": len(visible_records),
        "recommended_items": len(recommended_records),
        "ai_recommended_items": ai_recommended_items,
        "keyword_recommended_items": keyword_recommended_items,
        "latest_crawl_time": visible_records[0].get("爬取时间"),
        "latest_record": visible_records[0],
        "latest_recommendation": recommended_records[0] if recommended_records else None,
    }


async def update_item_status(filename: str, item_id: str, status: str, tenant_scope=None) -> bool:
    valid = {"active", "hidden", "expired"}
    if status not in valid:
        raise ValueError(f"status must be one of {valid}")
    return await asyncio.to_thread(_update_item_status_sync, filename, item_id, status, tenant_scope)


def _update_item_status_sync(filename: str, item_id: str, status: str, tenant_scope=None) -> bool:
    bootstrap_mysql_storage()
    conditions = ["result_filename = ?", "item_id = ?"]
    params: list = [_scoped_result_filename(filename, tenant_scope), item_id]
    _append_tenant_filter(conditions, params, tenant_scope)
    with mysql_connection() as conn:
        cursor = conn.execute(
            f"UPDATE result_items SET status = ? WHERE {' AND '.join(conditions)}",
            (status, *params),
        )
        conn.commit()
        return cursor.rowcount > 0


async def update_result_analysis(
    filename: str,
    item_id: str,
    ai_analysis: dict,
    tenant_scope=None,
) -> bool:
    return await asyncio.to_thread(
        _update_result_analysis_sync,
        filename,
        item_id,
        ai_analysis,
        tenant_scope,
    )


def _update_result_analysis_sync(
    filename: str,
    item_id: str,
    ai_analysis: dict,
    tenant_scope=None,
) -> bool:
    bootstrap_mysql_storage()
    conditions = ["result_filename = ?", "item_id = ?"]
    params: list = [_scoped_result_filename(filename, tenant_scope), item_id]
    _append_tenant_filter(conditions, params, tenant_scope)

    with mysql_connection() as conn:
        row = conn.execute(
            f"SELECT raw_json FROM result_items WHERE {' AND '.join(conditions)} LIMIT 1",
            tuple(params),
        ).fetchone()
        if row is None:
            return False

        record = _parse_raw_record(str(row["raw_json"]))
        record["ai_analysis"] = ai_analysis
        keyword_hit_count = ai_analysis.get("keyword_hit_count", 0)
        try:
            keyword_hit_count = int(keyword_hit_count)
        except (TypeError, ValueError):
            keyword_hit_count = 0

        cursor = conn.execute(
            f"""
            UPDATE result_items
            SET is_recommended = ?,
                analysis_source = ?,
                keyword_hit_count = ?,
                raw_json = ?
            WHERE {' AND '.join(conditions)}
            """,
            (
                1 if ai_analysis.get("is_recommended") else 0,
                ai_analysis.get("analysis_source"),
                keyword_hit_count,
                json.dumps(record, ensure_ascii=False),
                *params,
            ),
        )
        conn.commit()
        return cursor.rowcount > 0


async def load_result_blacklist_keywords(filename: str, tenant_scope=None) -> list[str]:
    return await asyncio.to_thread(_load_result_blacklist_keywords_sync, filename, tenant_scope)


def _load_result_blacklist_keywords_sync(filename: str, tenant_scope=None) -> list[str]:
    bootstrap_mysql_storage()
    with mysql_connection() as conn:
        return _load_blacklist_keywords_from_conn(conn, filename, tenant_scope)


async def save_result_blacklist_keywords(filename: str, keywords: list[str], tenant_scope=None) -> list[str]:
    return await asyncio.to_thread(_save_result_blacklist_keywords_sync, filename, keywords, tenant_scope)


def _save_result_blacklist_keywords_sync(filename: str, keywords: list[str], tenant_scope=None) -> list[str]:
    bootstrap_mysql_storage()
    normalized_keywords = normalize_blacklist_keywords(keywords)
    now = datetime.now().isoformat()
    with mysql_connection() as conn:
        scope_filename = _blacklist_scope_key(filename, tenant_scope)
        payload = (
            scope_filename,
            json.dumps(normalized_keywords, ensure_ascii=False),
            now,
        )
        if conn.backend == "mysql":
            conn.execute(
                """
                INSERT INTO result_blacklist_rules (
                    result_filename, blacklist_keywords_json, updated_at
                ) VALUES (?, ?, ?)
                ON DUPLICATE KEY UPDATE
                    blacklist_keywords_json = VALUES(blacklist_keywords_json),
                    updated_at = VALUES(updated_at)
                """,
                payload,
            )
        else:
            conn.execute(
                """
                INSERT INTO result_blacklist_rules (
                    result_filename, blacklist_keywords_json, updated_at
                ) VALUES (?, ?, ?)
                ON CONFLICT(result_filename) DO UPDATE SET
                    blacklist_keywords_json = excluded.blacklist_keywords_json,
                    updated_at = excluded.updated_at
                """,
                payload,
            )
        conn.commit()
    return normalized_keywords


def load_visible_result_item_ids(filename: str, tenant_scope=None) -> set[str]:
    bootstrap_mysql_storage()
    with mysql_connection() as conn:
        visible_records = _load_filtered_records_from_conn(
            conn,
            filename=filename,
            ai_recommended_only=False,
            keyword_recommended_only=False,
            sort_by="crawl_time",
            sort_order="desc",
            include_hidden=False,
            tenant_scope=tenant_scope,
        )
    item_ids: set[str] = set()
    for record in visible_records:
        product = record.get("商品信息", {}) or {}
        item_id = str(product.get("商品ID") or "").strip()
        if item_id:
            item_ids.add(item_id)
    return item_ids
