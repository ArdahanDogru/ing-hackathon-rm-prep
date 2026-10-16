"""Reset (approved by the user 2026-10-17; docs/web-ui.md W27; lead-owned).

"Sıfırla" puts every client back to the first state: approvals, rejections and
notes, holdings, meeting-text edits and approved texts, cards, the agent's
latest decisions and the research marks. The records are MOVED to
data/reset-archive/<YYYYMMDD-HHMMSS>/ (never deleted), the memory is cleared.
What stays: the data (snapshots, caches of rates and document links), the LLM
caches (briefs, text drafts, research results, the agent's content cache, so a
re-run costs nothing), the RM action log (it gets one "reset" record) and the
browser settings.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from rmprep.contracts import TR_TZ


class ResetBusy(RuntimeError):
    """The agent is running: the reset waits for the RM to try again."""


def move_files(src: Path, dest: Path, keep: Callable[[Path], bool]) -> int:
    """Moves the files of `src` (not recursive) for which keep(path) is true into
    `dest`; returns their number. A missing folder moves nothing."""
    if not src.is_dir():
        return 0
    n = 0
    for p in sorted(src.iterdir()):
        if p.is_file() and keep(p):
            dest.mkdir(parents=True, exist_ok=True)
            shutil.move(str(p), str(dest / p.name))
            n += 1
    return n


def make_reset(root: Path | str, backend, agent=None, research=None, *,
               now: Callable[[], datetime] = lambda: datetime.now(TR_TZ)
               ) -> Callable[[], dict]:
    """The reset function of the API (POST /api/reset). Each part is optional: a
    backend, agent or research without the reset method is skipped."""
    root = Path(root)

    def reset() -> dict:
        if agent is not None and callable(getattr(agent, "running", None)) and agent.running():
            raise ResetBusy("Ajan çalışıyor; bitince sıfırlayın.")
        stamp = now().astimezone(TR_TZ).strftime("%Y%m%d-%H%M%S")
        archive = root / "data" / "reset-archive" / stamp
        counts: dict[str, int] = {}
        if callable(getattr(backend, "reset_state", None)):
            counts.update(backend.reset_state(archive))
        if agent is not None and callable(getattr(agent, "reset_state", None)):
            counts["agent"] = agent.reset_state(archive / "agent")
        if research is not None and callable(getattr(research, "archive_marks", None)):
            counts["research_marks"] = research.archive_marks(archive / "research-marks")
        return {"archive": archive.relative_to(root).as_posix(), "moved": counts}

    return reset
