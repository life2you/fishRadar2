from datetime import datetime, timedelta
import asyncio

from src.infrastructure.persistence.mysql_bootstrap import bootstrap_mysql_storage
from src.infrastructure.persistence.mysql_connection import mysql_connection
from src.services.result_storage_service import save_result_record
from src.services.auth_service import (
    authenticate_credentials_sync,
    create_activation_codes_sync,
    get_tenant_detail_sync,
    redeem_activation_code_sync,
    register_tenant_user_sync,
    update_tenant_access_sync,
)


def test_tenant_registration_requires_activation_before_workspace_access(tmp_path, monkeypatch, mysql_test_env):
    monkeypatch.chdir(tmp_path)

    bootstrap_mysql_storage(
        legacy_result_dir=str(tmp_path / "jsonl"),
        legacy_price_history_dir=str(tmp_path / "price_history"),
    )

    registered = register_tenant_user_sync(
        username="tenant_alpha",
        password="secret123",
        tenant_name="Alpha Studio",
        display_name="Alpha",
    )
    assert registered.role == "tenant"
    assert registered.workspace_enabled is False
    assert registered.can_use_ai is False
    assert registered.allowed_routes == ["activate"]

    codes = create_activation_codes_sync(
        quantity=1,
        duration_minutes=60,
        note="alpha",
        created_by_user_id=1,
    )
    activated = redeem_activation_code_sync(codes[0]["code"], registered)
    assert activated.workspace_enabled is True
    assert activated.can_use_ai is False
    assert activated.allowed_routes == ["tasks", "results", "notifications"]
    assert activated.tenant_access_expires_at is not None
    assert datetime.fromisoformat(activated.tenant_access_expires_at) > datetime.now()

    tenant_id = activated.tenant_id
    assert tenant_id is not None
    update_tenant_access_sync(tenant_id, ai_enabled=True)

    refreshed = authenticate_credentials_sync("tenant_alpha", "secret123")
    assert refreshed is not None
    assert refreshed.workspace_enabled is True
    assert refreshed.can_use_ai is True

    expired_at = (datetime.now() - timedelta(minutes=5)).isoformat()
    with mysql_connection() as conn:
        conn.execute(
            "UPDATE tenants SET access_expires_at = ? WHERE id = ?",
            (expired_at, tenant_id),
        )
        conn.commit()

    expired = authenticate_credentials_sync("tenant_alpha", "secret123")
    assert expired is not None
    assert expired.workspace_enabled is False
    assert expired.access_expired is True
    assert expired.allowed_routes == ["activate"]

    renew_codes = create_activation_codes_sync(
        quantity=1,
        duration_minutes=1440,
        note="renewal",
        created_by_user_id=1,
    )
    renewed = redeem_activation_code_sync(renew_codes[0]["code"], expired)
    assert renewed.workspace_enabled is True
    assert renewed.access_expired is False


def test_extend_tenant_access_and_detail_metrics(tmp_path, monkeypatch, mysql_test_env):
    monkeypatch.chdir(tmp_path)

    bootstrap_mysql_storage(
        legacy_result_dir=str(tmp_path / "jsonl"),
        legacy_price_history_dir=str(tmp_path / "price_history"),
    )

    registered = register_tenant_user_sync(
        username="tenant_beta",
        password="secret123",
        tenant_name="Beta Studio",
        display_name="Beta",
    )
    codes = create_activation_codes_sync(
        quantity=1,
        duration_minutes=60,
        note="beta",
        created_by_user_id=1,
    )
    activated = redeem_activation_code_sync(codes[0]["code"], registered)
    tenant_id = activated.tenant_id
    assert tenant_id is not None
    original_expiry = datetime.fromisoformat(activated.tenant_access_expires_at)

    updated = update_tenant_access_sync(tenant_id, extend_access_minutes=1440)
    assert updated["access_expires_at"] is not None
    assert datetime.fromisoformat(updated["access_expires_at"]) > original_expiry

    with mysql_connection() as conn:
        conn.execute(
            """
            INSERT INTO tasks (
                id, tenant_id, task_name, enabled, keyword, description, analyze_images, max_pages,
                personal_only, min_price, max_price, cron, ai_prompt_base_file,
                ai_prompt_criteria_file, account_state_file, account_strategy, free_shipping,
                new_publish_option, region, decision_mode, keyword_rules_json, is_running
            ) VALUES (?, ?, ?, 1, ?, '', 1, 3, 1, NULL, NULL, NULL, 'prompts/base_prompt.txt',
                '', NULL, 'auto', 1, NULL, NULL, 'keyword', '[]', 1)
            """,
            (1, tenant_id, "Beta Task", "相机"),
        )
        conn.commit()

    asyncio.run(
        save_result_record(
            {
                "爬取时间": datetime.now().isoformat(),
                "搜索关键字": "xiangji",
                "任务名称": "Beta Task",
                "商品信息": {
                    "商品ID": "item-1",
                    "商品标题": "Beta Item",
                    "商品链接": "https://example.com/item-1",
                    "当前售价": "¥1200",
                    "发布时间": datetime.now().isoformat(),
                },
                "卖家信息": {"卖家昵称": "seller"},
                "ai_analysis": {
                    "analysis_source": "ai",
                    "is_recommended": True,
                },
            },
            keyword="xiangji",
            tenant_scope=tenant_id,
        )
    )

    detail = get_tenant_detail_sync(tenant_id)
    assert detail["tenant"]["id"] == tenant_id
    assert detail["metrics"]["task_count"] == 1
    assert detail["metrics"]["running_task_count"] == 1
    assert detail["metrics"]["result_file_count"] == 1
    assert detail["metrics"]["recommended_item_count"] == 1
