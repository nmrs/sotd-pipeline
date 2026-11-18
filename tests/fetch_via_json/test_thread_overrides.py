"""Tests for YAML include/exclude handling in fetch_via_json search."""

from pathlib import Path
from unittest.mock import patch

from sotd.fetch_via_json.search import process_thread_overrides_json, search_threads_json


def test_process_thread_overrides_json_reads_include(tmp_path: Path, monkeypatch) -> None:
    import sotd.fetch.overrides as overrides_mod

    path = tmp_path / "thread_overrides.yaml"
    path.write_text("""
include:
  2025-06-25:
    - https://www.reddit.com/r/Wetshaving/comments/includeid/inc/
exclude:
  2025-06-25:
    - https://www.reddit.com/r/Wetshaving/comments/excludeid/exc/
""")
    monkeypatch.setattr(overrides_mod, "OVERRIDE_PATH", path)

    with patch(
        "sotd.fetch_via_json.search.fetch_thread_by_url",
        return_value={"id": "includeid", "title": "Wednesday SOTD 25 June"},
    ) as mock_fetch:
        result = process_thread_overrides_json("2025-06", cookies={}, session=object())

    assert len(result) == 1
    assert result[0]["id"] == "includeid"
    assert result[0]["_override_date"] == "2025-06-25"
    mock_fetch.assert_called_once()
    assert "excludeid" not in mock_fetch.call_args[0][0]


def test_search_threads_json_applies_excludes(monkeypatch) -> None:
    monkeypatch.setattr(
        "sotd.fetch_via_json.search.filter_valid_threads_json",
        lambda threads, year, month, debug=False: threads,
    )
    monkeypatch.setattr(
        "sotd.fetch_via_json.search.process_thread_overrides_json",
        lambda month, cookies=None, session=None, debug=False, override_path=None: [
            {"id": "1ttrafo", "title": "Joke"}
        ],
    )
    monkeypatch.setattr(
        "sotd.fetch_via_json.search.load_thread_exclude_ids",
        lambda month, path=None: {"1ttrafo"},
    )
    monkeypatch.setattr(
        "sotd.fetch_via_json.search.search_reddit_json",
        lambda *a, **k: [{"id": "keep", "title": "Monday SOTD Thread - Jun 01, 2025"}],
    )
    # Also need calendar missing-day path - search_threads_json is complex.
    # Stub the whole early search by patching calendar.monthrange and making
    # first search return results that skip missing-day logic.
    result = search_threads_json("wetshaving", 2025, 6, cookies={})
    ids = [t["id"] for t in result]
    assert "keep" in ids
    assert "1ttrafo" not in ids
