import asyncio
import importlib
import sys
import types

from src.domain.models.task import Task


def test_cli_runs_single_task_with_prompt(tmp_path, load_json_fixture, monkeypatch):
    fake_scraper = types.ModuleType("src.scraper")

    async def placeholder_scrape(task_config, debug_limit):
        return 0

    fake_scraper.scrape_xianyu = placeholder_scrape
    monkeypatch.setitem(sys.modules, "src.scraper", fake_scraper)
    sys.modules.pop("spider_v2", None)

    spider_v2 = importlib.import_module("spider_v2")
    config_data = load_json_fixture("config.sample.json")
    base_prompt = "Base prompt. " + ("x" * 120) + " {{CRITERIA_SECTION}}"
    criteria_prompt = "Criteria text for A7M4."
    final_prompt = base_prompt.replace("{{CRITERIA_SECTION}}", criteria_prompt)

    state_path = tmp_path / "state.json"
    state_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(spider_v2, "STATE_FILE", str(state_path))
    monkeypatch.setattr(
        spider_v2,
        "materialize_runtime_account_states_sync",
        lambda **_kwargs: {
            "runtime_state_dir": str(tmp_path),
            "runtime_default_state_file": str(state_path),
        },
    )

    class FakeRepository:
        async def find_all(self):
            return [
                Task(
                    id=0,
                    task_name=config_data[0]["task_name"],
                    enabled=config_data[0]["enabled"],
                    keyword=config_data[0]["keyword"],
                    description=config_data[0]["description"],
                    analyze_images=True,
                    max_pages=config_data[0]["max_pages"],
                    personal_only=config_data[0]["personal_only"],
                    min_price=config_data[0]["min_price"],
                    max_price=config_data[0]["max_price"],
                    cron=config_data[0]["cron"],
                    ai_prompt_base_file="prompts/base_prompt.txt",
                    ai_prompt_criteria_file="prompts/sony_a7m4_criteria.txt",
                    ai_prompt_base_text=base_prompt,
                    ai_prompt_criteria_text=criteria_prompt,
                    ai_prompt_text=final_prompt,
                    decision_mode="ai",
                    keyword_rules=[],
                    is_running=False,
                ),
                Task(
                    id=1,
                    task_name=config_data[1]["task_name"],
                    enabled=config_data[1]["enabled"],
                    keyword=config_data[1]["keyword"],
                    description=config_data[1]["description"],
                    analyze_images=True,
                    max_pages=config_data[1]["max_pages"],
                    personal_only=config_data[1]["personal_only"],
                    min_price=config_data[1]["min_price"],
                    max_price=config_data[1]["max_price"],
                    cron=config_data[1]["cron"],
                    ai_prompt_base_file="prompts/base_prompt.txt",
                    ai_prompt_criteria_file="prompts/canon_r6_criteria.txt",
                    ai_prompt_base_text=base_prompt,
                    ai_prompt_criteria_text=criteria_prompt,
                    ai_prompt_text=final_prompt,
                    decision_mode="ai",
                    keyword_rules=[],
                    is_running=False,
                ),
            ]

    monkeypatch.setattr(spider_v2, "MySQLTaskRepository", FakeRepository)

    called = []

    async def fake_scrape_xianyu(task_config, debug_limit):
        called.append(task_config["task_name"])
        assert "{{CRITERIA_SECTION}}" not in task_config["ai_prompt_text"]
        assert "Criteria text for A7M4." in task_config["ai_prompt_text"]
        return 1

    monkeypatch.setattr(spider_v2, "scrape_xianyu", fake_scrape_xianyu)
    monkeypatch.setattr(sys, "argv", ["spider_v2.py", "--task-name", "Sony A7M4"])

    asyncio.run(spider_v2.main())

    assert called == ["Sony A7M4"]


def test_cli_runs_keyword_mode_without_prompt_files(tmp_path, load_json_fixture, monkeypatch):
    fake_scraper = types.ModuleType("src.scraper")

    async def placeholder_scrape(task_config, debug_limit):
        return 0

    fake_scraper.scrape_xianyu = placeholder_scrape
    monkeypatch.setitem(sys.modules, "src.scraper", fake_scraper)
    sys.modules.pop("spider_v2", None)

    spider_v2 = importlib.import_module("spider_v2")
    config_data = load_json_fixture("config.sample.json")
    config_data[0]["enabled"] = True
    config_data[0]["decision_mode"] = "keyword"
    config_data[0]["keyword_rules"] = ["a7m4", "验货宝"]
    config_data[0]["ai_prompt_base_file"] = "missing_base.txt"
    config_data[0]["ai_prompt_criteria_file"] = "missing_criteria.txt"

    state_path = tmp_path / "state.json"
    state_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(spider_v2, "STATE_FILE", str(state_path))
    monkeypatch.setattr(
        spider_v2,
        "materialize_runtime_account_states_sync",
        lambda **_kwargs: {
            "runtime_state_dir": str(tmp_path),
            "runtime_default_state_file": str(state_path),
        },
    )

    class FakeRepository:
        async def find_all(self):
            return [
                Task(
                    id=0,
                    task_name=config_data[0]["task_name"],
                    enabled=True,
                    keyword=config_data[0]["keyword"],
                    description=config_data[0]["description"],
                    analyze_images=True,
                    max_pages=config_data[0]["max_pages"],
                    personal_only=config_data[0]["personal_only"],
                    min_price=config_data[0]["min_price"],
                    max_price=config_data[0]["max_price"],
                    cron=config_data[0]["cron"],
                    ai_prompt_base_file="missing_base.txt",
                    ai_prompt_criteria_file="missing_criteria.txt",
                    ai_prompt_base_text="",
                    ai_prompt_criteria_text="",
                    ai_prompt_text="",
                    decision_mode="keyword",
                    keyword_rules=["a7m4", "验货宝"],
                    is_running=False,
                )
            ]

    monkeypatch.setattr(spider_v2, "MySQLTaskRepository", FakeRepository)

    captured = []

    async def fake_scrape_xianyu(task_config, debug_limit):
        captured.append(task_config)
        return 1

    monkeypatch.setattr(spider_v2, "scrape_xianyu", fake_scrape_xianyu)
    monkeypatch.setattr(sys, "argv", ["spider_v2.py", "--task-name", "Sony A7M4"])

    asyncio.run(spider_v2.main())

    assert len(captured) == 1
    assert captured[0]["decision_mode"] == "keyword"
    assert captured[0]["ai_prompt_text"] == ""
