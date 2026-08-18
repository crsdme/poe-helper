from __future__ import annotations

import re
from collections import Counter

from app.craft_log import CraftSession, list_sessions
from app.i18n import t
from app.item_icons import action_icon

USE_RE = re.compile(r"\bUSE\s+([a-z0-9_]+)\b", re.I)
SPENT_RE = re.compile(r"\bSPENT\b(.*)$", re.I)
PAIR_RE = re.compile(r"([a-z0-9_]+)=(\d+)", re.I)
CRAFT_DONE_RE = re.compile(r"\bCRAFT done\b")
CRAFT_MARK_RE = re.compile(r"\bCRAFT (?:done|skip)\b")
CHAIN_ITEM_RE = re.compile(r"\bCHAIN item\b")
CHAIN_SKIP_RE = re.compile(r"\bCHAIN skip\b")
HIT_RE = re.compile(r"\bHIT\b(?:\s+(.*))?$")
CHECK_HIT_RE = re.compile(r"\bCHECK\s+(?:found|has)\s+(.+?)\s+·", re.I)


def _head(raw: str) -> str:
    return raw.split("\n", 1)[0]


def _parse_spent(head: str) -> Counter[str] | None:
    match = SPENT_RE.search(head)
    if not match:
        return None
    values = Counter()
    for name, count in PAIR_RE.findall(match.group(1)):
        values[name.lower()] = int(count)
    return values


def _split_mods(text: str) -> list[str]:
    blob = (text or "").strip()
    if not blob:
        return []
    if " | " in blob:
        parts = blob.split(" | ")
    else:
        parts = blob.split(", ")
    return [part.strip() for part in parts if part.strip()]


def _legacy_chain_crafts(heads: list[str], starts: list[int], status: str) -> int:
    crafts = 0
    last = len(starts) - 1
    for index, start in enumerate(starts):
        end = starts[index + 1] if index < last else len(heads)
        segment = heads[start:end]
        finished = index < last or status == "done"
        if not finished:
            continue
        if any(CHAIN_SKIP_RE.search(line) for line in segment):
            continue
        if any(USE_RE.search(line) for line in segment):
            crafts += 1
    return crafts


def _session_spend(session: CraftSession) -> tuple[int, Counter[str], Counter[str], int]:
    spent: Counter[str] = Counter()
    hits: Counter[str] = Counter()
    snapshot: Counter[str] | None = None
    done = 0
    marked = False
    chain_starts: list[int] = []
    pending: list[str] = []
    hit_events = 0
    heads = [_head(raw) for raw in session.lines]
    for index, head in enumerate(heads):
        parsed = _parse_spent(head)
        if parsed is not None:
            snapshot = parsed
            continue
        check = CHECK_HIT_RE.search(head)
        if check:
            pending = _split_mods(check.group(1))
        hit = HIT_RE.search(head)
        if hit:
            names = _split_mods(hit.group(1) or "") or pending
            if names:
                hit_events += 1
                for name in names:
                    hits[name] += 1
            pending = []
            continue
        if CRAFT_MARK_RE.search(head):
            marked = True
            if CRAFT_DONE_RE.search(head):
                done += 1
            continue
        if CHAIN_ITEM_RE.search(head):
            chain_starts.append(index)
            pending = []
        match = USE_RE.search(head)
        if match:
            spent[match.group(1).lower()] += 1
    if snapshot is not None:
        spent = snapshot
    if marked:
        return done, spent, hits, hit_events
    if chain_starts:
        return _legacy_chain_crafts(heads, chain_starts, session.status), spent, hits, hit_events
    crafts = 1 if session.status == "done" and spent else 0
    return crafts, spent, hits, hit_events


def _fmt_avg(total: int, crafts: int) -> str | None:
    if crafts <= 0 or total <= 0:
        return None
    value = total / crafts
    if value >= 10:
        return str(int(round(value)))
    if value >= 1:
        text = f"{value:.1f}"
        return text[:-2] if text.endswith(".0") else text
    if value < 0.01:
        return "<0.01"
    return f"{value:.2f}"


def _fmt_pct(count: int, total: int) -> str | None:
    if total <= 0 or count <= 0:
        return None
    value = 100.0 * count / total
    if value >= 10:
        return str(int(round(value)))
    text = f"{value:.1f}"
    return text[:-2] if text.endswith(".0") else text


def _currency_rows(spent: Counter[str], crafts: int) -> list[dict]:
    rows = []
    for action_id, total in spent.most_common():
        rows.append(
            {
                "id": action_id,
                "name": t(f"action.{action_id}", default=action_id),
                "icon": action_icon(action_id),
                "total": total,
                "avg": _fmt_avg(total, crafts),
            }
        )
    return rows


def _mod_rows(hits: Counter[str], events: int) -> list[dict]:
    rows = []
    for name, count in hits.most_common():
        rows.append(
            {
                "name": name,
                "total": count,
                "pct": _fmt_pct(count, events),
            }
        )
    return rows


def stats_payload() -> dict:
    groups: dict[str, dict] = {}
    order: list[str] = []
    all_spent: Counter[str] = Counter()
    all_hits: Counter[str] = Counter()
    all_crafts = 0
    all_hit_events = 0
    sessions_used = 0
    for session in list_sessions():
        crafts, spent, hits, hit_events = _session_spend(session)
        if not spent and crafts <= 0 and not hits:
            continue
        sessions_used += 1
        all_crafts += crafts
        all_hit_events += hit_events
        all_spent.update(spent)
        all_hits.update(hits)
        key = session.name.strip() or session.scenario_id or "—"
        if key not in groups:
            groups[key] = {
                "id": key,
                "name": session.name.strip() or t("stats.unnamed"),
                "crafts": 0,
                "sessions": 0,
                "hit_events": 0,
                "spent": Counter(),
                "hits": Counter(),
            }
            order.append(key)
        row = groups[key]
        row["crafts"] += crafts
        row["sessions"] += 1
        row["hit_events"] += hit_events
        row["spent"].update(spent)
        row["hits"].update(hits)
    scenarios = []
    for key in order:
        row = groups[key]
        scenarios.append(
            {
                "id": row["id"],
                "name": row["name"],
                "crafts": row["crafts"],
                "sessions": row["sessions"],
                "currencies": _currency_rows(row["spent"], row["crafts"]),
                "mods": _mod_rows(row["hits"], row["hit_events"]),
            }
        )
    return {
        "crafts": all_crafts,
        "sessions": sessions_used,
        "currencies": _currency_rows(all_spent, all_crafts),
        "mods": _mod_rows(all_hits, all_hit_events),
        "scenarios": scenarios,
    }
