"""IDE 域动作注册 — 角色配置写入。

当前实现:
    create_character    新建角色目录（files 子集, 至少 profile.yml）
    update_character    改已有角色（mode: merge / overwrite, files 子集）
    update_interperson  人际关系（全量快照 + 角色粒度替换, 非增量）
    fetch_url           抓取网页资料（只读, APPROVAL_NEVER, 结果回灌给 LLM）
    done                收尾动作（LLM 声明本轮结束 / 等待用户）
        - 按文件类型校验（per-file validator）: profile 先实现, 其余占位
        - 显示名单一真源 = profile.yml 的 REQ~most_called_name,
          契约层在"文件是最终形态"时提取写进 payload["display_name"]（供审批/日志）

mode 语义（update_character）:
    overwrite   files 里的文件用提交的**完整内容**覆盖；未列出的文件不动
    merge       files 里的文件**字段级合并**进现有文件——提交的字段覆盖现有，
                现有未提及的字段保留；未列出的文件不动
    契约层按 mode 调整校验强度: overwrite → 完整检查; merge → 只验证提交的字段
    （完整性由执行层合并后检查）

update_interperson 语义:
    relations 是**该角色的完整关系快照**——LLM 提交后程序按角色粒度整体替换
    该角色在 interperson.json 中的条目，其他角色条目不动。既不是增量 append
    （无删除歧义：想删就在快照里去掉），也不是整文件覆盖（冲突面最小）。
    新增关系的依据硬校验（宁缺勿错）在执行层完成——执行层读现有文件对比出
    新增关系，若新增关系既无 sources 也无 basis 则拒绝执行并回灌给 LLM。
    契约层不访问文件系统、无法判断"新增"，故不做该硬校验。

fetch_url 语义:
    只读工具动作——LLM 需要资料时请求抓取, 结果由执行层回灌给 LLM 继续推理
    （interperson 查表失败、create 需要资料来源时都依赖它）。
    默认资料来源: 萌娘百科 / kivowiki / BAfandomwiki；v1 允许任意 http/https URL。
    契约层只校验请求结构；抓取（httpx + html.parser）与回灌是执行层职责。

TODO（未来 session）:
    1. search    搜索接口（DESIGN.md 预留, 先不实现）
    2. 快速写接口  用户显式指定目录, 对**仅 .yml** 做快速写/overwrite——
       受限后门: 路径由用户显式给 + 文件名后缀白名单（.yml）, 不做语义校验
    3. 跨文件键冲突检测: 主项目合并顺序 profile→personality→knowledge→
       experience→typical, 先加载优先（profile 赢）。顶层 key 跨文件重复 →
       warning 提示是否有意的覆盖（主项目语义明确, 不阻断）。
    4. 目录存在性 / 写盘 / diff / merge 合并 / interperson 对比新增 /
       网页抓取 = 执行层（executor）职责——契约层不访问文件系统, create 的
       "目录必须不存在"、update 的"目录必须存在"都在执行器检查。
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import yaml

from contract import (
    IDEActionRegistry,
    ActionSpec,
    APPROVAL_NEVER,
    APPROVAL_REQUIRED,
    RUNTIME_SHELL_FIELDS,
    ContractError,
    ValidationResult,
    is_valid_identifier,
)

# 角色五件套（与主项目 parsing.dynamic_character_parser._CHARACTER_FILES 对齐）
CHARACTER_FILES = (
    "profile.yml",
    "personality.yml",
    "knowledge.yml",
    "experience.yml",
    "typical.yml",
)
CHARACTER_FILE_SET = frozenset(CHARACTER_FILES)

# update 模式
MODE_MERGE = "merge"
MODE_OVERWRITE = "overwrite"
UPDATE_MODES = frozenset({MODE_MERGE, MODE_OVERWRITE})

# 抓取文本长度上限（防超长响应撑爆上下文）
MAX_FETCH_CHARS = 50000

# IDE 只读/收尾动作的外壳字段：运行时最小集 + reply（AI 对用户的话）
IDE_RUNTIME_FIELDS = RUNTIME_SHELL_FIELDS | frozenset({"reply"})


# ============================================================================
# 文件类型校验器（per-file validator）
# ============================================================================

def _validate_profile(yml: dict, payload: dict, errors: list[str], warnings: list[str], require_complete: bool) -> None:
    """profile.yml 内容校验 + 提取显示名。

    require_complete=True（create / overwrite）时:
        - 强制 REQ~most_called_name——它是主项目 get_display_name 的
          **代码级依赖**（列表/会话名显示必需），故比其他 REQ~ 字段严格。
          其余 REQ~ 字段无法在此检测缺失：约定驱动下没有固定字段清单
          （加字段 = 改 YAML 零代码），"没写的字段"不在 dict 里、无法枚举。
        - 提取显示名写回 payload（单一真源在 profile.yml）。
    require_complete=False（merge 补丁）时:
        只验证提交的字段本身——完整性由执行层合并后检查。
    """
    if not require_complete:
        return

    name = yml.get("REQ~most_called_name", "")
    if not isinstance(name, str) or not name.strip():
        errors.append("profile.yml 必须包含非空 REQ~most_called_name（界面显示名）")
    else:
        payload["display_name"] = name.strip()


def _validate_pending(yml: dict, payload: dict, errors: list[str], warnings: list[str], require_complete: bool) -> None:
    """未实现的文件类型校验器占位（personality/knowledge/experience/typical）。

    TODO(后续): 各文件类型的结构校验——行为逻辑层、独有知识库、预设经历、
    校准样本。当前 session 只覆盖 profile。
    """
    # 占位：显式忽略参数，保持与分派表签名一致
    del yml, payload, errors, warnings, require_complete


# 文件类型 → 校验器分派表
_FILE_VALIDATORS = {
    "profile.yml": _validate_profile,
    "personality.yml": _validate_pending,
    "knowledge.yml": _validate_pending,
    "experience.yml": _validate_pending,
    "typical.yml": _validate_pending,
}


# ============================================================================
# 共享：files 结构白名单
# ============================================================================

def _parse_files(files: Any, *, require_nonempty: bool) -> dict[str, str]:
    """files 结构白名单校验（硬错误）。返回 {文件名: YAML 文本}。"""
    if not isinstance(files, dict):
        raise ContractError("files 必须是对象（{文件名: YAML 文本}）")
    if require_nonempty and not files:
        raise ContractError("至少需要提供一个文件")

    clean: dict[str, str] = {}
    for name, content in files.items():
        if name not in CHARACTER_FILE_SET:
            raise ContractError(
                f"未知文件: {name!r}（允许: {', '.join(CHARACTER_FILES)}）"
            )
        if not isinstance(content, str) or not content.strip():
            raise ContractError(f"{name} 必须是非空 YAML 文本")
        clean[name] = content
    return clean


def _validate_files_content(payload: dict, require_complete: bool) -> ValidationResult:
    """共享内容校验：解析每个文件的 YAML 并按类型分派校验器。"""
    errors: list[str] = []
    warnings: list[str] = []

    for name, content in payload["files"].items():
        try:
            yml = yaml.safe_load(content)
        except yaml.YAMLError as e:
            errors.append(f"{name} YAML 解析失败: {e}")
            continue

        if not isinstance(yml, dict):
            errors.append(f"{name} 必须解析为对象（dict），不能是 null/空/列表")
            continue

        _FILE_VALIDATORS[name](yml, payload, errors, warnings, require_complete)

        # TODO(后续): 跨文件键冲突检测——主项目合并顺序 profile→…→typical,
        # 先加载优先（profile 赢）。顶层 key 跨文件重复 → warning 提示是否
        # 有意的覆盖。当前不实现，仅占位标注。

    return ValidationResult(tuple(errors), tuple(warnings))


# ============================================================================
# create_character — 新建角色目录
# ============================================================================

def parse_create_character(payload: dict[str, Any]) -> dict[str, Any]:
    """结构白名单校验（硬错误, 抛 ContractError）。

    只做结构层：不解析 YAML、不访问文件系统。
    """
    char_id = payload.get("character_id")
    if not is_valid_identifier(char_id):
        raise ContractError(
            f"character_id 必须匹配 [a-z0-9_]+ 且 ≤64 字符: {char_id!r}"
        )

    files = _parse_files(payload.get("files"), require_nonempty=True)
    if "profile.yml" not in files:
        raise ContractError("create_character 至少需要 profile.yml")

    return {
        "character_id": char_id,
        "files": files,
    }


def validate_create_character(payload: dict[str, Any]) -> ValidationResult:
    """内容软校验：新文件即最终形态 → require_complete=True。"""
    return _validate_files_content(payload, require_complete=True)


# ============================================================================
# update_character — 改已有角色
# ============================================================================

def parse_update_character(payload: dict[str, Any]) -> dict[str, Any]:
    """结构白名单校验（硬错误, 抛 ContractError）。"""
    char_id = payload.get("character_id")
    if not is_valid_identifier(char_id):
        raise ContractError(
            f"character_id 必须匹配 [a-z0-9_]+ 且 ≤64 字符: {char_id!r}"
        )

    mode = payload.get("mode", MODE_OVERWRITE)
    if mode not in UPDATE_MODES:
        raise ContractError(f"mode 必须是 {MODE_MERGE} 或 {MODE_OVERWRITE}: {mode!r}")

    files = _parse_files(payload.get("files"), require_nonempty=True)

    return {
        "character_id": char_id,
        "mode": mode,
        "files": files,
    }


def validate_update_character(payload: dict[str, Any]) -> ValidationResult:
    """内容软校验。

    overwrite → 提交的是完整文件, 完整检查（require_complete=True）；
    merge     → 提交的是补丁, 只验证提交的字段（require_complete=False），
                最终完整性由执行层合并现有文件后检查。
    """
    require_complete = payload["mode"] == MODE_OVERWRITE
    return _validate_files_content(payload, require_complete=require_complete)


# ============================================================================
# update_interperson — 人际关系（全量快照 + 角色粒度替换）
# ============================================================================

def parse_update_interperson(payload: dict[str, Any]) -> dict[str, Any]:
    """结构白名单校验（硬错误, 抛 ContractError）。

    只做结构层：不访问文件系统——"哪些关系是新增"由执行层对比现有文件判断。
    """
    char_id = payload.get("character_id")
    if not is_valid_identifier(char_id):
        raise ContractError(
            f"character_id 必须匹配 [a-z0-9_]+ 且 ≤64 字符: {char_id!r}"
        )

    relations = payload.get("relations")
    if not isinstance(relations, dict):
        raise ContractError("relations 必须是对象（{关系角色id: 权重}）")
    if not relations:
        raise ContractError("relations 不能为空")

    clean: dict[str, int] = {}
    for name, weight in relations.items():
        if not is_valid_identifier(name):
            raise ContractError(f"关系角色 id 非法: {name!r}")
        if isinstance(weight, bool) or not isinstance(weight, int):
            raise ContractError(f"权重必须是整数（不能是 bool）: {name}={weight!r}")
        clean[name] = weight

    return {
        "character_id": char_id,
        "relations": clean,
    }


def validate_update_interperson(payload: dict[str, Any]) -> ValidationResult:
    """内容软校验。

    注：新增关系的依据硬校验（宁缺勿错）不在此处——它需要读现有 interperson.json
    对比出"新增"关系，属于执行层职责。这里只做不依赖文件系统的软检查。
    """
    errors: list[str] = []
    warnings: list[str] = []

    for name, weight in payload["relations"].items():
        if weight < 1 or weight > 5:
            warnings.append(
                f"关系 {name} 权重 {weight} 超出常见范围 1-5，请确认是否有意"
            )

    return ValidationResult(tuple(errors), tuple(warnings))


# ============================================================================
# fetch_url — 抓取网页（只读工具, 结果回灌 LLM）
# ============================================================================

def _is_http_url(url: str) -> bool:
    """校验 http/https 完整 URL（有 netloc）。"""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def parse_fetch_url(payload: dict[str, Any]) -> dict[str, Any]:
    """结构校验（硬错误, 抛 ContractError）。

    只校验请求结构；抓取（httpx + html.parser）与结果回灌是执行层职责。
    """
    url = payload.get("url")
    if not isinstance(url, str) or not url.strip():
        raise ContractError("url 必须是非空字符串")
    url = url.strip()
    if not _is_http_url(url):
        raise ContractError(f"url 必须是合法的 http/https 地址: {url!r}")

    clean: dict[str, Any] = {"url": url}

    max_chars = payload.get("max_chars")
    if max_chars is not None:
        if isinstance(max_chars, bool) or not isinstance(max_chars, int):
            raise ContractError("max_chars 必须是正整数")
        if not 1 <= max_chars <= MAX_FETCH_CHARS:
            raise ContractError(f"max_chars 必须在 1-{MAX_FETCH_CHARS} 之间")
        clean["max_chars"] = max_chars

    return clean


# ============================================================================
# done — 收尾（LLM 声明本轮结束 / 等待用户）
# ============================================================================

def parse_done(payload: dict[str, Any]) -> dict[str, Any]:
    """收尾动作：几乎无 payload, 允许可选 message 补充说明。

    agent loop 收到 done 即停止本轮循环, 把控制权交回用户。
    """
    clean: dict[str, Any] = {}
    msg = payload.get("message")
    if msg is not None:
        if not isinstance(msg, str) or not msg.strip():
            raise ContractError("message 必须是非空字符串")
        clean["message"] = msg.strip()
    return clean


# ============================================================================
# IDE 注册表
# ============================================================================

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
