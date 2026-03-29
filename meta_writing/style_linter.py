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
]

# Multi-line rules: check patterns that span context or count across the full text.
_GLOBAL_RULES: list[tuple[str, re.Pattern[str], int, Severity, str, str]] = [
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
