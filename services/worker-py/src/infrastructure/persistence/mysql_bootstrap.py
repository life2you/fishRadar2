"""
MySQL 启动初始化与旧文件迁移。
"""
from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

from src.infrastructure.persistence.mysql_connection import init_schema, mysql_connection
from src.infrastructure.persistence.storage_names import (
    build_result_filename,
    normalize_keyword_from_filename,
    normalize_keyword_slug,
)
from src.services.account_state_service import (
    ACCOUNT_STATE_KIND_ACCOUNT,
    ACCOUNT_STATE_KIND_DEFAULT,
    DEFAULT_LOGIN_STATE_NAME,
    ensure_account_states_table,
    get_legacy_account_state_dir,
)
from src.services.auth_service import (
    bootstrap_default_auth_data,
    validate_admin_bootstrap_safety_sync,
)
from src.services.prompt_document_service import (
    PROMPT_SOURCE_SYSTEM,
    ensure_builtin_prompt_documents,
)


BOOTSTRAP_LOCK = threading.Lock()
LEGACY_RESULT_DIR = "jsonl"
LEGACY_PRICE_HISTORY_DIR = "price_history"
RESULTS_BOOTSTRAP_KEY = "bootstrap:legacy_results"
SNAPSHOTS_BOOTSTRAP_KEY = "bootstrap:legacy_price_snapshots"
ACCOUNT_STATES_BOOTSTRAP_KEY = "bootstrap:legacy_account_states"
PROMPTS_BOOTSTRAP_KEY = "bootstrap:legacy_prompts"
LEGACY_PROMPTS_DIR = "prompts"


def bootstrap_mysql_storage(
    db_path: str | None = None,
    *,
    legacy_result_dir: str = LEGACY_RESULT_DIR,
    legacy_price_history_dir: str = LEGACY_PRICE_HISTORY_DIR,
) -> None:
    if db_path is not None:
        raise ValueError("db_path 已不再支持。当前版本仅支持 MySQL。")
    ensure_builtin_prompt_documents()
    with BOOTSTRAP_LOCK:
        with mysql_connection() as conn:
            init_schema(conn)
            _import_prompt_documents_if_needed(conn, LEGACY_PROMPTS_DIR)
            _import_results_if_needed(conn, legacy_result_dir)
            _import_price_snapshots_if_needed(conn, legacy_price_history_dir)
            _import_account_states_if_needed(conn)
        validate_admin_bootstrap_safety_sync()
        bootstrap_default_auth_data()


def _table_is_empty(conn, table_name: str) -> bool:
    row = conn.execute(f"SELECT COUNT(1) AS total FROM {table_name}").fetchone()
    return row is None or int(row["total"]) == 0


def _load_json_file(path: Path):
    if not path.exists():
        return None
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return None
    return json.loads(content)


def _import_results_if_needed(conn, legacy_result_dir: str) -> None:
    if _bootstrap_completed(conn, RESULTS_BOOTSTRAP_KEY):
        return
    if not _table_is_empty(conn, "result_items"):
        _mark_bootstrap_completed(conn, RESULTS_BOOTSTRAP_KEY)
        conn.commit()
        return
    result_dir = Path(legacy_result_dir)
    if not result_dir.exists():
        _mark_bootstrap_completed(conn, RESULTS_BOOTSTRAP_KEY)
        conn.commit()
        return

    for path in sorted(result_dir.glob("*.jsonl")):
        filename = path.name
        keyword = normalize_keyword_from_filename(filename)
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                text = line.strip()
                if not text:
                    continue
                try:
                    record = json.loads(text)
                except json.JSONDecodeError:
                    continue
                _insert_result_record(conn, record, keyword=keyword, filename=filename)
    _mark_bootstrap_completed(conn, RESULTS_BOOTSTRAP_KEY)
    conn.commit()


def _import_price_snapshots_if_needed(conn, legacy_price_history_dir: str) -> None:
    if _bootstrap_completed(conn, SNAPSHOTS_BOOTSTRAP_KEY):
        return
    if not _table_is_empty(conn, "price_snapshots"):
        _mark_bootstrap_completed(conn, SNAPSHOTS_BOOTSTRAP_KEY)
        conn.commit()
        return
    history_dir = Path(legacy_price_history_dir)
    if not history_dir.exists():
        _mark_bootstrap_completed(conn, SNAPSHOTS_BOOTSTRAP_KEY)
        conn.commit()
        return

    for path in sorted(history_dir.glob("*_history.jsonl")):
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                text = line.strip()
                if not text:
                    continue
                try:
                    record = json.loads(text)
                except json.JSONDecodeError:
                    continue
                _insert_price_snapshot(conn, record)
    _mark_bootstrap_completed(conn, SNAPSHOTS_BOOTSTRAP_KEY)
    conn.commit()


def _import_account_states_if_needed(conn) -> None:
    if _bootstrap_completed(conn, ACCOUNT_STATES_BOOTSTRAP_KEY):
        return

    ensure_account_states_table(conn)
    now = _now_iso()
    legacy_state_dir = Path(get_legacy_account_state_dir())
    if legacy_state_dir.exists():
        for path in sorted(legacy_state_dir.glob("*.json")):
            content = path.read_text(encoding="utf-8").strip()
            if not content:
                continue
            conn.execute(
                """
                INSERT INTO account_states (name, kind, state_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON DUPLICATE KEY UPDATE
                    state_json = VALUES(state_json),
                    updated_at = VALUES(updated_at)
                """,
                (path.stem, ACCOUNT_STATE_KIND_ACCOUNT, content, now, now),
            )

    default_state_path = Path("xianyu_state.json")
    if default_state_path.exists():
        content = default_state_path.read_text(encoding="utf-8").strip()
        if content:
            conn.execute(
                """
                INSERT INTO account_states (name, kind, state_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON DUPLICATE KEY UPDATE
                    state_json = VALUES(state_json),
                    updated_at = VALUES(updated_at)
                """,
                (DEFAULT_LOGIN_STATE_NAME, ACCOUNT_STATE_KIND_DEFAULT, content, now, now),
            )

    _mark_bootstrap_completed(conn, ACCOUNT_STATES_BOOTSTRAP_KEY)
    conn.commit()


def _import_prompt_documents_if_needed(conn, legacy_prompts_dir: str) -> None:
    if _bootstrap_completed(conn, PROMPTS_BOOTSTRAP_KEY):
        return
    prompt_dir = Path(legacy_prompts_dir)
    if not prompt_dir.exists():
        _mark_bootstrap_completed(conn, PROMPTS_BOOTSTRAP_KEY)
        conn.commit()
        return

    now = _now_iso()
    for path in sorted(prompt_dir.glob("*.txt")):
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            continue
        filename = str(path.as_posix())
        conn.execute(
            """
            INSERT INTO prompt_documents (filename, content, source, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE
                content = VALUES(content),
                updated_at = VALUES(updated_at)
            """,
            (filename, content, PROMPT_SOURCE_SYSTEM, now, now),
        )

    _mark_bootstrap_completed(conn, PROMPTS_BOOTSTRAP_KEY)
    conn.commit()


def _insert_result_record(conn, record: dict, *, keyword: str, filename: str) -> None:
    item = record.get("商品信息", {}) or {}
    analysis = record.get("ai_analysis", {}) or {}
    link = str(item.get("商品链接") or "")
    if link:
        link_unique_key = link.split("&", 1)[0]
    else:
        item_id = str(item.get("商品ID") or "").strip()
        if item_id:
            link_unique_key = f"item:{item_id}"
        else:
            link_unique_key = "hash:" + hashlib.sha1(
                json.dumps(record, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest()
    final_keyword = str(record.get("搜索关键字") or keyword)
    result_filename = filename or build_result_filename(final_keyword)
    keyword_hit_count = analysis.get("keyword_hit_count", 0)
    try:
        keyword_hit_count = int(keyword_hit_count)
    except (TypeError, ValueError):
        keyword_hit_count = 0

    conn.execute(
        """
        INSERT OR IGNORE INTO result_items (
            result_filename, keyword, task_name, crawl_time, publish_time, price,
            price_display, item_id, title, link, link_unique_key, seller_nickname,
            is_recommended, analysis_source, keyword_hit_count, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            result_filename,
            final_keyword,
            record.get("任务名称", ""),
            record.get("爬取时间", ""),
            item.get("发布时间"),
            _parse_price(item.get("当前售价")),
            item.get("当前售价"),
            item.get("商品ID"),
            item.get("商品标题"),
            link,
            link_unique_key,
            (record.get("卖家信息", {}) or {}).get("卖家昵称") or item.get("卖家昵称"),
            _as_int(analysis.get("is_recommended", False)),
            analysis.get("analysis_source"),
            keyword_hit_count,
            json.dumps(record, ensure_ascii=False),
        ),
    )


def _insert_price_snapshot(conn, record: dict) -> None:
    keyword = str(record.get("keyword") or "")
    slug = str(record.get("keyword_slug") or normalize_keyword_slug(keyword))
    conn.execute(
        """
        INSERT OR IGNORE INTO price_snapshots (
            keyword_slug, keyword, task_name, snapshot_time, snapshot_day, run_id,
            item_id, title, price, price_display, tags_json, region, seller,
            publish_time, link
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            slug,
            keyword,
            record.get("task_name", ""),
            record.get("snapshot_time", ""),
            record.get("snapshot_day", ""),
            record.get("run_id", ""),
            record.get("item_id", ""),
            record.get("title", ""),
            _parse_price(record.get("price")),
            record.get("price_display"),
            json.dumps(record.get("tags") or [], ensure_ascii=False),
            record.get("region"),
            record.get("seller"),
            record.get("publish_time"),
            record.get("link"),
        ),
    )


def _as_int(value) -> int:
    if isinstance(value, bool):
        return 1 if value else 0
    if value is None:
        return 0
    return 1 if str(value).strip().lower() in {"1", "true", "yes", "on"} else 0


def _parse_price(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return round(float(value), 2)

    text = str(value).strip().replace("¥", "").replace(",", "")
    if not text or text in {"价格异常", "暂无", "-", "N/A"}:
        return None
    if text.endswith("万"):
        text = str(float(text[:-1]) * 10000)
    try:
        return round(float(text), 2)
    except (TypeError, ValueError):
        return None


def _bootstrap_completed(conn, key: str) -> bool:
    row = conn.execute(
        "SELECT value FROM app_metadata WHERE `key` = ?",
        (key,),
    ).fetchone()
    return row is not None


def _mark_bootstrap_completed(conn, key: str) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO app_metadata(`key`, value)
        VALUES (?, 'done')
        """,
        (key,),
    )


def _now_iso() -> str:
    from datetime import datetime

    return datetime.now().isoformat(timespec="seconds")
