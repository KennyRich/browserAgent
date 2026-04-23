"""Per-session structured logging: JSONL events + Markdown summary."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path


class SessionLogger:
    def __init__(self, logs_dir: str, session_id: str) -> None:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")
        self._session_id = session_id
        self._session_dir = Path(logs_dir) / f"{ts}_{session_id}"
        self._session_dir.mkdir(parents=True, exist_ok=True)
        self._events_path = self._session_dir / "events.jsonl"
        self._session_start = time.perf_counter()

    @property
    def session_dir(self) -> Path:
        return self._session_dir

    def log(self, event: str, step: int, data: dict, duration_ms: int | None = None) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": self._session_id,
            "step": step,
            "event": event,
            "data": data,
        }
        if duration_ms is not None:
            record["duration_ms"] = duration_ms
        with open(self._events_path, "a") as f:
            f.write(json.dumps(record) + "\n")

    def save_error_screenshot(self, step: int, image_bytes: bytes) -> str:
        screenshots_dir = self._session_dir / "screenshots"
        screenshots_dir.mkdir(exist_ok=True)
        path = screenshots_dir / f"step_{step:02d}_error.jpg"
        path.write_bytes(image_bytes)
        return str(path.relative_to(self._session_dir))

    def elapsed_ms(self) -> int:
        return int((time.perf_counter() - self._session_start) * 1000)

    def write_summary(self, task: str, answer: str) -> None:
        events = []
        if self._events_path.exists():
            for line in self._events_path.read_text().splitlines():
                if line.strip():
                    events.append(json.loads(line))

        start_evt = next((e for e in events if e["event"] == "session_start"), None)
        end_evt = next((e for e in events if e["event"] == "session_end"), None)

        provider = start_evt["data"].get("provider", "?") if start_evt else "?"
        model = start_evt["data"].get("model", "?") if start_evt else "?"
        vision = start_evt["data"].get("vision", False) if start_evt else False
        total_steps = end_evt["data"].get("total_steps", "?") if end_evt else "?"
        duration = end_evt["data"].get("duration_ms", 0) if end_evt else 0
        duration_s = duration / 1000

        lines = [
            f"# Session {self._session_id}",
            f"**Date:** {events[0]['timestamp'][:16] if events else '?'}",
            f"**Task:** {task}",
            f"**Provider:** {provider} / {model}",
            f"**Vision:** {'ON' if vision else 'OFF'}",
            f"**Result:** {total_steps} steps ({duration_s:.1f}s)",
            "",
        ]

        current_step = 0
        step_tools: list[str] = []
        step_planner = ""
        step_error = ""
        step_state = ""
        step_duration = 0

        def flush_step():
            if current_step == 0:
                return
            header = f"## Step {current_step}"
            if step_error:
                header += " - ERROR"
            if step_duration:
                header += f" ({step_duration / 1000:.1f}s)"
            lines.append(header)
            if step_planner:
                lines.append(f"**Planner:** {step_planner}")
            if step_tools:
                lines.append("**Tools:**")
                for t in step_tools:
                    lines.append(f"- {t}")
            if step_state:
                lines.append(f"**State:** {step_state}")
            if step_error:
                lines.append(f"**Error:** {step_error}")
            lines.append("")

        for evt in events:
            evt_step = evt.get("step", 0)
            evt_type = evt["event"]
            data = evt.get("data", {})
            dur = evt.get("duration_ms")

            if evt_type in ("session_start", "session_end"):
                continue

            if evt_step != current_step and evt_step > 0:
                flush_step()
                current_step = evt_step
                step_tools = []
                step_planner = ""
                step_error = ""
                step_state = ""
                step_duration = 0

            if evt_type == "planner_result":
                instr = data.get("instruction", "")
                step_planner = instr
                if dur:
                    step_planner += f" ({dur / 1000:.1f}s)"

            elif evt_type == "tool_call":
                name = data.get("tool_name", "?")
                args = data.get("args", "")
                args_str = str(args)[:80]
                step_tools.append(f"{name}({args_str})")

            elif evt_type == "tool_result":
                if step_tools:
                    result = data.get("result", "")[:60]
                    success = data.get("success", True)
                    status = "OK" if success else "FAILED"
                    dur_str = f" ({dur / 1000:.1f}s)" if dur else ""
                    step_tools[-1] += f" -> {status}: {result}{dur_str}"

            elif evt_type == "browser_state":
                url = data.get("url", "")
                title = data.get("title", "")
                step_state = f"{url} - {title}"

            elif evt_type == "step_result":
                step_duration = dur or 0
                if not data.get("success", True):
                    step_error = data.get("message", "Unknown error")[:200]

            elif evt_type == "error":
                step_error = data.get("message", "Unknown error")[:200]
                screenshot_path = data.get("screenshot_path")
                if screenshot_path:
                    step_error += f"\n**Screenshot:** {screenshot_path}"

        flush_step()

        lines.append(f"---\n**Final Answer:** {answer}")

        summary_path = self._session_dir / "summary.md"
        summary_path.write_text("\n".join(lines))
