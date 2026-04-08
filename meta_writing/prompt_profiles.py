"""Project-specific prompt profiles.

These profiles let shared agents stay generic while still applying
project-level style constraints where appropriate.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptProfile:
    key: str
    display_name: str
    planner_notes: str = ""
    writer_notes: str = ""
    expansion_notes: str = ""
    revision_notes: str = ""
    continuity_notes: str = ""
    negative_examples_profile: str | None = None
    theme_review_enabled: bool = False


GENERIC_PROFILE = PromptProfile(
    key="generic",
    display_name="通用项目",
    planner_notes="""\
## 项目风格附加约束

- 以角色动机、冲突推进、信息节奏和章末钩子为核心。
- 不要默认任何特定审美流派；除非创作者指导明确要求，否则不要自行注入“克制美学/微感/留白”或固定平台套路。
""",
    writer_notes="""\
## 项目风格附加约束

- 让人物像人在现场说话和行动，不要把每句台词都写成结论或金句。
- 风格遵循当前项目指导，不要把其他小说的专用写法规约带进来。
""",
    expansion_notes="""\
## 扩写约束

- 优先补足场景推进、人物互动和必要细节，不要把扩写写成另一种风格的重写。
""",
    revision_notes="""\
## 修订约束

- 优先修正具体问题，不要趁修订时替项目切换风格。
""",
    continuity_notes="""\
## 风格化审查边界

- 只检查真正影响连续性的风格问题或知识流错误。
- 不要额外执行任何项目外的专用文风审查规则。
""",
)


TOMATO_ROMANCE_PROFILE = PromptProfile(
    key="tomato_romance",
    display_name="番茄快节奏女频",
    planner_notes="""\
## 项目风格附加约束（番茄快节奏）

- 规划优先保证高梗密度、快节奏、强情绪和明确的关系推进。
- 每章尽量有具体动作、拉扯、笑点/爽点和结尾钩子，不要把章节规划成抒情散文。
- 不要自行套用其他项目专属的文学化规约。
""",
    writer_notes="""\
## 项目风格附加约束（番茄快节奏）

- 对话以生活化、即时反应和人物拉扯为先，少用句句落结论的台词。
- 节奏要快，但场景里仍要有具体动作和信息推进，避免空喊情绪。
- 系统、反转、笑点、爽点要服务当前场景，不要喧宾夺主。
- 不要自行切到“克制美学/微感/留白”写法，除非创作者指导明确要求。
""",
    expansion_notes="""\
## 扩写约束（番茄快节奏）

- 扩写优先补足冲突链条、互动层次和包袱回收，而不是增加抒情停顿。
- 保持章节推进感，新增段落也要继续服务爽点、笑点或关系变化。
""",
    revision_notes="""\
## 修订约束（番茄快节奏）

- 修订时优先处理台词过于宣言化、系统过度介入、信息堆叠过满等问题。
""",
    continuity_notes="""\
## 风格化审查边界（番茄快节奏）

- 审查重点是人物状态、信息流、剧情因果，以及高梗密度快节奏项目常见的节奏性错误。
- 不做额外的文学风格专项审查，也不要用慢热文学标准去否定快节奏表达。
""",
)


LITERARY_MICROFEEL_PROFILE = PromptProfile(
    key="literary_microfeel",
    display_name="克制微感文学",
    planner_notes="""\
## 本作风格要求（克制美学）

- 人物不直接说破情感，用行动、物件、沉默推进关系。
- 感知描写只给物理细节，不替角色总结情绪。
- 关系推进通过具体事件、共同感知、遗留物和沉默时刻，而非心理剖白。
- 每章要有一个具体的感知场景，伏笔推进要自然，不要直接写“她意识到XX”。
""",
    writer_notes="""\
## 本作风格要求（克制美学）

- 用动作、物件、停顿和空间感承接情绪，不直白下定义。
- 微感描写只写物理痕迹，不写“X记得Y”、不拟人、不读心、不替读者总结。
""",
    expansion_notes="""\
## 扩写约束（克制微感）

- 扩写优先补足物理细节、静默互动和场景层次，不要用大段解释替代留白。
""",
    revision_notes="""\
## 修订约束（克制微感）

- 修订时保持克制和留白，不要为了说明问题而改成直白解释。
""",
    continuity_notes="""\
## 微感描写文风

- 涉及微感（通过触觉/听觉感知物体残留痕迹）的描写必须遵守“纯感官、不解读”原则。
- ❌ “X记得Y”句式、拟人化、读心术、直白情感总结。
- ✅ 只写声音的频率/质感/层次、温度的分布/变化、磨损的形状/深浅，让读者自己连线。
""",
    negative_examples_profile="literary_microfeel",
    theme_review_enabled=True,
)


PROMPT_PROFILES = {
    GENERIC_PROFILE.key: GENERIC_PROFILE,
    TOMATO_ROMANCE_PROFILE.key: TOMATO_ROMANCE_PROFILE,
    LITERARY_MICROFEEL_PROFILE.key: LITERARY_MICROFEEL_PROFILE,
}


def get_prompt_profile(key: str | None) -> PromptProfile:
    if key and key in PROMPT_PROFILES:
        return PROMPT_PROFILES[key]
    return GENERIC_PROFILE


def detect_prompt_profile(
    creator_guidance: str = "",
    target_satisfaction_type: str = "",
) -> PromptProfile:
    combined = "\n".join(
        part.strip()
        for part in (creator_guidance, target_satisfaction_type)
        if part and part.strip()
    )

    literary_markers = (
        "克制美学",
        "微感",
        "留白",
        "纯感官",
        "物体记录时间",
        "不解释",
    )
    if any(marker in combined for marker in literary_markers):
        return LITERARY_MICROFEEL_PROFILE

    tomato_markers = (
        "番茄",
        "高梗密度",
        "快节奏",
        "强情绪",
        "系统向",
        "打脸",
        "吐槽",
        "爽点",
        "拉扯",
        "女频",
    )
    if any(marker in combined for marker in tomato_markers):
        return TOMATO_ROMANCE_PROFILE

    return GENERIC_PROFILE
