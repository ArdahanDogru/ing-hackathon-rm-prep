"""`python -m rmprep serve`: the API and the built web app on one local address
(docs/web-ui.md section 1)."""

from __future__ import annotations

import sys
from pathlib import Path

DEFAULT_PORT = 8600


def build_app(root: Path, personas_dir: Path | None = None):
    from rmprep.api.app import create_app
    from rmprep.backend import RealBackend

    backend = RealBackend(root, personas_dir=personas_dir)
    dist = root / "web" / "dist"
    if not (dist / "index.html").is_file():
        print(f"web/dist missing: run `npm ci; npm run build` in {root / 'web'} (API only for now)",
              file=sys.stderr)
        dist = None
    return create_app(backend, static_dir=dist)


def serve(root: Path, port: int = DEFAULT_PORT, personas_dir: Path | None = None) -> None:
    import uvicorn

    app = build_app(root, personas_dir)
    print(f"rmprep: http://127.0.0.1:{port}", file=sys.stderr)
    uvicorn.run(app, host="127.0.0.1", port=port)       # local only, no login
