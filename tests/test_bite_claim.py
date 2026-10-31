# Guards: apostrophes in commit subjects stay as-is in the PR comment, while < > & are still escaped.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import recent


def test_comment_keeps_apostrophes(tmp_path):
    c = {"sha": "a" * 40, "subject": "Fix Bite's <b> & more", "undo": "unguarded"}
    text = recent.write_comment(tmp_path, [c]).read_text(encoding="utf-8")
    assert "Bite's &lt;b&gt; &amp; more" in text
