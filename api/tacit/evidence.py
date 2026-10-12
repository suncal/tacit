"""Turn a backfill report into a human-readable evidence page (used for the TSM pitch): what was mined from a real
repo, what the judge would have let through, and what it caught. Pure read of the JSON + draft score details."""
from __future__ import annotations

import json
import sqlite3
import sys


def render(report_path: str, db_path: str) -> str:
    r = json.load(open(report_path))
    c = sqlite3.connect(db_path)
    ev = {i: (n, a) for i, n, a in c.execute("select id, evidence_count, actor from playbooks")}
    humans = c.execute("select count(distinct actor) from events where actor_type='human'").fetchone()[0]
    threads = c.execute("select count(distinct thread_key) from events").fetchone()[0]
    bt = r["backtest"]
    out = [f"# Evidence: {r['repo']} (public issue tracker, history since {r['since'][:10]})", "",
           f"Generated {r['generated_at']} by `tacit backfill-github`. Brain: {r['brain']['provider']} ({r['brain']['model']}); judge: separate model.", "",
           "| | |", "|---|---|",
           f"| Events ingested | {r['mine']['events']} (bots excluded) |",
           f"| Threads | {threads} |", f"| Humans observed | {humans} |",
           f"| Playbooks mined | {r['mine']['found']} |",
           f"| Backtested | {len(bt['playbooks'])} playbooks with ≥7 examples, {bt['total']['n']} real triggers |",
           f"| Would have handled (judge ≥ 0.5) | {bt['total']['hits']} / {bt['total']['n']} = {bt['total']['hit_rate']:.0%} |", "",
           "## Per job", "", "| Job | Owner | Examples | Handled | Mean judge score |", "|---|---|---|---|---|"]
    for p in sorted(bt["playbooks"], key=lambda p: -p["hit_rate"]):
        n, a = ev.get(p["id"], ("?", "?"))
        out.append(f"| {p['name']} | {a} | {n} | {p['hits']}/{p['n']} ({p['hit_rate']:.0%}) | {p['mean_score']:.2f} |")
    out += ["", "## What the judge caught", "",
            "Lowest-scored drafts and the judge's reason. These are the drafts the trust ladder would never promote.", ""]
    rows = []
    for p in bt["playbooks"]:
        for row in p["rows"]:
            d = c.execute("select score_detail from drafts where id=?", (row["draft_id"],)).fetchone()
            why = (json.loads(d[0]).get("why") if d else "") or ""
            rows.append((row["score"], p["name"], why, row["draft"], row["actual"]))
    rows.sort(key=lambda x: x[0])
    for s, name, why, draft, actual in rows[:6]:
        out += [f"**{name}** — judge {s:.2f}: _{why.strip()}_", "", f"> draft: {draft[:220].strip()}", ">", f"> human: {actual[:220].strip()}", ""]
    out += ["## What it got right", ""]
    for s, name, why, draft, actual in [x for x in rows if x[0] >= 0.9][:4]:
        out += [f"**{name}** — judge {s:.2f}: _{why.strip()}_", "", f"> draft: {draft[:220].strip()}", ">", f"> human: {actual[:220].strip()}", ""]
    return "\n".join(out)


if __name__ == "__main__":
    print(render(sys.argv[1], sys.argv[2]))
