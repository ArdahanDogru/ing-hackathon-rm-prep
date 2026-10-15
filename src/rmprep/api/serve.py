"""`python -m rmprep serve`: the API and the built web app on one local address
(docs/web-ui.md section 1)."""

from __future__ import annotations

import sys
from pathlib import Path

DEFAULT_PORT = 8600


def build_app(root: Path, personas_dir: Path | None = None):
    from rmprep.api.app import create_app
    from rmprep.api.ingest_job import IngestControl
    from rmprep.api.views import ViewBuilder
    from rmprep.backend import RealBackend
    from rmprep.decision import load_config
    from rmprep.ingest.pipeline import Paths
    from rmprep.research.service import research_from_root

    backend = RealBackend(root, personas_dir=personas_dir)
    import yaml
    narrator_raw = yaml.safe_load((root / "config" / "narrator.yaml").read_text(encoding="utf-8")) or {}
    views = ViewBuilder(backend, load_config(root / "config" / "decision.yaml"),
                        market_series=narrator_raw.get("market_note", {}).get("series"))   # W15
    dist = root / "web" / "dist"
    if not (dist / "index.html").is_file():
        print(f"web/dist missing: run `npm ci; npm run build` in {root / 'web'} (API only for now)",
              file=sys.stderr)
        dist = None
    # web research (docs/research.md); a root without its config has no research routes
    research = research_from_root(root) if (Path(root) / "config" / "research.yaml").is_file() else None
    # agentic top 3 (docs/agent.md); a root without its config has no agent (the route answers "off")
    agent = None
    if (Path(root) / "config" / "agent.yaml").is_file():
        from rmprep.agent.service import agent_from_root
        agent = agent_from_root(root, research)
    # L1: every decision and edit of the RM (spec 2026-10-15-rm-action-log-design)
    from rmprep.api.action_log import ActionLog
    action_log = ActionLog(Path(root) / "data" / "logs" / "rm-actions")
    return create_app(backend, views=views, static_dir=dist,
                      ingest=IngestControl(Paths(Path(root).resolve())), research=research,
                      agent=agent, action_log=action_log)


def serve(root: Path, port: int = DEFAULT_PORT, personas_dir: Path | None = None) -> None:
    import uvicorn

    app = build_app(root, personas_dir)
    print(f"rmprep: http://127.0.0.1:{port}", file=sys.stderr)
    uvicorn.run(app, host="127.0.0.1", port=port)       # local only, no login
