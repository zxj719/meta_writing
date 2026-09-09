"""Style Linter — fast regex-based detection of known prose anti-patterns.

Zero-cost post-generation check. Catches "直白解读" patterns that break
the show-don't-tell principle established for 微感 descriptions.

Usage:
    from meta_writing.style_linter import StyleLinter
    linter = StyleLinter()
    issues = linter.check(chapter_text)
    if issues:
        for issue in issues:
            print(f"[{issue.severity}] L{issue.line}: {issue.message}")
            print(f"  原文: {issue.text}")
            print(f"  建议: {issue.suggestion}")
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Severity(str, Enum):
    ERROR = "error"      # Must fix — breaks established style rules
    WARNING = "warning"  # Should fix — likely a problem
    INFO = "info"        # Worth reviewing — may be intentional


@dataclass
class StyleIssue:
    """A single style violation found by the linter."""
    line: int
    text: str
    pattern_name: str
    message: str
    suggestion: str
    severity: Severity


# Each rule: (name, compiled regex, severity, message, suggestion)
# Patterns operate on individual lines.
_LINE_RULES: list[tuple[str, re.Pattern[str], Severity, str, str]] = [
    (
        "object_remembers",
        re.compile(
            r"(?:沙发|椅子|门框|门槛|墙壁|铁皮|木头|柜子|砚台|烟灰缸|台灯|桌子|窗台|地板|栏杆|扶手|书架|收银机|花盆|水龙头|门环|棺材|遗像|花圈)"
            r"[^。，、]{0,6}记得"
        ),
        Severity.ERROR,
        '物体\u201c记得\u201d\u2014\u2014直白解读，破坏留白',
        '改为纯物理描写（声音/振动/磨损/温度差异），让读者自己连线',
    ),
    (
        "generic_remembers",
        re.compile(r"它[们]?记得"),
        Severity.ERROR,
        '\u201c它记得\u201d\u2014\u2014拟人化解读物体记忆',
        '去掉\u201c记得\u201d，直接写物理现象',
    ),
    (
        "object_speaking",
        re.compile(
            r"(?:沙发|门框|墙壁|铁皮|木头|地板|书架|收银机|花盆)"
            r"[^。]{0,10}(?:在说话|在说|在叫|在等[^着人])"
        ),
        Severity.ERROR,
        '物体\u201c在说话/在等\u201d\u2014\u2014拟人化点破',
        '删除拟人化语句，用环境音或沉默替代',
    ),
    (
        "mind_reading",
        re.compile(r"(?:他|她)[^。]{0,4}在想[：:：]"),
        Severity.ERROR,
        '读心术\u2014\u2014微感不能读人的想法',
        '改为从物体痕迹推断，或删除',
    ),
    (
        "emotional_statement",
        re.compile(r"(?:她[懂明理解]了?(?:那种|这种|一种)?(?:孤独|悲伤|寂寞|温暖|安心)|原来不是[我她他]一个人)"),
        Severity.WARNING,
        '直白情感陈述\u2014\u2014应由读者自行体会',
        '用动作、沉默、身体反应替代',
    ),
    (
        "she_doesnt_know",
        re.compile(r"她不知道"),
        Severity.INFO,
        '\u201c她不知道\u201d\u2014\u2014全文不宜超过3次',
        '如已超过3次，改为具体的犹豫动作或沉默',
    ),
    (
        "structural_header_residue",
        re.compile(r"\*\*节点[一二三四五六七八九十\d]"),
        Severity.ERROR,
        "规划标记残留在正文中——Writer Agent留下的章节结构标记",
        "删除所有**节点X**格式的标记，这是规划用标记不是正文",
    ),
    (
        "speaking_style_meta",
        re.compile(r"(他|她)说话的方式是"),
        Severity.INFO,
        "说话方式元注释——直接说结果，不解释说话方式",
        "删除对说话方式的描述，直接写对话或反应",
    ),
    (
        "this_too_template",
        re.compile(r"这[^。！？\n]{0,16}太[^。！？\n]{0,24}[。！？]?"),
        Severity.ERROR,
        '“这……太……”夸张模板——像口头反应占位，不像具体现场',
        '改为人物动作、对白反应或可感知的场景细节，不要用“这也太……”直接替读者总结',
    ),
    (
        "negation_definition_template",
        re.compile(r"(?:这?不是[^。！？\n]{0,24}(?:，|,)?(?:而是|是))"),
        Severity.ERROR,
        '“不是……是……/不是，是……”硬转折模板——反向下定义会削弱现场感',
        '改成直接叙述、动作反应或具体细节，不要靠“不是，是”制造力度',
    ),
    (
        "flat_expression_template",
        re.compile(r"(?:脸色[^。！？\n]{0,8}沉(?:了)?下(?:去|来)|眼神[^。！？\n]{0,8}冷(?:了)?下(?:去|来))"),
        Severity.ERROR,
        '“脸色沉下去/眼神冷下去”扁平神态模板——神态缺少可见层次',
        '延展为微表情、体态、外貌锚点或环境反应，例如唇线、眉骨、指节、站姿和光影变化',
    ),
    (
        "na_intensifier_but_scaffold",
        re.compile(r"那[^。！？\n]{0,18}很[^。！？\n]{1,18}(?:，|,)(?:但|但是)[^。！？\n]{1,30}"),
        Severity.ERROR,
        '“那……很……，但……”机械转折句——像在用固定脚手架制造细腻感',
        '改成更具体的动作、神态或环境承接，避免先抽象判断再用“但”转向',
    ),
    (
        "na_negation_but_scaffold",
        re.compile(r"那[^。！？\n]{0,18}不[^。！？\n]{1,18}(?:，|,)(?:但|但是)[^。！？\n]{1,30}"),
        Severity.ERROR,
        '“那……不……，但……”机械转折句——否定后硬转会留下AI腔',
        '改为直接呈现现场变化，或拆成自然对白/动作，不要靠“那不……但……”下判断',
    ),
]

# Multi-line rules: check patterns that span context or count across the full text.
_GLOBAL_RULES: list[tuple[str, re.Pattern[str], int, Severity, str, str]] = [
    (
        "contrast_scaffold_overuse",
        re.compile(r"[^\n。！？]{4,30}(?:，|,)(?:但|但是|却|可)[^\n。！？]{4,30}[。！？]"),
        6,
        Severity.ERROR,
        '“X，但Y”对照脚手架出现过多——句法重复过强，机械感明显',
        '保留最有力的少量对照句，其余改成动作、停顿、环境变化或直接叙述，避免整章都靠“但/却”拐弯',
    ),
    (
        "short_sentence_tic_overuse",
        re.compile(r"(?:^|\n)很[\u4e00-\u9fff]{1,3}[。！？](?=\n|$)"),
        3,
        Severity.WARNING,
        '独立“很X。”短句出现过多——像固定结尾口癖，容易暴露AI节拍',
        '删掉一半以上的“很X。”独句，改成并入前句的具体描写，或换成更有信息量的动作/环境句',
    ),
    (
        "negation_parallelism_overuse",
        re.compile(r"(?:这?不是[^。！？\n]{0,24}(?:，|,)?(?:而是|是))"),
        3,
        Severity.WARNING,
        '“不是……是……/这不是……是……”否定式排比出现过多——像模板化强调，不像现场反应',
        '保留极少数最有力的句子，其余改成直接叙述、动作反应或场景细节，不要靠反向下定义制造力度',
    ),
    (
        "na_zhong_na_zhong",
        re.compile(r"是那种.{0,30}的那种"),
        5,
        Severity.WARNING,
        '"是那种X的那种Y"嵌套句式出现超过5次——高频散文口头禅，造成节奏麻木',
        '删除"是那种"/"的那种"框架，改为直接描写：把"那种味道"改写成具体的气味动词',
    ),
    (
        "na_zhong_na_zhong_heavy",
        re.compile(r"是那种.{0,30}的那种"),
        8,
        Severity.ERROR,
        '"是那种X的那种Y"出现超过8次——严重节奏单调，必须修改',
        '全章保留≤4处，其余句子改写：去掉"是那种"框架，直接呈现感官细节',
    ),
    (
        "she_doesnt_know_overuse",
        re.compile(r"她不知道"),
        3,  # max allowed occurrences
        Severity.WARNING,
        '\u201c她不知道\u201d出现超过3次',
        '保留最有力的2-3处，其余改为动作或删除',
    ),
    (
        "enn_overuse",
        re.compile(r"\u201c嗯。\u201d"),
        3,
        Severity.WARNING,
        '"嗯。"作为对话回应出现超过3次',
        "变化对话反应：用动作/沉默/其他短回应替代部分'嗯。'",
    ),
    (
        "scale_reporting_overuse",
        re.compile(r"刻度(从|是|升|降|回|在|已|到)[^。]{0,15}[。，]"),
        3,
        Severity.WARNING,
        "刻度汇报出现超过3次——变成感知日志而非叙事",
        "全章最多2次刻度提及（开章确认+关键峰值），删除中间状态汇报",
    ),
    (
        "confirmation_tic",
        re.compile(r"(?:^|\n)[^。\n]*(?:可以[。。]|稳的[。。])"),
        2,
        Severity.INFO,
        '"可以。"/"稳的。"作为独立确认句出现超过2次',
        "这类短确认句全章最多1次，其余改为具体的感知描述",
    ),
]


def _chinese_char_count(text: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", text))


def _find_tiny_paragraph_triplets(lines: list[str]) -> list[StyleIssue]:
    issues: list[StyleIssue] = []
    streak: list[tuple[int, str]] = []

    for line_num, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped:
            continue

        if 1 <= _chinese_char_count(stripped) <= 2:
            streak.append((line_num, stripped))
            if len(streak) == 3:
                preview = " / ".join(item[1] for item in streak)
                issues.append(StyleIssue(
                    line=streak[0][0],
                    text=preview[:80],
                    pattern_name="tiny_paragraph_triplet",
                    message='连续三次单字/双字成段——容易形成空洞的“有力感”',
                    suggestion='保留最有信息量的一处，其余并入前后动作、神态、外貌或环境描写',
                    severity=Severity.ERROR,
                ))
        else:
            streak = []

    return issues


def _find_opening_yi_jiu_scaffold(lines: list[str]) -> list[StyleIssue]:
    """Flag chapter openings that start with the overused “一……就……” beat."""
    for line_num, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if re.search(r"一[^。！？\n]{1,20}就[^。！？\n]{1,30}", stripped):
            return [
                StyleIssue(
                    line=line_num,
                    text=stripped[:80],
                    pattern_name="opening_yi_jiu_scaffold",
                    message='章节开头使用“一……就……”起手式——开篇节拍容易显得模板化',
                    suggestion='换成具体画面、人物动作、环境声或一句更有钩子的对白开场，不要每章开头都用条件式起笔',
                    severity=Severity.ERROR,
                )
            ]

        return []

    return []


class StyleLinter:
    """Fast regex-based style checker for generated prose."""

    def check(self, text: str) -> list[StyleIssue]:
        """Check text for style violations.

        Args:
            text: Chapter text to check.

        Returns:
            List of StyleIssue objects, sorted by line number.
        """
        issues: list[StyleIssue] = []
        lines = text.split("\n")

        # Line-level rules
        for line_num, line in enumerate(lines, 1):
            if not line.strip():
                continue
            for name, pattern, severity, message, suggestion in _LINE_RULES:
                if pattern.search(line):
                    issues.append(StyleIssue(
                        line=line_num,
                        text=line.strip()[:80],
                        pattern_name=name,
                        message=message,
                        suggestion=suggestion,
                        severity=severity,
                    ))

        issues.extend(_find_tiny_paragraph_triplets(lines))
        issues.extend(_find_opening_yi_jiu_scaffold(lines))

        # Global rules (count-based)
        for name, pattern, max_count, severity, message, suggestion in _GLOBAL_RULES:
            matches = pattern.findall(text)
            if len(matches) > max_count:
                issues.append(StyleIssue(
                    line=0,
                    text=f"共出现{len(matches)}次（上限{max_count}次）",
                    pattern_name=name,
                    message=message,
                    suggestion=suggestion,
                    severity=severity,
                ))

        issues.sort(key=lambda i: (i.line, i.severity.value))
        return issues

    def format_report(self, issues: list[StyleIssue]) -> str:
        """Format issues as a human-readable report."""
        if not issues:
            return "✅ 文风检查通过，未发现反模式。"

        lines = [f"## 文风检查：发现 {len(issues)} 个问题\n"]
        for issue in issues:
            icon = {"error": "🔴", "warning": "🟡", "info": "🔵"}[issue.severity.value]
            loc = f"L{issue.line}" if issue.line else "全文"
            lines.append(f"{icon} **[{loc}] {issue.message}** ({issue.pattern_name})")
            lines.append(f"   原文: {issue.text}")
            lines.append(f"   建议: {issue.suggestion}")
            lines.append("")
        return "\n".join(lines)

    def format_feedback_for_writer(self, issues: list[StyleIssue]) -> str:
        """Format issues as revision instructions for the Writer Agent."""
        if not issues:
            return ""

        error_issues = [i for i in issues if i.severity == Severity.ERROR]
        if not error_issues:
            return ""

        lines = ["## 文风修改要求（必须修改）\n"]
        for issue in error_issues:
            loc = f"第{issue.line}行" if issue.line else "全文"
            lines.append(f"- {loc}：{issue.message}。{issue.suggestion}")
            lines.append(f"  原文片段：「{issue.text}」")
            lines.append("")
        return "\n".join(lines)
