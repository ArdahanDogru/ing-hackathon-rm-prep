"""Source files keep LF line endings (`.gitattributes` is `* -text`, so git does
not convert them; a CRLF rewrite shows as a full-file diff at merge)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_python_files_have_lf_line_endings():
    files = [p for d in ("src", "tests") for p in (ROOT / d).rglob("*.py")]
    bad = [str(p.relative_to(ROOT)) for p in files if b"\r" in p.read_bytes()]
    assert files
    assert bad == [], f"CRLF line endings in: {bad}"
