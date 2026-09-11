"""HTTP surface: setup → login → keys → events → playbooks → approvals → undo → export."""


def test_first_run_setup_and_auth(client):
    assert client.get("/api/v1/auth/status").json()["needs_setup"] is True
    r = client.post("/api/v1/auth/setup", json={"email": "a@b.co", "name": "A", "password": "correct-horse"})
    assert r.status_code == 200 and r.json()["role"] == "admin"
    assert client.get("/api/v1/auth/me").json()["email"] == "a@b.co"
    client.cookies.clear()
    assert client.get("/api/v1/overview").status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "a@b.co", "password": "wrong"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "a@b.co", "password": "correct-horse"}).status_code == 200
    key = client.post("/api/v1/auth/keys", json={"name": "ci"}).json()["key"]
    client.cookies.clear()
    assert client.get("/api/v1/overview", headers={"Authorization": f"Bearer {key}"}).status_code == 200
    assert client.get("/api/v1/overview", headers={"Authorization": "Bearer tk_nope"}).status_code == 401
    client.post("/api/v1/auth/login", json={"email": "a@b.co", "password": "correct-horse"})


def test_events_to_playbooks_to_action(client):
    client.post("/api/v1/auth/setup", json={"email": "a@b.co", "name": "A", "password": "correct-horse"})
    from tacit.seed import _events
    evs = _events()
    r = client.post("/api/v1/events/batch", json=evs[:200])
    assert r.status_code == 201 and r.json()["ingested"] == 200
    r = client.post("/api/v1/events/batch", json=evs[:200])
    assert r.json()["duplicates"] == 200                             # idempotent on external_id
    client.post("/api/v1/events/batch", json=evs[200:])
    m = client.post("/api/v1/playbooks/mine").json()
    assert m["created"] >= 4
    pbs = client.get("/api/v1/playbooks").json()["playbooks"]
    inv = next(p for p in pbs if "invoice" in p["name"])
    assert inv["stage"] == "candidate" and inv["recommendation"]["to"] == "shadow"
    r = client.post(f"/api/v1/playbooks/{inv['id']}/stage", json={"stage": "auto"})
    assert r.status_code == 422                                          # can't skip the ladder without trust
    assert client.post(f"/api/v1/playbooks/{inv['id']}/stage", json={"stage": "shadow"}).json()["stage"] == "shadow"
    bt = client.post("/api/v1/playbooks/backtest", json={"playbook_ids": [inv["id"]]}).json()
    assert bt["total"]["n"] > 5
    detail = client.get(f"/api/v1/playbooks/{inv['id']}").json()
    assert detail["trust"]["scored"] == bt["total"]["n"] and len(detail["drafts"]) > 0
    # propose → a live trigger creates an approval with a preview
    client.post(f"/api/v1/playbooks/{inv['id']}/stage", json={"stage": "propose"})
    client.post("/api/v1/events", json={"system": "slack", "kind": "message", "actor": "jonas", "text": "where's the invoice for Acme?", "target": "#billing", "thread_key": "slack:C_BILLING:api1", "meta": {"channel": "#billing"}})
    ap = client.get("/api/v1/approvals").json()["approvals"]
    assert len(ap) == 1 and ap[0]["playbook"]["name"] == inv["name"] and ap[0]["preview"]["text"]
    run = client.post(f"/api/v1/approvals/{ap[0]['id']}/decide", json={"approve": True}).json()["run"]
    assert run["status"] == "done" and run["actions"][0]["undo"]
    u = client.post(f"/api/v1/runs/{run['id']}/undo").json()
    assert u["tx_status"] == "undone"
    ov = client.get("/api/v1/overview").json()
    assert ov["counts"]["playbooks"]["propose"] == 1
    ex = client.get("/api/v1/export").json()
    assert set(ex) >= {"events", "playbooks", "drafts", "runs", "actions", "audit"}
    assert client.get("/api/v1/audit/export").headers["content-type"].startswith("application/x-ndjson")


def test_webhook_and_meeting(client):
    client.post("/api/v1/auth/setup", json={"email": "a@b.co", "name": "A", "password": "correct-horse"})
    r = client.post("/api/v1/webhooks/deploy", json={"version": "1.2.3"})
    assert r.json()["event"] == "webhook:deploy"
    m = client.post("/api/v1/meetings", json={"title": "t", "transcript": "Sam: Sam will ship the fix by Friday.\nMaya: Decision: we go with 20%."}).json()
    assert "Decisions" in m["notes"] and m["action_items"][0]["owner"] == "Sam"
    acc = client.post(f"/api/v1/meetings/{m['id']}/accept", json={"index": 0}).json()
    assert len(acc["created"]) == 1
    assert len(client.get("/api/v1/tasks?status=open").json()["tasks"]) == 1
    assert client.get("/api/docs").status_code == 200
