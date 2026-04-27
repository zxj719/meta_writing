"""Project-specific prompt profiles."""

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
    third_editor_enabled: bool = True
    third_editor_mode: str = "story"


GENERIC_PROFILE = PromptProfile(
    key="generic",
    display_name="通用项目",
    planner_notes="""\
## 项目风格附加约束

- 以角色动机、冲突推进、信息节奏和章末钩子为核心。
- 除非创作者明确要求，否则不要自行注入某种固定审美流派。
""",
    writer_notes="""\
## 项目风格附加约束

- 让人物像活人在现场说话和行动，不要把每句台词都写成结论。
- 主要角色要持续带着外貌、神态和站姿锚点。
- 环境不能只报地点名，要让光线、气味、声音或温度参与叙事。
""",
    expansion_notes="""\
## 扩写约束

- 优先补场景推进、人物互动和必要细节，不要把扩写写成换文风。
""",
    revision_notes="""\
## 修订约束

- 优先修具体问题，不要借修订之机切风格。
""",
    continuity_notes="""\
## 审查边界

- 只检查真正影响连贯性、信息流和人物状态的问题。
""",
    third_editor_enabled=True,
    third_editor_mode="story",
)


TOMATO_ROMANCE_PROFILE = PromptProfile(
    key="tomato_romance",
    display_name="番茄快节奏女频",
    planner_notes="""\
## 项目风格附加约束（番茄快节奏）

- 规划优先保证高梗密度、快节奏、强情绪和明确的关系推进。
- 每章尽量有具体动作、拉扯、笑点/爽点和章尾钩子。
- 不要把章节规划成抒情散文或慢热文学章。
""",
    writer_notes="""\
## 项目风格附加约束（番茄快节奏）

- 对话以生活化、即时反应和人物拉扯为先，少写宣言式台词。
- 节奏要快，但场景里仍要有具体动作和信息推进。
- 避免模板式断句和“不是……是……”这类重复脚手架。
- 主角外貌锚点要持续出现，关键高光时刻优先补神态和环境。
""",
    expansion_notes="""\
## 扩写约束（番茄快节奏）

- 扩写优先补冲突链条、互动层次和包袱回收。
- 新增段落仍要服务笑点、爽点或关系推进。
""",
    revision_notes="""\
## 修订约束（番茄快节奏）

- 优先处理台词太像口号、系统抢戏、支线堆叠和 AI 腔脚手架。
- 如果出现外貌、神态、环境缺口，要定点补上。
""",
    continuity_notes="""\
## 审查边界（番茄快节奏）

- 审查重点是高梗密度、快节奏项目里的人物状态、信息流、剧情因果和常见节奏性错误。
- 不要用慢热文学标准否定快节奏表达。
""",
    third_editor_enabled=True,
    third_editor_mode="story",
)


LITERARY_MICROFEEL_PROFILE = PromptProfile(
    key="literary_microfeel",
    display_name="克制微感文学",
    planner_notes="""\
## 本作风格要求（克制美学）

- 人物不直说情绪，用动作、物件、停顿和沉默推进关系。
- 微感描写只给物理痕迹，不替读者下总结。
""",
    writer_notes="""\
## 本作风格要求（克制美学）

- 用动作、物件、空间和停顿承接情绪，不直白下定义。
- 微感描写只写物理痕迹，不读心，不拟人。
""",
    expansion_notes="""\
## 扩写约束（克制微感）

- 扩写优先补物理细节、静默互动和场景层次，不用大段解释替代留白。
""",
    revision_notes="""\
## 修订约束（克制微感）

- 修订时保持克制和留白，不要因为说明问题而改成解释腔。
""",
    continuity_notes="""\
## 微感描写风格

- 涉及微感时必须遵守“纯感官、不解释”原则。
- 禁止“X 记得 Y”句式、拟人化、读心术和直接情绪总结。
""",
    negative_examples_profile="literary_microfeel",
    third_editor_enabled=True,
    third_editor_mode="literary_theme",
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
