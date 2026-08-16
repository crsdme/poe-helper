from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from app.paths import LOGS_DIR, ensure_data_dirs
_lock = threading.Lock()
_current_id: str | None = None


@dataclass
class CraftSession:
    id: str
    name: str
    scenario_id: str
    started_at: str
    status: str = "running"
    lines: list[str] = field(default_factory=list)

    def when(self) -> str:
        try:
            return datetime.fromisoformat(self.started_at).strftime("%d.%m %H:%M")
        except ValueError:
            return self.started_at

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "scenario_id": self.scenario_id,
            "started_at": self.started_at,
            "status": self.status,
            "lines": self.lines,
        }

    @classmethod
    def from_dict(cls, data: dict) -> CraftSession:
        return cls(
            id=str(data.get("id") or uuid4().hex),
            name=str(data.get("name") or ""),
            scenario_id=str(data.get("scenario_id") or ""),
            started_at=str(data.get("started_at") or ""),
            status=str(data.get("status") or "stopped"),
            lines=[str(line) for line in data.get("lines") or []],
        )


def _path(session_id: str) -> Path:
    return LOGS_DIR / f"{session_id}.json"


def _write(session: CraftSession) -> None:
    ensure_data_dirs()
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    _path(session.id).write_text(
        json.dumps(session.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _read(session_id: str) -> CraftSession | None:
    path = _path(session_id)
    if not path.is_file():
        return None
    try:
        return CraftSession.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, TypeError):
        return None


def begin_session(name: str, scenario_id: str = "") -> str | None:
    from app.config import load_config

    if not load_config().logs_enabled:
        return None
    session = CraftSession(
        id=uuid4().hex,
        name=name,
        scenario_id=scenario_id,
        started_at=datetime.now().isoformat(timespec="seconds"),
        status="running",
        lines=[],
    )
    global _current_id
    with _lock:
        _write(session)
        _current_id = session.id
    return session.id


def _stamp_block(text: str) -> str:
    stamp = datetime.now().strftime("%H:%M:%S")
    parts = text.split("\n")
    entry = f"{stamp}  {parts[0]}"
    if len(parts) == 1:
        return entry
    pad = " " * (len(stamp) + 2)
    rest = "\n".join(pad + line if line else line for line in parts[1:])
    return f"{entry}\n{rest}"


def append_session(line: str) -> None:
    text = (line or "").rstrip()
    if not text:
        return
    from app.config import load_config

    if not load_config().logs_enabled:
        return
    entry = _stamp_block(text)
    global _current_id
    with _lock:
        session_id = _current_id
        if not session_id:
            return
        session = _read(session_id)
        if session is None:
            return
        session.lines.append(entry)
        _write(session)


def finish_session(status: str) -> None:
    global _current_id
    with _lock:
        session_id = _current_id
        if not session_id:
            return
        session = _read(session_id)
        if session is None:
            return
        session.status = status or "stopped"
        _write(session)
        _current_id = None


def list_sessions() -> list[CraftSession]:
    if not LOGS_DIR.is_dir():
        return []
    sessions: list[CraftSession] = []
    with _lock:
        for path in LOGS_DIR.glob("*.json"):
            try:
                sessions.append(CraftSession.from_dict(json.loads(path.read_text(encoding="utf-8"))))
            except (OSError, json.JSONDecodeError, TypeError):
                continue
    sessions.sort(key=lambda row: row.started_at, reverse=True)
    return sessions


def load_session(session_id: str) -> CraftSession | None:
    with _lock:
        return _read(session_id)


def delete_session(session_id: str) -> None:
    global _current_id
    with _lock:
        path = _path(session_id)
        if path.is_file():
            try:
                path.unlink()
            except OSError:
                pass
        if _current_id == session_id:
            _current_id = None


def session_matches(session: CraftSession, query: str) -> bool:
    from app.i18n import t

    needle = (query or "").strip().lower()
    if not needle:
        return True
    if needle in (session.name or "").lower():
        return True
    if needle in (session.status or "").lower():
        return True
    status_label = t(f"logs.status_{session.status}", default=session.status)
    if needle in status_label.lower():
        return True
    if needle in session.when().lower():
        return True
    return any(needle in line.lower() for line in session.lines)


def grouped_sessions(query: str = "") -> list[tuple[str, list[CraftSession]]]:
    groups: dict[str, list[CraftSession]] = {}
    order: list[str] = []
    for session in list_sessions():
        if not session_matches(session, query):
            continue
        key = session.name.strip() or "—"
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(session)
    return [(name, groups[name]) for name in order]


def matching_lines(session: CraftSession, query: str) -> list[str]:
    needle = (query or "").strip().lower()
    if not needle:
        return session.lines
    hits = [line for line in session.lines if needle in line.lower()]
    if hits:
        return hits
    if needle in (session.name or "").lower():
        return session.lines
    return hits
