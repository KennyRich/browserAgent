from pydantic_ai import RunContext

from browser_agent.models import AgentDeps


async def save_finding(
    ctx: RunContext[AgentDeps],
    key: str,
    content: str,
    source_url: str | None = None,
) -> str:
    """Save a named finding to memory for later recall across tasks.

    Args:
        key: A short descriptive key for this finding (e.g. "top_hn_stories", "bitcoin_price").
        content: The actual finding content to store.
        source_url: Optional URL where this finding was discovered.
    """
    try:
        await ctx.deps.memory.save_finding(key, content, source_url)
        return f"Saved finding '{key}' to memory."
    except Exception as e:
        return f"Failed to save finding: {e}"


async def recall_finding(ctx: RunContext[AgentDeps], key: str) -> str:
    """Recall a specific finding from memory by its key.

    Args:
        key: The key of the finding to recall.
    """
    try:
        content = await ctx.deps.memory.recall_finding(key)
        if content:
            return f"[{key}]: {content}"
        return f"No finding found with key '{key}'."
    except Exception as e:
        return f"Failed to recall finding: {e}"


async def search_memory(ctx: RunContext[AgentDeps], query: str) -> str:
    """Search all saved findings by keyword.

    Args:
        query: Search term to match against finding keys and content.
    """
    try:
        results = await ctx.deps.memory.search_findings(query)
        if not results:
            return f"No findings matching '{query}'."
        lines = []
        for r in results:
            preview = r["content"][:150]
            lines.append(f"  [{r['key']}]: {preview}")
        return "\n".join(lines)
    except Exception as e:
        return f"Failed to search memory: {e}"


async def list_memories(ctx: RunContext[AgentDeps]) -> str:
    """List all saved findings with their keys and short previews."""
    try:
        findings = await ctx.deps.memory.list_findings()
        if not findings:
            return "No findings saved yet."
        lines = []
        for f in findings:
            lines.append(f"  [{f['key']}]: {f['preview']}")
        return "\n".join(lines)
    except Exception as e:
        return f"Failed to list memories: {e}"


async def delete_finding(ctx: RunContext[AgentDeps], key: str) -> str:
    """Delete a finding from memory by its key.

    Args:
        key: The key of the finding to delete.
    """
    try:
        deleted = await ctx.deps.memory.delete_finding(key)
        if deleted:
            return f"Deleted finding '{key}'."
        return f"No finding found with key '{key}'."
    except Exception as e:
        return f"Failed to delete finding: {e}"
