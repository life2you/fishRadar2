import asyncio
import sys
import os
import argparse
import signal
import contextlib
import re

from src.infrastructure.config.settings import scraper_settings
from src.infrastructure.persistence.mysql_task_repository import MySQLTaskRepository
from src.scraper import scrape_xianyu
from src.services.account_state_service import (
    get_runtime_account_state_dir,
    materialize_runtime_account_states_sync,
    resolve_runtime_account_path,
)
from src.services.task_prompt_service import resolve_runtime_ai_prompt

STATE_FILE = scraper_settings.state_file


async def main():
    parser = argparse.ArgumentParser(
        description="闲鱼商品监控脚本，支持多任务配置和实时AI分析。",
        epilog="""
使用示例:
  # 运行数据库中所有启用的任务
  python spider_v2.py

  # 只运行名为 "Sony A7M4" 的任务 (通常由调度器调用)
  python spider_v2.py --task-name "Sony A7M4"

  # 调试模式: 运行所有任务，但每个任务只处理前3个新发现的商品
  python spider_v2.py --debug-limit 3
""",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--debug-limit", type=int, default=0, help="调试模式：每个任务仅处理前 N 个新商品（0 表示无限制）")
    parser.add_argument("--task-id", type=int, help="只运行指定ID的单个任务 (用于任务进程调度)")
    parser.add_argument("--task-name", type=str, help="只运行指定名称的单个任务 (用于定时任务调度)")
    args = parser.parse_args()

    repository = MySQLTaskRepository()
    tasks = await repository.find_all()
    tasks_config = [task.model_dump() for task in tasks]

    runtime_state = materialize_runtime_account_states_sync(
        runtime_state_dir=get_runtime_account_state_dir(),
        runtime_default_state_file=STATE_FILE,
    )

    def normalize_keywords(value):
        if value is None:
            return []
        if isinstance(value, str):
            raw_values = re.split(r"[\n,]+", value)
        elif isinstance(value, (list, tuple, set)):
            raw_values = list(value)
        else:
            raw_values = [value]

        normalized = []
        seen = set()
        for item in raw_values:
            text = str(item).strip()
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(text)
        return normalized

    def flatten_legacy_groups(groups):
        merged = []
        for group in groups or []:
            if isinstance(group, dict):
                merged.extend(normalize_keywords(group.get("include_keywords")))
        return normalize_keywords(merged)

    def has_bound_account(tasks: list) -> bool:
        for task in tasks:
            account = task.get("account_state_file")
            if isinstance(account, str) and account.strip():
                return True
        return False

    def has_any_state_file() -> bool:
        state_dir = runtime_state["runtime_state_dir"]
        if os.path.isdir(state_dir):
            for name in os.listdir(state_dir):
                if name.endswith(".json"):
                    return True
        return False

    if not os.path.exists(STATE_FILE) and not has_bound_account(tasks_config) and not has_any_state_file():
        sys.exit(
            f"错误: 未找到登录状态文件。请在 state/ 中添加账号或配置 account_state_file。"
        )

    # 为 AI 任务准备最终 prompt 文本，优先使用数据库中已落库的文本。
    for task in tasks_config:
        decision_mode = str(task.get("decision_mode", "ai")).strip().lower()
        if decision_mode not in {"ai", "keyword"}:
            decision_mode = "ai"
        task["decision_mode"] = decision_mode
        keyword_rules = task.get("keyword_rules")
        if keyword_rules is None and task.get("keyword_rule_groups") is not None:
            task["keyword_rules"] = flatten_legacy_groups(task.get("keyword_rule_groups") or [])
        else:
            task["keyword_rules"] = normalize_keywords(keyword_rules)
        task["account_state_file"] = resolve_runtime_account_path(
            task.get("account_state_file"),
            runtime_dir=runtime_state["runtime_state_dir"],
        )

        if decision_mode == "keyword":
            task["ai_prompt_text"] = ""
            continue

        try:
            task["ai_prompt_text"] = resolve_runtime_ai_prompt(task)
            if not task["ai_prompt_text"]:
                print(f"警告: 任务 '{task['task_name']}' 未解析到可用的 AI prompt，该任务的AI分析将被跳过。")
            elif len(task["ai_prompt_text"]) < 100:
                print(f"警告: 任务 '{task['task_name']}' 生成的prompt过短 ({len(task['ai_prompt_text'])} 字符)，可能存在问题。")
            elif "{{CRITERIA_SECTION}}" in task["ai_prompt_text"]:
                print(f"警告: 任务 '{task['task_name']}' 的prompt中仍包含占位符，替换可能失败。")
            else:
                print(f"✅ 任务 '{task['task_name']}' 的prompt生成成功，长度: {len(task['ai_prompt_text'])} 字符")
        except Exception as e:
            print(f"错误: 任务 '{task['task_name']}' 处理prompt内容时发生异常: {e}，该任务的AI分析将被跳过。")
            task["ai_prompt_text"] = ""

    print("\n--- 开始执行监控任务 ---")
    if args.debug_limit > 0:
        print(f"** 调试模式已激活，每个任务最多处理 {args.debug_limit} 个新商品 **")
    
    if args.task_id is not None:
        print(f"** 定时任务模式：只执行任务 ID {args.task_id} **")
    elif args.task_name:
        print(f"** 定时任务模式：只执行任务 '{args.task_name}' **")

    print("--------------------")

    active_task_configs = []
    if args.task_id is not None:
        task_found = next((task for task in tasks_config if task.get('id') == args.task_id), None)
        if task_found:
            if task_found.get("enabled", False):
                active_task_configs.append(task_found)
            else:
                print(f"任务 ID {args.task_id} 已被禁用，跳过执行。")
        else:
            print(f"错误：在配置文件中未找到 ID 为 {args.task_id} 的任务。")
            return
    elif args.task_name:
        # 如果指定了任务名称，只查找该任务
        task_found = next((task for task in tasks_config if task.get('task_name') == args.task_name), None)
        if task_found:
            if task_found.get("enabled", False):
                active_task_configs.append(task_found)
            else:
                print(f"任务 '{args.task_name}' 已被禁用，跳过执行。")
        else:
            print(f"错误：在配置文件中未找到名为 '{args.task_name}' 的任务。")
            return
    else:
        # 否则，按原计划加载所有启用的任务
        active_task_configs = [task for task in tasks_config if task.get("enabled", False)]

    if not active_task_configs:
        print("没有需要执行的任务，程序退出。")
        return

    # 为每个启用的任务创建一个异步执行协程
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    tasks = []
    for task_conf in active_task_configs:
        print(f"-> 任务 '{task_conf['task_name']}' 已加入执行队列。")
        tasks.append(asyncio.create_task(scrape_xianyu(task_config=task_conf, debug_limit=args.debug_limit)))

    async def _shutdown_watcher():
        await stop_event.wait()
        print("\n收到终止信号，正在优雅退出，取消所有爬虫任务...")
        for t in tasks:
            if not t.done():
                t.cancel()

    shutdown_task = asyncio.create_task(_shutdown_watcher())

    try:
        # 并发执行所有任务
        results = await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        shutdown_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await shutdown_task

    print("\n--- 所有任务执行完毕 ---")
    for i, result in enumerate(results):
        task_name = active_task_configs[i]['task_name']
        if isinstance(result, Exception):
            print(f"任务 '{task_name}' 因异常而终止: {result}")
        else:
            print(f"任务 '{task_name}' 正常结束，本次运行共处理了 {result} 个新商品。")

if __name__ == "__main__":
    asyncio.run(main())
