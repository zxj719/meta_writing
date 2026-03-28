"""Negative example library — bad→good pairs from actual editorial fixes.

Injected into Writer and Expansion prompts to prevent known anti-patterns
from being generated in the first place.

Each example has:
- category: which rule it violates
- bad: the original problematic text
- good: the corrected version
- why: brief explanation of the fix
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StyleExample:
    category: str
    bad: str
    good: str
    why: str


# Curated from Ch4/Ch5 actual edits
NEGATIVE_EXAMPLES: list[StyleExample] = [
    # --- Object "remembers" ---
    StyleExample(
        category="物体记得",
        bad="沙发记得他坐下去的弧度",
        good="沙发的弹簧在那个位置有一个弧度，布料在那里凹下去一块",
        why="物体没有记忆，只写物理现象",
    ),
    StyleExample(
        category="物体记得",
        bad="铁皮记得那种温度",
        good="被捂过的铁皮振动频率不同，声音闷一些、钝一些",
        why="温度是物理痕迹，不是记忆",
    ),
    StyleExample(
        category="物体记得",
        bad="砚台记得墨汁的重量",
        good="砚台底部有一圈磨损的痕迹，中间凹下去一点——长年累月研墨留下的",
        why="用磨损痕迹替代'记得'",
    ),
    # --- Personification ---
    StyleExample(
        category="拟人化",
        bad="书店在等。八十七天。",
        good="雨还在下。落在卷帘门上，落在窗台的积灰里，落在门槛的锈迹上。八十七天。",
        why="书店不会'等'，用环境细节传达空置感",
    ),
    StyleExample(
        category="拟人化",
        bad="墙壁在叹气",
        good="墙皮在潮气里起了泡，指甲大小的碎片翘起来",
        why="墙壁只有物理状态",
    ),
    # --- Over-explanation / technical ---
    StyleExample(
        category="过度解释",
        bad="不是微感的声音，是真实的、当下的、物理的声音",
        good="翻页声落在耳朵里，轻而清晰",
        why="不需要反复标注'这是真实声音'，直接写声音本身",
    ),
    StyleExample(
        category="过度解释",
        bad="这让她意识到了一件事：她以前听到的只是'表面'",
        good="（删除顿悟陈述，让层次感通过描写自然呈现）",
        why="不替读者总结领悟，让描写说话",
    ),
    StyleExample(
        category="科技术语",
        bad="弹簧在长年累月的压缩和回弹中，金属晶格在微观层面发生了变化",
        good="旧弹簧的声音是闷的，带着一种钝感，像被磨了太久的刀刃",
        why="感官比喻替代材料科学术语",
    ),
    StyleExample(
        category="科技术语",
        bad="棉纤维细胞壁在缓慢的氧化中发生了微观的坍塌",
        good="布面摸上去有一种绵软的粗糙，像被洗了太多次的旧毛巾",
        why="触觉比喻替代化学术语",
    ),
    # --- Direct emotion ---
    StyleExample(
        category="直白情感",
        bad="她懂了那种孤独",
        good="她的手从书架上收回来，攥了一下，松开",
        why="用动作替代情感陈述",
    ),
    StyleExample(
        category="直白情感",
        bad="她感到一阵安心",
        good="她的肩膀松下来了一点",
        why="身体反应替代心理描写",
    ),
    # --- Overuse of "她不知道" ---
    StyleExample(
        category="她不知道",
        bad="她不知道自己在干什么。她不知道为什么会这样。她不知道该怎么办。",
        good="她把一本诗集从第二排挪到第三排，又从第三排挪回来。",
        why="用无意识的重复动作替代'不知道'堆砌",
    ),
]


def format_examples_for_prompt(max_examples: int = 8) -> str:
    """Format negative examples as a prompt section for the Writer."""
    lines = [
        "## 已知反模式及修正（从实际编辑中提取）\n",
        "以下是之前章节中被修正的写法。请在写作时避免类似模式：\n",
    ]

    for i, ex in enumerate(NEGATIVE_EXAMPLES[:max_examples], 1):
        lines.append(f"### 反模式{i}：{ex.category}")
        lines.append(f"- ❌ 原文：「{ex.bad}」")
        lines.append(f"- ✅ 改为：「{ex.good}」")
        lines.append(f"- 原因：{ex.why}")
        lines.append("")

    return "\n".join(lines)
