"""
兼容层：保留旧模块导出，内部统一转向新的 settings 配置体系。
"""
from __future__ import annotations

import os
import sys

from openai import AsyncOpenAI

from src.infrastructure.config.settings import scraper_settings, settings
from src.services.notification_config_service import load_notification_settings
from src.services.platform_settings_service import load_ai_runtime_settings_sync


_ai_runtime = load_ai_runtime_settings_sync()
_notification_settings = load_notification_settings()

STATE_FILE = scraper_settings.state_file
IMAGE_SAVE_DIR = settings.image_save_dir
TASK_IMAGE_DIR_PREFIX = settings.task_image_dir_prefix

API_URL_PATTERN = "h5api.m.goofish.com/h5/mtop.taobao.idlemtopsearch.pc.search"
DETAIL_API_URL_PATTERN = "h5api.m.goofish.com/h5/mtop.taobao.idle.pc.detail"

PROXY_URL = _ai_runtime.proxy_url
RUN_HEADLESS = scraper_settings.run_headless
LOGIN_IS_EDGE = scraper_settings.login_is_edge
RUNNING_IN_DOCKER = scraper_settings.running_in_docker
AI_DEBUG_MODE = _ai_runtime.debug_mode
SKIP_AI_ANALYSIS = _ai_runtime.skip_analysis
ENABLE_THINKING = _ai_runtime.enable_thinking
ENABLE_RESPONSE_FORMAT = _ai_runtime.enable_response_format

NTFY_TOPIC_URL = _notification_settings.ntfy_topic_url
GOTIFY_URL = _notification_settings.gotify_url
GOTIFY_TOKEN = _notification_settings.gotify_token
BARK_URL = _notification_settings.bark_url
WX_BOT_URL = _notification_settings.wx_bot_url
TELEGRAM_BOT_TOKEN = _notification_settings.telegram_bot_token
TELEGRAM_CHAT_ID = _notification_settings.telegram_chat_id
WEBHOOK_URL = _notification_settings.webhook_url
WEBHOOK_METHOD = _notification_settings.webhook_method
WEBHOOK_HEADERS = _notification_settings.webhook_headers
WEBHOOK_CONTENT_TYPE = _notification_settings.webhook_content_type
WEBHOOK_QUERY_PARAMETERS = _notification_settings.webhook_query_parameters
WEBHOOK_BODY = _notification_settings.webhook_body
PCURL_TO_MOBILE = _notification_settings.pcurl_to_mobile

IMAGE_DOWNLOAD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:139.0) Gecko/20100101 Firefox/139.0",
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

os.makedirs(IMAGE_SAVE_DIR, exist_ok=True)

if PROXY_URL:
    os.environ["HTTP_PROXY"] = PROXY_URL
    os.environ["HTTPS_PROXY"] = PROXY_URL

client: AsyncOpenAI | None = None


def get_ai_request_params(**kwargs):
    if ENABLE_THINKING:
        kwargs["extra_body"] = {"enable_thinking": False}

    if not ENABLE_RESPONSE_FORMAT and "text" in kwargs:
        text_config = kwargs.get("text")
        if isinstance(text_config, dict):
            text_config = dict(text_config)
            text_config.pop("format", None)
            if text_config:
                kwargs["text"] = text_config
            else:
                del kwargs["text"]
    return kwargs
