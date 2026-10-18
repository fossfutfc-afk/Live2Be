"""剧情基调（story tone）— 从角色卡读取（personality.yml 的 SIG~story_tone）。

**为什么写在五件套里**: 基调是"角色是谁"的一部分——AI 从卡学习角色,
基调也必须从卡来（story_tones.json 独立配置会让 AI 的理解和卡的设定脱节）。
五件套的作者用心写卡 → 基调自然贴合角色。

**为什么在对话生成层注入（DESIGN_BRAIN.md §0 基调，见 docs/archive/）**: 基调必须在"最一开始"
告诉 AI——mmt/VN 开场时注入 system prompt, 让**生成的剧情**符合角色类型
（谐星向/照顾向/…）; digest 是事后提炼, 剧情已经生成完了, 救不了基调。

谐星向角色（阿露）: 无厘头/吃瘪是常态, 但关键时也要认真的互诉衷肠;
照顾向角色（遥香）: 成长与被照顾是主线, 谐星适可而止。

⚠️ 2026-10-15 搬进 `core/parsing/`（原住 `core/common/`）—— 它是**角色卡访问器**
（读 `DynamicCharacter.story_tone`）, 与 `core/parsing/` 里那些"从卡里读东西"的件同族,
不是横切基础设施。
⚠️ `DEFAULT_TONE` 是**进 system prompt 的文案**（住在 `.py` 里）—— 按 1e 的标准,
"人可改的提示词"该住 md; 今天先记在这儿, 没动（它是兜底那一条, 改的频率低）。
"""

from __future__ import annotations

#: 默认通用基调（角色卡未配置 SIG~story_tone → 兜底, 不挡会话）
DEFAULT_TONE = (
    "剧情基调：通用——积极正面、阳光向上; 适度谐星与认真并存, "
    "两者的切换自然发生（不强行升华, 也不为了搞笑牺牲真实感）"
)


def load_story_tone(char=None, character_id: str = "") -> str:
    """角色剧情基调文本（从 DynamicCharacter.story_tone 读）;

    未配置 → 默认通用基调（宁缺勿错）。兼容传 char 对象或仅 character_id
    （后者无法查卡 → 直接返回默认; 调用方应优先传已加载的 char）。
    """
    tone = ""
    if char is not None:
        tone = getattr(char, "story_tone", "") or ""
    if isinstance(tone, str) and tone.strip():
        return tone.strip()
    return DEFAULT_TONE
