"""Platform-level business settings stored in MySQL."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from typing import Any, Callable

from src.infrastructure.config.env_manager import env_manager
from src.infrastructure.config.settings import AISettings, DEFAULT_TELEGRAM_API_BASE_URL
from src.infrastructure.persistence.mysql_connection import init_schema, mysql_connection


PLATFORM_NOTIFICATION_SETTINGS_KEY = "platform:notification_settings"
PLATFORM_ROTATION_SETTINGS_KEY = "platform:rotation_settings"
PLATFORM_AI_RUNTIME_SETTINGS_KEY = "platform:ai_runtime_settings"
PLATFORM_FAILURE_GUARD_SETTINGS_KEY = "platform:failure_guard_settings"


def _notification_defaults() -> dict[str, Any]:
    return {
        "NTFY_TOPIC_URL": "",
        "GOTIFY_URL": "",
        "GOTIFY_TOKEN": "",
        "BARK_URL": "",
        "WX_BOT_URL": "",
        "TELEGRAM_BOT_TOKEN": "",
        "TELEGRAM_CHAT_ID": "",
        "TELEGRAM_API_BASE_URL": DEFAULT_TELEGRAM_API_BASE_URL,
        "WEBHOOK_URL": "",
        "WEBHOOK_METHOD": "POST",
        "WEBHOOK_HEADERS": "",
        "WEBHOOK_CONTENT_TYPE": "JSON",
        "WEBHOOK_QUERY_PARAMETERS": "",
        "WEBHOOK_BODY": "",
        "PCURL_TO_MOBILE": True,
    }


def _rotation_defaults() -> dict[str, Any]:
    return {
        "ACCOUNT_ROTATION_ENABLED": False,
        "ACCOUNT_ROTATION_MODE": "per_task",
        "ACCOUNT_ROTATION_RETRY_LIMIT": 2,
        "ACCOUNT_BLACKLIST_TTL": 300,
        "PROXY_ROTATION_ENABLED": False,
        "PROXY_ROTATION_MODE": "per_task",
        "PROXY_POOL": "",
        "PROXY_ROTATION_RETRY_LIMIT": 2,
        "PROXY_BLACKLIST_TTL": 300,
    }


def _ai_runtime_defaults() -> dict[str, Any]:
    return {
        "PROXY_URL": "",
        "AI_DEBUG_MODE": False,
        "ENABLE_RESPONSE_FORMAT": True,
        "ENABLE_THINKING": False,
        "SKIP_AI_ANALYSIS": False,
        "AI_ANALYSIS_CONCURRENCY": 2,
        "SELLER_PROFILE_CACHE_TTL": 1800,
    }


def _failure_guard_defaults() -> dict[str, Any]:
    return {
        "TASK_FAILURE_THRESHOLD": 3,
        "TASK_FAILURE_PAUSE_SECONDS": 24 * 60 * 60,
        "TASK_FAILURE_TZ": "Asia/Shanghai",
    }


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_text(value: Any, default: str) -> str:
    if value is None:
        return default
    return str(value).strip()


def _env_notification_seed() -> dict[str, Any]:
    defaults = _notification_defaults()
    values = {}
    for key, default in defaults.items():
        raw = env_manager.get_value(key)
        if isinstance(default, bool):
            values[key] = _as_bool(raw, default)
        else:
            values[key] = _as_text(raw, str(default)) if raw is not None else default
    return values


def _env_rotation_seed() -> dict[str, Any]:
    defaults = _rotation_defaults()
    values = {}
    for key, default in defaults.items():
        raw = env_manager.get_value(key)
        if isinstance(default, bool):
            values[key] = _as_bool(raw, default)
        elif isinstance(default, int):
            values[key] = _as_int(raw, default)
        else:
            values[key] = _as_text(raw, str(default)) if raw is not None else default
    return values


def _env_ai_runtime_seed() -> dict[str, Any]:
    defaults = _ai_runtime_defaults()
    values = {}
    for key, default in defaults.items():
        raw = env_manager.get_value(key)
        if isinstance(default, bool):
            values[key] = _as_bool(raw, default)
        elif isinstance(default, int):
            values[key] = _as_int(raw, default)
        else:
            values[key] = _as_text(raw, str(default)) if raw is not None else default
    return values


def _env_failure_guard_seed() -> dict[str, Any]:
    defaults = _failure_guard_defaults()
    return {
        "TASK_FAILURE_THRESHOLD": _as_int(os.getenv("TASK_FAILURE_THRESHOLD"), defaults["TASK_FAILURE_THRESHOLD"]),
        "TASK_FAILURE_PAUSE_SECONDS": _as_int(
            os.getenv("TASK_FAILURE_PAUSE_SECONDS"),
            defaults["TASK_FAILURE_PAUSE_SECONDS"],
        ),
        "TASK_FAILURE_TZ": _as_text(os.getenv("TASK_FAILURE_TZ"), defaults["TASK_FAILURE_TZ"]),
    }


def _read_metadata_json_sync(key: str) -> dict[str, Any] | None:
    with mysql_connection() as conn:
        init_schema(conn)
        row = conn.execute(
            "SELECT value FROM app_metadata WHERE `key` = ?",
            (key,),
        ).fetchone()
    if row is None or not row.get("value"):
        return None
    try:
        parsed = json.loads(str(row["value"]))
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _write_metadata_json_sync(key: str, payload: dict[str, Any]) -> dict[str, Any]:
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    with mysql_connection() as conn:
        init_schema(conn)
        conn.execute(
            "INSERT OR REPLACE INTO app_metadata(`key`, value) VALUES (?, ?)",
            (key, serialized),
        )
        conn.commit()
    return payload


def _load_section_sync(
    key: str,
    *,
    defaults: dict[str, Any],
    seed_loader: Callable[[], dict[str, Any]],
    normalizer: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    defaults_copy = deepcopy(defaults)
    stored = _read_metadata_json_sync(key)
    if stored is None:
        seeded = normalizer({**defaults_copy, **seed_loader()})
        _write_metadata_json_sync(key, seeded)
        return seeded
    return normalizer({**defaults_copy, **stored})


def _save_section_sync(
    key: str,
    *,
    defaults: dict[str, Any],
    payload: dict[str, Any],
    normalizer: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    normalized = normalizer({**deepcopy(defaults), **payload})
    return _write_metadata_json_sync(key, normalized)


def _normalize_notification_values(values: dict[str, Any]) -> dict[str, Any]:
    defaults = _notification_defaults()
    normalized = {}
    for key, default in defaults.items():
        raw = values.get(key, default)
        if isinstance(default, bool):
            normalized[key] = _as_bool(raw, default)
        else:
            normalized[key] = _as_text(raw, str(default)) if raw is not None else ""
    if not normalized["TELEGRAM_API_BASE_URL"]:
        normalized["TELEGRAM_API_BASE_URL"] = DEFAULT_TELEGRAM_API_BASE_URL
    normalized["WEBHOOK_METHOD"] = (normalized["WEBHOOK_METHOD"] or "POST").strip().upper()
    normalized["WEBHOOK_CONTENT_TYPE"] = (
        normalized["WEBHOOK_CONTENT_TYPE"] or "JSON"
    ).strip().upper()
    return normalized


def _normalize_rotation_values(values: dict[str, Any]) -> dict[str, Any]:
    defaults = _rotation_defaults()
    return {
        "ACCOUNT_ROTATION_ENABLED": _as_bool(
            values.get("ACCOUNT_ROTATION_ENABLED"),
            defaults["ACCOUNT_ROTATION_ENABLED"],
        ),
        "ACCOUNT_ROTATION_MODE": _as_text(
            values.get("ACCOUNT_ROTATION_MODE"),
            defaults["ACCOUNT_ROTATION_MODE"],
        ).lower() or defaults["ACCOUNT_ROTATION_MODE"],
        "ACCOUNT_ROTATION_RETRY_LIMIT": max(
            1,
            _as_int(
                values.get("ACCOUNT_ROTATION_RETRY_LIMIT"),
                defaults["ACCOUNT_ROTATION_RETRY_LIMIT"],
            ),
        ),
        "ACCOUNT_BLACKLIST_TTL": max(
            0,
            _as_int(values.get("ACCOUNT_BLACKLIST_TTL"), defaults["ACCOUNT_BLACKLIST_TTL"]),
        ),
        "PROXY_ROTATION_ENABLED": _as_bool(
            values.get("PROXY_ROTATION_ENABLED"),
            defaults["PROXY_ROTATION_ENABLED"],
        ),
        "PROXY_ROTATION_MODE": _as_text(
            values.get("PROXY_ROTATION_MODE"),
            defaults["PROXY_ROTATION_MODE"],
        ).lower() or defaults["PROXY_ROTATION_MODE"],
        "PROXY_POOL": _as_text(values.get("PROXY_POOL"), defaults["PROXY_POOL"]),
        "PROXY_ROTATION_RETRY_LIMIT": max(
            1,
            _as_int(
                values.get("PROXY_ROTATION_RETRY_LIMIT"),
                defaults["PROXY_ROTATION_RETRY_LIMIT"],
            ),
        ),
        "PROXY_BLACKLIST_TTL": max(
            0,
            _as_int(values.get("PROXY_BLACKLIST_TTL"), defaults["PROXY_BLACKLIST_TTL"]),
        ),
    }


def _normalize_ai_runtime_values(values: dict[str, Any]) -> dict[str, Any]:
    defaults = _ai_runtime_defaults()
    return {
        "PROXY_URL": _as_text(values.get("PROXY_URL"), defaults["PROXY_URL"]),
        "AI_DEBUG_MODE": _as_bool(values.get("AI_DEBUG_MODE"), defaults["AI_DEBUG_MODE"]),
        "ENABLE_RESPONSE_FORMAT": _as_bool(
            values.get("ENABLE_RESPONSE_FORMAT"),
            defaults["ENABLE_RESPONSE_FORMAT"],
        ),
        "ENABLE_THINKING": _as_bool(values.get("ENABLE_THINKING"), defaults["ENABLE_THINKING"]),
        "SKIP_AI_ANALYSIS": _as_bool(
            values.get("SKIP_AI_ANALYSIS"),
            defaults["SKIP_AI_ANALYSIS"],
        ),
        "AI_ANALYSIS_CONCURRENCY": max(
            1,
            _as_int(
                values.get("AI_ANALYSIS_CONCURRENCY"),
                defaults["AI_ANALYSIS_CONCURRENCY"],
            ),
        ),
        "SELLER_PROFILE_CACHE_TTL": max(
            0,
            _as_int(
                values.get("SELLER_PROFILE_CACHE_TTL"),
                defaults["SELLER_PROFILE_CACHE_TTL"],
            ),
        ),
    }


def _normalize_failure_guard_values(values: dict[str, Any]) -> dict[str, Any]:
    defaults = _failure_guard_defaults()
    return {
        "TASK_FAILURE_THRESHOLD": max(
            1,
            _as_int(values.get("TASK_FAILURE_THRESHOLD"), defaults["TASK_FAILURE_THRESHOLD"]),
        ),
        "TASK_FAILURE_PAUSE_SECONDS": max(
            60,
            _as_int(
                values.get("TASK_FAILURE_PAUSE_SECONDS"),
                defaults["TASK_FAILURE_PAUSE_SECONDS"],
            ),
        ),
        "TASK_FAILURE_TZ": _as_text(values.get("TASK_FAILURE_TZ"), defaults["TASK_FAILURE_TZ"])
        or defaults["TASK_FAILURE_TZ"],
    }


def load_notification_config_values_sync() -> dict[str, Any]:
    return _load_section_sync(
        PLATFORM_NOTIFICATION_SETTINGS_KEY,
        defaults=_notification_defaults(),
        seed_loader=_env_notification_seed,
        normalizer=_normalize_notification_values,
    )


def save_notification_config_values_sync(payload: dict[str, Any]) -> dict[str, Any]:
    return _save_section_sync(
        PLATFORM_NOTIFICATION_SETTINGS_KEY,
        defaults=_notification_defaults(),
        payload=payload,
        normalizer=_normalize_notification_values,
    )


def load_rotation_settings_sync() -> dict[str, Any]:
    return _load_section_sync(
        PLATFORM_ROTATION_SETTINGS_KEY,
        defaults=_rotation_defaults(),
        seed_loader=_env_rotation_seed,
        normalizer=_normalize_rotation_values,
    )


def save_rotation_settings_sync(payload: dict[str, Any]) -> dict[str, Any]:
    return _save_section_sync(
        PLATFORM_ROTATION_SETTINGS_KEY,
        defaults=_rotation_defaults(),
        payload=payload,
        normalizer=_normalize_rotation_values,
    )


def load_ai_runtime_settings_sync() -> AISettings:
    values = _load_section_sync(
        PLATFORM_AI_RUNTIME_SETTINGS_KEY,
        defaults=_ai_runtime_defaults(),
        seed_loader=_env_ai_runtime_seed,
        normalizer=_normalize_ai_runtime_values,
    )
    if hasattr(AISettings, "model_construct"):
        return AISettings.model_construct(
            proxy_url=values["PROXY_URL"] or None,
            debug_mode=values["AI_DEBUG_MODE"],
            enable_response_format=values["ENABLE_RESPONSE_FORMAT"],
            enable_thinking=values["ENABLE_THINKING"],
            skip_analysis=values["SKIP_AI_ANALYSIS"],
        )
    return AISettings.construct(
        proxy_url=values["PROXY_URL"] or None,
        debug_mode=values["AI_DEBUG_MODE"],
        enable_response_format=values["ENABLE_RESPONSE_FORMAT"],
        enable_thinking=values["ENABLE_THINKING"],
        skip_analysis=values["SKIP_AI_ANALYSIS"],
    )


def load_ai_runtime_values_sync() -> dict[str, Any]:
    return _load_section_sync(
        PLATFORM_AI_RUNTIME_SETTINGS_KEY,
        defaults=_ai_runtime_defaults(),
        seed_loader=_env_ai_runtime_seed,
        normalizer=_normalize_ai_runtime_values,
    )


def save_ai_runtime_values_sync(payload: dict[str, Any]) -> dict[str, Any]:
    return _save_section_sync(
        PLATFORM_AI_RUNTIME_SETTINGS_KEY,
        defaults=_ai_runtime_defaults(),
        payload=payload,
        normalizer=_normalize_ai_runtime_values,
    )


def load_failure_guard_settings_sync() -> dict[str, Any]:
    return _load_section_sync(
        PLATFORM_FAILURE_GUARD_SETTINGS_KEY,
        defaults=_failure_guard_defaults(),
        seed_loader=_env_failure_guard_seed,
        normalizer=_normalize_failure_guard_values,
    )


def save_failure_guard_settings_sync(payload: dict[str, Any]) -> dict[str, Any]:
    return _save_section_sync(
        PLATFORM_FAILURE_GUARD_SETTINGS_KEY,
        defaults=_failure_guard_defaults(),
        payload=payload,
        normalizer=_normalize_failure_guard_values,
    )
