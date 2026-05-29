from __future__ import annotations

from src.services.prompt_document_service import get_prompt_content


CRITERIA_PLACEHOLDER = "{{CRITERIA_SECTION}}"


def read_prompt_file(path: str | None) -> str:
    if not path:
        return ""
    return get_prompt_content(path).strip()


def compose_ai_prompt_text(base_prompt_text: str | None, criteria_text: str | None) -> str:
    base = str(base_prompt_text or "")
    criteria = str(criteria_text or "")
    if not base.strip():
        return criteria.strip()
    if CRITERIA_PLACEHOLDER in base:
        return base.replace(CRITERIA_PLACEHOLDER, criteria).strip()
    if criteria.strip():
        return f"{base.rstrip()}\n\n{criteria.strip()}".strip()
    return base.strip()


def build_task_prompt_payload(
    *,
    base_prompt_file: str,
    criteria_file: str,
    base_prompt_text: str | None = None,
    criteria_text: str | None = None,
) -> dict[str, str]:
    final_base_text = str(base_prompt_text or "").strip() or read_prompt_file(base_prompt_file).strip()
    final_criteria_text = str(criteria_text or "").strip() or read_prompt_file(criteria_file).strip()
    final_prompt_text = compose_ai_prompt_text(final_base_text, final_criteria_text)
    return {
        "ai_prompt_base_file": base_prompt_file,
        "ai_prompt_criteria_file": criteria_file,
        "ai_prompt_base_text": final_base_text,
        "ai_prompt_criteria_text": final_criteria_text,
        "ai_prompt_text": final_prompt_text,
    }


def resolve_runtime_ai_prompt(task_config: dict) -> str:
    direct_prompt = str(task_config.get("ai_prompt_text") or "").strip()
    if direct_prompt:
        return direct_prompt

    base_prompt_text = str(task_config.get("ai_prompt_base_text") or "").strip()
    criteria_text = str(task_config.get("ai_prompt_criteria_text") or "").strip()
    if base_prompt_text or criteria_text:
        return compose_ai_prompt_text(base_prompt_text, criteria_text)

    base_prompt_file = str(task_config.get("ai_prompt_base_file") or "").strip()
    criteria_file = str(task_config.get("ai_prompt_criteria_file") or "").strip()
    if base_prompt_file or criteria_file:
        payload = build_task_prompt_payload(
            base_prompt_file=base_prompt_file,
            criteria_file=criteria_file,
        )
        return payload["ai_prompt_text"]

    legacy_file = str(task_config.get("ai_prompt_file") or "").strip()
    return read_prompt_file(legacy_file).strip()


def build_criteria_generation_input(
    *,
    task_name: str | None,
    keyword: str | None,
    description: str | None,
) -> str:
    normalized_description = str(description or "").strip()
    normalized_keyword = str(keyword or "").strip()
    normalized_task_name = str(task_name or "").strip()

    lines = [
        "请基于以下监控任务信息生成分析标准。",
    ]
    if normalized_task_name:
        lines.append(f"任务名称：{normalized_task_name}")
    if normalized_keyword:
        lines.append(f"搜索关键词：{normalized_keyword}")
    if normalized_description:
        lines.append(f"详细需求：{normalized_description}")
    else:
        lines.append("详细需求：请根据任务名称与搜索关键词理解商品类型，并生成相应的筛选标准。")

    return "\n".join(lines).strip()
