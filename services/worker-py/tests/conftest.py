import json
import os
import re
import sys
import uuid
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import pytest


repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))


DEFAULT_TEST_MYSQL_URL = os.getenv(
    "TEST_MYSQL_URL",
    "mysql://root:123456@127.0.0.1:3306/fishradar_pytest?charset=utf8mb4",
)


def build_test_database_url(test_name: str) -> str:
    parsed = urlparse(DEFAULT_TEST_MYSQL_URL)
    base_database = parsed.path.lstrip("/") or "fishradar_pytest"
    suffix = re.sub(r"[^a-z0-9]+", "_", test_name.lower()).strip("_") or "case"
    unique_suffix = uuid.uuid4().hex[:8]
    max_total_length = 64
    reserved = len(unique_suffix) + 2
    max_base_length = max_total_length - reserved - 16
    trimmed_base = base_database[:max(12, max_base_length)]
    max_suffix_length = max_total_length - len(trimmed_base) - reserved
    suffix = suffix[:max(8, max_suffix_length)]
    database_name = f"{trimmed_base}_{suffix}_{unique_suffix}"
    query = urlencode(dict(parse_qsl(parsed.query, keep_blank_values=True)) or {"charset": "utf8mb4"})
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            f"/{database_name}",
            "",
            query,
            "",
        )
    )


@pytest.fixture()
def mysql_test_env(monkeypatch, request):
    database_url = build_test_database_url(request.node.name)
    monkeypatch.setenv("APP_DATABASE_URL", database_url)
    return database_url


@pytest.fixture()
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture()
def load_json_fixture(fixtures_dir):
    def _load(name: str):
        return json.loads((fixtures_dir / name).read_text(encoding="utf-8"))

    return _load
