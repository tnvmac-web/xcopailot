"""CLI main entry point — xcopilot command."""

from __future__ import annotations

import asyncio
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from xcopilot.cli.commands import (
    checkpoints,
    config,
    doctor,
    graph,
    init,
    mcp,
    memory,
    model,
    run,
    setup,
    skill,
    skills,
    update,
)
from xcopilot.cli.serve import serve

console = Console()


@click.group()
@click.version_option(version="0.1.1", prog_name="xcopilot")
@click.option("--project", "-p", type=click.Path(exists=True), help="Project root directory")
@click.option(
    "--mode",
    type=click.Choice(["standard", "auto-ask", "plan", "bypass", "dont-ask"]),
    default="standard",
    help="Permission mode",
)
@click.pass_context
def cli(ctx, project, mode):
    """X-Copilot — Self-growing AI agent for Windows."""
    ctx.ensure_object(dict)
    ctx.obj["project_root"] = Path(project) if project else Path.cwd()
    ctx.obj["permission_mode"] = mode


# ── Delegation command group ────────────────────────────

@click.group()
def delegate():
    """Task delegation to X-Copilot subagents."""

@delegate.command("run")
@click.argument("goal")
@click.option("--context", "-c", default=None, help="Context for the subagent")
@click.option("--role", "-r", default="leaf", type=click.Choice(["leaf", "orchestrator"]))
@click.option("--model", "-m", default=None, help="Model override")
@click.option("--toolsets", "-t", multiple=True, help="Allowed toolsets (repeatable)")
@click.option("--mode", "-p", default="standard", type=click.Choice(["standard", "auto-ask", "plan", "bypass", "dont-ask"]))
@click.option("--background", "-b", is_flag=True, help="Run in background (async delegation)")
@click.pass_context
def delegate_run(ctx, goal, context, role, model, toolsets, mode, background):
    """Delegate a task to an X-Copilot subagent."""
    from xcopilot.core.delegation import TaskDelegator
    from xcopilot.permission.pipeline import PermissionMode

    project_root = ctx.obj.get("project_root", Path.cwd())
    perm_mode = PermissionMode(mode)
    delegator = TaskDelegator(project_root=project_root, permission_mode=perm_mode)

    console.print(f"[cyan]Delegating:[/cyan] {goal[:60]}...")
    task = delegator.delegate(
        goal, context=context, role=role, model=model,
        allowed_toolsets=tuple(toolsets),
    )
    console.print(f"  Task ID: [bold]{task.task_id}[/bold]")
    console.print(f"  Role: {role}  Mode: {mode}")

    if perm_mode == PermissionMode.PLAN:
        console.print("[red]PLAN mode denies delegation.[/red]")
        delegator.cancel(task.task_id)
        return

    async def _run() -> None:
        result = await delegator.run(task.task_id)
        console.print(f"  Status: [green]{result.status.value}[/green]")
        console.print(f"  Duration: {result.duration_seconds}s  API calls: {result.api_calls}")
        if result.summary:
            console.print(f"  Summary: {result.summary[:200]}")
        if result.error:
            console.print(f"  [red]Error: {result.error}[/red]")

    asyncio.run(_run())

@delegate.command("batch")
@click.argument("goals")
@click.option("--context", "-c", default=None, help="Context shared by all subagents")
@click.option("--role", "-r", default="leaf", type=click.Choice(["leaf", "orchestrator"]))
@click.option("--model", "-m", default=None, help="Model override")
@click.option("--toolsets", "-t", multiple=True, help="Allowed toolsets (repeatable)")
@click.option("--mode", "-p", default="standard", type=click.Choice(["standard", "auto-ask", "plan", "bypass", "dont-ask"]))
@click.pass_context
def delegate_batch(ctx, goals, context, role, model, toolsets, mode):
    """Delegate multiple goals in parallel (space-separated)."""
    from xcopilot.core.delegation import TaskDelegator
    from xcopilot.permission.pipeline import PermissionMode

    project_root = ctx.obj.get("project_root", Path.cwd())
    perm_mode = PermissionMode(mode)
    delegator = TaskDelegator(project_root=project_root, permission_mode=perm_mode)

    goal_list = [g.strip() for g in goals.split() if g.strip()]
    if not goal_list:
        console.print("[red]No goals provided. Usage: xcopilot delegate batch \"goal1\" \"goal2\" ...[/red]")
        return

    console.print(f"[cyan]Delegating {len(goal_list)} tasks in parallel...[/cyan]")
    for i, g in enumerate(goal_list):
        task = delegator.delegate(g, context=context, role=role, model=model,
                                  allowed_toolsets=tuple(toolsets))
        console.print(f"  [{i+1}] {task.task_id}: {g[:50]}...")

    if perm_mode == PermissionMode.PLAN:
        console.print("[red]PLAN mode denies delegation.[/red]")
        for tid in list(delegator._tasks.keys()):
            delegator.cancel(tid)
        return

    async def _run_all() -> None:
        results = await delegator.run_all()
        for tid, result in results.items():
            console.print(f"  [{tid}] Status: [green]{result.status.value}[/green]  Duration: {result.duration_seconds}s")
            if result.error:
                console.print(f"    [red]Error: {result.error}[/red]")

    asyncio.run(_run_all())

@delegate.command("status")
@click.argument("task_id")
@click.pass_context
def delegate_status(ctx, task_id):
    """Check the status of a delegated task."""
    from xcopilot.core.delegation import TaskDelegator

    project_root = ctx.obj.get("project_root", Path.cwd())
    delegator = TaskDelegator(project_root=project_root)
    task = delegator.status(task_id)
    if task is None:
        console.print(f"[red]Task {task_id} not found.[/red]")
        return
    console.print(f"  ID: [bold]{task.task_id}[/bold]")
    console.print(f"  Goal: {task.goal[:60]}...")
    status_style = "green" if task.status.value == "succeeded" else "red" if task.status.value in ("failed", "cancelled") else "yellow"
    console.print(f"  Status: [{status_style}]{task.status.value}[/{status_style}]")
    console.print(f"  Role: {task.role}  Created: {task.created_at}")
    if task.error:
        console.print(f"  [red]Error: {task.error}[/red]")

@delegate.command("list")
@click.pass_context
def delegate_list(ctx):
    """List all delegated tasks."""
    from xcopilot.core.delegation import TaskDelegator

    project_root = ctx.obj.get("project_root", Path.cwd())
    delegator = TaskDelegator(project_root=project_root)
    tasks = delegator.list_tasks()
    if not tasks:
        console.print("[yellow]No delegated tasks.[/yellow]")
        return
    table = Table(title="Delegated Tasks")
    table.add_column("ID", style="cyan")
    table.add_column("Goal", style="green")
    table.add_column("Status", style="yellow")
    table.add_column("Role", style="white")
    for t in tasks:
        table.add_row(t.task_id, t.goal[:40], t.status.value, t.role)
    console.print(table)

@delegate.command("cancel")
@click.argument("task_id")
@click.pass_context
def delegate_cancel(ctx, task_id):
    """Cancel a delegated task."""
    from xcopilot.core.delegation import TaskDelegator

    project_root = ctx.obj.get("project_root", Path.cwd())
    delegator = TaskDelegator(project_root=project_root)
    if delegator.cancel(task_id):
        console.print(f"[green]Task {task_id} cancelled.[/green]")
    else:
        console.print(f"[red]Task {task_id} not found or already terminal.[/red]")

@delegate.command("summary")
@click.pass_context
def delegate_summary(ctx):
    """Show aggregated delegation statistics."""
    from xcopilot.core.delegation import TaskDelegator

    project_root = ctx.obj.get("project_root", Path.cwd())
    delegator = TaskDelegator(project_root=project_root)
    stats = delegator.summary()
    console.print(f"  Total tasks: [bold]{stats['total_tasks']}[/bold]")
    for status, count in stats['by_status'].items():
        console.print(f"  {status}: {count}")
    console.print(f"  Avg duration: {stats['avg_duration_seconds']}s")
    console.print(f"  Total duration: {stats['total_duration_seconds']}s")

# Add all command groups
cli.add_command(delegate)
cli.add_command(memory)
cli.add_command(skills)
cli.add_command(checkpoints)
cli.add_command(graph)
cli.add_command(update)
cli.add_command(config)
cli.add_command(model)
cli.add_command(mcp)
cli.add_command(skill)
cli.add_command(init)
cli.add_command(doctor)
cli.add_command(setup)
cli.add_command(run)
cli.add_command(serve)


@cli.command()
@click.option("--test-mode", is_flag=True, help="Run in test mode (no model API)")
@click.pass_context
def start(ctx, test_mode):
    """Start the X-Copilot agent REPL."""
    from xcopilot.core.evaluator import Evaluator
    from xcopilot.core.learner import LearnerEngine
    from xcopilot.core.planner import PlannerEngine
    from xcopilot.memory import MemoryEngine
    from xcopilot.permission.pipeline import PermissionMode, PermissionPipeline
    from xcopilot.tools import FileTool, SearchTool, ShellTool, WebTool

    project_root = ctx.obj["project_root"]
    perm_mode = getattr(PermissionMode, ctx.obj["permission_mode"].upper())

    console.print(
        Panel.fit(
            "[bold cyan]X-Copilot[/bold cyan] — Self-growing AI agent for Windows",
            subtitle="v0.1.0",
        )
    )

    # Initialize components
    memory = MemoryEngine(project_root=str(project_root))
    _learner = LearnerEngine(memory)
    _planner = PlannerEngine(memory)
    _evaluator = Evaluator()
    _pipeline = PermissionPipeline(perm_mode)

    _tools = {
        "shell": ShellTool(_pipeline),
        "file": FileTool(_pipeline),
        "search": SearchTool(),
        "web": WebTool(_pipeline),
    }

    console.print("[green]✓[/green] Memory engine initialized")
    console.print("[green]✓[/green] Learner engine ready")
    console.print("[green]✓[/green] Planner engine ready")
    console.print("[green]✓[/green] Evaluator ready")
    console.print(f"[green]✓[/green] Permission mode: {perm_mode.value}")
    console.print("[green]✓[/green] Tools loaded: shell, file, search, web")

    if test_mode:
        console.print("[yellow]Test mode enabled - no model API calls[/yellow]")

    console.print("\n[bold]Ready for commands![/bold] Type 'help' for available commands.\n")

    # Enhanced REPL with prompt_toolkit (syntax highlighting, auto-completion)
    while True:
        try:
            user_input = console.input("[bold cyan]xcopilot>[/bold cyan] ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                console.print("[yellow]Goodbye![/yellow]")
                break
            elif user_input.lower() == "help":
                _print_help()
            elif user_input.lower() == "memory":
                _show_memory_status(memory)
            elif user_input.lower() == "skills":
                _show_skills(memory)
            elif user_input.lower() == "graph":
                _build_graph(project_root)
            elif user_input.lower() == "checkpoints":
                _show_checkpoints(project_root)
            elif user_input.lower().startswith("rewind "):
                _rewind_checkpoint(user_input.split(" ", 1)[1], project_root)
            elif user_input.lower() == "update":
                _check_update()
            else:
                console.print(f"[dim]Processing: {user_input}[/dim]")
                # In full implementation, would use learner/planner/evaluator
                console.print(
                    "[yellow]Full agent loop not yet implemented. Use CLI subcommands.[/yellow]"
                )
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted. Type 'exit' to quit.[/yellow]")
        except EOFError:
            break


def _print_help():
    console.print("\n[bold]Available commands:[/bold]")
    commands = [
        ("help", "Show this help"),
        ("memory", "Show memory status"),
        ("skills", "List available skills"),
        ("graph", "Build knowledge graph"),
        ("checkpoints", "List checkpoints"),
        ("rewind <id>", "Rewind to checkpoint"),
        ("update", "Check for updates"),
        ("model list", "List available models"),
        ("model chat", "Quick chat with a model"),
        ("mcp list", "List MCP servers"),
        ("skill search", "Search skills marketplace"),
        ("init project", "Initialize new project"),
        ("doctor", "Run diagnostics"),
        ("run webapp", "Run WebApp (Next.js)"),
        ("run desktop", "Run Desktop App (Tauri)"),
        ("run all", "Run both WebApp and Desktop App"),
        ("exit/quit/q", "Exit the REPL"),
    ]
    for cmd, desc in commands:
        console.print(f"  [cyan]{cmd:<25}[/cyan] {desc}")
    console.print()


def _show_memory_status(memory):
    console.print("[blue]Memory Status:[/blue]")
    console.print(f"  Session: {len(memory.session._data)} items")
    console.print("  Episodic: connected")
    console.print("  Semantic: connected")
    console.print("  Procedural: connected")
    console.print("  Project: connected")


def _show_skills(memory):
    skills = memory.procedural.list_skills()
    if skills:
        console.print("[blue]Available Skills:[/blue]")
        for skill in skills:
            console.print(f"  [cyan]{skill.name}[/cyan]: {skill.description}")
    else:
        console.print("[yellow]No skills found[/yellow]")


def _build_graph(project_root):
    from xcopilot.core.graph import KnowledgeGraph

    graph = KnowledgeGraph()
    with console.status("[bold green]Building knowledge graph..."):
        graph.build(str(project_root))
    stats = graph.stats()
    console.print(f"[green]✓[/green] Graph built: {stats['nodes']} nodes, {stats['edges']} edges")


def _show_checkpoints(project_root):
    from xcopilot.core.checkpoint import CheckpointManager

    cp_mgr = CheckpointManager(checkpoints_dir=str(project_root / ".xcopilot" / "checkpoints"))
    checkpoints = cp_mgr.list_checkpoints()
    if checkpoints:
        table = Table(title="Checkpoints")
        table.add_column("ID", style="cyan")
        table.add_column("Timestamp", style="dim")
        table.add_column("Action", style="green")
        table.add_column("Target", style="yellow")
        for cp in checkpoints:
            table.add_row(cp["id"], cp["timestamp"], cp["action"], cp["target"])
        console.print(table)
    else:
        console.print("[yellow]No checkpoints yet[/yellow]")


def _rewind_checkpoint(checkpoint_id, project_root):
    from xcopilot.core.checkpoint import CheckpointManager

    cp_mgr = CheckpointManager(checkpoints_dir=str(project_root / ".xcopilot" / "checkpoints"))
    if cp_mgr.rewind(checkpoint_id):
        console.print(f"[green]✓[/green] Rewound to {checkpoint_id}")
    else:
        console.print(f"[red]✗[/red] Checkpoint {checkpoint_id} not found")


def _check_update():
    from xcopilot.core.updater import Updater

    updater = Updater()
    info = updater.check()
    console.print(f"[blue]Current: 0.1.0, Latest: {info.version}[/blue]")


# ── Desktop command group ──────────────────────

@click.group()
def desktop():
    """X-Copilot Desktop App (Electron)."""

@desktop.command("start")
@click.option("--dev", is_flag=True, help="Run in development mode with DevTools")
@click.option("--server", is_flag=True, help="Start server only (no UI)")
@click.pass_context
def desktop_start(ctx, dev, server):
    """Start the X-Copilot desktop app."""
    import subprocess
    import sys
    from pathlib import Path

    project_root = ctx.obj.get("project_root", Path.cwd())
    desktop_dir = project_root / "desktop"

    if server:
        # Start server only
        console.print("[cyan]Starting X-Copilot server...[/cyan]")
        subprocess.run([sys.executable, "-m", "server.main", "serve"], cwd=str(project_root))
        return

    # Start Electron app
    console.print("[cyan]Starting X-Copilot Desktop App...[/cyan]")

    # Ensure dependencies are installed
    pkg_json = desktop_dir / "package.json"
    if pkg_json.exists():
        console.print("[yellow]Installing Electron dependencies...[/yellow]")
        subprocess.run(["npm", "install"], cwd=str(desktop_dir), check=False)

    # Launch Electron
    electron_cmd = ["npx", "electron", "."]
    if dev:
        electron_cmd.append("--dev")

    try:
        subprocess.run(electron_cmd, cwd=str(desktop_dir), check=True)
    except FileNotFoundError:
        console.print("[red]Electron not found. Run: cd desktop && npm install[/red]")
    except KeyboardInterrupt:
        console.print("\n[yellow]Desktop app stopped.[/yellow]")

@desktop.command("status")
def desktop_status():
    """Check if the desktop app and server are running."""
    import urllib.request
    import json

    console.print("[cyan]X-Copilot Desktop Status[/cyan]")

    # Check server
    try:
        req = urllib.request.Request("http://127.0.0.1:8001/health")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            console.print(f"  Server: [green]Running[/green] ({data.get('status', 'ok')})")
    except Exception:
        console.print("  Server: [red]Not running[/red]")

    # Check Electron
    try:
        result = subprocess.run(
            ["pgrep", "-f", "electron"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            console.print("  Desktop: [green]Running[/green]")
        else:
            console.print("  Desktop: [red]Not running[/red]")
    except Exception:
        console.print("  Desktop: [yellow]Cannot check[/yellow]")

cli.add_command(desktop)

# ── Webapp command ──────────────────────────────

@click.command("webapp")
@click.option("--port", "-p", default=3000, help="Port for the webapp")
@click.option("--host", "-h", default="127.0.0.1", help="Host for the webapp")
@click.option("--server", is_flag=True, help="Start server only (no browser)")
@click.pass_context
def webapp(ctx, port, host, server):
    """Start the X-Copilot web dashboard."""
    import webbrowser
    from pathlib import Path

    project_root = ctx.obj.get("project_root", Path.cwd())
    webapp_dir = project_root / "webapp"

    if not webapp_dir.exists():
        console.print("[red]Webapp not found. Create webapp/ directory first.[/red]")
        return

    # Start server if not running
    if not server:
        console.print("[cyan]Starting X-Copilot server...[/cyan]")
        import subprocess
        subprocess.Popen(
            [sys.executable, "-m", "server.main", "serve"],
            cwd=str(project_root),
        )
        import time
        time.sleep(2)  # Wait for server to start

    # Open browser
    url = f"http://{host}:{port}"
    console.print(f"[green]Web Dashboard: {url}[/green]")
    webbrowser.open(url)

cli.add_command(webapp)

if __name__ == "__main__":
    cli()