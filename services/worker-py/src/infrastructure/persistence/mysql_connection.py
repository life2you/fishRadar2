"""MySQL database connection and schema initialization helpers."""
from __future__ import annotations

import os
import re
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator
from urllib.parse import parse_qs, unquote, urlparse

try:
    import pymysql
    from pymysql.cursors import DictCursor
except ImportError:  # pragma: no cover - depends on optional dependency
    pymysql = None
    DictCursor = None


MYSQL_BACKEND = "mysql"
MYSQL_BOOTSTRAP_LOCK = threading.Lock()
MYSQL_READY_DATABASES: set[tuple[str, int, str, str]] = set()

MYSQL_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS app_metadata (
        `key` VARCHAR(255) PRIMARY KEY COMMENT '元数据键',
        `value` TEXT NOT NULL COMMENT '元数据值'
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='应用元数据表'
    """,
    """
    CREATE TABLE IF NOT EXISTS tasks (
        id BIGINT PRIMARY KEY COMMENT '任务ID',
        tenant_id BIGINT NULL COMMENT '租户ID',
        task_name VARCHAR(255) NOT NULL COMMENT '任务名称',
        enabled TINYINT(1) NOT NULL COMMENT '是否启用',
        keyword VARCHAR(255) NOT NULL COMMENT '搜索关键词',
        description TEXT COMMENT '任务描述或AI筛选需求',
        analyze_images TINYINT(1) NOT NULL COMMENT '是否分析商品图片',
        max_pages INT NOT NULL COMMENT '最大翻页数',
        personal_only TINYINT(1) NOT NULL COMMENT '是否仅看个人卖家',
        min_price VARCHAR(64) COMMENT '最低价格',
        max_price VARCHAR(64) COMMENT '最高价格',
        cron VARCHAR(255) COMMENT 'Cron调度表达式',
        ai_prompt_base_file VARCHAR(255) NOT NULL COMMENT 'AI基础提示词文件路径',
        ai_prompt_criteria_file VARCHAR(255) NOT NULL COMMENT 'AI分析标准文件路径',
        ai_prompt_base_text LONGTEXT NULL COMMENT 'AI基础提示词文本',
        ai_prompt_criteria_text LONGTEXT NULL COMMENT 'AI分析标准文本',
        ai_prompt_text LONGTEXT NULL COMMENT '最终AI提示词文本',
        account_state_file VARCHAR(255) COMMENT '绑定账号登录态文件路径',
        account_strategy VARCHAR(32) NOT NULL COMMENT '账号使用策略',
        free_shipping TINYINT(1) NOT NULL COMMENT '是否筛选包邮商品',
        new_publish_option VARCHAR(64) COMMENT '发布时间筛选条件',
        region VARCHAR(255) COMMENT '地区筛选条件',
        decision_mode VARCHAR(32) NOT NULL COMMENT '决策模式(ai或keyword)',
        keyword_rules_json LONGTEXT NOT NULL COMMENT '关键词规则JSON',
        is_running TINYINT(1) NOT NULL COMMENT '任务是否运行中'
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='监控任务配置表'
    """,
    """
    CREATE TABLE IF NOT EXISTS result_items (
        id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
        tenant_id BIGINT NULL COMMENT '租户ID',
        result_filename VARCHAR(255) NOT NULL COMMENT '结果集逻辑文件名',
        keyword VARCHAR(255) NOT NULL COMMENT '搜索关键词',
        task_name VARCHAR(255) NOT NULL COMMENT '来源任务名称',
        crawl_time VARCHAR(64) NOT NULL COMMENT '抓取时间',
        publish_time VARCHAR(64) COMMENT '商品发布时间',
        price DOUBLE COMMENT '商品数值价格',
        price_display VARCHAR(64) COMMENT '商品展示价格',
        item_id VARCHAR(255) COMMENT '商品ID',
        title TEXT COMMENT '商品标题',
        link TEXT COMMENT '商品链接',
        link_unique_key VARCHAR(512) NOT NULL COMMENT '商品去重键',
        seller_nickname VARCHAR(255) COMMENT '卖家昵称',
        is_recommended TINYINT(1) NOT NULL COMMENT '是否推荐',
        analysis_source VARCHAR(32) COMMENT '分析来源',
        keyword_hit_count INT NOT NULL COMMENT '关键词命中次数',
        status VARCHAR(32) NOT NULL DEFAULT 'active' COMMENT '结果状态(active/hidden/expired)',
        raw_json LONGTEXT NOT NULL COMMENT '原始结果JSON',
        UNIQUE KEY uniq_result_link (result_filename, link_unique_key)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='监控结果明细表'
    """,
    """
    CREATE TABLE IF NOT EXISTS price_snapshots (
        id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
        tenant_id BIGINT NULL COMMENT '租户ID',
        keyword_slug VARCHAR(255) NOT NULL COMMENT '关键词标准化标识',
        keyword VARCHAR(255) NOT NULL COMMENT '搜索关键词',
        task_name VARCHAR(255) NOT NULL COMMENT '来源任务名称',
        snapshot_time VARCHAR(64) NOT NULL COMMENT '快照时间',
        snapshot_day VARCHAR(32) NOT NULL COMMENT '快照日期',
        run_id VARCHAR(64) NOT NULL COMMENT '单次运行批次ID',
        item_id VARCHAR(255) NOT NULL COMMENT '商品ID',
        title TEXT COMMENT '商品标题',
        price DOUBLE NOT NULL COMMENT '商品价格',
        price_display VARCHAR(64) COMMENT '商品展示价格',
        tags_json LONGTEXT NOT NULL COMMENT '商品标签JSON',
        region VARCHAR(255) COMMENT '发货地区',
        seller VARCHAR(255) COMMENT '卖家昵称',
        publish_time VARCHAR(64) COMMENT '商品发布时间',
        link TEXT COMMENT '商品链接',
        UNIQUE KEY uniq_snapshot_item (keyword_slug, run_id, item_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='价格历史快照表'
    """,
    """
    CREATE TABLE IF NOT EXISTS result_blacklist_rules (
        result_filename VARCHAR(255) PRIMARY KEY COMMENT '结果集逻辑文件名',
        blacklist_keywords_json LONGTEXT NOT NULL COMMENT '黑名单关键词JSON',
        updated_at VARCHAR(64) NOT NULL COMMENT '更新时间'
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='结果黑名单规则表'
    """,
    """
    CREATE TABLE IF NOT EXISTS tenants (
        id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '租户ID',
        name VARCHAR(255) NOT NULL COMMENT '租户名称',
        slug VARCHAR(255) NOT NULL UNIQUE COMMENT '租户唯一标识',
        status VARCHAR(32) NOT NULL COMMENT '租户状态',
        ai_enabled TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否允许租户使用AI分析',
        activation_required TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否需要卡密激活后才能使用',
        activated_at VARCHAR(64) NULL COMMENT '激活时间',
        access_expires_at VARCHAR(64) NULL COMMENT '工作台权限到期时间',
        created_at VARCHAR(64) NOT NULL COMMENT '创建时间'
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='租户表'
    """,
    """
    CREATE TABLE IF NOT EXISTS users (
        id BIGINT PRIMARY KEY COMMENT '用户ID',
        username VARCHAR(255) NOT NULL UNIQUE COMMENT '登录用户名',
        password_hash VARCHAR(512) NOT NULL COMMENT '密码哈希',
        role VARCHAR(32) NOT NULL COMMENT '平台角色',
        status VARCHAR(32) NOT NULL COMMENT '用户状态',
        display_name VARCHAR(255) NULL COMMENT '显示名称',
        created_at VARCHAR(64) NOT NULL COMMENT '创建时间'
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户表'
    """,
    """
    CREATE TABLE IF NOT EXISTS user_tenant_memberships (
        id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
        user_id BIGINT NOT NULL COMMENT '用户ID',
        tenant_id BIGINT NOT NULL COMMENT '租户ID',
        membership_role VARCHAR(32) NOT NULL COMMENT '租户内角色',
        created_at VARCHAR(64) NOT NULL COMMENT '创建时间',
        UNIQUE KEY uniq_user_tenant_membership (user_id, tenant_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户租户关系表'
    """,
    """
    CREATE TABLE IF NOT EXISTS auth_sessions (
        session_token VARCHAR(255) PRIMARY KEY COMMENT '会话令牌',
        user_id BIGINT NOT NULL COMMENT '用户ID',
        tenant_id BIGINT NULL COMMENT '租户ID',
        expires_at VARCHAR(64) NOT NULL COMMENT '过期时间',
        created_at VARCHAR(64) NOT NULL COMMENT '创建时间'
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='登录会话表'
    """,
    """
    CREATE TABLE IF NOT EXISTS account_states (
        id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '登录态记录ID',
        name VARCHAR(255) NOT NULL COMMENT '登录态名称',
        kind VARCHAR(32) NOT NULL COMMENT '登录态类型(account/default)',
        state_json LONGTEXT NOT NULL COMMENT '登录态JSON内容',
        created_at VARCHAR(64) NOT NULL COMMENT '创建时间',
        updated_at VARCHAR(64) NOT NULL COMMENT '更新时间',
        UNIQUE KEY uniq_account_state_kind_name (kind, name)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='登录态存储表'
    """,
    """
    CREATE TABLE IF NOT EXISTS activation_codes (
        id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '卡密ID',
        code VARCHAR(255) NOT NULL UNIQUE COMMENT '激活卡密',
        status VARCHAR(32) NOT NULL COMMENT '卡密状态',
        duration_minutes INT NOT NULL DEFAULT 1440 COMMENT '激活后可使用时长(分钟)',
        note VARCHAR(255) NULL COMMENT '备注',
        created_by_user_id BIGINT NULL COMMENT '创建管理员用户ID',
        redeemed_by_tenant_id BIGINT NULL COMMENT '兑换租户ID',
        redeemed_by_user_id BIGINT NULL COMMENT '兑换用户ID',
        redeemed_at VARCHAR(64) NULL COMMENT '兑换时间',
        created_at VARCHAR(64) NOT NULL COMMENT '创建时间'
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='租户激活卡密表'
    """,
    """
    CREATE TABLE IF NOT EXISTS tenant_notification_settings (
        tenant_id BIGINT PRIMARY KEY COMMENT '租户ID',
        settings_json LONGTEXT NOT NULL COMMENT '通知配置JSON',
        updated_at VARCHAR(64) NOT NULL COMMENT '更新时间'
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='租户通知配置表'
    """,
    """
    CREATE TABLE IF NOT EXISTS announcements (
        id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '公告ID',
        title VARCHAR(255) NOT NULL COMMENT '公告标题',
        content LONGTEXT NOT NULL COMMENT '公告内容',
        level VARCHAR(32) NOT NULL DEFAULT 'info' COMMENT '公告级别',
        status VARCHAR(32) NOT NULL DEFAULT 'draft' COMMENT '公告状态',
        dismissible TINYINT(1) NOT NULL DEFAULT 1 COMMENT '租户端是否可关闭',
        published_at VARCHAR(64) NULL COMMENT '发布时间',
        expires_at VARCHAR(64) NULL COMMENT '过期时间',
        created_at VARCHAR(64) NOT NULL COMMENT '创建时间',
        updated_at VARCHAR(64) NOT NULL COMMENT '更新时间',
        created_by_user_id BIGINT NULL COMMENT '创建人用户ID'
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='平台公告表'
    """,
    """
    CREATE TABLE IF NOT EXISTS ai_accounts (
        id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT 'AI账号ID',
        name VARCHAR(255) NOT NULL COMMENT 'AI账号名称',
        api_key TEXT NULL COMMENT 'AI账号密钥',
        base_url VARCHAR(512) NOT NULL COMMENT 'AI接口地址',
        model_name VARCHAR(255) NOT NULL COMMENT '模型名称',
        supports_image TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否支持图片分析',
        supports_text TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否支持纯文本分析',
        enabled TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
        priority INT NOT NULL DEFAULT 100 COMMENT '优先级，越小越优先',
        notes TEXT NULL COMMENT '备注说明',
        created_at VARCHAR(64) NOT NULL COMMENT '创建时间',
        updated_at VARCHAR(64) NOT NULL COMMENT '更新时间'
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI账号池表'
    """,
    """
    CREATE TABLE IF NOT EXISTS prompt_documents (
        filename VARCHAR(255) PRIMARY KEY COMMENT 'Prompt逻辑文件名',
        content LONGTEXT NOT NULL COMMENT 'Prompt文本内容',
        source VARCHAR(32) NOT NULL DEFAULT 'system' COMMENT '来源(system/generated/manual)',
        created_at VARCHAR(64) NOT NULL COMMENT '创建时间',
        updated_at VARCHAR(64) NOT NULL COMMENT '更新时间'
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Prompt文档表'
    """,
    """
    CREATE TABLE IF NOT EXISTS task_failure_guards (
        task_key VARCHAR(255) PRIMARY KEY COMMENT '任务熔断键',
        consecutive_failures INT NOT NULL DEFAULT 0 COMMENT '连续失败次数',
        paused_until VARCHAR(64) NULL COMMENT '暂停到期时间',
        last_notified_date VARCHAR(32) NULL COMMENT '最近通知日期',
        last_failure_reason TEXT NULL COMMENT '最近失败原因',
        last_failure_at VARCHAR(64) NULL COMMENT '最近失败时间',
        last_success_at VARCHAR(64) NULL COMMENT '最近成功时间',
        cookie_path VARCHAR(512) NULL COMMENT '关联登录态文件路径',
        cookie_mtime DOUBLE NULL COMMENT '登录态文件修改时间',
        updated_at VARCHAR(64) NOT NULL COMMENT '更新时间'
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='任务失败熔断状态表'
    """,
    """
    CREATE TABLE IF NOT EXISTS worker_jobs (
        id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '队列任务ID',
        job_key VARCHAR(64) NULL COMMENT '外部作业标识',
        job_type VARCHAR(64) NOT NULL COMMENT '任务类型(start_task/stop_task)',
        task_id BIGINT NOT NULL COMMENT '关联任务ID',
        task_name VARCHAR(255) NULL COMMENT '任务名称快照',
        status VARCHAR(32) NOT NULL DEFAULT 'pending' COMMENT '队列状态',
        current_step VARCHAR(64) NULL COMMENT '当前步骤',
        message TEXT NULL COMMENT '状态消息',
        steps_json LONGTEXT NULL COMMENT '步骤状态JSON',
        result_json LONGTEXT NULL COMMENT '结果JSON',
        payload_json LONGTEXT NULL COMMENT '附加参数JSON',
        requested_by_user_id BIGINT NULL COMMENT '发起用户ID',
        source VARCHAR(64) NOT NULL DEFAULT 'api' COMMENT '来源',
        worker_id VARCHAR(128) NULL COMMENT '消费Worker标识',
        process_id BIGINT NULL COMMENT '执行进程ID',
        created_at VARCHAR(64) NOT NULL COMMENT '创建时间',
        claimed_at VARCHAR(64) NULL COMMENT '领取时间',
        finished_at VARCHAR(64) NULL COMMENT '结束时间',
        error_message TEXT NULL COMMENT '错误信息'
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Worker任务队列表'
    """,
)

MYSQL_INDEX_DEFINITIONS = (
    ("idx_tasks_name", "tasks", "CREATE INDEX idx_tasks_name ON tasks(task_name)"),
    ("idx_tasks_tenant_id", "tasks", "CREATE INDEX idx_tasks_tenant_id ON tasks(tenant_id)"),
    (
        "idx_results_tenant_filename",
        "result_items",
        "CREATE INDEX idx_results_tenant_filename ON result_items(tenant_id, result_filename, crawl_time)",
    ),
    (
        "idx_results_filename_crawl",
        "result_items",
        "CREATE INDEX idx_results_filename_crawl ON result_items(result_filename, crawl_time)",
    ),
    (
        "idx_results_filename_publish",
        "result_items",
        "CREATE INDEX idx_results_filename_publish ON result_items(result_filename, publish_time)",
    ),
    (
        "idx_worker_jobs_status_created",
        "worker_jobs",
        "CREATE INDEX idx_worker_jobs_status_created ON worker_jobs(status, created_at)",
    ),
    (
        "idx_worker_jobs_task_status",
        "worker_jobs",
        "CREATE INDEX idx_worker_jobs_task_status ON worker_jobs(task_id, status)",
    ),
    (
        "uniq_worker_jobs_job_key",
        "worker_jobs",
        "CREATE UNIQUE INDEX uniq_worker_jobs_job_key ON worker_jobs(job_key)",
    ),
    (
        "idx_results_filename_price",
        "result_items",
        "CREATE INDEX idx_results_filename_price ON result_items(result_filename, price)",
    ),
    (
        "idx_results_filename_recommended",
        "result_items",
        "CREATE INDEX idx_results_filename_recommended ON result_items(result_filename, is_recommended, analysis_source, crawl_time)",
    ),
    (
        "idx_results_filename_status_crawl",
        "result_items",
        "CREATE INDEX idx_results_filename_status_crawl ON result_items(result_filename, status, crawl_time)",
    ),
    (
        "idx_snapshots_tenant_keyword_time",
        "price_snapshots",
        "CREATE INDEX idx_snapshots_tenant_keyword_time ON price_snapshots(tenant_id, keyword_slug, snapshot_time)",
    ),
    (
        "idx_snapshots_keyword_time",
        "price_snapshots",
        "CREATE INDEX idx_snapshots_keyword_time ON price_snapshots(keyword_slug, snapshot_time)",
    ),
    (
        "idx_snapshots_keyword_item_time",
        "price_snapshots",
        "CREATE INDEX idx_snapshots_keyword_item_time ON price_snapshots(keyword_slug, item_id, snapshot_time)",
    ),
    ("idx_users_username", "users", "CREATE INDEX idx_users_username ON users(username)"),
    ("idx_auth_sessions_user_id", "auth_sessions", "CREATE INDEX idx_auth_sessions_user_id ON auth_sessions(user_id)"),
    ("idx_activation_codes_status", "activation_codes", "CREATE INDEX idx_activation_codes_status ON activation_codes(status)"),
    (
        "idx_announcements_status_publish",
        "announcements",
        "CREATE INDEX idx_announcements_status_publish ON announcements(status, published_at)",
    ),
    ("idx_ai_accounts_enabled_priority", "ai_accounts", "CREATE INDEX idx_ai_accounts_enabled_priority ON ai_accounts(enabled, priority, id)"),
    (
        "idx_task_failure_guards_paused_until",
        "task_failure_guards",
        "CREATE INDEX idx_task_failure_guards_paused_until ON task_failure_guards(paused_until)",
    ),
)

MYSQL_TENANT_COLUMNS_MIGRATION_KEY = "migration:mysql_tenant_columns_v1"
MYSQL_TENANT_ACCESS_MIGRATION_KEY = "migration:mysql_tenant_access_v2"
MYSQL_COMMENT_MIGRATION_KEY = "migration:mysql_schema_comments_v2"
MYSQL_AI_ACCOUNTS_MIGRATION_KEY = "migration:mysql_ai_accounts_v1"
MYSQL_TASK_PROMPT_STORAGE_MIGRATION_KEY = "migration:mysql_task_prompt_storage_v1"
MYSQL_ACCOUNT_STATES_MIGRATION_KEY = "migration:mysql_account_states_v1"

MYSQL_COMMENT_STATEMENTS = (
    """
    ALTER TABLE app_metadata
    MODIFY COLUMN `key` VARCHAR(255) NOT NULL COMMENT '元数据键',
    MODIFY COLUMN `value` TEXT NOT NULL COMMENT '元数据值',
    COMMENT = '应用元数据表'
    """,
    """
    ALTER TABLE tasks
    MODIFY COLUMN id BIGINT NOT NULL COMMENT '任务ID',
    MODIFY COLUMN tenant_id BIGINT NULL COMMENT '租户ID',
    MODIFY COLUMN task_name VARCHAR(255) NOT NULL COMMENT '任务名称',
    MODIFY COLUMN enabled TINYINT(1) NOT NULL COMMENT '是否启用',
    MODIFY COLUMN keyword VARCHAR(255) NOT NULL COMMENT '搜索关键词',
    MODIFY COLUMN description TEXT NULL COMMENT '任务描述或AI筛选需求',
    MODIFY COLUMN analyze_images TINYINT(1) NOT NULL COMMENT '是否分析商品图片',
    MODIFY COLUMN max_pages INT NOT NULL COMMENT '最大翻页数',
    MODIFY COLUMN personal_only TINYINT(1) NOT NULL COMMENT '是否仅看个人卖家',
    MODIFY COLUMN min_price VARCHAR(64) NULL COMMENT '最低价格',
    MODIFY COLUMN max_price VARCHAR(64) NULL COMMENT '最高价格',
    MODIFY COLUMN cron VARCHAR(255) NULL COMMENT 'Cron调度表达式',
    MODIFY COLUMN ai_prompt_base_file VARCHAR(255) NOT NULL COMMENT 'AI基础提示词文件路径',
    MODIFY COLUMN ai_prompt_criteria_file VARCHAR(255) NOT NULL COMMENT 'AI分析标准文件路径',
    MODIFY COLUMN ai_prompt_base_text LONGTEXT NULL COMMENT 'AI基础提示词文本',
    MODIFY COLUMN ai_prompt_criteria_text LONGTEXT NULL COMMENT 'AI分析标准文本',
    MODIFY COLUMN ai_prompt_text LONGTEXT NULL COMMENT '最终AI提示词文本',
    MODIFY COLUMN account_state_file VARCHAR(255) NULL COMMENT '绑定账号登录态文件路径',
    MODIFY COLUMN account_strategy VARCHAR(32) NOT NULL COMMENT '账号使用策略',
    MODIFY COLUMN free_shipping TINYINT(1) NOT NULL COMMENT '是否筛选包邮商品',
    MODIFY COLUMN new_publish_option VARCHAR(64) NULL COMMENT '发布时间筛选条件',
    MODIFY COLUMN region VARCHAR(255) NULL COMMENT '地区筛选条件',
    MODIFY COLUMN decision_mode VARCHAR(32) NOT NULL COMMENT '决策模式(ai或keyword)',
    MODIFY COLUMN keyword_rules_json LONGTEXT NOT NULL COMMENT '关键词规则JSON',
    MODIFY COLUMN is_running TINYINT(1) NOT NULL COMMENT '任务是否运行中',
    COMMENT = '监控任务配置表'
    """,
    """
    ALTER TABLE result_items
    MODIFY COLUMN id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
    MODIFY COLUMN tenant_id BIGINT NULL COMMENT '租户ID',
    MODIFY COLUMN result_filename VARCHAR(255) NOT NULL COMMENT '结果集逻辑文件名',
    MODIFY COLUMN keyword VARCHAR(255) NOT NULL COMMENT '搜索关键词',
    MODIFY COLUMN task_name VARCHAR(255) NOT NULL COMMENT '来源任务名称',
    MODIFY COLUMN crawl_time VARCHAR(64) NOT NULL COMMENT '抓取时间',
    MODIFY COLUMN publish_time VARCHAR(64) NULL COMMENT '商品发布时间',
    MODIFY COLUMN price DOUBLE NULL COMMENT '商品数值价格',
    MODIFY COLUMN price_display VARCHAR(64) NULL COMMENT '商品展示价格',
    MODIFY COLUMN item_id VARCHAR(255) NULL COMMENT '商品ID',
    MODIFY COLUMN title TEXT NULL COMMENT '商品标题',
    MODIFY COLUMN link TEXT NULL COMMENT '商品链接',
    MODIFY COLUMN link_unique_key VARCHAR(512) NOT NULL COMMENT '商品去重键',
    MODIFY COLUMN seller_nickname VARCHAR(255) NULL COMMENT '卖家昵称',
    MODIFY COLUMN is_recommended TINYINT(1) NOT NULL COMMENT '是否推荐',
    MODIFY COLUMN analysis_source VARCHAR(32) NULL COMMENT '分析来源',
    MODIFY COLUMN keyword_hit_count INT NOT NULL COMMENT '关键词命中次数',
    MODIFY COLUMN status VARCHAR(32) NOT NULL DEFAULT 'active' COMMENT '结果状态(active/hidden/expired)',
    MODIFY COLUMN raw_json LONGTEXT NOT NULL COMMENT '原始结果JSON',
    COMMENT = '监控结果明细表'
    """,
    """
    ALTER TABLE price_snapshots
    MODIFY COLUMN id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
    MODIFY COLUMN tenant_id BIGINT NULL COMMENT '租户ID',
    MODIFY COLUMN keyword_slug VARCHAR(255) NOT NULL COMMENT '关键词标准化标识',
    MODIFY COLUMN keyword VARCHAR(255) NOT NULL COMMENT '搜索关键词',
    MODIFY COLUMN task_name VARCHAR(255) NOT NULL COMMENT '来源任务名称',
    MODIFY COLUMN snapshot_time VARCHAR(64) NOT NULL COMMENT '快照时间',
    MODIFY COLUMN snapshot_day VARCHAR(32) NOT NULL COMMENT '快照日期',
    MODIFY COLUMN run_id VARCHAR(64) NOT NULL COMMENT '单次运行批次ID',
    MODIFY COLUMN item_id VARCHAR(255) NOT NULL COMMENT '商品ID',
    MODIFY COLUMN title TEXT NULL COMMENT '商品标题',
    MODIFY COLUMN price DOUBLE NOT NULL COMMENT '商品价格',
    MODIFY COLUMN price_display VARCHAR(64) NULL COMMENT '商品展示价格',
    MODIFY COLUMN tags_json LONGTEXT NOT NULL COMMENT '商品标签JSON',
    MODIFY COLUMN region VARCHAR(255) NULL COMMENT '发货地区',
    MODIFY COLUMN seller VARCHAR(255) NULL COMMENT '卖家昵称',
    MODIFY COLUMN publish_time VARCHAR(64) NULL COMMENT '商品发布时间',
    MODIFY COLUMN link TEXT NULL COMMENT '商品链接',
    COMMENT = '价格历史快照表'
    """,
    """
    ALTER TABLE result_blacklist_rules
    MODIFY COLUMN result_filename VARCHAR(255) NOT NULL COMMENT '结果集逻辑文件名',
    MODIFY COLUMN blacklist_keywords_json LONGTEXT NOT NULL COMMENT '黑名单关键词JSON',
    MODIFY COLUMN updated_at VARCHAR(64) NOT NULL COMMENT '更新时间',
    COMMENT = '结果黑名单规则表'
    """,
    """
    ALTER TABLE ai_accounts
    MODIFY COLUMN id BIGINT NOT NULL AUTO_INCREMENT COMMENT 'AI账号ID',
    MODIFY COLUMN name VARCHAR(255) NOT NULL COMMENT 'AI账号名称',
    MODIFY COLUMN api_key TEXT NULL COMMENT 'AI账号密钥',
    MODIFY COLUMN base_url VARCHAR(512) NOT NULL COMMENT 'AI接口地址',
    MODIFY COLUMN model_name VARCHAR(255) NOT NULL COMMENT '模型名称',
    MODIFY COLUMN supports_image TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否支持图片分析',
    MODIFY COLUMN supports_text TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否支持纯文本分析',
    MODIFY COLUMN enabled TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
    MODIFY COLUMN priority INT NOT NULL DEFAULT 100 COMMENT '优先级，越小越优先',
    MODIFY COLUMN notes TEXT NULL COMMENT '备注说明',
    MODIFY COLUMN created_at VARCHAR(64) NOT NULL COMMENT '创建时间',
    MODIFY COLUMN updated_at VARCHAR(64) NOT NULL COMMENT '更新时间',
    COMMENT = 'AI账号池表'
    """,
    """
    ALTER TABLE tenants
    MODIFY COLUMN id BIGINT NOT NULL AUTO_INCREMENT COMMENT '租户ID',
    MODIFY COLUMN name VARCHAR(255) NOT NULL COMMENT '租户名称',
    MODIFY COLUMN slug VARCHAR(255) NOT NULL COMMENT '租户唯一标识',
    MODIFY COLUMN status VARCHAR(32) NOT NULL COMMENT '租户状态',
    MODIFY COLUMN ai_enabled TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否允许租户使用AI分析',
    MODIFY COLUMN activation_required TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否需要卡密激活后才能使用',
    MODIFY COLUMN activated_at VARCHAR(64) NULL COMMENT '激活时间',
    MODIFY COLUMN access_expires_at VARCHAR(64) NULL COMMENT '工作台权限到期时间',
    MODIFY COLUMN created_at VARCHAR(64) NOT NULL COMMENT '创建时间',
    COMMENT = '租户表'
    """,
    """
    ALTER TABLE users
    MODIFY COLUMN id BIGINT NOT NULL COMMENT '用户ID',
    MODIFY COLUMN username VARCHAR(255) NOT NULL COMMENT '登录用户名',
    MODIFY COLUMN password_hash VARCHAR(512) NOT NULL COMMENT '密码哈希',
    MODIFY COLUMN role VARCHAR(32) NOT NULL COMMENT '平台角色',
    MODIFY COLUMN status VARCHAR(32) NOT NULL COMMENT '用户状态',
    MODIFY COLUMN display_name VARCHAR(255) NULL COMMENT '显示名称',
    MODIFY COLUMN created_at VARCHAR(64) NOT NULL COMMENT '创建时间',
    COMMENT = '用户表'
    """,
    """
    ALTER TABLE user_tenant_memberships
    MODIFY COLUMN id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
    MODIFY COLUMN user_id BIGINT NOT NULL COMMENT '用户ID',
    MODIFY COLUMN tenant_id BIGINT NOT NULL COMMENT '租户ID',
    MODIFY COLUMN membership_role VARCHAR(32) NOT NULL COMMENT '租户内角色',
    MODIFY COLUMN created_at VARCHAR(64) NOT NULL COMMENT '创建时间',
    COMMENT = '用户租户关系表'
    """,
    """
    ALTER TABLE auth_sessions
    MODIFY COLUMN session_token VARCHAR(255) NOT NULL COMMENT '会话令牌',
    MODIFY COLUMN user_id BIGINT NOT NULL COMMENT '用户ID',
    MODIFY COLUMN tenant_id BIGINT NULL COMMENT '租户ID',
    MODIFY COLUMN expires_at VARCHAR(64) NOT NULL COMMENT '过期时间',
    MODIFY COLUMN created_at VARCHAR(64) NOT NULL COMMENT '创建时间',
    COMMENT = '登录会话表'
    """,
    """
    ALTER TABLE account_states
    MODIFY COLUMN id BIGINT NOT NULL AUTO_INCREMENT COMMENT '登录态记录ID',
    MODIFY COLUMN name VARCHAR(255) NOT NULL COMMENT '登录态名称',
    MODIFY COLUMN kind VARCHAR(32) NOT NULL COMMENT '登录态类型(account/default)',
    MODIFY COLUMN state_json LONGTEXT NOT NULL COMMENT '登录态JSON内容',
    MODIFY COLUMN created_at VARCHAR(64) NOT NULL COMMENT '创建时间',
    MODIFY COLUMN updated_at VARCHAR(64) NOT NULL COMMENT '更新时间',
    COMMENT = '登录态存储表'
    """,
    """
    ALTER TABLE activation_codes
    MODIFY COLUMN id BIGINT NOT NULL AUTO_INCREMENT COMMENT '卡密ID',
    MODIFY COLUMN code VARCHAR(255) NOT NULL COMMENT '激活卡密',
    MODIFY COLUMN status VARCHAR(32) NOT NULL COMMENT '卡密状态',
    MODIFY COLUMN duration_minutes INT NOT NULL DEFAULT 1440 COMMENT '激活后可使用时长(分钟)',
    MODIFY COLUMN note VARCHAR(255) NULL COMMENT '备注',
    MODIFY COLUMN created_by_user_id BIGINT NULL COMMENT '创建管理员用户ID',
    MODIFY COLUMN redeemed_by_tenant_id BIGINT NULL COMMENT '兑换租户ID',
    MODIFY COLUMN redeemed_by_user_id BIGINT NULL COMMENT '兑换用户ID',
    MODIFY COLUMN redeemed_at VARCHAR(64) NULL COMMENT '兑换时间',
    MODIFY COLUMN created_at VARCHAR(64) NOT NULL COMMENT '创建时间',
    COMMENT = '租户激活卡密表'
    """,
    """
    ALTER TABLE tenant_notification_settings
    MODIFY COLUMN tenant_id BIGINT NOT NULL COMMENT '租户ID',
    MODIFY COLUMN settings_json LONGTEXT NOT NULL COMMENT '通知配置JSON',
    MODIFY COLUMN updated_at VARCHAR(64) NOT NULL COMMENT '更新时间',
    COMMENT = '租户通知配置表'
    """,
    """
    ALTER TABLE announcements
    MODIFY COLUMN id BIGINT NOT NULL AUTO_INCREMENT COMMENT '公告ID',
    MODIFY COLUMN title VARCHAR(255) NOT NULL COMMENT '公告标题',
    MODIFY COLUMN content LONGTEXT NOT NULL COMMENT '公告内容',
    MODIFY COLUMN level VARCHAR(32) NOT NULL DEFAULT 'info' COMMENT '公告级别',
    MODIFY COLUMN status VARCHAR(32) NOT NULL DEFAULT 'draft' COMMENT '公告状态',
    MODIFY COLUMN dismissible TINYINT(1) NOT NULL DEFAULT 1 COMMENT '租户端是否可关闭',
    MODIFY COLUMN published_at VARCHAR(64) NULL COMMENT '发布时间',
    MODIFY COLUMN expires_at VARCHAR(64) NULL COMMENT '过期时间',
    MODIFY COLUMN created_at VARCHAR(64) NOT NULL COMMENT '创建时间',
    MODIFY COLUMN updated_at VARCHAR(64) NOT NULL COMMENT '更新时间',
    MODIFY COLUMN created_by_user_id BIGINT NULL COMMENT '创建人用户ID',
    COMMENT = '平台公告表'
    """,
    """
    ALTER TABLE task_failure_guards
    MODIFY COLUMN task_key VARCHAR(255) NOT NULL COMMENT '任务熔断键',
    MODIFY COLUMN consecutive_failures INT NOT NULL DEFAULT 0 COMMENT '连续失败次数',
    MODIFY COLUMN paused_until VARCHAR(64) NULL COMMENT '暂停到期时间',
    MODIFY COLUMN last_notified_date VARCHAR(32) NULL COMMENT '最近通知日期',
    MODIFY COLUMN last_failure_reason TEXT NULL COMMENT '最近失败原因',
    MODIFY COLUMN last_failure_at VARCHAR(64) NULL COMMENT '最近失败时间',
    MODIFY COLUMN last_success_at VARCHAR(64) NULL COMMENT '最近成功时间',
    MODIFY COLUMN cookie_path VARCHAR(512) NULL COMMENT '关联登录态文件路径',
    MODIFY COLUMN cookie_mtime DOUBLE NULL COMMENT '登录态文件修改时间',
    MODIFY COLUMN updated_at VARCHAR(64) NOT NULL COMMENT '更新时间',
    COMMENT = '任务失败熔断状态表'
    """,
)


@dataclass(frozen=True)
class MysqlConfig:
    host: str
    port: int
    user: str
    password: str
    database: str
    charset: str = "utf8mb4"


class DatabaseCursor:
    def __init__(self, cursor):
        self._cursor = cursor

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    @property
    def rowcount(self) -> int:
        return int(getattr(self._cursor, "rowcount", 0) or 0)

    @property
    def lastrowid(self) -> Any:
        return getattr(self._cursor, "lastrowid", None)


class DatabaseConnection:
    def __init__(self, raw_connection):
        self.backend = MYSQL_BACKEND
        self._raw = raw_connection

    def execute(self, query: str, params: tuple | list | dict | None = None) -> DatabaseCursor:
        cursor = self._raw.cursor()
        normalized_params = params or ()
        cursor.execute(
            _adapt_query(query, normalized_params),
            _normalize_params(normalized_params),
        )
        return DatabaseCursor(cursor)

    def commit(self) -> None:
        self._raw.commit()

    def rollback(self) -> None:
        self._raw.rollback()

    def close(self) -> None:
        self._raw.close()


def get_database_url() -> str:
    url = str(os.getenv("APP_DATABASE_URL", "") or "").strip()
    if not url:
        raise RuntimeError("APP_DATABASE_URL 未设置。当前版本仅支持 MySQL。")
    if not url.startswith(("mysql://", "mysql+pymysql://")):
        raise ValueError("APP_DATABASE_URL 仅支持 mysql:// 或 mysql+pymysql://")
    return url


def _parse_mysql_config(url: str) -> MysqlConfig:
    parsed = urlparse(url)
    if parsed.scheme not in {"mysql", "mysql+pymysql"}:
        raise ValueError("Unsupported MySQL URL scheme")
    database = parsed.path.lstrip("/")
    if not database:
        raise ValueError("MySQL URL must include a database name")
    query = parse_qs(parsed.query)
    charset = (query.get("charset") or ["utf8mb4"])[0]
    return MysqlConfig(
        host=parsed.hostname or "127.0.0.1",
        port=int(parsed.port or 3306),
        user=unquote(parsed.username or ""),
        password=unquote(parsed.password or ""),
        database=database,
        charset=charset,
    )


def _mysql_connect(config: MysqlConfig, *, with_database: bool):
    if pymysql is None:  # pragma: no cover
        raise RuntimeError("PyMySQL is required when APP_DATABASE_URL points to MySQL")
    kwargs = {
        "host": config.host,
        "port": config.port,
        "user": config.user,
        "password": config.password,
        "charset": config.charset,
        "autocommit": False,
        "cursorclass": DictCursor,
    }
    if with_database:
        kwargs["database"] = config.database
    return pymysql.connect(**kwargs)


def _escape_mysql_identifier(identifier: str) -> str:
    return identifier.replace("`", "``")


def _ensure_mysql_database(config: MysqlConfig) -> None:
    ready_key = (config.host, config.port, config.user, config.database)
    if ready_key in MYSQL_READY_DATABASES:
        return
    with MYSQL_BOOTSTRAP_LOCK:
        if ready_key in MYSQL_READY_DATABASES:
            return
        bootstrap_conn = _mysql_connect(config, with_database=False)
        try:
            db_name = _escape_mysql_identifier(config.database)
            bootstrap_conn.cursor().execute(
                f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            bootstrap_conn.commit()
        finally:
            bootstrap_conn.close()
        MYSQL_READY_DATABASES.add(ready_key)


def _normalize_params(params):
    if isinstance(params, dict):
        return params
    return tuple(params)


def _adapt_query(query: str, params=None) -> str:
    sql = query.replace("INSERT OR IGNORE INTO", "INSERT IGNORE INTO")
    sql = sql.replace("INSERT OR REPLACE INTO", "REPLACE INTO")
    if isinstance(params, dict):
        return re.sub(r":([A-Za-z_][A-Za-z0-9_]*)", r"%(\1)s", sql)
    return sql.replace("?", "%s")


def _mysql_column_exists(conn: DatabaseConnection, table_name: str, column_name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = ?
          AND column_name = ?
        LIMIT 1
        """,
        (table_name, column_name),
    ).fetchone()
    return row is not None


def _mysql_index_exists(conn: DatabaseConnection, table_name: str, index_name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name = ?
          AND index_name = ?
        LIMIT 1
        """,
        (table_name, index_name),
    ).fetchone()
    return row is not None


def init_schema(conn: DatabaseConnection) -> None:
    for statement in MYSQL_SCHEMA_STATEMENTS:
        conn.execute(statement)
    _migrate_tenant_columns(conn)
    _migrate_tenant_access_controls(conn)
    _migrate_result_items_status(conn)
    _migrate_task_prompt_storage(conn)
    _migrate_account_states(conn)
    _migrate_worker_jobs(conn)
    _apply_mysql_comments(conn)
    for index_name, table_name, statement in MYSQL_INDEX_DEFINITIONS:
        if not _mysql_index_exists(conn, table_name, index_name):
            conn.execute(statement)
    conn.commit()


def _migrate_result_items_status(conn: DatabaseConnection) -> None:
    row = conn.execute(
        "SELECT value FROM app_metadata WHERE `key` = ?",
        ("migration:result_items_status",),
    ).fetchone()
    if row is not None:
        return

    if not _mysql_column_exists(conn, "result_items", "status"):
        conn.execute(
            "ALTER TABLE result_items ADD COLUMN status VARCHAR(32) NOT NULL DEFAULT 'active'"
        )
    conn.execute(
        "INSERT OR REPLACE INTO app_metadata(`key`, value) VALUES (?, 'done')",
        ("migration:result_items_status",),
    )
    if not _mysql_index_exists(conn, "result_items", "idx_results_filename_status_crawl"):
        conn.execute(
            "CREATE INDEX idx_results_filename_status_crawl ON result_items(result_filename, status, crawl_time)"
        )


def _migrate_tenant_columns(conn: DatabaseConnection) -> None:
    row = conn.execute(
        "SELECT value FROM app_metadata WHERE `key` = ?",
        (MYSQL_TENANT_COLUMNS_MIGRATION_KEY,),
    ).fetchone()
    if row is not None:
        return

    for table_name in ("tasks", "result_items", "price_snapshots"):
        if not _mysql_column_exists(conn, table_name, "tenant_id"):
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN tenant_id BIGINT NULL")

    conn.execute(
        "INSERT OR REPLACE INTO app_metadata(`key`, value) VALUES (?, 'done')",
        (MYSQL_TENANT_COLUMNS_MIGRATION_KEY,),
    )


def _migrate_tenant_access_controls(conn: DatabaseConnection) -> None:
    row = conn.execute(
        "SELECT value FROM app_metadata WHERE `key` = ?",
        (MYSQL_TENANT_ACCESS_MIGRATION_KEY,),
    ).fetchone()
    if row is not None:
        return

    tenant_columns = (
        ("ai_enabled", "TINYINT(1) NOT NULL DEFAULT 0"),
        ("activation_required", "TINYINT(1) NOT NULL DEFAULT 1"),
        ("activated_at", "VARCHAR(64) NULL"),
        ("access_expires_at", "VARCHAR(64) NULL"),
    )
    for column_name, column_type in tenant_columns:
        if not _mysql_column_exists(conn, "tenants", column_name):
            conn.execute(f"ALTER TABLE tenants ADD COLUMN {column_name} {column_type}")

    if not _mysql_column_exists(conn, "activation_codes", "duration_minutes"):
        conn.execute(
            "ALTER TABLE activation_codes ADD COLUMN duration_minutes INT NOT NULL DEFAULT 1440"
        )

    conn.execute(
        """
        UPDATE tenants
        SET ai_enabled = COALESCE(ai_enabled, 0),
            activation_required = COALESCE(activation_required, 1)
        """
    )
    conn.execute(
        """
        UPDATE activation_codes
        SET duration_minutes = COALESCE(duration_minutes, 1440)
        """
    )
    conn.execute(
        """
        UPDATE tenants
        SET activation_required = 0
        WHERE slug = ?
        """,
        ("platform-admin",),
    )
    conn.execute(
        "INSERT OR REPLACE INTO app_metadata(`key`, value) VALUES (?, 'done')",
        (MYSQL_TENANT_ACCESS_MIGRATION_KEY,),
    )


def _apply_mysql_comments(conn: DatabaseConnection) -> None:
    row = conn.execute(
        "SELECT value FROM app_metadata WHERE `key` = ?",
        (MYSQL_COMMENT_MIGRATION_KEY,),
    ).fetchone()
    if row is not None:
        return
    for statement in MYSQL_COMMENT_STATEMENTS:
        conn.execute(statement)
    conn.execute(
        "INSERT OR REPLACE INTO app_metadata(`key`, value) VALUES (?, 'done')",
        (MYSQL_COMMENT_MIGRATION_KEY,),
    )


def _migrate_task_prompt_storage(conn: DatabaseConnection) -> None:
    row = conn.execute(
        "SELECT value FROM app_metadata WHERE `key` = ?",
        (MYSQL_TASK_PROMPT_STORAGE_MIGRATION_KEY,),
    ).fetchone()
    if row is not None:
        return

    column_definitions = (
        ("ai_prompt_base_text", "LONGTEXT NULL COMMENT 'AI基础提示词文本'"),
        ("ai_prompt_criteria_text", "LONGTEXT NULL COMMENT 'AI分析标准文本'"),
        ("ai_prompt_text", "LONGTEXT NULL COMMENT '最终AI提示词文本'"),
    )
    for column_name, column_sql in column_definitions:
        if not _mysql_column_exists(conn, "tasks", column_name):
            conn.execute(f"ALTER TABLE tasks ADD COLUMN {column_name} {column_sql}")

    from src.services.task_prompt_service import build_task_prompt_payload

    rows = conn.execute(
        """
        SELECT id, decision_mode, ai_prompt_base_file, ai_prompt_criteria_file,
               ai_prompt_base_text, ai_prompt_criteria_text, ai_prompt_text
        FROM tasks
        """
    ).fetchall()
    for row in rows:
        decision_mode = str(row.get("decision_mode") or "ai").strip().lower()
        if decision_mode == "keyword":
            conn.execute(
                """
                UPDATE tasks
                SET ai_prompt_base_text = COALESCE(ai_prompt_base_text, ''),
                    ai_prompt_criteria_text = COALESCE(ai_prompt_criteria_text, ''),
                    ai_prompt_text = ''
                WHERE id = ?
                """,
                (row["id"],),
            )
            continue

        payload = build_task_prompt_payload(
            base_prompt_file=str(row.get("ai_prompt_base_file") or "").strip(),
            criteria_file=str(row.get("ai_prompt_criteria_file") or "").strip(),
            base_prompt_text=row.get("ai_prompt_base_text"),
            criteria_text=row.get("ai_prompt_criteria_text"),
        )
        conn.execute(
            """
            UPDATE tasks
            SET ai_prompt_base_text = ?,
                ai_prompt_criteria_text = ?,
                ai_prompt_text = ?
            WHERE id = ?
            """,
            (
                payload["ai_prompt_base_text"],
                payload["ai_prompt_criteria_text"],
                payload["ai_prompt_text"],
                row["id"],
            ),
        )

    conn.execute(
        "INSERT OR REPLACE INTO app_metadata(`key`, value) VALUES (?, 'done')",
        (MYSQL_TASK_PROMPT_STORAGE_MIGRATION_KEY,),
    )


def _migrate_account_states(conn: DatabaseConnection) -> None:
    row = conn.execute(
        "SELECT value FROM app_metadata WHERE `key` = ?",
        (MYSQL_ACCOUNT_STATES_MIGRATION_KEY,),
    ).fetchone()
    if row is not None:
        return
    if not _mysql_column_exists(conn, "account_states", "kind"):
        conn.execute(
            "ALTER TABLE account_states ADD COLUMN kind VARCHAR(32) NOT NULL DEFAULT 'account' COMMENT '登录态类型(account/default)'"
        )
    if not _mysql_column_exists(conn, "account_states", "state_json"):
        conn.execute(
            "ALTER TABLE account_states ADD COLUMN state_json LONGTEXT NOT NULL COMMENT '登录态JSON内容'"
        )
    if not _mysql_column_exists(conn, "account_states", "created_at"):
        conn.execute(
            "ALTER TABLE account_states ADD COLUMN created_at VARCHAR(64) NOT NULL DEFAULT '' COMMENT '创建时间'"
        )
    if not _mysql_column_exists(conn, "account_states", "updated_at"):
        conn.execute(
            "ALTER TABLE account_states ADD COLUMN updated_at VARCHAR(64) NOT NULL DEFAULT '' COMMENT '更新时间'"
        )
    conn.execute(
        "INSERT OR REPLACE INTO app_metadata(`key`, value) VALUES (?, 'done')",
        (MYSQL_ACCOUNT_STATES_MIGRATION_KEY,),
    )


def _migrate_worker_jobs(conn: DatabaseConnection) -> None:
    row = conn.execute(
        "SELECT value FROM app_metadata WHERE `key` = ?",
        ("migration:worker_jobs_v2",),
    ).fetchone()
    if row is not None:
        return

    column_definitions = (
        ("job_key", "VARCHAR(64) NULL COMMENT '外部作业标识'"),
        ("task_name", "VARCHAR(255) NULL COMMENT '任务名称快照'"),
        ("current_step", "VARCHAR(64) NULL COMMENT '当前步骤'"),
        ("message", "TEXT NULL COMMENT '状态消息'"),
        ("steps_json", "LONGTEXT NULL COMMENT '步骤状态JSON'"),
        ("result_json", "LONGTEXT NULL COMMENT '结果JSON'"),
    )
    for column_name, column_sql in column_definitions:
        if not _mysql_column_exists(conn, "worker_jobs", column_name):
            conn.execute(f"ALTER TABLE worker_jobs ADD COLUMN {column_name} {column_sql}")

    conn.execute(
        "INSERT OR REPLACE INTO app_metadata(`key`, value) VALUES (?, 'done')",
        ("migration:worker_jobs_v2",),
    )


@contextmanager
def mysql_connection(db_path: str | None = None) -> Iterator[DatabaseConnection]:
    """Connect to MySQL through APP_DATABASE_URL."""
    if db_path is not None:
        raise ValueError("db_path 已不再支持。当前版本仅支持 MySQL。")

    config = _parse_mysql_config(get_database_url())
    _ensure_mysql_database(config)
    raw = _mysql_connect(config, with_database=True)
    conn = DatabaseConnection(raw)
    try:
        yield conn
    except Exception:
        try:
            conn.rollback()
        finally:
            conn.close()
        raise
    else:
        conn.close()
