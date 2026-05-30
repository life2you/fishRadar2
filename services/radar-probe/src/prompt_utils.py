from typing import Awaitable, Callable, Optional

from src.infrastructure.external.ai_client import AIClient
from src.services.ai_account_service import list_ai_route_candidates
from src.services.prompt_document_service import get_prompt_content

# The meta-prompt to instruct the AI
META_PROMPT_TEMPLATE = """
你是一位世界级的AI提示词工程大师。你的任务是根据用户提供的【购买需求】，模仿一个【参考范例】，为闲鱼监控机器人的AI分析模块（代号 EagleEye）生成一份全新的【分析标准】文本。

你的输出必须严格遵循【参考范例】的结构、语气和核心原则，但内容要完全针对用户的【购买需求】进行定制。最终生成的文本将作为AI分析模块的思考指南。

---
这是【参考范例】（`macbook_criteria.txt`）：
```text
{reference_text}
```
---

这是用户的【购买需求】：
```text
{user_description}
```
---

请现在开始生成全新的【分析标准】文本。请注意：
1.  **只输出新生成的文本内容**，不要包含任何额外的解释、标题或代码块标记。
2.  保留范例中的 `[V6.3 核心升级]`、`[V6.4 逻辑修正]` 等版本标记，这有助于保持格式一致性。
3.  将范例中所有与 "MacBook" 相关的内容，替换为与用户需求商品相关的内容。
4.  思考并生成针对新商品类型的“一票否决硬性原则”和“危险信号清单”。
"""

ProgressCallback = Callable[[str, str], Awaitable[None]]


async def _report_progress(
    progress_callback: Optional[ProgressCallback],
    step_key: str,
    message: str,
) -> None:
    if progress_callback:
        await progress_callback(step_key, message)


def _read_reference_text(reference_file_path: str) -> str:
    content = get_prompt_content(reference_file_path)
    if content.strip():
        return content
    raise FileNotFoundError(f"参考文件未找到: {reference_file_path}")


async def _request_generated_text(ai_client: AIClient, prompt: str) -> str:
    print("正在调用AI生成新的分析标准，请稍候...")
    try:
        generated_text = await ai_client._call_ai(
            [{"role": "user", "content": prompt}],
            temperature=0.5,
            max_output_tokens=800,
            enable_json_output=False,
        )
    except Exception as exc:
        print(f"调用 OpenAI API 时出错: {exc}")
        raise

    print("AI已成功生成内容。")
    return generated_text.strip()


async def _generate_text_with_candidates(prompt: str) -> str:
    candidates = await list_ai_route_candidates(require_images=False)
    if not candidates:
        raise RuntimeError("没有可用的 AI 账号可用于生成分析标准。")

    last_error: Exception | None = None
    for account in candidates:
        ai_client = AIClient(account if account.id != 0 else None)
        active_error: BaseException | None = None
        try:
            if not ai_client.is_available():
                ai_client.refresh()
            if not ai_client.is_available():
                continue
            return await _request_generated_text(ai_client, prompt)
        except Exception as exc:
            active_error = exc
            last_error = exc
            print(f"账号 {account.name} 生成分析标准失败: {exc}")
        finally:
            await _close_ai_client(ai_client, active_error)

    raise RuntimeError(f"所有 AI 账号生成分析标准均失败: {last_error}")


async def _close_ai_client(
    ai_client: AIClient,
    active_error: BaseException | None,
) -> None:
    try:
        await ai_client.close()
    except Exception as close_error:
        print(f"关闭 AI 客户端时出错: {close_error}")
        if active_error is None:
            raise


async def generate_criteria(
    user_description: str,
    reference_file_path: str,
    progress_callback: Optional[ProgressCallback] = None,
) -> str:
    """
    Generates a new criteria file content using AI.
    """
    try:
        await _report_progress(progress_callback, "reference", "正在读取参考文件。")
        print(f"正在读取参考文件: {reference_file_path}")
        reference_text = _read_reference_text(reference_file_path)

        await _report_progress(progress_callback, "prompt", "正在构建发送给 AI 的指令。")
        print("正在构建发送给AI的指令...")
        prompt = META_PROMPT_TEMPLATE.format(
            reference_text=reference_text,
            user_description=user_description,
        )

        await _report_progress(progress_callback, "llm", "正在调用 AI 生成分析标准。")
        return await _generate_text_with_candidates(prompt)
    except Exception as exc:
        raise
