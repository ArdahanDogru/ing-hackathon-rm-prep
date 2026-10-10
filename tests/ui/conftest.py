from pathlib import Path

import pytest

from rmprep.ui.fake import FakeBackend

CONTRACT_FIX = Path(__file__).resolve().parents[1] / "contracts" / "fixtures"
APP = Path(__file__).resolve().parents[2] / "src" / "rmprep" / "ui" / "app.py"
PERSONA_IDS = ["P01", "P02", "P03", "P04", "P05"]
SNAPSHOT = "20261010-001233-6b20"


@pytest.fixture
def fake() -> FakeBackend:
    return FakeBackend(CONTRACT_FIX)


def app_test(backend=None):
    """An AppTest of the page with a FakeBackend (or the given backend) put in."""
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(APP), default_timeout=30)
    at.session_state["backend"] = backend or FakeBackend(CONTRACT_FIX)
    return at


def run(at):
    """Run the script once more and fail on any exception in the page."""
    at.run()
    assert not at.exception, at.exception
    return at
