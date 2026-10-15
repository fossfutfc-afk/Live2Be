"""MMT 执行层 — 按 approval=auto 执行动作，reply 承载对白。

契约层只解析动作（纯结构校验, 不碰文件系统/运行时）；执行层负责动作的
实际执行——读角色资料、模拟媒体发送、羁绊触发判定。每个动作成功返回
ExecResult(ok=True, message=回灌给 LLM 的内容)；不可执行抛 MmtExecError
（message 同样回灌给 LLM 修正, 而不是崩溃）。

动作执行（对应 core/mmt/mmt_actions.py 的动作集）:
    mmt_chat                 对白已在 action.reply——执行仅确认, 正常回复核心路径
    mmt_look                 ⭐ 翻她自己的记忆（2026-10-08）—— 真正的实现在
                             `core/brain/read/find.py`, 由引擎注入 `look_fn`;
                             这里只兜"没接线"（MmtExecError, 硬）
    mmt_send_media           图片发送占位——媒体管线未接入, 仅回灌确认
    mmt_trigger_bond_story   触发放行——**引擎不拦节奏**（2026-09-02 v2 用户拍板:
                             轮数只是建议, 由 momotalk 每轮注记提示时机; 紧急剧情
                             sensei 遇险等 LLM 自行裁决随时触发）; 放行即切剧情模式

信息架构（2026-10-08 校正 —— ⛔ L3 深挖层随 `mmt_inspect_character` 退役）:
    L0 自我层（角色设定）/ L1 人际层（**她眼里的他们** —— 立场物化成 `entity.text`,
    由 brain 段注入, **不再经本文件**）/ L2 硬知识。
    ⚠️ 从前那个"按权重分级读**别人**的客观档案"的入口已删（用户裁: 客观档案混进
    主观看法里是错的 —— 她该只知道**自己眼里的他们**）。

设计决策:
    - 执行器持有会话当前角色（set_current_character）, trigger/look 依赖它。
    - 触发 bool: 引擎建议不拦截（v1 曾硬拒不足 6 轮——2026-09-02 v2 用户复盘
      否决: 玩家遇险时角色尬聊是硬闸的伪正确; 时机建议由 momotalk._bond_progress_note
      每轮注入, 触发与否全权交给 LLM 的剧情判断）。
    - 人际层工具（`load_interperson` + 折行规整）当前内联在本文件,
      待 core/parsing/relation_parser.py 落地后移入。
    - 错误统一走 MmtExecError（Live2BeError 子类）, 由调用方捕获回灌。

TODO（后续 session）:
    - core/parsing/relation_parser.py: 移入人际层工具
    - 媒体管线（存储/查库/LLM 生成）落地后替换 _execute_mmt_send_media 的占位
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import yaml

from contract import DOMAIN_MMT, AgentAction
from contract.errors import Live2BeError
from core.parsing.dynamic_character_parser import (
    CharacterLoader,
    DynamicCharacter,
)
from infra import paths

# interperson.yml 默认路径（`infra/paths.py` 的宏——项目根绝对, cwd 无关）
DEFAULT_INTERPERSON_PATH = paths.INTERPERSON_PATH

#: **汉字之间**的空白（`>` 折叠块的产物）—— 见 `_fold_layout`。
#: 两侧的字符类 = CJK 汉字 + 中文标点（`\u3000-\u303f` `\uff00-\uffef`）。
_CJK_GAP = re.compile(
    r"(?<=[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef])\s+"
    r"(?=[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef])")


class MmtExecError(Live2BeError):
    """MMT 执行层拒绝/失败。message 供调用方回灌给 LLM 修正。

    __str__ 自动产出 [mmt_executor.py][MmtExecError][message]。
    """


@dataclass
class ExecResult:
    """执行结果。message 回灌给 LLM（或展示给用户）。"""

    ok: bool
    message: str


# ============================================================================
# 人际层工具（待 relation_parser.py 落地后移入）
# ============================================================================

def _fold_layout(text: str) -> str:
    """**换行 = 排版, 空格 = 内容** —— 折行的痕不进 prompt。

    ⭐ 语义（2026-10-08 定, 作者就按这个写）:
      · **换行删掉不留痕**（`|` 字面块 ⇒ 换行原样留着 ⇒ 这里直接删）——
        作者可以把一句长立场折成任意多行, **汉字↔拉丁 交界处也不会多出空格**
        （`我非常信任\\nsensei` ⇒ `我非常信任sensei`）;
      · ⭐ **同一行里自己敲的空格保留**（`她极度信任 sensei 与 Aru` 照旧）——
        那是**内容**, 不是排版。
    ⚠️ 兼容 `>`（折叠块）: 它在**解析时**就把换行变成了空格 ⇒ 这里再用 `_CJK_GAP`
    兜掉"汉字之间"那种（拉丁旁边那种兜不掉 —— 所以**推荐 `|`**）。
    `knowledge.yml` 的 `SIG~friends` 今天正是被 `>` 咬的（`…在某个人面前 敞开心扉`）。
    """
    return _CJK_GAP.sub("", text.replace("\r\n", "\n").replace("\n", "")).strip()


def load_interperson(path: str | Path) -> dict:
    """读取 `interperson.yml`（缺失 → {}；损坏 → MmtExecError）。

    ⭐ **两种形状都收**（2026-10-08 换写法, 一次换一个角色）:
      · **新形**（值 = dict）: `{叫法: {"text": 立场句, "id"?: 角色 id, "name"/"aliases"?: …}}`
        —— "她眼里的他们"（主观看法, 从 `knowledge.yml` 的 `SIG~friends` 搬来,
        由 `ensure_entities(stances=…)` 物化成 `entity.text`）;
      · **旧形**（值 = 数字）: `{角色 id: 1|2|3}` —— 熟知程度。⚠️ 那是给
        `mmt_inspect_character` 开门的数字, 而它 **2026-10-08 已退役** ⇒
        今天**没有任何读者**（`hinomiya_chinatsu` 那一行还是这样）;
        读取照样收（表是作者的, 引擎不擅自解释）。

    ⚠️ 2026-10-08 起是 **YAML**（原来是 `.json`）: 值变成长句立场, JSON 写不了折行、
    还要转义; YAML 还能写真注释。⛔ 只认这一种格式（**不留第二条真源**）。
    ⚠️ 字符串值统一过 `_fold_layout`（**换行 = 排版, 空格 = 内容**）。

    Returns:
        `{char_id: {…}}`; ⚠️ **`__` 开头的键被丢掉**（防御: 旧 `.json` 用 `__comment__`
        写注释, 那种键会被候选表/渲染器当成一个"人"）。
    """
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        raise MmtExecError(f"interperson.yml 读取失败: {e}") from e
    if data is None:                                 # 空文件 = 没有关系, 不是错误
        return {}
    if not isinstance(data, dict):
        raise MmtExecError(f"interperson.yml 内容不是映射（{type(data).__name__}）: {path}")
    data = {k: v for k, v in data.items() if not str(k).startswith("__")}
    for entry in data.values():
        if not isinstance(entry, dict):
            continue
        for item in entry.values():
            if isinstance(item, dict):
                for key, value in item.items():
                    if isinstance(value, str):
                        item[key] = _fold_layout(value)
                    elif isinstance(value, list):
                        item[key] = [_fold_layout(v) if isinstance(v, str) else v
                                     for v in value]
    return data


# ============================================================================
# 执行器
# ============================================================================

class MmtExecutor:
    """MMT 动作执行器。characters_root = config/characters 目录。"""

    def __init__(
        self,
        characters_root: str | Path,
        interperson_path: str | Path | None = None,
        *,
        look_fn: Callable[[str, str, str], str] | None = None,
    ):
        """`look_fn`: ⭐ `mmt_look` 的**取数接缝**（`(entity, clue, when) -> 给她看的那段字`）。

        由 engine 注入（它手里有 store / 本轮 `now` / 角色名）—— 见
        `_execute_mmt_look` 的 docstring（为什么不把 store 塞进来）。
        ⚠️ `None` ⇒ 那次 `mmt_look` 抛 `MmtExecError`（明确报错, 不静默返回空）。
        """
        self.char_loader = CharacterLoader(characters_root)
        self.interperson_path = (
            Path(interperson_path) if interperson_path
            else Path(DEFAULT_INTERPERSON_PATH)
        )
        self.current_char: DynamicCharacter | None = None
        self.look_fn = look_fn

    # ------------------------------------------------------------------
    # 会话上下文
    # ------------------------------------------------------------------

    def set_current_character(self, char: DynamicCharacter | None) -> None:
        """设置会话当前角色（trigger/look 依赖它）。"""
        self.current_char = char

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    def execute(self, action: AgentAction) -> ExecResult:
        """执行一个已通过契约校验的 MMT 动作。抛 MmtExecError 表示不可执行。

        统一入口: 按动作名分派到 _execute_{action}。调用方捕获 MmtExecError
        并把 message 回灌给 LLM。
        """
        if action.domain != DOMAIN_MMT:
            raise MmtExecError(f"非 MMT 域动作: {action.domain}:{action.action}")
        handler = getattr(self, f"_execute_{action.action}", None)
        if handler is None:
            raise MmtExecError(f"未知执行动作: {action.action}")
        return handler(action)

    # ==================================================================
    # mmt_chat — 说一句话（正常回复核心路径）
    # ==================================================================

    def _execute_mmt_chat(self, action: AgentAction) -> ExecResult:
        """对白已在 action.reply——执行即确认。

        模拟手机操作（operation）是展示层元数据, 由调用方渲染, 无需执行。
        """
        return ExecResult(ok=True, message="已回复")

    # ==================================================================
    # mmt_look — 翻阅她自己的记忆（⭐ 真检索走注入的回调）
    # ==================================================================

    def _execute_mmt_look(self, action: AgentAction) -> ExecResult:
        """⭐ **接缝在构造参数**（2026-10-08）: 取数不在这里, 在 engine。

        为什么是回调而不是"把 `WikiStoreV2` 塞进 executor":
          · **store 是每会话重建的**（`start_session` 里建）⇒ 存成字段迟早是**陈旧引用**;
          · 检索还缺两样 executor 没有的东西: **本轮的 `now`**（`parse_when` 要）与
            角色的显示名/别名（第一人称渲染要）—— 它们都在 engine 手里;
          · 与 `engine.embed_fn` 那条接缝同一个哲学: **引擎给能力, 动作层给语义**。

        ⚠️ `look_fn` 缺席 ⇒ `MmtExecError`（**硬问题, 明确**）—— ⛔ 不静默返回空:
        那会让她以为"翻过了、没有", 而真相是"引擎没接线"。
        ⚠️ 反过来, "翻了但没翻到"是**正常结果**（`ok=True` + 一段人话）, 不是失败。
        """
        if self.current_char is None:
            raise MmtExecError("尚未进入会话, 无法翻阅记忆")
        if self.look_fn is None:
            raise MmtExecError("mmt_look 未接线（引擎没有注入 look_fn）")
        entity = action.payload.get("entity") or ""
        clue = action.payload.get("clue") or ""
        when = action.payload.get("when") or ""
        return ExecResult(ok=True, message=str(self.look_fn(entity, clue, when)))

    # ==================================================================
    # mmt_send_media — 发图片（占位, 媒体管线后续接入）
    # ==================================================================

    def _execute_mmt_send_media(self, action: AgentAction) -> ExecResult:
        """图片发送占位——存储/查库/LLM 生成管线未接入, 仅回灌确认。

        用户已确认: 媒体方案先不细化, 保证回复流程正常即可。
        不伪造图片, 明说占位让 LLM 知道媒体尚未真实落地。
        """
        desc = action.payload["image"]
        library_id = action.payload["library_id"]
        if library_id:
            message = (
                f"[图片占位] 引用资源库 {library_id}（{desc}）——"
                "媒体管线未接入, 后续落地查库/生成"
            )
        else:
            message = (
                f"[图片占位] {desc}——媒体管线未接入, 后续落地查库/生成"
            )
        return ExecResult(ok=True, message=message)

    # ==================================================================
    # mmt_trigger_bond_story — bool 触发判定（好感度门槛 + LLM 决策）
    # ==================================================================

    def _execute_mmt_trigger_bond_story(self, action: AgentAction) -> ExecResult:
        if self.current_char is None:
            raise MmtExecError("尚未进入会话, 无法触发羁绊剧情")

        # 2026-09-02 v2（用户复盘拍板）: **引擎不拦节奏**——轮数不再是闸门
        # （玩家遇险时角色尬聊 6 轮是硬拒的伪正确）。
        # ⭐ 2026-10-08（P16 封印）: 连"每轮注记按轮次建议时机"那半也退役了 ——
        #    现在**引擎对触发时机彻底不表态**（既不放闸也不催）; 何时触发只由
        #    规则书 §【羁绊剧情触发】的契机判据 + LLM 的剧情与人设判断决定。
        # 触发与否全权交给 LLM 的剧情判断——紧急/危险场面随时可触发。
        # 2026-09-05: reason 退役——payload 带 chapter_title（本章标题, 触发即命题）;
        # 起因由上下文窗口承载（触发前对话在窗口里, bond 首场自带）
        title = str(action.payload.get("chapter_title") or "").strip()
        suffix = f"（本章: {title}）" if title else ""
        return ExecResult(
            ok=True,
            message=f"羁绊剧情触发成功{suffix}——切换到羁绊剧情模式",
        )

    # ==================================================================
    # 内部
    # ==================================================================
