"""CLI entry point — Rich-based interactive interface.

Commands:
- init: Initialize a new story with StoryCore configuration
- generate: Generate the next chapter (full pipeline)
- status: Show current Story Bible status
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt
from rich.table import Table
from rich.markdown import Markdown

from .orchestrator import Orchestrator
from .story_bible.loader import StoryBibleLoader
from .story_bible.schema import (
    CoreTriangle,
    Character,
    Genre,
    GrowthStage,
    MotivationType,
    StoryCore,
    WorldLayer,
)

console = Console()


@click.group()
@click.option("--project-dir", default=".", help="Project directory path")
@click.pass_context
def cli(ctx: click.Context, project_dir: str) -> None:
    """meta_writing — Multi-agent Chinese web novel generation system."""
    ctx.ensure_object(dict)
    ctx.obj["project_dir"] = Path(project_dir).resolve()


@cli.command()
@click.pass_context
def init(ctx: click.Context) -> None:
    """Initialize a new story with StoryCore configuration."""
    project_dir = ctx.obj["project_dir"]
    loader = StoryBibleLoader(project_dir / "story_data")

    console.print(Panel("📖 初始化新故事", style="bold blue"))

    hook = Prompt.ask("一句话核心 (Hook)")

    # Genre selection
    console.print("\n可选体裁:")
    for i, genre in enumerate(Genre, 1):
        console.print(f"  {i}. {genre.value}")
    genre_idx = IntPrompt.ask("选择体裁编号", default=1) - 1
    genre = list(Genre)[genre_idx]

    satisfaction = Prompt.ask("核心爽点类型", default="")
    total_chapters = IntPrompt.ask("计划总章节数", default=100)

    # Foreshadowing config
    genre_defaults = {"玄幻仙侠": 30, "言情": 15, "悬疑推理": 20}
    default_age = genre_defaults.get(genre.value, 20)
    max_age = IntPrompt.ask(f"伏笔最大寿命（章数，默认{default_age}）", default=default_age)

    # World layers
    console.print("\n[bold]世界架构（五层）[/bold] — 可选，按回车跳过")
    layers = []
    layer_names = ["表层世界 (日常)", "规则层 (运行逻辑)", "禁忌层 (危险边界)", "真相层 (隐藏秘密)", "本质层 (核心命题)"]
    for name in layer_names:
        desc = Prompt.ask(f"  {name}", default="")
        if desc:
            layers.append(WorldLayer(name=name, description=desc))

    core = StoryCore(
        hook=hook,
        genre=genre,
        target_satisfaction_type=satisfaction,
        world_layers=layers,
        foreshadowing_max_age_chapters=max_age,
        total_planned_chapters=total_chapters,
    )
    loader.save_core(core)
    console.print(Panel("✅ 故事核心已保存", style="green"))

    # Add first character?
    if Prompt.ask("\n是否添加第一个角色？", choices=["y", "n"], default="y") == "y":
        _add_character_interactive(loader)


@cli.command()
@click.option("--guidance", default="", help="Additional guidance for the planner")
@click.pass_context
def generate(ctx: click.Context, guidance: str) -> None:
    """Generate the next chapter using the full pipeline."""
    project_dir = ctx.obj["project_dir"]

    async def _run() -> None:
        orch = Orchestrator(project_dir)

        async def select_branch(branches):
            console.print(Panel("🔀 剧情分支选择", style="bold yellow"))
            for i, branch in enumerate(branches):
                table = Table(title=f"分支 {i + 1}: {branch.title}", show_header=False)
                table.add_row("大纲", branch.outline)
                table.add_row("涉及角色", ", ".join(branch.characters_involved))
                table.add_row("影响", branch.consequences)
                table.add_row("爽点级别", branch.satisfaction_type)
                table.add_row("钩子类型", branch.hook_type)
                table.add_row("风险等级", branch.risk_level)
                console.print(table)
                console.print()
            return IntPrompt.ask("选择分支", choices=[str(i + 1) for i in range(len(branches))]) - 1

        async def review_chapter(text, continuity_result):
            console.print(Panel("📝 章节审查", style="bold cyan"))
            console.print(Markdown(text[:2000] + "\n\n...(已截断)..." if len(text) > 2000 else text))

            if continuity_result and continuity_result.issues:
                console.print(Panel("⚠️ 连续性问题", style="yellow"))
                console.print(continuity_result.format_feedback())

            action = Prompt.ask("操作", choices=["approve", "reject", "edit"], default="approve")
            notes = ""
            if action in ("reject", "edit"):
                notes = Prompt.ask("备注/修改内容")
            return action, notes

        async def confirm_states(changes):
            console.print(Panel("📋 状态变更确认", style="bold magenta"))
            table = Table(show_header=True)
            table.add_column("角色")
            table.add_column("字段")
            table.add_column("旧值")
            table.add_column("新值")
            for c in changes:
                table.add_row(c["character"], c["field"], c["old_value"], c["new_value"])
            console.print(table)
            return Prompt.ask("确认写入Story Bible？", choices=["y", "n"], default="y") == "y"

        try:
            chapter_text = await orch.generate_chapter(
                branch_selector=select_branch,
                human_reviewer=review_chapter,
                state_confirmer=confirm_states,
                guidance=guidance,
            )
            console.print(Panel(
                f"✅ 第{orch.state.chapter_number}章生成完成 ({len(chapter_text)}字)",
                style="bold green",
            ))
            console.print(f"Token用量: {orch.llm.usage.total_tokens:,} tokens")
            console.print(f"预估成本: ${orch.llm.usage.estimated_cost_usd(MODEL_SONNET):.2f}")
        except Exception as e:
            console.print(Panel(f"❌ 错误: {e}", style="bold red"))
            raise

    asyncio.run(_run())


@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show current Story Bible status."""
    project_dir = ctx.obj["project_dir"]
    loader = StoryBibleLoader(project_dir / "story_data")

    try:
        bible = loader.load()
    except Exception as e:
        console.print(f"[red]无法加载Story Bible: {e}[/red]")
        console.print("运行 `meta-writing init` 初始化故事。")
        return

    console.print(Panel("📖 Story Bible 状态", style="bold blue"))

    # Core info
    table = Table(title="故事核心", show_header=False)
    table.add_row("Hook", bible.core.hook)
    table.add_row("体裁", bible.core.genre.value)
    table.add_row("当前章节", str(bible.core.current_chapter))
    table.add_row("计划章节", str(bible.core.total_planned_chapters or "未设定"))
    console.print(table)

    # Characters
    if bible.characters:
        char_table = Table(title=f"角色 ({len(bible.characters)})")
        char_table.add_column("名称")
        char_table.add_column("动机类型")
        char_table.add_column("成长阶段")
        char_table.add_column("位置")
        for char in bible.characters.values():
            char_table.add_row(char.name, char.motivation_type.value, char.growth_stage.value, char.location)
        console.print(char_table)

    # Foreshadowing
    active = bible.active_foreshadowing()
    if active:
        fs_table = Table(title=f"活跃伏笔 ({len(active)})")
        fs_table.add_column("ID")
        fs_table.add_column("描述")
        fs_table.add_column("植入章节")
        fs_table.add_column("年龄")
        for f in active:
            age = f.age_at(bible.core.current_chapter)
            fs_table.add_row(f.id, f.setup_description[:40], str(f.setup_chapter), f"{age}章")
        console.print(fs_table)

    console.print(f"\n时间线事件: {len(bible.timeline)}")
    console.print(f"世界规则: {len(bible.world_rules)}")
    console.print(f"章节摘要: {len(bible.chapter_summaries)}")


@cli.command()
@click.pass_context
def add_character(ctx: click.Context) -> None:
    """Interactively add a character to the Story Bible."""
    project_dir = ctx.obj["project_dir"]
    loader = StoryBibleLoader(project_dir / "story_data")
    _add_character_interactive(loader)


def _add_character_interactive(loader: StoryBibleLoader) -> None:
    """Interactive character creation."""
    console.print(Panel("👤 添加角色", style="bold cyan"))

    name = Prompt.ask("角色名")
    physical = Prompt.ask("外貌描述", default="")
    traits = Prompt.ask("性格特征（逗号分隔）", default="")
    trait_list = [t.strip() for t in traits.split(",") if t.strip()] if traits else []

    # Core triangle
    console.print("\n[bold]核心三角[/bold]")
    desire = Prompt.ask("  欲望 (想要什么)")
    ability = Prompt.ask("  能力 (能做什么)")
    obstacle = Prompt.ask("  阻碍 (什么挡路)")

    # Motivation type
    console.print("\n动机类型:")
    for i, mt in enumerate(MotivationType, 1):
        console.print(f"  {i}. {mt.value}")
    mt_idx = IntPrompt.ask("选择", default=1) - 1
    motivation = list(MotivationType)[mt_idx]

    is_pov = Prompt.ask("是否为POV角色？", choices=["y", "n"], default="n") == "y"

    char = Character(
        name=name,
        physical_description=physical,
        personality_traits=trait_list,
        core_triangle=CoreTriangle(desire=desire, ability=ability, obstacle=obstacle),
        motivation_type=motivation,
        is_pov=is_pov,
    )
    loader.save_character(char)
    console.print(f"[green]✅ 角色 {name} 已保存[/green]")


def main() -> None:
    """Entry point."""
    cli(obj={})


if __name__ == "__main__":
    main()
