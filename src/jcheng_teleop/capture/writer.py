"""Non-blocking append-only capture writer.

`record()` only appends to an in-memory queue: it never opens, writes or flushes
a file on the caller's thread, so the control loop and the stop path are never
waiting on storage. A background thread drains the queue; a failure marks the
writer `faulted` and is reported at seal time instead of propagating into the
tick loop. When the queue is full, ordinary rows are dropped first; priority
rows (stop intent, safety/fault events, gateway results) are dropped only if no
ordinary row remains.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import threading
from typing import Any

STREAMS = {
    "input": "input.jsonl",
    "action": "action.jsonl",
    "command": "command.jsonl",
    "observation": "observation.jsonl",
    "events": "events.jsonl",
}


class CapturePathError(ValueError):
    pass


def _assert_outside_git(path: Path) -> None:
    for parent in (path, *path.parents):
        if (parent / ".git").exists():
            raise CapturePathError(
                f"capture root must stay outside a git worktree: {path}"
            )
        if parent == parent.parent:
            break


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


class CaptureWriter:
    """Bounded-queue JSONL writer with a background drain thread."""

    def __init__(
        self,
        root: str | Path,
        capture_id: str,
        *,
        queue_limit: int = 4096,
        start_thread: bool = True,
        drain_delay_s: float = 0.0,
    ) -> None:
        if queue_limit <= 0:
            raise ValueError("queue_limit must be positive")
        self.root = Path(root).expanduser().resolve()
        self.capture_id = capture_id
        _assert_outside_git(self.root)
        self.path = self.root / capture_id
        if self.path.exists():
            raise CapturePathError(f"capture already exists: {self.path}")
        try:
            self.path.mkdir(parents=True, exist_ok=False)
        except OSError as exc:
            raise CapturePathError(f"cannot create capture directory: {exc}") from exc

        self.queue_limit = queue_limit
        self.drain_delay_s = drain_delay_s
        self._normal: deque[tuple[str, dict[str, Any]]] = deque()
        self._priority: deque[tuple[str, dict[str, Any]]] = deque()
        self._condition = threading.Condition()
        self._closed = False
        self._fault: str | None = None
        self._internal_errors = 0
        self.accepted = {name: 0 for name in STREAMS}
        self.written = {name: 0 for name in STREAMS}
        self.dropped = {name: 0 for name in STREAMS}
        self.dropped_priority = 0
        self._handles: dict[str, Any] = {}
        for name in STREAMS:
            (self.path / STREAMS[name]).touch(exist_ok=False)
        self._thread = (
            threading.Thread(target=self._drain_loop, name="jcheng-capture-writer", daemon=True)
            if start_thread
            else None
        )
        if self._thread is not None:
            self._thread.start()

    @property
    def fault(self) -> str | None:
        return self._fault

    @property
    def faulted(self) -> bool:
        return self._fault is not None

    def record(self, stream: str, row: dict[str, Any], *, priority: bool = False) -> bool:
        """Queue one row. Never raises and never touches storage on this thread."""
        try:
            if stream not in STREAMS:
                self._internal_errors += 1
                return False
            with self._condition:
                if self._closed or self._fault is not None:
                    self.dropped[stream] += 1
                    return False
                size = len(self._normal) + len(self._priority)
                if size >= self.queue_limit:
                    dropped = self._drop_one_locked()
                    if not dropped:
                        self.dropped[stream] += 1
                        return False
                queue = self._priority if priority else self._normal
                queue.append((stream, row))
                self.accepted[stream] += 1
                self._condition.notify()
                return True
        except Exception:  # pragma: no cover - defensive; must never reach the loop
            self._internal_errors += 1
            return False

    def _drop_one_locked(self) -> bool:
        if self._normal:
            stream, _ = self._normal.popleft()
            self.dropped[stream] += 1
            return True
        if self._priority:
            stream, _ = self._priority.popleft()
            self.dropped[stream] += 1
            self.dropped_priority += 1
            return True
        return False

    def _open(self, stream: str):
        handle = self._handles.get(stream)
        if handle is None:
            handle = (self.path / STREAMS[stream]).open("a", encoding="utf-8")
            self._handles[stream] = handle
        return handle

    def _write_row(self, stream: str, row: dict[str, Any]) -> None:
        line = json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        self._open(stream).write(line + "\n")
        self.written[stream] += 1

    def flush(self) -> None:
        for handle in self._handles.values():
            handle.flush()

    def _drain_once(self) -> int:
        count = 0
        while True:
            with self._condition:
                if self._priority:
                    stream, row = self._priority.popleft()
                elif self._normal:
                    stream, row = self._normal.popleft()
                else:
                    return count
            self._write_row(stream, row)
            count += 1

    def _drain_loop(self) -> None:
        while True:
            with self._condition:
                while not self._closed and not self._priority and not self._normal:
                    self._condition.wait(timeout=0.5)
                if self._closed and not self._priority and not self._normal:
                    return
            try:
                self._drain_once()
                if self.drain_delay_s:
                    threading.Event().wait(self.drain_delay_s)
            except Exception as exc:  # storage error: fail closed for the capture
                with self._condition:
                    self._fault = f"{type(exc).__name__}: {exc}"
                    self._normal.clear()
                    self._priority.clear()
                    self._condition.notify_all()
                return

    def close(self, manifest: dict[str, Any] | None = None) -> dict[str, Any]:
        """Stop accepting rows, drain, hash the streams and optionally seal."""
        with self._condition:
            self._closed = True
            self._condition.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=10.0)
            if self._thread.is_alive():
                with self._condition:
                    self._fault = self._fault or "drain thread did not stop"
        self.flush()
        for handle in self._handles.values():
            handle.close()
        self._handles.clear()
        files = []
        for name in STREAMS:
            file_path = self.path / STREAMS[name]
            files.append(
                {
                    "path": STREAMS[name],
                    "bytes": file_path.stat().st_size,
                    "sha256": _sha256_file(file_path),
                    "stream": name,
                }
            )
        seal = {
            "capture_path": str(self.path),
            "files": files,
            "accepted": dict(self.accepted),
            "written": dict(self.written),
            "dropped": dict(self.dropped),
            "dropped_priority": self.dropped_priority,
            "fault": self._fault,
            "internal_errors": self._internal_errors,
        }
        if manifest is not None:
            manifest = dict(manifest)
            manifest.setdefault("capture", {})
            manifest["capture"]["files"] = files
            manifest["capture"]["rows"] = {
                name: {
                    "accepted": self.accepted[name],
                    "written": self.written[name],
                    "dropped": self.dropped[name],
                }
                for name in STREAMS
            }
            manifest["capture"]["dropped_priority"] = self.dropped_priority
            if self._fault is not None:
                flags = manifest["capture"].setdefault("quality_flags", [])
                if "recorder_fault" not in flags:
                    flags.append("recorder_fault")
                limitations = manifest["capture"].setdefault("limitations", [])
                limitations.append(f"recorder fault: {self._fault}")
            manifest_path = self.path / "manifest.json"
            manifest_path.write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            sums = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
            lines = []
            for name in sorted(STREAMS.values()):
                digest = _sha256_file(self.path / name).split(":", 1)[1]
                lines.append(f"{digest}  {name}")
            lines.append(f"{sums}  manifest.json")
            (self.path / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
            seal["manifest_sha256"] = "sha256:" + sums
        return seal


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
