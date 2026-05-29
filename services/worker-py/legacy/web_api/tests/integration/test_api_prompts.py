from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import prompts


def test_prompts_builtin_documents_are_available_without_disk_files(
    tmp_path,
    monkeypatch,
    mysql_test_env,
):
    monkeypatch.chdir(tmp_path)

    app = FastAPI()
    app.include_router(prompts.router)
    client = TestClient(app)

    list_resp = client.get("/api/prompts")
    assert list_resp.status_code == 200
    assert "base_prompt.txt" in list_resp.json()
    assert "macbook_criteria.txt" in list_resp.json()

    get_resp = client.get("/api/prompts/macbook_criteria.txt")
    assert get_resp.status_code == 200
    assert "MacBook Air" in get_resp.json()["content"]


def test_prompts_list_and_get_are_backed_by_database(tmp_path, monkeypatch, mysql_test_env):
    monkeypatch.chdir(tmp_path)
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    (prompts_dir / "base_prompt.txt").write_text("base prompt content", encoding="utf-8")
    (prompts_dir / "macbook_criteria.txt").write_text("criteria content", encoding="utf-8")

    app = FastAPI()
    app.include_router(prompts.router)
    client = TestClient(app)

    list_resp = client.get("/api/prompts")
    assert list_resp.status_code == 200
    assert list_resp.json() == ["base_prompt.txt", "macbook_criteria.txt"]

    get_resp = client.get("/api/prompts/base_prompt.txt")
    assert get_resp.status_code == 200
    assert get_resp.json()["content"] == "base prompt content"


def test_prompt_update_persists_to_database_without_overwriting_disk_file(
    tmp_path,
    monkeypatch,
    mysql_test_env,
):
    monkeypatch.chdir(tmp_path)
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    prompt_file = prompts_dir / "base_prompt.txt"
    prompt_file.write_text("original on disk", encoding="utf-8")

    app = FastAPI()
    app.include_router(prompts.router)
    client = TestClient(app)

    update_resp = client.put(
        "/api/prompts/base_prompt.txt",
        json={"content": "updated in database"},
    )
    assert update_resp.status_code == 200

    get_resp = client.get("/api/prompts/base_prompt.txt")
    assert get_resp.status_code == 200
    assert get_resp.json()["content"] == "updated in database"
    assert prompt_file.read_text(encoding="utf-8") == "original on disk"
