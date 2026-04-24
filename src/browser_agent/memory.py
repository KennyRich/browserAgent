import uuid
from datetime import datetime, timezone

import aiosqlite


class MemoryStore:
    def __init__(self, db_path: str = "memory.db") -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None
        self._session_id = uuid.uuid4().hex[:12]

    async def initialize(self) -> None:
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS findings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                content TEXT NOT NULL,
                source_url TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                task TEXT NOT NULL,
                answer TEXT NOT NULL,
                step_count INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                summary TEXT NOT NULL,
                entries_summarized INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
        """)

    async def save_finding(
        self, key: str, content: str, source_url: str | None = None
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            "INSERT OR REPLACE INTO findings (key, content, source_url, created_at) VALUES (?, ?, ?, ?)",
            (key, content, source_url, now),
        )
        await self._db.commit()

    async def recall_finding(self, key: str) -> str | None:
        cursor = await self._db.execute(
            "SELECT content FROM findings WHERE key = ?", (key,)
        )
        row = await cursor.fetchone()
        return row[0] if row else None

    async def search_findings(self, query: str) -> list[dict]:
        cursor = await self._db.execute(
            "SELECT key, content, source_url FROM findings WHERE key LIKE ? OR content LIKE ?",
            (f"%{query}%", f"%{query}%"),
        )
        rows = await cursor.fetchall()
        return [
            {"key": row[0], "content": row[1], "source_url": row[2]}
            for row in rows
        ]

    async def list_findings(self) -> list[dict]:
        cursor = await self._db.execute(
            "SELECT key, content, source_url FROM findings ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        return [
            {"key": row[0], "preview": row[1][:100], "source_url": row[2]}
            for row in rows
        ]

    async def delete_finding(self, key: str) -> bool:
        cursor = await self._db.execute(
            "DELETE FROM findings WHERE key = ?", (key,)
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def add_conversation(self, task: str, answer: str, steps: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            "INSERT INTO conversations (session_id, task, answer, step_count, created_at) VALUES (?, ?, ?, ?, ?)",
            (self._session_id, task, answer, steps, now),
        )
        await self._db.commit()

    async def format_context(self) -> str:
        latest_summary = await self._get_latest_summary()
        entries_after = await self._get_conversations_after_summary()

        parts = []
        if latest_summary:
            parts.append(f"Summary of earlier conversation:\n{latest_summary}")

        for i, entry in enumerate(entries_after, 1):
            parts.append(f"  [{i}] Task: \"{entry['task']}\" -> Answer: \"{entry['answer']}\"")

        return "\n".join(parts) if parts else ""

    async def total_length(self) -> int:
        context = await self.format_context()
        return len(context)

    async def summarize(self, model) -> None:
        from pydantic_ai import Agent

        context = await self.format_context()
        if not context:
            return

        summarizer = Agent(
            model,
            system_prompt="Summarize this conversation history into a concise paragraph preserving all key facts, findings, and answers. Be specific — include names, numbers, URLs, and conclusions.",
        )
        result = await summarizer.run(context)

        entry_count = await self._count_session_conversations()
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            "INSERT INTO summaries (session_id, summary, entries_summarized, created_at) VALUES (?, ?, ?, ?)",
            (self._session_id, result.output, entry_count, now),
        )
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    async def _get_latest_summary(self) -> str | None:
        cursor = await self._db.execute(
            "SELECT summary FROM summaries WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
            (self._session_id,),
        )
        row = await cursor.fetchone()
        return row[0] if row else None

    async def _get_conversations_after_summary(self) -> list[dict]:
        cursor = await self._db.execute(
            "SELECT created_at FROM summaries WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
            (self._session_id,),
        )
        row = await cursor.fetchone()
        last_summary_time = row[0] if row else "1970-01-01"

        cursor = await self._db.execute(
            "SELECT task, answer, step_count FROM conversations WHERE session_id = ? AND created_at > ? ORDER BY created_at",
            (self._session_id, last_summary_time),
        )
        rows = await cursor.fetchall()
        return [
            {"task": row[0], "answer": row[1], "step_count": row[2]}
            for row in rows
        ]

    async def _count_session_conversations(self) -> int:
        cursor = await self._db.execute(
            "SELECT COUNT(*) FROM conversations WHERE session_id = ?",
            (self._session_id,),
        )
        row = await cursor.fetchone()
        return row[0]
