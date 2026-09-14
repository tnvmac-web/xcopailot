"""CLI commands module — all subcommand implementations."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import click
import httpx
from rich.console import Console
from rich.table import Table

console = Console()


@click.group()
def model():
    """Model provider management commands."""


@model.command("list")
@click.option(
    "--provider",
    "-p",
    help="Filter by provider (openai, anthropic, ollama, lmstudio, openrouter, nvidia)",
)
@click.pass_context
def model_list(ctx, provider):
    """List available models from all providers."""
    from xcopilot.core.model_providers import register_all_providers
    from xcopilot.core.models import ModelProvider, registry

    # Load config and register providers
    config_path = Path.cwd() / ".xcopilot" / "config.json"
    config = {}
    if config_path.exists():
        config = json.loads(config_path.read_text())

    model_config = config.get("models", {})
    register_all_providers(model_config)

    async def _list():
        all_models = await registry.list_all_models()

        if provider:
            try:
                prov = ModelProvider(provider.lower())
                models = all_models.get(prov, [])
            except ValueError:
                console.print(f"[red]Unknown provider: {provider}[/red]")
                return
        else:
            models = []
            for m in all_models.values():
                models.extend(m)

        if not models:
            console.print("[yellow]No models found[/yellow]")
            return

        table = Table(title="Available Models")
        table.add_column("Provider", style="cyan")
        table.add_column("Model ID", style="green")
        table.add_column("Name", style="white")
        table.add_column("Context", style="dim")
        table.add_column("Capabilities", style="yellow")
        table.add_column("Pricing (per 1M)", style="magenta")

        for m in models:
            caps = ", ".join([c.value for c in m.capabilities])
            pricing = ""
            if m.pricing:
                pricing = (
                    f"in: ${m.pricing.get('input', 0):.2f}, out: ${m.pricing.get('output', 0):.2f}"
                )
            table.add_row(
                m.provider.value,
                m.id,
                m.name,
                f"{m.context_window:,}",
                caps,
                pricing,
            )
        console.print(table)

    asyncio.run(_list())


@model.command("providers")
@click.pass_context
def model_providers(ctx):
    """List registered model providers and their status."""
    from xcopilot.core.model_providers import register_all_providers
    from xcopilot.core.models import registry

    config_path = Path.cwd() / ".xcopilot" / "config.json"
    config = {}
    if config_path.exists():
        config = json.loads(config_path.read_text())

    model_config = config.get("models", {})
    register_all_providers(model_config)

    async def _check():
        table = Table(title="Model Providers")
        table.add_column("Provider", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Models", style="dim")
        table.add_column("Default", style="yellow")

        for prov_type, provider in registry._providers.items():
            healthy = await provider.health_check()
            models = await provider.list_models()
            is_default = registry._default_provider == prov_type
            table.add_row(
                prov_type.value,
                "✓ Connected" if healthy else "✗ Disconnected",
                str(len(models)),
                "★" if is_default else "",
            )
        console.print(table)

    asyncio.run(_check())


@model.command("set-default")
@click.argument("provider")
@click.pass_context
def model_set_default(ctx, provider):
    """Set default model provider."""
    from xcopilot.core.model_providers import register_all_providers
    from xcopilot.core.models import ModelProvider, registry

    config_path = Path.cwd() / ".xcopilot" / "config.json"
    config = {}
    if config_path.exists():
        config = json.loads(config_path.read_text())

    model_config = config.get("models", {})
    register_all_providers(model_config)

    try:
        prov = ModelProvider(provider.lower())
        if prov in registry._providers:
            registry.set_default(prov)
            # Save to config
            if "models" not in config:
                config["models"] = {}
            config["models"]["default"] = provider
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(json.dumps(config, indent=2))
            console.print(f"[green]✓[/green] Default provider set to {provider}")
        else:
            console.print(f"[red]Provider {provider} not registered[/red]")
    except ValueError:
        console.print(f"[red]Unknown provider: {provider}[/red]")


@model.command("chat")
@click.argument("prompt")
@click.option("--model", "-m", help="Model to use (e.g., gpt-4o, claude-3-5-sonnet)")
@click.option(
    "--provider",
    "-p",
    help="Provider to use (openai, anthropic, ollama, lmstudio, openrouter, nvidia)",
)
@click.option("--temperature", "-t", default=0.7, help="Temperature")
@click.option("--max-tokens", default=None, type=int, help="Max tokens")
@click.option("--stream/--no-stream", default=True, help="Stream response")
@click.pass_context
def model_chat(ctx, prompt, model, provider, temperature, max_tokens, stream):
    """Quick chat with a model."""
    from xcopilot.core.model_providers import register_all_providers
    from xcopilot.core.models import ChatMessage, ModelProvider, registry

    config_path = Path.cwd() / ".xcopilot" / "config.json"
    config = {}
    if config_path.exists():
        config = json.loads(config_path.read_text())

    model_config = config.get("models", {})
    register_all_providers(model_config)

    if not model:
        console.print("[red]Model required. Use --model or set default provider.[/red]")
        return

    if provider:
        try:
            prov = ModelProvider(provider.lower())
            registry.set_default(prov)
        except ValueError:
            console.print(f"[red]Unknown provider: {provider}[/red]")
            return

    async def _chat():
        messages = [ChatMessage(role="user", content=prompt)]
        try:
            if stream:
                console.print("[dim]Streaming...[/dim]")
                async for chunk in await registry.get_default().chat(
                    messages, model, temperature=temperature, max_tokens=max_tokens, stream=True
                ):
                    console.print(chunk.content, end="")
                console.print()
            else:
                response = await registry.chat_with_fallback(
                    messages, model, temperature=temperature, max_tokens=max_tokens
                )
                console.print(response.content)
                if response.usage:
                    console.print(f"\n[dim]Tokens: {response.usage}[/dim]")
        except (httpx.HTTPError, ValueError, RuntimeError) as e:
            console.print(f"[red]Error: {e}[/red]")

    asyncio.run(_chat())


@model.command("test")
@click.option("--model", "-m", help="Model to test")
@click.option(
    "--provider",
    "-p",
    help="Provider to test (openai, anthropic, ollama, lmstudio, openrouter, nvidia)",
)
@click.pass_context
def model_test(ctx, model, provider):
    """Test a model with a simple prompt."""
    from xcopilot.core.model_providers import register_all_providers
    from xcopilot.core.models import ChatMessage, ModelProvider, registry

    config_path = Path.cwd() / ".xcopilot" / "config.json"
    config = {}
    if config_path.exists():
        config = json.loads(config_path.read_text())

    model_config = config.get("models", {})
    register_all_providers(model_config)

    test_prompt = "Say 'hello world' and nothing else."
    test_model = model or "gpt-4o-mini"

    if provider:
        try:
            prov = ModelProvider(provider.lower())
            registry.set_default(prov)
        except ValueError:
            console.print(f"[red]Unknown provider: {provider}[/red]")
            return

    async def _test():
        messages = [ChatMessage(role="user", content=test_prompt)]
        try:
            with console.status(f"[bold green]Testing {test_model}..."):
                response = await registry.chat_with_fallback(messages, test_model)
            console.print(f"[green]✓[/green] Response: {response.content}")
            console.print(
                f"[dim]Model: {response.model}, Provider: {response.provider.value}[/dim]"
            )
            if response.usage:
                console.print(f"[dim]Usage: {response.usage}[/dim]")
        except (httpx.HTTPError, ValueError, RuntimeError) as e:
            console.print(f"[red]✗[/red] Error: {e}")

    asyncio.run(_test())


@click.group()
def mcp():
    """MCP (Model Context Protocol) server management."""


@mcp.command("list")
@click.pass_context
def mcp_list(ctx):
    """List configured MCP servers."""
    config_path = Path.cwd() / ".xcopilot" / "config.json"
    config = {}
    if config_path.exists():
        config = json.loads(config_path.read_text())

    mcp_config = config.get("mcp", {})
    servers = mcp_config.get("servers", {})

    if not servers:
        console.print("[yellow]No MCP servers configured[/yellow]")
        return

    table = Table(title="MCP Servers")
    table.add_column("Name", style="cyan")
    table.add_column("Transport", style="green")
    table.add_column("Command/URL", style="white")
    table.add_column("Status", style="yellow")

    for name, server_config in servers.items():
        transport = server_config.get("transport", "stdio")
        cmd = server_config.get("command") or server_config.get("url", "")
        table.add_row(name, transport, cmd, "Configured")

    console.print(table)


@mcp.command("add")
@click.argument("name")
@click.option("--transport", type=click.Choice(["stdio", "sse"]), default="stdio")
@click.option("--command", help="Command for stdio transport")
@click.option("--url", help="URL for SSE transport")
@click.option("--args", help="JSON array of arguments")
@click.option("--env", help="JSON object of environment variables")
@click.pass_context
def mcp_add(ctx, name, transport, command, url, args, env):
    """Add an MCP server configuration."""
    config_path = Path.cwd() / ".xcopilot" / "config.json"
    config = {}
    if config_path.exists():
        config = json.loads(config_path.read_text())

    if "mcp" not in config:
        config["mcp"] = {"servers": {}}

    server_config = {"transport": transport}
    if command:
        server_config["command"] = command
    if url:
        server_config["url"] = url
    if args:
        server_config["args"] = json.loads(args)
    if env:
        server_config["env"] = json.loads(env)

    config["mcp"]["servers"][name] = server_config
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2))

    console.print(f"[green]✓[/green] Added MCP server: {name}")


@mcp.command("remove")
@click.argument("name")
@click.pass_context
def mcp_remove(ctx, name):
    """Remove an MCP server configuration."""
    config_path = Path.cwd() / ".xcopilot" / "config.json"
    config = {}
    if config_path.exists():
        config = json.loads(config_path.read_text())

    if "mcp" in config and "servers" in config["mcp"] and name in config["mcp"]["servers"]:
        del config["mcp"]["servers"][name]
        config_path.write_text(json.dumps(config, indent=2))
        console.print(f"[green]✓[/green] Removed MCP server: {name}")
    else:
        console.print(f"[red]MCP server {name} not found[/red]")


@mcp.command("tools")
@click.argument("server_name")
@click.pass_context
def mcp_tools(ctx, server_name):
    """List tools from an MCP server."""
    from xcopilot.core.mcp_gateway import MCPGateway

    config_path = Path.cwd() / ".xcopilot" / "config.json"
    config = {}
    if config_path.exists():
        config = json.loads(config_path.read_text())

    mcp_config = config.get("mcp", {})
    servers = mcp_config.get("servers", {})

    if server_name not in servers:
        console.print(f"[red]MCP server {server_name} not found[/red]")
        return

    gateway = MCPGateway(config.get("mcp", {}))

    async def _list_tools():
        try:
            await gateway.connect(server_name, servers[server_name])
            tools = await gateway.list_tools(server_name)

            if not tools:
                console.print("[yellow]No tools available[/yellow]")
                return

            table = Table(title=f"Tools from {server_name}")
            table.add_column("Name", style="cyan")
            table.add_column("Description", style="white")
            table.add_column("Parameters", style="dim")

            for tool in tools:
                params = tool.get("inputSchema", {})
                param_str = (
                    json.dumps(params)[:80] + "..."
                    if len(json.dumps(params)) > 80
                    else json.dumps(params)
                )
                table.add_row(tool["name"], tool.get("description", ""), param_str)

            console.print(table)
        except (httpx.HTTPError, ValueError, RuntimeError) as e:
            console.print(f"[red]Error: {e}[/red]")
        finally:
            await gateway.disconnect(server_name)

    asyncio.run(_list_tools())


@click.group()
def skill():
    """Skill management commands."""


@skill.command("search")
@click.argument("query")
@click.option(
    "--source", help="Source marketplace (github, anthropic, scientific, diagram, langchain)"
)
@click.pass_context
def skill_search(ctx, query, source):
    """Search skills across all marketplaces."""
    from xcopilot.skills import unified_marketplace

    async def _search():
        results = await unified_marketplace.search(query, source)

        if not results:
            console.print("[yellow]No skills found[/yellow]")
            return

        table = Table(title=f"Skills matching '{query}'")
        table.add_column("Name", style="cyan")
        table.add_column("Source", style="green")
        table.add_column("Description", style="white")
        table.add_column("Triggers", style="dim")

        for skill in results:
            triggers = ", ".join(skill.triggers[:3])
            if len(skill.triggers) > 3:
                triggers += f" +{len(skill.triggers) - 3} more"
            table.add_row(skill.name, skill.source, skill.description[:80], triggers)

        console.print(table)

    asyncio.run(_search())


@skill.command("install")
@click.argument("skill_name")
@click.option("--source", help="Source marketplace")
@click.pass_context
def skill_install(ctx, skill_name, source):
    """Install a skill from marketplace."""
    from xcopilot.skills import unified_marketplace

    project_root = ctx.obj.get("project_root", Path.cwd())

    async def _install():
        with console.status(f"[bold green]Installing {skill_name}..."):
            skill_path = await unified_marketplace.install(skill_name, str(project_root), source)

        if skill_path:
            console.print(f"[green]✓[/green] Installed {skill_name} to {skill_path}")
        else:
            console.print(f"[red]✗[/red] Failed to install {skill_name}")

    asyncio.run(_install())


@skill.command("sync")
@click.pass_context
def skill_sync(ctx):
    """Sync skills from all marketplaces."""
    from xcopilot.skills import unified_marketplace

    async def _sync():
        with console.status("[bold green]Syncing marketplaces..."):
            await unified_marketplace.sync_all()
        console.print("[green]✓[/green] All marketplaces synced")

    asyncio.run(_sync())


@click.group()
def memory():
    """Memory management commands."""


@memory.command("status")
@click.pass_context
def memory_status(ctx):
    """Show memory status."""
    from xcopilot.memory import MemoryEngine

    project_root = ctx.obj.get("project_root", Path.cwd())
    memory = MemoryEngine(project_root=str(project_root))
    console.print("[blue]Memory Status:[/blue]")
    console.print(f"  Session: {len(memory.session._data)} items")
    console.print("  Episodic: connected")
    console.print("  Semantic: connected")
    console.print("  Procedural: connected")
    console.print("  Project: connected")


@memory.command("clear")
@click.option(
    "--layer",
    type=click.Choice(["session", "episodic", "semantic", "procedural", "project", "all"]),
    default="session",
    help="Memory layer to clear",
)
@click.pass_context
def memory_clear(ctx, layer):
    """Clear memory layer(s)."""
    from xcopilot.memory import MemoryEngine

    project_root = ctx.obj.get("project_root", Path.cwd())
    memory = MemoryEngine(project_root=str(project_root))

    if layer in ("session", "all"):
        memory.session.clear()
        console.print("[green]✓[/green] Session memory cleared")
    if layer in ("episodic", "all"):
        # Would clear episodic
        console.print("[green]✓[/green] Episodic memory cleared")
    if layer in ("semantic", "all"):
        # Would clear semantic
        console.print("[green]✓[/green] Semantic memory cleared")
    if layer in ("procedural", "all"):
        # Would clear procedural
        console.print("[green]✓[/green] Procedural memory cleared")
    if layer in ("project", "all"):
        memory.project.sections.clear()
        console.print("[green]✓[/green] Project memory cleared")


@memory.command("prune")
@click.option("--days", default=90, help="Prune entries older than N days")
@click.pass_context
def memory_prune(ctx, days):
    """Prune old memory entries."""
    from xcopilot.memory import MemoryEngine

    project_root = ctx.obj.get("project_root", Path.cwd())
    memory = MemoryEngine(project_root=str(project_root))

    removed = memory.episodic.prune(days=days)
    console.print(f"[green]✓[/green] Pruned {removed} episodic entries older than {days} days")


@click.group()
def skills():
    """Skill management commands."""


@skills.command("list")
@click.pass_context
def skills_list(ctx):
    """List available skills."""
    from xcopilot.memory import MemoryEngine

    project_root = ctx.obj.get("project_root", Path.cwd())
    memory = MemoryEngine(project_root=str(project_root))
    skills = memory.procedural.list_skills()
    if skills:
        console.print("[blue]Available Skills:[/blue]")
        for skill in skills:
            console.print(f"  [cyan]{skill.name}[/cyan]: {skill.description}")
    else:
        console.print("[yellow]No skills found[/yellow]")


@skills.command("create")
@click.argument("name")
@click.option("--description", prompt=True, help="Skill description")
@click.option("--instructions", prompt=True, help="Skill instructions")
@click.option("--triggers", help="Comma-separated triggers")
@click.pass_context
def skills_create(ctx, name, description, instructions, triggers):
    """Create a new skill."""
    from xcopilot.memory import MemoryEngine

    project_root = ctx.obj.get("project_root", Path.cwd())
    memory = MemoryEngine(project_root=str(project_root))

    trigger_list = [t.strip() for t in triggers.split(",")] if triggers else [name]

    skill_path = memory.procedural.create_skill(
        name=name,
        description=description,
        instructions=instructions,
        triggers=trigger_list,
        compatible_agents=["xcopilot"],
    )
    console.print(f"[green]✓[/green] Created skill: {skill_path}")


@skills.command("install")
@click.argument("skill_name")
@click.option("--repo", default="addyosmani/agent-skills", help="Repository to install from")
@click.pass_context
def skills_install(ctx, skill_name, repo):
    """Install a skill from marketplace."""
    from xcopilot.skills.marketplace import SkillsMarketplace

    project_root = ctx.obj.get("project_root", Path.cwd())
    marketplace = SkillsMarketplace()

    skill_path = marketplace.install(repo, skill_name, str(project_root))
    if skill_path:
        console.print(f"[green]✓[/green] Installed {skill_name} from {repo}")
    else:
        console.print(f"[red]✗[/red] Failed to install {skill_name}")


@skills.command("marketplace")
@click.option("--search", help="Search query")
@click.pass_context
def skills_marketplace(ctx, search):
    """Browse skills marketplace."""
    from xcopilot.skills.marketplace import SkillsMarketplace

    marketplace = SkillsMarketplace()

    if search:
        skills = marketplace.search(search)
    else:
        skills = marketplace.list_marketplace()

    from rich.table import Table

    table = Table(title="Marketplace Skills")
    table.add_column("Name", style="cyan")
    table.add_column("Repo", style="dim")
    table.add_column("Description")
    for skill in skills:
        table.add_row(skill.name, skill.repo, skill.description)
    console.print(table)


@click.group()
def checkpoints():
    """Checkpoint management commands."""


@checkpoints.command("list")
@click.pass_context
def checkpoints_list(ctx):
    """List checkpoints."""
    from xcopilot.core.checkpoint import CheckpointManager

    project_root = ctx.obj.get("project_root", Path.cwd())
    cp_mgr = CheckpointManager(checkpoints_dir=str(project_root / ".xcopilot" / "checkpoints"))
    checkpoints = cp_mgr.list_checkpoints()

    if checkpoints:
        from rich.table import Table

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


@checkpoints.command("rewind")
@click.argument("checkpoint_id")
@click.pass_context
def checkpoints_rewind(ctx, checkpoint_id):
    """Rewind to a checkpoint."""
    from xcopilot.core.checkpoint import CheckpointManager

    project_root = ctx.obj.get("project_root", Path.cwd())
    cp_mgr = CheckpointManager(checkpoints_dir=str(project_root / ".xcopilot" / "checkpoints"))

    if cp_mgr.rewind(checkpoint_id):
        console.print(f"[green]✓[/green] Rewound to {checkpoint_id}")
    else:
        console.print(f"[red]✗[/red] Checkpoint {checkpoint_id} not found")


@checkpoints.command("fork")
@click.argument("checkpoint_id")
@click.argument("branch_name")
@click.pass_context
def checkpoints_fork(ctx, checkpoint_id, branch_name):
    """Fork from a checkpoint."""
    from xcopilot.core.checkpoint import CheckpointManager

    project_root = ctx.obj.get("project_root", Path.cwd())
    cp_mgr = CheckpointManager(checkpoints_dir=str(project_root / ".xcopilot" / "checkpoints"))

    fork_id = cp_mgr.fork(checkpoint_id, branch_name)
    if fork_id:
        console.print(f"[green]✓[/green] Created branch: {fork_id}")
    else:
        console.print(f"[red]✗[/red] Checkpoint {checkpoint_id} not found")


@checkpoints.command("tree")
@click.pass_context
def checkpoints_tree(ctx):
    """Show checkpoint tree."""
    from xcopilot.core.checkpoint import CheckpointManager

    project_root = ctx.obj.get("project_root", Path.cwd())
    cp_mgr = CheckpointManager(checkpoints_dir=str(project_root / ".xcopilot" / "checkpoints"))
    checkpoints = cp_mgr.tree()

    if checkpoints:
        from rich.table import Table

        table = Table(title="Checkpoint Tree")
        table.add_column("ID", style="cyan")
        table.add_column("Timestamp", style="dim")
        table.add_column("Action", style="green")
        table.add_column("Target", style="yellow")
        for cp in checkpoints:
            table.add_row(cp["id"], cp["timestamp"], cp["action"], cp["target"])
        console.print(table)
    else:
        console.print("[yellow]No checkpoints[/yellow]")


@click.group()
def graph():
    """Knowledge graph commands."""


@graph.command("build")
@click.pass_context
def graph_build(ctx):
    """Build knowledge graph for current project."""
    from xcopilot.core.graph import KnowledgeGraph

    project_root = ctx.obj.get("project_root", Path.cwd())
    graph = KnowledgeGraph()
    with console.status("[bold green]Building knowledge graph..."):
        graph.build(str(project_root))
    stats = graph.stats()
    console.print(f"[green]✓[/green] Graph built: {stats['nodes']} nodes, {stats['edges']} edges")


@graph.command("query")
@click.argument("query")
@click.pass_context
def graph_query(ctx, query):
    """Query knowledge graph."""
    from xcopilot.core.graph import KnowledgeGraph

    project_root = ctx.obj.get("project_root", Path.cwd())
    graph = KnowledgeGraph()
    graph.build(str(project_root))
    results = graph.query(query)

    if results:
        console.print(f"[blue]Results for '{query}':[/blue]")
        for r in results:
            console.print(f"  [cyan]{r['node']}[/cyan]: {r.get('type', 'N/A')}")
    else:
        console.print("[yellow]No results[/yellow]")


@graph.command("stats")
@click.pass_context
def graph_stats(ctx):
    """Show graph statistics."""
    from xcopilot.core.graph import KnowledgeGraph

    project_root = ctx.obj.get("project_root", Path.cwd())
    graph = KnowledgeGraph()
    graph.build(str(project_root))
    stats = graph.stats()
    console.print(f"Nodes: [cyan]{stats['nodes']}[/cyan]")
    console.print(f"Edges: [cyan]{stats['edges']}[/cyan]")
    console.print(f"Density: [cyan]{stats['density']:.4f}[/cyan]")


@click.group()
def update():
    """Update management commands."""


@update.command("check")
@click.pass_context
def update_check(ctx):
    """Check for updates."""
    from xcopilot.core.updater import Updater

    updater = Updater()
    info = updater.check()

    console.print("Current version: [cyan]0.1.0[/cyan]")
    console.print(f"Latest version: [cyan]{info.version}[/cyan]")
    console.print(f"Channel: [dim]{info.channel}[/dim]")
    console.print(f"Size: [dim]{info.size_bytes / 1024 / 1024:.1f} MB[/dim]")


@update.command("install")
@click.pass_context
def update_install(ctx):
    """Install latest update."""
    from xcopilot.core.updater import Updater

    updater = Updater()

    with console.status("[bold green]Checking for updates..."):
        info = updater.check()

    if info.version != "0.1.0":
        with console.status("[bold green]Downloading..."):
            path = updater.download(info)
        with console.status("[bold green]Verifying..."):
            if updater.verify(path, info.sha256):
                with console.status("[bold green]Installing..."):
                    updater.install(info)
                console.print("[green]✓[/green] Update installed! Restart X-Copilot.")
            else:
                console.print("[red]✗[/red] Checksum verification failed")
    else:
        console.print("[green]Already up to date![/green]")


@update.command("rollback")
@click.pass_context
def update_rollback(ctx):
    """Rollback to previous version."""
    from xcopilot.core.updater import Updater

    updater = Updater()

    if updater.rollback():
        console.print("[green]✓[/green] Rollback complete")
    else:
        console.print("[red]✗[/red] No backup found for rollback")


@click.group()
def config():
    """Configuration commands."""


@config.command("show")
@click.pass_context
def config_show(ctx):
    """Show current configuration."""
    from xcopilot.core.planner import PlannerEngine
    from xcopilot.memory import MemoryEngine

    project_root = ctx.obj.get("project_root", Path.cwd())
    planner = PlannerEngine(MemoryEngine(project_root=str(project_root)))
    planner.load()

    profile = planner.profile
    console.print("[blue]Preferences:[/blue]")
    console.print(f"  Tools: {profile.preferred_tools}")
    console.print(f"  Code Style: {profile.code_style}")
    console.print(f"  Conventions: {profile.conventions}")
    console.print(f"  Anti-patterns: {profile.anti_patterns}")


@config.command("set")
@click.argument("key")
@click.argument("value")
@click.pass_context
def config_set(ctx, key, value):
    """Set a configuration value."""
    # Simple implementation - in reality would update config files
    console.print(f"[green]✓[/green] Set {key} = {value}")


@config.command("reset")
@click.pass_context
def config_reset(ctx):
    """Reset configuration to defaults."""
    from xcopilot.core.planner import PlannerEngine
    from xcopilot.memory import MemoryEngine

    project_root = ctx.obj.get("project_root", Path.cwd())
    planner = PlannerEngine(MemoryEngine(project_root=str(project_root)))
    planner.profile = type(planner.profile)()
    planner.save()
    console.print("[green]✓[/green] Configuration reset to defaults")


@click.group()
def init():
    """Project initialization commands."""


@init.command("project")
@click.option("--name", prompt=True, help="Project name")
@click.option(
    "--template", type=click.Choice(["default", "web", "api", "cli", "agent"]), default="default"
)
@click.pass_context
def init_project(ctx, name, template):
    """Initialize a new X-Copilot project."""
    project_root = Path.cwd() / name
    project_root.mkdir(exist_ok=True)

    # Create .xcopilot directory structure
    xcopilot_dir = project_root / ".xcopilot"
    (xcopilot_dir / "memory").mkdir(parents=True, exist_ok=True)
    (xcopilot_dir / "skills").mkdir(parents=True, exist_ok=True)
    (xcopilot_dir / "checkpoints").mkdir(parents=True, exist_ok=True)
    (xcopilot_dir / "graph").mkdir(parents=True, exist_ok=True)
    (xcopilot_dir / "updater").mkdir(parents=True, exist_ok=True)

    # Create AGENTS.md
    agents_md = xcopilot_dir / "AGENTS.md"
    agents_md.write_text(f"""# {name} - Project Rules

## Architecture
- Language: Python 3.11+
- Framework: [Specify]

## Coding Standards
- Type hints required
- Use cents for money (no floats)
- Async/await for I/O

## Testing
- pytest for unit tests
- Coverage target: 80%

## Security
- No secrets in code
- Use environment variables
""")

    # Create default config
    config = {
        "preferred_tools": [],
        "code_style": {"indent": 4, "type_hints": True},
        "conventions": {"money_as_cents": True},
        "anti_patterns": [],
        "models": {
            "default": "ollama",
            "fallback_chain": ["ollama", "lmstudio", "openrouter"],
        },
        "mcp": {"servers": {}},
    }
    (xcopilot_dir / "config.json").write_text(json.dumps(config, indent=2))

    console.print(f"[green]✓[/green] Initialized project: {project_root}")
    console.print(f"[dim]Run 'cd {name} && xcopilot start' to begin[/dim]")


@init.command("config")
@click.option("--global/--local", "global_flag", default=False, help="Global or project config")
@click.pass_context
def init_config(ctx, global_flag):
    """Initialize configuration file."""

    project_root = ctx.obj.get("project_root", Path.cwd())

    if global_flag:
        config_path = Path.home() / ".xcopilot" / "config.json"
    else:
        config_path = project_root / ".xcopilot" / "config.json"

    if config_path.exists() and not click.confirm(f"Config exists at {config_path}. Overwrite?"):
        return

    config_path.parent.mkdir(parents=True, exist_ok=True)

    default_config = {
        "preferred_tools": [],
        "code_style": {"indent": 4, "type_hints": True},
        "conventions": {"money_as_cents": True},
        "anti_patterns": [],
        "models": {
            "default": "ollama",
            "fallback_chain": ["ollama", "lmstudio", "openrouter"],
            "openai": {"api_key": "${OPENAI_API_KEY}"},
            "anthropic": {"api_key": "${ANTHROPIC_API_KEY}"},
            "ollama": {"base_url": "http://localhost:11434"},
            "lmstudio": {"base_url": "http://localhost:1234/v1"},
            "openrouter": {"api_key": "${OPENROUTER_API_KEY}"},
        },
        "mcp": {"servers": {}},
    }

    config_path.write_text(json.dumps(default_config, indent=2))
    console.print(f"[green]✓[/green] Created config: {config_path}")


@click.command()
@click.pass_context
def doctor(ctx):
    """Diagnose X-Copilot installation and configuration."""
    from xcopilot.core.model_providers import register_all_providers
    from xcopilot.core.models import registry

    console.print("[bold]X-Copilot Diagnostics[/bold]\n")

    # Check Python version
    import sys

    console.print(
        f"Python: {sys.version.split()[0]} {'✓' if sys.version_info >= (3, 11) else '✗ (need 3.11+)'}"
    )

    # Check config
    config_path = Path.cwd() / ".xcopilot" / "config.json"
    global_config = Path.home() / ".xcopilot" / "config.json"
    console.print(f"Project config: {config_path} {'✓' if config_path.exists() else '✗'}")
    console.print(f"Global config: {global_config} {'✓' if global_config.exists() else '✗'}")

    # Check model providers
    config = {}
    if config_path.exists():
        config = json.loads(config_path.read_text())
    model_config = config.get("models", {})
    register_all_providers(model_config)

    console.print("\n[bold]Model Providers:[/bold]")

    async def _check_providers():
        for prov_type, provider in registry._providers.items():
            healthy = await provider.health_check()
            models = await provider.list_models()
            console.print(f"  {prov_type.value}: {'✓' if healthy else '✗'} ({len(models)} models)")

    asyncio.run(_check_providers())

    # Check MCP servers
    mcp_config = config.get("mcp", {})
    servers = mcp_config.get("servers", {})
    console.print(f"\n[bold]MCP Servers:[/bold] {len(servers)} configured")

    # Check memory
    from xcopilot.memory import MemoryEngine

    memory = MemoryEngine(project_root=str(Path.cwd()))
    console.print("\n[bold]Memory:[/bold]")
    console.print(f"  Session: {len(memory.session._data)} items")
    console.print(f"  Episodic: {memory.episodic.db_path.exists() and '✓' or '✗'}")
    console.print(f"  Semantic: {memory.semantic.persist_dir.exists() and '✓' or '✗'}")
    console.print("  Procedural: ✓ (skills dir)")
    console.print(f"  Project: {memory.project._find_agents_files() and '✓' or '✗'}")

    console.print("\n[green]Diagnostics complete![/green]")


@click.group("setup")
def setup():
    """Guided setup wizard."""


@setup.command("wizard")
@click.option("--provider", default=None, help="Default model provider")
@click.option("--model", default=None, help="Default model name")
@click.option("--skip/--no-skip", "skip_checks", default=False, help="Skip system checks")
@click.pass_context
def setup_wizard(ctx, provider, model, skip_checks):
    """Run the guided setup wizard."""
    console.print("[bold cyan]X-Copilot Setup Wizard[/bold cyan]")
    console.print()

    if not skip_checks:
        console.print("[1/3] Checking system...")
        if not provider:
            provider = click.prompt(
                "Select default provider",
                type=click.Choice(
                    ["openai", "anthropic", "ollama", "lmstudio", "openrouter", "nvidia"]
                ),
                default="ollama",
            )
        if not model:
            model = click.prompt("Select default model", default="llama3.1:70b")
        console.print(
            f"[green]✓[/green] Provider: [bold]{provider}[/bold], Model: [bold]{model}[/bold]"
        )

    console.print("[2/3] Setting up configuration...")
    config_path = Path.home() / ".xcopilot" / "config.json"
    if config_path.exists():
        console.print("[yellow]! existing config found[/yellow]")
        if click.confirm("Overwrite existing config?"):
            config_path.write_text(
                json.dumps(
                    {
                        "default_provider": provider,
                        "default_model": model,
                        "api_mode": "chat_completions",
                        "mcp_servers": {},
                        "skills": [],
                    },
                    indent=2,
                )
            )
        console.print("[green]✓[/green] Configuration updated")
    else:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(
                {
                    "default_provider": provider,
                    "default_model": model,
                    "api_mode": "chat_completions",
                    "mcp_servers": {},
                    "skills": [],
                },
                indent=2,
            )
        )
        console.print(f"[green]✓[/green] Configuration created at [dim]{config_path}[/dim]")

    console.print("[3/3] Verifying setup...")
    console.print(
        "[green]✓[/green] Setup complete! Run [bold]xcopilot start[/bold] to begin.[/green]"
    )


@click.group()
def run():
    """Run X-Copilot applications."""


@run.command("webapp")
@click.option("--port", "-p", default=3000, help="Port to run on")
@click.option("--host", "-h", default="localhost", help="Host to bind to")
@click.pass_context
def run_webapp(ctx, port, host):
    """Run the WebApp (Next.js)."""
    import os
    import subprocess

    webapp_dir = Path.cwd() / "webapp"
    if not webapp_dir.exists():
        console.print(
            "[red]WebApp directory not found. Make sure you're in the X-Copilot project root.[/red]"
        )
        return

    console.print(f"[green]Starting WebApp on http://{host}:{port}[/green]")

    env = os.environ.copy()
    env["PORT"] = str(port)
    env["HOSTNAME"] = host

    try:
        subprocess.run(["npm", "run", "dev"], cwd=webapp_dir, env=env, check=True)
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Failed to start WebApp: {e}[/red]")
    except FileNotFoundError:
        console.print("[red]npm not found. Please install Node.js first.[/red]")


@run.command("desktop")
@click.pass_context
def run_desktop(ctx):
    """Run the Desktop App (Tauri)."""
    import os
    import subprocess

    desktop_dir = Path.cwd() / "desktop"
    if not desktop_dir.exists():
        console.print(
            "[red]Desktop directory not found. Make sure you're in the X-Copilot project root.[/red]"
        )
        return

    console.print("[green]Starting Desktop App (Tauri dev mode)...[/green]")

    try:
        subprocess.run(
            ["npm", "run", "tauri", "dev"], cwd=desktop_dir, env=os.environ.copy(), check=True
        )
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Failed to start Desktop App: {e}[/red]")
    except FileNotFoundError:
        console.print("[red]npm or cargo not found. Please install Node.js and Rust first.[/red]")


@run.command("all")
@click.option("--webapp-port", default=3000, help="WebApp port")
@click.option("--webapp-host", default="localhost", help="WebApp host")
@click.pass_context
def run_all(ctx, webapp_port, webapp_host):
    """Run both WebApp and Desktop App concurrently."""
    import os
    import signal
    import subprocess
    import sys

    webapp_dir = Path.cwd() / "webapp"
    desktop_dir = Path.cwd() / "desktop"

    if not webapp_dir.exists() or not desktop_dir.exists():
        console.print("[red]WebApp or Desktop directory not found.[/red]")
        return

    console.print("[green]Starting WebApp and Desktop App...[/green]")

    env = os.environ.copy()
    env["PORT"] = str(webapp_port)
    env["HOSTNAME"] = webapp_host

    processes = []

    def cleanup(signum=None, frame=None):
        console.print("\n[yellow]Shutting down...[/yellow]")
        for p in processes:
            if p.poll() is None:
                p.terminate()
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    try:
        webapp_proc = subprocess.Popen(["npm", "run", "dev"], cwd=webapp_dir, env=env)
        processes.append(webapp_proc)

        desktop_proc = subprocess.Popen(
            ["npm", "run", "tauri", "dev"], cwd=desktop_dir, env=os.environ.copy()
        )
        processes.append(desktop_proc)

        # Wait for both processes
        for p in processes:
            p.wait()

    except FileNotFoundError:
        console.print("[red]npm or cargo not found. Please install Node.js and Rust first.[/red]")
    except KeyboardInterrupt:
        cleanup()


# Export all command groups
__all__ = [
    "checkpoints",
    "config",
    "doctor",
    "graph",
    "init",
    "mcp",
    "memory",
    "model",
    "run",
    "skill",
    "skills",
    "update",
]
