#!/usr/bin/env python
"""Editorial pass — runs Style + Theme agents on all chapters.

Usage:
    cd project_root
    source .venv/Scripts/activate  # Windows
    python scripts/editorial_pass.py

Output: editorial_report.md
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Allow running from project root without installing the package
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from meta_writing.llm import LLMClient
from meta_writing.style_linter import StyleLinter
from meta_writing.agents.style import StyleAgent
from meta_writing.agents.theme import ThemeAgent

CHAPTERS_DIR = project_root / "chapters"
SUMMARIES_DIR = project_root / "story_data" / "chapter_summaries"
OUTPUT_FILE = project_root / "editorial_report.md"

ARC_CONTEXT = """\
弧线节奏：孤独→相遇→互补感知→命名声音博物馆→找到呈现方式
章节1-2：各自孤独期，微感介绍
章节3-5：相遇/接触期，互补感知萌芽
章节6-8：协作期，命名和形式探索
章节9-10：整合期，声音博物馆具体化
"""


def load_chapter(num: int) -> str | None:
    """Load chapter text by number. Returns None if not found."""
    path = CHAPTERS_DIR / f"{num:03d}.md"
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def load_summary(num: int) -> str:
    """Load chapter summary YAML as plain text for context."""
    path = SUMMARIES_DIR / f"{num:03d}.yaml"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def format_linter_issues(issues: list) -> str:
    if not issues:
        return "无问题\n"
    lines = []
    severity_icons = {"error": "🔴", "warning": "🟡", "info": "🔵"}
    for issue in issues:
        icon = severity_icons.get(str(issue.severity.value if hasattr(issue.severity, 'value') else issue.severity), "🔵")
        lines.append(f"{icon} L{issue.line} `{issue.pattern_name}`: {issue.message}")
        lines.append(f"   原文: 「{issue.text[:60]}」")
        lines.append(f"   建议: {issue.suggestion}")
        lines.append("")
    return "\n".join(lines)


async def run_editorial_pass() -> None:
    api_key = os.environ.get("MINIMAX_API_KEY", "")
    if not api_key:
        print("WARNING: MINIMAX_API_KEY not set. LLM calls will fail.", file=sys.stderr)

    llm = LLMClient(api_key=api_key)
    linter = StyleLinter()
    style_agent = StyleAgent(llm=llm)
    theme_agent = ThemeAgent(llm=llm)

    # Discover all chapters
    chapter_files = sorted(CHAPTERS_DIR.glob("*.md"))
    chapter_numbers = []
    for f in chapter_files:
        try:
            num = int(f.stem)
            chapter_numbers.append(num)
        except ValueError:
            continue

    if not chapter_numbers:
        print("No chapters found in", CHAPTERS_DIR, file=sys.stderr)
        return

    print(f"Found {len(chapter_numbers)} chapters: {chapter_numbers}")

    report_sections: list[str] = []
    report_sections.append("# 编辑报告 — 声音博物馆\n")
    report_sections.append(f"章节范围：{chapter_numbers[0]}–{chapter_numbers[-1]}\n\n")
    report_sections.append("---\n")

    # Load all chapter texts
    chapters: dict[int, str] = {}
    for num in chapter_numbers:
        text = load_chapter(num)
        if text:
            chapters[num] = text

    # Per-chapter review
    for num in chapter_numbers:
        text = chapters.get(num)
        if not text:
            print(f"  Chapter {num:03d}: file missing, skipping")
            continue

        print(f"  Reviewing chapter {num:03d}...")

        # Get previous chapter ending for echo detection
        prev_num = num - 1
        prev_ending = ""
        if prev_num in chapters:
            prev_ending = chapters[prev_num][-300:]

        # Get previous chapter summary for theme progression check
        prev_summary = load_summary(num - 1) if num > 1 else ""

        # Run StyleLinter (sync, instant)
        linter_issues = linter.check(text)

        # Run StyleAgent (LLM)
        style_result = await style_agent.review(
            chapter_text=text,
            previous_chapter_ending=prev_ending,
            chapter_number=num,
        )

        # Run ThemeAgent per chapter (LLM)
        theme_result = await theme_agent.review_chapter(
            chapter_text=text,
            chapter_number=num,
            previous_chapter_summary=prev_summary,
            arc_context=ARC_CONTEXT,
        )

        # Build chapter section
        health_icon = {
            "healthy": "✅",
            "needs_work": "🟡",
            "critical": "🔴",
            "unknown": "❓",
        }.get(theme_result.thematic_health, "❓")

        passed_icon = "✅" if style_result.passed else "🔴"

        section = [
            f"## 第{num}章\n",
            f"**文风审查**: {passed_icon}  **主题健康度**: {health_icon} {theme_result.thematic_health}\n",
            "",
            "### StyleLinter（正则）\n",
            format_linter_issues(linter_issues),
            "",
            "### StyleAgent（LLM）\n",
        ]

        if style_result.issues:
            section.append(style_result.format_feedback())
        else:
            section.append("无问题\n")

        if style_result.rhythm_notes:
            section.append(f"\n**节奏观察**: {style_result.rhythm_notes}\n")

        section.append("")
        section.append("### ThemeAgent（主题）\n")

        if theme_result.issues:
            section.append(theme_result.format_feedback())
        else:
            section.append("无问题\n")

        if theme_result.arc_position_notes:
            section.append(f"\n**弧线位置**: {theme_result.arc_position_notes}\n")

        if theme_result.what_this_chapter_adds:
            section.append(f"\n**本章贡献**: {theme_result.what_this_chapter_adds}\n")

        section.append("\n---\n")

        report_sections.extend(section)

    # Cross-arc ThemeAgent review for all chapters
    print("  Running cross-arc ThemeAgent review...")
    all_chapters_list = [(num, chapters[num]) for num in chapter_numbers if num in chapters]

    if len(all_chapters_list) > 1:
        arc_result = await theme_agent.review_arc(
            chapters=all_chapters_list,
            arc_context=ARC_CONTEXT,
        )

        health_icon = {
            "healthy": "✅",
            "needs_work": "🟡",
            "critical": "🔴",
            "unknown": "❓",
        }.get(arc_result.thematic_health, "❓")

        arc_section = [
            f"## 跨章主题审查（第{all_chapters_list[0][0]}–{all_chapters_list[-1][0]}章）\n",
            f"**整体主题健康度**: {health_icon} {arc_result.thematic_health}\n",
            "",
        ]

        if arc_result.issues:
            arc_section.append(arc_result.format_feedback())
        else:
            arc_section.append("无跨章问题\n")

        if arc_result.arc_position_notes:
            arc_section.append(f"\n**整体弧线评估**: {arc_result.arc_position_notes}\n")

        if arc_result.what_this_chapter_adds:
            arc_section.append(f"\n**整体贡献评估**: {arc_result.what_this_chapter_adds}\n")

        arc_section.append("\n---\n")
        report_sections.extend(arc_section)

    # Token usage summary
    usage = llm.usage
    report_sections.append("## Token 使用统计\n")
    report_sections.append(f"- 输入 tokens: {usage.input_tokens:,}\n")
    report_sections.append(f"- 输出 tokens: {usage.output_tokens:,}\n")
    report_sections.append(f"- 估算费用: ${usage.estimated_cost_usd('MiniMax-M2.7'):.4f}\n")

    # Write report
    report_text = "\n".join(report_sections)
    OUTPUT_FILE.write_text(report_text, encoding="utf-8")
    print(f"\nReport written to: {OUTPUT_FILE}")
    print(f"Token usage: {usage.input_tokens:,} in / {usage.output_tokens:,} out")


if __name__ == "__main__":
    asyncio.run(run_editorial_pass())
