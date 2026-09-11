"""Transcript → notes + action items. Works with or without a model."""
import json
import re

PROMPT = """Turn this meeting transcript into (1) crisp markdown notes and (2) action items.
Return ONLY JSON: {"notes": "<markdown>", "action_items": [{"title": "...", "owner": "...", "due": "..."}]}

Transcript:
"""
ACTION_RX = re.compile(r"\b(will|should|needs? to|need to|todo|to-do|action|let'?s|going to|must|by (?:mon|tue|wed|thu|fri|next|tomorrow|end))\b", re.I)
SPEAKER_RX = re.compile(r"^\s*([A-Z][\w .'-]{0,30}?)\s*[:\-]\s*(.+)$")


def summarize(brain, transcript: str):
    if brain is not None and brain.is_llm:
        try:
            out = brain.complete("You write excellent meeting notes.", [{"role": "user", "content": PROMPT + transcript}], [])
            m = re.search(r"\{.*\}", out.text, flags=re.S)
            data = json.loads(m.group(0))
            return data.get("notes", ""), [_norm(i) for i in data.get("action_items", [])]
        except Exception:
            pass
    return _extractive(transcript)


def _norm(i):
    return {"title": str(i.get("title", "")).strip(), "owner": str(i.get("owner", "")).strip(), "due": str(i.get("due", "")).strip(), "accepted": False}


def _extractive(transcript: str):
    lines = [l.strip() for l in transcript.splitlines() if l.strip()]
    speakers, items, decisions = {}, [], []
    for l in lines:
        m = SPEAKER_RX.match(l)
        who, said = (m.group(1).strip(), m.group(2).strip()) if m else ("", l)
        if who:
            speakers[who] = speakers.get(who, 0) + 1
        if re.search(r"\b(decided|agreed|decision|we'?ll go with|final)\b", said, re.I):
            decisions.append(said)
        if ACTION_RX.search(said):
            owner = who
            om = re.search(r"\b([A-Z][a-z]+)\s+(?:will|should|needs? to|is going to)\b", said)
            if om:
                owner = om.group(1)
            dm = re.search(r"\b(by\s+(?:monday|tuesday|wednesday|thursday|friday|tomorrow|next week|end of (?:day|week)|eod|eow)|tomorrow|next week)\b", said, re.I)
            items.append({"title": said.rstrip(".")[:140], "owner": owner, "due": dm.group(1) if dm else "", "accepted": False})
    notes = f"## Summary\n{len(lines)} lines, {len(speakers)} speakers" + (f": {', '.join(speakers)}" if speakers else "") + ".\n\n"
    if decisions:
        notes += "## Decisions\n" + "\n".join(f"- {d}" for d in decisions) + "\n\n"
    notes += "## Action items\n" + ("\n".join(f"- **{i['owner'] or 'unassigned'}** — {i['title']}" + (f" ({i['due']})" if i["due"] else "") for i in items) or "- none detected")
    return notes, items[:25]
