"""Unit tests for YAML thread include/exclude overrides."""

from pathlib import Path
from unittest.mock import Mock

from sotd.fetch.overrides import (
    apply_thread_excludes,
    extract_thread_id_from_url,
    load_thread_exclude_ids,
    load_thread_overrides_data,
)


def test_extract_thread_id_from_url() -> None:
    assert (
        extract_thread_id_from_url(
            "https://www.reddit.com/r/Wetshaving/comments/1lk3ooa/wednesday_sotd_25_june/"
        )
        == "1lk3ooa"
    )
    assert (
        extract_thread_id_from_url(
            "https://www.reddit.com/r/Wetshaving/comments/1ttrafo/comment/op4r7jq/"
        )
        == "1ttrafo"
    )
    assert extract_thread_id_from_url("/r/wetshaving/comments/abc123/") == "abc123"
    assert extract_thread_id_from_url("not-a-url") is None
    assert extract_thread_id_from_url("") is None


def test_load_thread_exclude_ids(tmp_path: Path) -> None:
    path = tmp_path / "thread_overrides.yaml"
    path.write_text("""
include: {}
exclude:
  2026-06-01:
    - https://www.reddit.com/r/Wetshaving/comments/1ttrafo/monday_lather_games/
  2026-06-02:
    - https://www.reddit.com/r/Wetshaving/comments/otherid/other/
  2026-07-01:
    - https://www.reddit.com/r/Wetshaving/comments/julyid/july/
""")
    assert load_thread_exclude_ids("2026-06", path) == {"1ttrafo", "otherid"}
    assert load_thread_exclude_ids("2026-07", path) == {"julyid"}
    assert load_thread_exclude_ids("2025-01", path) == set()


def test_load_thread_exclude_ids_skips_bad_urls(tmp_path: Path, caplog) -> None:
    path = tmp_path / "thread_overrides.yaml"
    path.write_text("""
exclude:
  2026-06-01:
    - not-a-reddit-url
    - https://www.reddit.com/r/Wetshaving/comments/goodid/title/
""")
    with caplog.at_level("WARNING"):
        ids = load_thread_exclude_ids("2026-06", path)
    assert ids == {"goodid"}
    assert "Could not extract thread id" in caplog.text


def test_load_thread_exclude_ids_missing_file(tmp_path: Path) -> None:
    assert load_thread_exclude_ids("2026-06", tmp_path / "missing.yaml") == set()


def test_load_thread_exclude_ids_missing_exclude_key(tmp_path: Path) -> None:
    path = tmp_path / "thread_overrides.yaml"
    path.write_text("""
include:
  2025-06-25:
    - https://www.reddit.com/r/Wetshaving/comments/1lk3ooa/wednesday/
""")
    assert load_thread_exclude_ids("2025-06", path) == set()


def test_apply_thread_excludes_praw_and_dict() -> None:
    keep = Mock(id="keep")
    drop = Mock(id="1ttrafo")
    assert [t.id for t in apply_thread_excludes([keep, drop], {"1ttrafo"})] == ["keep"]

    threads = [{"id": "keep"}, {"id": "1ttrafo"}, {"id": "t3_other"}]
    result = apply_thread_excludes(threads, {"1ttrafo", "t3_other"})
    assert result == [{"id": "keep"}]


def test_apply_thread_excludes_empty_set_noop() -> None:
    threads = [{"id": "a"}, {"id": "b"}]
    assert apply_thread_excludes(threads, set()) == threads


def test_warn_on_legacy_root_date_keys(tmp_path: Path, caplog) -> None:
    path = tmp_path / "thread_overrides.yaml"
    path.write_text("""
2025-06-25:
  - https://www.reddit.com/r/Wetshaving/comments/1lk3ooa/wednesday/
""")
    with caplog.at_level("WARNING"):
        data = load_thread_overrides_data(path)
    keys = {k.isoformat() if hasattr(k, "isoformat") else str(k) for k in data}
    assert "2025-06-25" in keys
    assert "Legacy thread override schema" in caplog.text


def test_include_loader_reads_include_section_only(tmp_path: Path, monkeypatch) -> None:
    import sotd.fetch.overrides as overrides_mod
    from sotd.fetch.reddit import load_thread_overrides

    path = tmp_path / "thread_overrides.yaml"
    path.write_text("""
include:
  2025-06-25:
    - https://www.reddit.com/r/Wetshaving/comments/includeid/inc/
exclude:
  2025-06-25:
    - https://www.reddit.com/r/Wetshaving/comments/excludeid/exc/
2025-06-26:
  - https://www.reddit.com/r/Wetshaving/comments/legacyid/leg/
""")
    monkeypatch.setattr(overrides_mod, "OVERRIDE_PATH", path)

    urls = load_thread_overrides("2025-06")
    assert urls == ["https://www.reddit.com/r/Wetshaving/comments/includeid/inc/"]
    assert "legacyid" not in "".join(urls)
    assert "excludeid" not in "".join(urls)


def _restore_overrides_module(monkeypatch, original_env, original_path):
    """Reload sotd.fetch.overrides with the ambient env restored.

    Tests that reload the module (to re-evaluate the import-time default
    path under a patched SOTD_DATA_DIR) must leave the module exactly as
    imported: same OVERRIDE_PATH the test process started with.
    """
    import importlib

    import sotd.fetch.overrides as overrides_mod

    if original_env is None:
        monkeypatch.delenv("SOTD_DATA_DIR", raising=False)
    else:
        monkeypatch.setenv("SOTD_DATA_DIR", original_env)
    importlib.reload(overrides_mod)
    assert overrides_mod.OVERRIDE_PATH == original_path


def test_default_override_path_uses_configured_data_dir(tmp_path: Path, monkeypatch) -> None:
    """#23 instance 1: default path follows SOTD_DATA_DIR, any CWD.

    Regression: OVERRIDE_PATH was a bare CWD-relative
    Path("data/thread_overrides.yaml"), so fetch run from any directory but
    the repo root — and with SOTD_DATA_DIR set — silently loaded no
    overrides at all.
    """
    import importlib
    import os

    import sotd.fetch.overrides as overrides_mod

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "thread_overrides.yaml").write_text("""
include:
  2025-06-25:
    - https://www.reddit.com/r/Wetshaving/comments/includeid/inc/
exclude:
  2026-06-01:
    - https://www.reddit.com/r/Wetshaving/comments/1ttrafo/monday_lather_games/
""")
    other_cwd = tmp_path / "elsewhere"
    other_cwd.mkdir()

    original_env = os.environ.get("SOTD_DATA_DIR")
    original_path = overrides_mod.OVERRIDE_PATH
    monkeypatch.setenv("SOTD_DATA_DIR", str(data_dir))
    monkeypatch.chdir(other_cwd)
    importlib.reload(overrides_mod)
    try:
        assert overrides_mod.OVERRIDE_PATH == data_dir / "thread_overrides.yaml"
        assert overrides_mod.OVERRIDE_PATH.is_absolute()
        # Default-path loads read the configured data dir, not ./data.
        assert overrides_mod.load_thread_exclude_ids("2026-06") == {"1ttrafo"}
        assert overrides_mod.load_thread_exclude_ids("2026-07") == set()
        data = overrides_mod.load_thread_overrides_data()
        assert overrides_mod.iter_month_urls(data.get("include"), "2025-06") == [
            ("2025-06-25", "https://www.reddit.com/r/Wetshaving/comments/includeid/inc/")
        ]
        # The PRAW loader re-imports OVERRIDE_PATH on each call, so it picks
        # the reloaded path up too.
        from sotd.fetch.reddit import load_thread_overrides

        assert load_thread_overrides("2025-06") == [
            "https://www.reddit.com/r/Wetshaving/comments/includeid/inc/"
        ]
    finally:
        _restore_overrides_module(monkeypatch, original_env, original_path)


def test_default_override_path_anchored_at_repo_root(tmp_path: Path, monkeypatch) -> None:
    """#23 instance 1: with no SOTD_DATA_DIR the default is repo data/, any CWD."""
    import importlib
    import os

    import sotd.fetch.overrides as overrides_mod

    other_cwd = tmp_path / "elsewhere"
    other_cwd.mkdir()

    original_env = os.environ.get("SOTD_DATA_DIR")
    original_path = overrides_mod.OVERRIDE_PATH
    monkeypatch.delenv("SOTD_DATA_DIR", raising=False)
    monkeypatch.chdir(other_cwd)
    importlib.reload(overrides_mod)
    try:
        repo_root = Path(overrides_mod.__file__).resolve().parent.parent.parent
        assert overrides_mod.OVERRIDE_PATH == repo_root / "data" / "thread_overrides.yaml"
        assert overrides_mod.OVERRIDE_PATH.is_absolute()
    finally:
        _restore_overrides_module(monkeypatch, original_env, original_path)


def test_load_thread_overrides_data_missing_file_warns(tmp_path: Path, caplog) -> None:
    """#23 instance 1: a missing overrides file warns loudly, naming the path."""
    missing = tmp_path / "missing.yaml"
    with caplog.at_level("WARNING", logger="sotd.fetch.overrides"):
        assert load_thread_overrides_data(missing) == {}
    assert "not found" in caplog.text
    assert str(missing) in caplog.text


def test_default_override_path_missing_file_warns(tmp_path: Path, monkeypatch, caplog) -> None:
    """#23 instance 1: the default path warns when the configured file is absent."""
    import importlib
    import os

    import sotd.fetch.overrides as overrides_mod

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    other_cwd = tmp_path / "elsewhere"
    other_cwd.mkdir()

    original_env = os.environ.get("SOTD_DATA_DIR")
    original_path = overrides_mod.OVERRIDE_PATH
    monkeypatch.setenv("SOTD_DATA_DIR", str(data_dir))
    monkeypatch.chdir(other_cwd)
    importlib.reload(overrides_mod)
    try:
        with caplog.at_level("WARNING", logger="sotd.fetch.overrides"):
            assert overrides_mod.load_thread_exclude_ids("2026-06") == set()
        assert "not found" in caplog.text
        assert str(data_dir / "thread_overrides.yaml") in caplog.text
    finally:
        _restore_overrides_module(monkeypatch, original_env, original_path)
