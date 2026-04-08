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

from .llm import MODEL_SONNET, SUPPORTED_WRITER_PROVIDERS
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
from .workspace import (
    SUPPORTED_WORKFLOW_MODES,
    WORKFLOW_MODE_MANUAL,
    WorkspaceManager,
)

console = Console()


@click.group()
@click.option("--project-dir", default=None, help="Explicit novel project directory path")
@click.option("--project", default=None, help="Novel project name inside the workspace")
@click.option("--workspace-dir", default=".", help="Workspace root containing the novels library")
@click.pass_context
def cli(
    ctx: click.Context,
    project_dir: str | None,
    project: str | None,
    workspace_dir: str,
) -> None:
    """meta_writing — Multi-agent Chinese web novel generation system."""
    ctx.ensure_object(dict)
    manager = WorkspaceManager(Path(workspace_dir).resolve())
    ctx.obj["workspace_manager"] = manager
    ctx.obj["project"] = project
    ctx.obj["project_dir"] = None
    if ctx.invoked_subcommand != "project":
        try:
            ctx.obj["project_dir"] = manager.resolve_project_dir(
                project=project,
                project_dir=project_dir,
                cwd=Path.cwd(),
            )
        except FileNotFoundError as exc:
            raise click.ClickException(str(exc)) from exc


def _resolve_loader(ctx: click.Context) -> tuple[Path, StoryBibleLoader]:
    project_dir: Path = ctx.obj["project_dir"]
    return project_dir, StoryBibleLoader(project_dir / "story_data")


def _enforce_project_workflow_mode(
    ctx: click.Context,
    expected_mode: str,
    command_label: str,
) -> None:
    project_dir: Path = ctx.obj["project_dir"]
    manager: WorkspaceManager = ctx.obj["workspace_manager"]
    actual_mode = manager.workflow_mode_for_project_dir(project_dir)
    if actual_mode and actual_mode != expected_mode:
        raise click.ClickException(
            f"{command_label} requires a project in {expected_mode} workflow mode. "
            f"Current project mode: {actual_mode}."
        )


@cli.group()
def project() -> None:
    """Manage multiple novel projects."""


@project.command("create")
@click.argument("name")
@click.option(
    "--from-project-dir",
    default=None,
    help="Optional existing novel project directory to copy from",
)
@click.option(
    "--move-source/--copy-source",
    default=False,
    help="Move the imported story files out of the source directory after copying",
)
@click.option(
    "--mode",
    "workflow_mode",
    type=click.Choice(list(SUPPORTED_WORKFLOW_MODES)),
    default=WORKFLOW_MODE_MANUAL,
    show_default=True,
    help="Workflow mode for the new project",
)
@click.option("--activate/--no-activate", default=True, help="Set as the active project")
@click.pass_context
def create_project(
    ctx: click.Context,
    name: str,
    from_project_dir: str | None,
    move_source: bool,
    workflow_mode: str,
    activate: bool,
) -> None:
    """Create a new novel project scaffold."""
    manager: WorkspaceManager = ctx.obj["workspace_manager"]
    project_dir = manager.create_project(
        name,
        source_dir=from_project_dir,
        move_source=move_source,
        workflow_mode=workflow_mode,
    )
    if activate:
        manager.set_current_project(name)
    console.print(
        Panel(
            f"项目已创建: {project_dir}\n当前激活: {'是' if activate else '否'}",
            style="green",
        )
    )


@project.command("list")
@click.pass_context
def list_projects(ctx: click.Context) -> None:
    """List known novel projects."""
    manager: WorkspaceManager = ctx.obj["workspace_manager"]
    projects = manager.list_projects()
    if not projects:
        console.print("未发现项目。")
        return

    for item in projects:
        suffix = " (active)" if item.is_active else ""
        console.print(f"{item.name} [{item.workflow_mode}]{suffix}", markup=False)


@project.command("use")
@click.argument("name")
@click.pass_context
def use_project(ctx: click.Context, name: str) -> None:
    """Set the active novel project."""
    manager: WorkspaceManager = ctx.obj["workspace_manager"]
    manager.set_current_project(name)
    console.print(f"当前项目已切换到: {name}")


@project.command("current")
@click.pass_context
def current_project(ctx: click.Context) -> None:
    """Show the active novel project."""
    manager: WorkspaceManager = ctx.obj["workspace_manager"]
    current = manager.get_current_project()
    if current:
        console.print(current)
    else:
        console.print("当前没有激活项目。")


@project.command("mode")
@click.argument("workflow_mode", type=click.Choice(list(SUPPORTED_WORKFLOW_MODES)))
@click.option("--name", default=None, help="Project name to update (defaults to current project)")
@click.pass_context
def project_mode(ctx: click.Context, workflow_mode: str, name: str | None) -> None:
    """Set the workflow mode for a project."""
    manager: WorkspaceManager = ctx.obj["workspace_manager"]
    target_name = name or manager.get_current_project()
    if not target_name:
        raise click.ClickException("当前没有激活项目，请先使用 project use 或传入 --name。")
    manager.set_project_workflow_mode(target_name, workflow_mode)
    console.print(f"{target_name} workflow mode -> {workflow_mode}")


@project.command("migrate-root")
@click.argument("name")
@click.option(
    "--move-source/--copy-source",
    default=True,
    help="Move the legacy root story files after copying",
)
@click.option(
    "--mode",
    "workflow_mode",
    type=click.Choice(list(SUPPORTED_WORKFLOW_MODES)),
    default=WORKFLOW_MODE_MANUAL,
    show_default=True,
    help="Workflow mode for the migrated project",
)
@click.option("--activate/--no-activate", default=False, help="Set as the active project")
@click.pass_context
def migrate_root_project(
    ctx: click.Context,
    name: str,
    move_source: bool,
    workflow_mode: str,
    activate: bool,
) -> None:
    """Move legacy root-level novel files into a named project."""
    manager: WorkspaceManager = ctx.obj["workspace_manager"]
    project_dir = manager.migrate_legacy_root_project(
        name,
        move_source=move_source,
        workflow_mode=workflow_mode,
    )
    if activate:
        manager.set_current_project(name)
    console.print(f"已迁移 root legacy project -> {project_dir}")


@cli.command()
@click.pass_context
def init(ctx: click.Context) -> None:
    """Initialize a new story with StoryCore configuration."""
    project_dir, loader = _resolve_loader(ctx)

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

    writer_provider = Prompt.ask(
        "Writer provider",
        choices=list(SUPPORTED_WRITER_PROVIDERS),
        default="minimax",
    )
    chapter_target_chars = IntPrompt.ask("Target chapter chars", default=2000)
    default_min_chars = max(800, int(chapter_target_chars * 0.8))
    chapter_min_chars = IntPrompt.ask("Minimum chars before expansion", default=default_min_chars)

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
        chapter_target_chars=chapter_target_chars,
        chapter_min_chars=chapter_min_chars,
        writer_provider=writer_provider,
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
    _enforce_project_workflow_mode(ctx, expected_mode="manual", command_label="meta-writing generate")
    project_dir: Path = ctx.obj["project_dir"]

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
    _, loader = _resolve_loader(ctx)

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
    _, loader = _resolve_loader(ctx)
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
