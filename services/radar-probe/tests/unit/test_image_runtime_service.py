import asyncio
from pathlib import Path

from src.services import image_runtime_service


def test_download_all_images_runs_with_concurrency(tmp_path, monkeypatch):
    monkeypatch.setattr(
        image_runtime_service.settings,
        "image_save_dir",
        str(tmp_path / "images"),
    )

    active_downloads = 0
    max_active_downloads = 0

    async def fake_download(url, save_path):
        nonlocal active_downloads, max_active_downloads
        active_downloads += 1
        max_active_downloads = max(max_active_downloads, active_downloads)
        await asyncio.sleep(0.02)
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        Path(save_path).write_text("ok", encoding="utf-8")
        active_downloads -= 1
        return save_path

    monkeypatch.setattr(image_runtime_service, "_download_single_image", fake_download)

    async def run():
        return await image_runtime_service.download_all_images(
            "product-1",
            [
                "https://example.com/1.jpg",
                "https://example.com/2.jpg",
                "https://example.com/3.jpg",
            ],
            task_name="demo",
            concurrency=3,
        )

    paths = asyncio.run(run())
    assert len(paths) == 3
    assert max_active_downloads == 3
