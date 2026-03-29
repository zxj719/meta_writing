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
    # --- Structural planning headers in prose ---
    StyleExample(
        category="规划标记残留",
        bad="**节点二：声音博物馆**\n\n夏浮站在供销社门口……",
        good="夏浮站在供销社门口……",
        why="**节点X**是规划标记，不是正文——直接输出正文，不留结构标题",
    ),
    # --- 刻度 over-reporting ---
    StyleExample(
        category="刻度过度汇报",
        bad="刻度从两升到两点五。……刻度升到三。……刻度从三升到三点五。……刻度回落到三。",
        good="刻度从两升到三点五。（只记录开章基准和感知峰值，删除中间状态）",
        why="刻度多于2次成为感知日志，破坏叙事节奏；只写有意义的转折点",
    ),
    # --- Short confirmation tics ---
    StyleExample(
        category="确认短句口头禅",
        bad="两。可以。\n\n……稳的。\n\n……还好。",
        good="两。可以出门了。（全章最多1次独立确认短句，其余融入描写）",
        why="重复的短确认句产生AI节拍感，像系统报告而非小说叙事",
    ),
    # --- Speaking-style meta-commentary ---
    StyleExample(
        category="说话方式元注释",
        bad="他说话的方式是从外部观察往内部描述，慢一点，因为他要把看见的转换成语言。",
        good="（删除元注释，直接写他说的话和停顿）",
        why="解释角色说话方式是作者对读者说话，打破叙事沉浸；让对话本身表现节奏",
    ),
    # --- Ending structure copy from previous chapter ---
    StyleExample(
        category="结尾结构复制",
        bad="这不是让她安心的想法，也不是让她不安的想法。只是一个新的事实。（与上一章结尾句式完全相同）",
        good="（用本章独有的意象或场景细节收尾，不复制前章结构）",
        why="连续两章用相同结尾句式，读者会感到单调；每章结尾需要自己的最终意象",
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
