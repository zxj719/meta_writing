"""Interactive chapter generation runner — bypasses Rich CLI for non-TTY use."""
import asyncio
import os
import sys
from pathlib import Path

# Load .env
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from meta_writing.orchestrator import Orchestrator
from meta_writing.llm import MODEL_OPUS, MODEL_SONNET  # noqa: F401


PROJECT_DIR = Path(__file__).parent


async def run_planner(guidance: str = "") -> None:
    """Run planner only, print branches for selection."""
    orch = Orchestrator(PROJECT_DIR)
    bible = orch.load_bible()
    chapter_number = bible.core.current_chapter + 1

    recent_text = orch.get_recent_chapters_text(chapter_number)
    bible_context = orch.compressor.compress(bible, chapter_number, pov_character=None)

    print(f"\n{'='*60}")
    print(f"  正在为第 {chapter_number} 章生成剧情分支...")
    print(f"{'='*60}\n")

    planner_result = await orch.planner.plan(
        bible_context=bible_context,
        recent_chapters_text=recent_text,
        chapter_number=chapter_number,
        additional_guidance=guidance,
    )

    print(f"分析: {planner_result.context_notes}\n")

    for i, branch in enumerate(planner_result.branches):
        print(f"--- 分支 {i+1}: {branch.title} ---")
        print(f"  大纲: {branch.outline}")
        print(f"  角色: {', '.join(branch.characters_involved)}")
        print(f"  影响: {branch.consequences}")
        print(f"  爽点: {branch.satisfaction_type} | 钩子: {branch.hook_type}")
        print(f"  钩子描述: {branch.hook_description}")
        print(f"  风险: {branch.risk_level}")
        print()

    tokens = orch.llm.usage
    print(f"Token用量: {tokens.total_tokens:,} (输入: {tokens.input_tokens:,}, 输出: {tokens.output_tokens:,})")

    return planner_result, orch, bible, chapter_number, bible_context, recent_text


async def run_writer(orch, bible, bible_context, recent_text, chapter_number, branch) -> str:
    """Write chapter from selected branch."""
    # Recompress with active characters
    bible_context = orch.compressor.compress(
        bible, chapter_number,
        active_character_names=branch.characters_involved,
    )

    print(f"\n{'='*60}")
    print(f"  正在撰写第 {chapter_number} 章: {branch.title}")
    print(f"{'='*60}\n")

    writer_result = await orch.writer.write(
        bible_context=bible_context,
        recent_chapters_text=recent_text,
        outline=branch.outline,
        chapter_number=chapter_number,
    )

    chapter_text = writer_result.chapter_text
    print(f"章节字数: {len(chapter_text)}")

    # Save chapter
    chapters_dir = orch.chapters_dir
    chapters_dir.mkdir(parents=True, exist_ok=True)
    chapter_path = chapters_dir / f"{chapter_number:03d}.md"
    chapter_path.write_text(chapter_text, encoding="utf-8")
    print(f"已保存到: {chapter_path}")

    # Update current_chapter
    bible.core.current_chapter = chapter_number
    orch.loader.save(bible)

    tokens = orch.llm.usage
    print(f"\nToken总用量: {tokens.total_tokens:,} (输入: {tokens.input_tokens:,}, 输出: {tokens.output_tokens:,})")

    return chapter_text


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "plan"
    guidance = sys.argv[2] if len(sys.argv) > 2 else ""

    if mode == "plan":
        asyncio.run(run_planner(guidance))
    elif mode == "full":
        # Full pipeline: plan + auto-select first branch + write
        branch_idx = int(sys.argv[2]) if len(sys.argv) > 2 else 0
        guidance = sys.argv[3] if len(sys.argv) > 3 else ""

        async def full():
            result = await run_planner(guidance)
            planner_result, orch, bible, chapter_number, bible_context, recent_text = result
            branch = planner_result.branches[branch_idx]
            print(f"\n>>> 选择分支 {branch_idx+1}: {branch.title}\n")
            return await run_writer(orch, bible, bible_context, recent_text, chapter_number, branch)

        asyncio.run(full())
