"""IDE 域动作 — 分文件组织。

    common.py      共享: 常量 + per-file 校验器 + files 白名单
    character.py   create_character / update_character
    interperson.py update_interperson
    net.py         fetch_url / done

动作语义:
    create_character    新建角色目录（files 子集, 至少 profile.yml）
    update_character    改已有角色（mode: merge / overwrite, files 子集）
    update_interperson  人际关系（全量快照 + 角色粒度替换, 非增量）
    fetch_url           抓取网页资料（只读, APPROVAL_NEVER, 结果回灌给 LLM）
    done                收尾动作（LLM 声明本轮结束 / 等待用户）

mode 语义（update_character）:
    overwrite   files 里的文件用提交的**完整内容**覆盖；未列出的文件不动
    merge       files 里的文件**字段级合并**进现有文件——提交的字段覆盖现有，
                现有未提及的字段保留；未列出的文件不动
    契约层按 mode 调整校验强度: overwrite → 完整检查; merge → 只验证提交的字段

update_interperson 语义:
    relations 是**该角色的完整关系快照**——程序按角色粒度整体替换该角色在
    interperson.json 中的条目，其他角色条目不动。新增关系的依据硬校验
    （宁缺勿错）在执行层完成（读现有文件对比"新增"），契约层不做。

fetch_url 语义:
    只读工具动作——LLM 需要资料时请求抓取, 结果由执行层回灌给 LLM 继续推理。
    默认资料来源: 萌娘百科 `https://zh.moegirl.org.cn/`（已验证可用）。
    契约层只校验请求结构；抓取与回灌是执行层职责。

TODO（未来 session）:
    1. search    搜索接口（DESIGN.md 预留, 先不实现）
    2. 快速写接口  用户显式指定目录, 对**仅 .yml** 做快速写/overwrite——
       受限后门: 路径由用户显式给 + 文件名后缀白名单（.yml）, 不做语义校验
    3. 跨文件键冲突检测: 主项目合并顺序 profile→…→typical, 先加载优先
       （profile 赢）。顶层 key 跨文件重复 → warning（主项目语义明确, 不阻断）
"""

from __future__ import annotations

from contract import (
    IDEActionRegistry,
    ActionSpec,
    APPROVAL_NEVER,
    APPROVAL_REQUIRED,
)

from fetch.actions.common import IDE_RUNTIME_FIELDS
from fetch.actions.character import (
    parse_create_character,
    parse_update_character,
    validate_create_character,
    validate_update_character,
)
from fetch.actions.interperson import (
    parse_update_interperson,
    validate_update_interperson,
)
from fetch.actions.net import parse_done, parse_fetch_url


def build_ide_registry() -> IDEActionRegistry:
    """构建注册了全部 IDE 动作的注册表。"""
    registry = IDEActionRegistry()
    registry.register(ActionSpec(
        "create_character",
        parse_create_character,
        APPROVAL_REQUIRED,
        validate_create_character,
        payload_schema=(
            "character_id: 小写英文全名+下划线, 如 igusa_haruka\n"
            "files: 对象, 键 ∈ {profile.yml, personality.yml, knowledge.yml, "
            "experience.yml, typical.yml};\n"
            "      profile.yml 必填且须含非空 REQ~most_called_name;\n"
            "      遵循 REQ~/SIG~/无前缀/null 字段约定"
        ),
    ))
    registry.register(ActionSpec(
        "update_character",
        parse_update_character,
        APPROVAL_REQUIRED,
        validate_update_character,
        payload_schema=(
            "character_id: 要更新的角色 id\n"
            "mode: 'merge'（字段级合并, 现有未提及的字段保留）或 "
            "'overwrite'（整体覆盖, 默认）\n"
            "files: 对象, 至少一个文件; 键 ∈ 五件套;\n"
            "      overwrite 模式 profile.yml 须含非空 REQ~most_called_name"
        ),
    ))
    registry.register(ActionSpec(
        "update_interperson",
        parse_update_interperson,
        APPROVAL_REQUIRED,
        validate_update_interperson,
        payload_schema=(
            "character_id: 要更新的角色 id（interperson.json 的外层 key）\n"
            "relations: 该角色的**完整关系快照**（整体替换, 不是增量）:\n"
            "      {关系角色id: 权重int}, 如 {'rikuhachima_aru': 2, ...}\n"
            "      想删掉某关系就在快照中去掉; 新增关系必须有依据"
        ),
    ))
    registry.register(ActionSpec(
        "fetch_url",
        parse_fetch_url,
        APPROVAL_NEVER,
        prompt_fields=IDE_RUNTIME_FIELDS,  # 只读动作: 无 sources/basis, 但支持 reply
        payload_schema=(
            "url: 要抓取的网页完整 URL（http/https）。"
            "萌娘百科默认 https://zh.moegirl.org.cn/（zh.moegirl.cn 等已失效）\n"
            "max_chars: 可选, 限制返回文本最大字符数（1-50000, 默认由执行层决定）"
        ),
    ))
    registry.register(ActionSpec(
        "done",
        parse_done,
        APPROVAL_NEVER,
        prompt_fields=IDE_RUNTIME_FIELDS,
        payload_schema=(
            "message: 可选, 给用户的一句话补充说明（留空即默认'等待用户'）"
        ),
    ))
    return registry
