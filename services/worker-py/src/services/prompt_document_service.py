from __future__ import annotations

from datetime import datetime
from src.infrastructure.persistence.mysql_connection import init_schema, mysql_connection


PROMPT_SOURCE_SYSTEM = "system"
PROMPT_SOURCE_MANUAL = "manual"
PROMPT_SOURCE_GENERATED = "generated"


BUILTIN_PROMPT_DOCUMENTS = {
    "prompts/base_prompt.txt": """你是世界顶级的二手交易分析专家，代号 **EagleEye-V6.4**。你的核心任务是基于我提供的严格标准，对一个以JSON格式提供的商品信息进行深入的、基于用户画像的评估。你的分析必须极度严谨，并以一个结构化的JSON对象返回你的完整分析，不能有任何额外的文字。

{{CRITERIA_SECTION}}

### **第三部分：输出格式 (必须严格遵守)**

你的输出必须是以下格式的单个 JSON 对象，不能包含任何额外的注释或解释性文字。

```json
{
  "prompt_version": "EagleEye-V6.4",
  "is_recommended": boolean,
  "reason": "一句话综合评价。若为有条件推荐，需明确指出：'有条件推荐，卖家画像为顶级个人玩家，但需在购买前向其确认[电池健康度]和[维修历史]等缺失信息。'",
  "risk_tags": ["string"],
  "criteria_analysis": {
    "model_chip": { "status": "string", "comment": "string", "evidence": "string" },
    "battery_health": { "status": "string", "comment": "string", "evidence": "string" },
    "condition": { "status": "string", "comment": "string", "evidence": "string" },
    "history": { "status": "string", "comment": "string", "evidence": "string" },
    "seller_type": {
      "status": "string",
      "persona": "string",
      "comment": "【首要结论】综合性的结论，必须首先点明卖家画像。如果判定为FAIL，必须在此明确指出是基于哪个危险信号以及不符合的逻辑链。",
      "analysis_details": {
        "temporal_analysis": {
          "comment": "关于交易时间间隔和分布的分析结论。",
          "evidence": "例如：交易记录横跨数年，间隔期长，符合个人卖家特征。"
        },
        "selling_behavior": {
          "comment": "关于其售卖商品种类的分析。",
          "evidence": "例如：售卖商品多为个人升级换代的数码产品，逻辑自洽。"
        },
        "buying_behavior": {
          "comment": "【关键】关于其购买历史的分析结论。",
          "evidence": "例如：购买记录显示为游戏盘和生活用品，符合个人消费行为。"
        },
        "behavioral_summary": {
          "comment": "【V6.3 新增】对卖家完整行为逻辑链的最终总结。必须明确回答：这是一个怎样的卖家？其买卖行为是否构成一个可信的个人故事？",
          "evidence": "例如：'该卖家的行为逻辑链完整：早期购买游戏，中期购入相机和镜头，近期开始出售旧款电子设备。这是一个典型的数码产品消费者的成长路径，可信度极高。' 或 '逻辑链断裂：该卖家大量购买维修配件，却声称所有售卖设备均为自用，故事不可信。'"
        }
      }
    },
    "shipping": { "status": "string", "comment": "string", "evidence": "string" },
    "seller_credit": { "status": "string", "comment": "string", "evidence": "string" }
  }
}
```""",
    "prompts/macbook_criteria.txt": """### **第一部分：核心分析原则 (不可违背)**

1.  **画像优先原则 (PERSONA-FIRST PRINCIPLE) [V6.3 核心升级]**: 这是解决“高级玩家”与“普通贩子”识别混淆的最高指导原则。在评估卖家时，你的首要任务不是寻找孤立的疑点，而是**构建一个连贯的卖家“行为画像”**。你必须回答核心问题：“这个卖家的所有行为（买、卖、评价、签名）组合起来，讲述的是一个怎样的故事？”
    *   **如果故事是连贯的个人行为**（例如，一个热爱数码产品，不断体验、升级、出掉旧设备的发烧友），那么一些表面上的“疑点”（如交易频率略高）可以被合理解释，**不应**作为否决依据。
    *   **如果故事是矛盾的、不连贯的，或者明确指向商业行为**（例如，购买记录是配件和坏机，售卖记录却是大量“几乎全新”的同型号机器），那么即便卖家伪装得很好，也必须判定为商家。

2.  **一票否决硬性原则 (HARD DEAL-BREAKER RULES)**: 以下是必须严格遵守的否决条件。任何一项不满足，`is_recommended` 必须立即判定为 `false`。
    *   **型号/芯片**: 必须是 **MacBook Air** 且明确为 **M1 芯片**。
    *   **卖家信用**: `卖家信用等级` 必须是 **'卖家信用极好'**。
    *   **邮寄方式**: 必须 **支持邮寄**。
    *   **电池健康硬性门槛**: 若明确提供了电池健康度，其数值 **`必须 ≥ 90%`**。
    *   **【V6.4 逻辑修正】机器历史**: **不得出现**任何“维修过”、“更换过部件”、“有暗病”等明确表示有拆修历史的描述。

3.  **图片至上原则 (IMAGE-FIRST PRINCIPLE)**: 如果图片信息（如截图）与文本描述冲突，**必须以图片信息为最终裁决依据**。

4.  **【V6.4 逻辑修正】信息缺失处理原则 (MISSING-INFO HANDLING)**: 对于可后天询问的关键信息（特指**电池健康度**和**维修历史**），若完全未找到，状态应为 `NEEDS_MANUAL_CHECK`，这**不直接导致否决**。如果卖家画像极为优秀，可以进行“有条件推荐”。

---

### **第二部分：详细分析指南**

**A. 商品本身评估 (Criteria Analysis):**

1.  **型号芯片 (`model_chip`)**: 核对所有文本和图片。非 MacBook Air M1 则 `FAIL`。
2.  **电池健康 (`battery_health`)**: 健康度 ≥ 90%。若无信息，则为 `NEEDS_MANUAL_CHECK`。
3.  **成色外观 (`condition`)**: 最多接受“细微划痕”。仔细审查图片四角、A/D面。
4.  **【V6.4 逻辑修正】机器历史 (`history`)**: 严格审查所有文本和图片，寻找“换过”、“维修”、“拆过”、“进水”、“功能不正常”等负面描述。**若完全未提及，则状态为 `NEEDS_MANUAL_CHECK`**；若有任何拆修证据，则为 `FAIL`。

**B. 卖家与市场评估 (核心)**

5.  **卖家背景深度分析 (`seller_type`) - [决定性评估]**:
    *   **核心目标**: 运用“画像优先原则”，判定卖家是【个人玩家】还是【商家/贩子】。
    *   **【V6.3 升级】危险信号清单 (Red Flag List) 及豁免条款**:
        *   **交易频率**: 短期内有密集交易。
            *   **【发烧友豁免条款】**: 如果交易记录时间跨度长（如超过2年），且买卖行为能形成“体验-升级-出售”的逻辑闭环，则此条不适用。一个长期发烧友在几年内有数十次交易是正常的。
        *   **商品垂直度**: 发布的商品高度集中于某一特定型号或品类。
            *   **【发烧友豁免条款】**: 如果卖家是该领域的深度玩家（例如，从他的购买记录、评价和发言能看出），专注于某个系列是其专业性的体现。关键看他是在“玩”还是在“出货”。
        *   **“行话”**: 描述中出现“同行、工作室、拿货、量大从优”等术语。
            *   **【无豁免】**: 此为强烈的商家信号。
        *   **物料购买**: 购买记录中出现批量配件、维修工具、坏机等。
            *   **【无豁免】**: 此为决定性的商家证据。
        *   **图片/标题风格**: 图片背景高度统一、专业；或标题模板化。
            *   **【发烧友豁免条款】**: 如果卖家追求完美，有自己的“摄影棚”或固定角落来展示他心爱的物品，这是加分项。关键看图片传递的是“爱惜感”还是“商品感”。

6.  **邮寄方式 (`shipping`)**: 明确“仅限xx地面交/自提”则 `FAIL`。
7.  **卖家信用 (`seller_credit`)**: `卖家信用等级` 必须为 **'卖家信用极好'**。""",
}


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def normalize_prompt_filename(filename: str | None) -> str:
    normalized = str(filename or "").strip().replace("\\", "/")
    if not normalized:
        return ""
    if "/" not in normalized:
        return f"prompts/{normalized}"
    return normalized


def _get_builtin_prompt_content(filename: str | None) -> str:
    normalized = normalize_prompt_filename(filename)
    return str(BUILTIN_PROMPT_DOCUMENTS.get(normalized) or "")


def list_prompt_documents() -> list[str]:
    with mysql_connection() as conn:
        init_schema(conn)
        rows = conn.execute(
            """
            SELECT filename
            FROM prompt_documents
            ORDER BY filename ASC
            """
        ).fetchall()
    filenames = {str(row["filename"]) for row in rows}
    filenames.update(BUILTIN_PROMPT_DOCUMENTS.keys())
    return sorted(filenames)


def get_prompt_document(filename: str) -> dict | None:
    normalized = normalize_prompt_filename(filename)
    with mysql_connection() as conn:
        init_schema(conn)
        row = conn.execute(
            """
            SELECT filename, content, source, created_at, updated_at
            FROM prompt_documents
            WHERE filename = ?
            """,
            (normalized,),
        ).fetchone()
    if row is None:
        builtin_content = _get_builtin_prompt_content(normalized)
        if not builtin_content:
            return None
        now = _now_iso()
        return {
            "filename": normalized,
            "content": builtin_content,
            "source": PROMPT_SOURCE_SYSTEM,
            "created_at": now,
            "updated_at": now,
        }
    return dict(row)


def get_prompt_content(filename: str | None) -> str:
    normalized = normalize_prompt_filename(filename)
    if not normalized:
        return ""
    try:
        document = get_prompt_document(normalized)
    except Exception:
        document = None
    if document is not None:
        return str(document.get("content") or "")
    return _get_builtin_prompt_content(normalized)


def ensure_builtin_prompt_documents() -> None:
    now = _now_iso()
    with mysql_connection() as conn:
        init_schema(conn)
        for filename, content in BUILTIN_PROMPT_DOCUMENTS.items():
            existing = conn.execute(
                "SELECT filename, created_at FROM prompt_documents WHERE filename = ?",
                (filename,),
            ).fetchone()
            if existing is not None:
                continue
            conn.execute(
                """
                INSERT INTO prompt_documents (filename, content, source, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (filename, content, PROMPT_SOURCE_SYSTEM, now, now),
            )
        conn.commit()


def upsert_prompt_document(
    filename: str,
    content: str,
    *,
    source: str = PROMPT_SOURCE_MANUAL,
) -> dict:
    normalized = normalize_prompt_filename(filename)
    if not normalized:
        raise ValueError("filename 不能为空")

    now = _now_iso()
    with mysql_connection() as conn:
        init_schema(conn)
        existing = conn.execute(
            "SELECT filename, created_at FROM prompt_documents WHERE filename = ?",
            (normalized,),
        ).fetchone()
        created_at = str(existing["created_at"]) if existing else now
        conn.execute(
            """
            INSERT INTO prompt_documents (filename, content, source, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE
                content = VALUES(content),
                source = VALUES(source),
                updated_at = VALUES(updated_at)
            """,
            (normalized, content, source, created_at, now),
        )
        conn.commit()
    return {
        "filename": normalized,
        "content": content,
        "source": source,
        "created_at": created_at,
        "updated_at": now,
    }
