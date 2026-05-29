from __future__ import annotations

import asyncio
import os
import re
import shutil

import requests

from src.infrastructure.config.settings import settings
from src.utils import retry_on_failure


IMAGE_DOWNLOAD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:139.0) Gecko/20100101 Firefox/139.0",
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


def _positive_int(value, default: int) -> int:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default


DEFAULT_IMAGE_DOWNLOAD_CONCURRENCY = max(
    1,
    _positive_int(os.getenv("IMAGE_DOWNLOAD_CONCURRENCY", "3"), 3),
)


def _safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        try:
            print(text.encode("ascii", errors="ignore").decode("ascii"))
        except Exception:
            print("[输出包含无法显示的字符]")


@retry_on_failure(retries=2, delay=3)
async def _download_single_image(url: str, save_path: str) -> str:
    loop = asyncio.get_running_loop()
    response = await loop.run_in_executor(
        None,
        lambda: requests.get(url, headers=IMAGE_DOWNLOAD_HEADERS, timeout=20, stream=True),
    )
    response.raise_for_status()
    with open(save_path, "wb") as file_handle:
        for chunk in response.iter_content(chunk_size=8192):
            file_handle.write(chunk)
    return save_path


def _build_image_save_path(
    product_id: str,
    index: int,
    url: str,
    task_image_dir: str,
) -> str:
    clean_url = url.split(".heic")[0] if ".heic" in url else url
    file_name_base = os.path.basename(clean_url).split("?")[0]
    file_name = f"product_{product_id}_{index}_{file_name_base}"
    file_name = re.sub(r'[\\/*?:"<>|]', "", file_name)
    if not os.path.splitext(file_name)[1]:
        file_name += ".jpg"
    return os.path.join(task_image_dir, file_name)


async def download_all_images(
    product_id: str,
    image_urls: list[str],
    task_name: str = "default",
    concurrency: int | None = None,
) -> list[str]:
    if not image_urls:
        return []

    task_image_dir = os.path.join(
        settings.image_save_dir,
        f"{settings.task_image_dir_prefix}{task_name}",
    )
    os.makedirs(task_image_dir, exist_ok=True)

    urls = [url.strip() for url in image_urls if str(url).strip().startswith("http")]
    if not urls:
        return []

    max_concurrency = _positive_int(concurrency, DEFAULT_IMAGE_DOWNLOAD_CONCURRENCY)
    semaphore = asyncio.Semaphore(max_concurrency)
    total_images = len(urls)

    async def _download_one(index: int, url: str):
        save_path = _build_image_save_path(product_id, index, url, task_image_dir)
        if os.path.exists(save_path):
            _safe_print(
                f"   [图片] 图片 {index}/{total_images} 已存在，跳过下载: {os.path.basename(save_path)}"
            )
            return save_path
        async with semaphore:
            _safe_print(f"   [图片] 正在下载图片 {index}/{total_images}: {url}")
            if await _download_single_image(url, save_path):
                _safe_print(
                    f"   [图片] 图片 {index}/{total_images} 已成功下载到: {os.path.basename(save_path)}"
                )
                return save_path
        return None

    tasks = [
        asyncio.create_task(_download_one(index, url))
        for index, url in enumerate(urls, start=1)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    saved_paths: list[str] = []
    for url, result in zip(urls, results):
        try:
            if isinstance(result, Exception):
                raise result
            if result:
                saved_paths.append(result)
        except Exception as exc:
            _safe_print(f"   [图片] 处理图片 {url} 时发生错误，已跳过此图: {exc}")

    return saved_paths


def cleanup_task_images(task_name: str) -> None:
    task_image_dir = os.path.join(
        settings.image_save_dir,
        f"{settings.task_image_dir_prefix}{task_name}",
    )
    if os.path.exists(task_image_dir):
        try:
            shutil.rmtree(task_image_dir)
            _safe_print(f"   [清理] 已删除任务 '{task_name}' 的临时图片目录: {task_image_dir}")
        except Exception as exc:
            _safe_print(f"   [清理] 删除任务 '{task_name}' 的临时图片目录时出错: {exc}")
