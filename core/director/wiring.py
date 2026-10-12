"""`core.director` 的**接线层**（C11, `docs/EXEC_SPLIT.md`）。

两个"给 VN 上层用"的小接线函数, 与导演本体分开:

    `_build_director(char)`   构建视觉导演 + **任何失败 → None**（纯文本降级, 宁缺勿错）;
    `_trigger_title(engine)`  从最近一轮动作轨迹取 `mmt_trigger_bond_story` 的
                              `chapter_title`（找不到 → 空串; 进程重启后 trace 为空, 标题
                              真源仍是事件流, 见 `webgui.bond._title_from_events`）。

## 为什么它们不在 `core/ui/vn_cli.py`（C11 搬来的理由; 该文件 C12b 已搬去 `apps/vn_cli.py`）

webgui 需要这两个函数（`bond/api.py` 建导演、`bond/replay.py` 取章名）, 而它们住在
CLI **应用**里 ⇒ **webgui → CLI** 的反向依赖。搬到 `core.director`（引擎层, 无 web 依赖）
后方向正过来: webgui → core.director.wiring ← apps/vn_cli。

## 纪律

· 本模块**不 import `renderer`**（那是 CLI 的事）——`core→renderer` 的唯一来源是
  CLI 应用自己的显示路径（C12b 起整个搬去 `apps/`）;
· 代码从 `vn_cli.py` **逐字搬来**（零行为改动）。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from core.director import build_director

if TYPE_CHECKING:                      # 只为注解（`annotations` 未来导入）——避免运行期循环
    from core.mmt.engine import MomoTalkEngine

logger = logging.getLogger(__name__)


def _build_director(char):
    """构建视觉导演（v2 纯查表模式, 无辅助 LLM; 任何失败 → None 纯文本）。

    情感由主 LLM 在段落内联 emotion 给出, 导演只做 place→背景查表;
    背景/音乐等未来非情感决策若需语义仲裁, 直接用 llm/client.py 的 LLMClient。
    """
    try:
        return build_director(char)
    except Exception as e:
        logger.warning("视觉导演构建失败, 本次 VN 纯文本模式: %s", e)
        return None


def _trigger_title(engine: MomoTalkEngine) -> str:
    """从最近一轮动作轨迹里取触发动作的 chapter_title（找不到 → 空串）。

    2026-09-05: reason 退役——payload 带 chapter_title（触发即命题）。
    """
    if not engine.trace:
        return ""
    for step in reversed(engine.trace):
        if step.get("action") == "mmt_trigger_bond_story":
            payload = step.get("payload") or {}
            return str(payload.get("chapter_title") or "").strip()
    return ""
