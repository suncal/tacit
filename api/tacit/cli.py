"""    tacit serve         run the API + console
    tacit demo          seed a demo org, then serve
    tacit doctor        what's connected, which brain
    tacit seed          seed only
"""
from __future__ import annotations

import argparse
import os
import sys


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="tacit")
    ap.add_argument("cmd", nargs="?", default="serve", choices=["serve", "demo", "doctor", "seed"])
    ap.add_argument("--port", type=int)
    ap.add_argument("--host")
    ap.add_argument("--db")
    ap.add_argument("--brain")
    ap.add_argument("--reload", action="store_true")
    a = ap.parse_args(argv)
    if a.port:
        os.environ["TACIT_PORT"] = str(a.port)
    if a.host:
        os.environ["TACIT_HOST"] = a.host
    if a.db:
        os.environ["TACIT_DATABASE_URL"] = a.db if "://" in a.db else f"sqlite:///{a.db}"
    if a.brain:
        os.environ["TACIT_BRAIN_PROVIDER"] = a.brain
    if a.cmd == "demo" and not os.environ.get("TACIT_ORG_NAME"):
        os.environ["TACIT_ORG_NAME"] = "Northwind Labs"
    from .settings import get_settings
    s = get_settings()
    from .db import Base, engine
    from . import models  # noqa: F401  (register tables before create_all)
    Base.metadata.create_all(engine)
    from .app import TacitApp
    if a.cmd == "doctor":
        t = TacitApp(s)
        b = t.brain_info()
        print(f"tacit {__import__('tacit').__version__}\ndb:     {s.database_url}\nbrain:  {b['provider']} ({b['model']}){'' if b['llm'] else '  ← no LLM: deterministic local brain'}")
        for i in t.integrations():
            print(f"{i['name']:<12} {'connected' if i['connected'] else 'not set  '}  {i['detail'] if i['connected'] else '(' + i['how'] + ')'}")
        print(f"tools:  {len(t.registry.all())}")
        return 0
    t = TacitApp(s)
    if a.cmd in ("demo", "seed"):
        from .seed import seed
        r = seed(t)
        print("seed:", r)
        if a.cmd == "seed":
            return 0
    import uvicorn
    from .main import create_app
    app = create_app(t, background=True)
    print(f"Tacit is up → http://{s.host}:{s.port}   docs → /api/docs   brain={t.brain_info()['provider']}")
    if a.cmd == "demo":
        print("demo login → demo@northwind.dev / tacit-demo")
    uvicorn.run(app, host=s.host, port=s.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
