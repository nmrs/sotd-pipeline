#!/usr/bin/env python3
"""Regression tests: BrushMatcher defaults resolve from the run's data dir.

BrushMatcher.__init__ defaulted its four catalog paths to bare CWD-relative
Path("data/...") values, so a bare BrushMatcher() raised FileNotFoundError
(missing brush_scoring_config.yaml) from any working directory but the repo
root -- even with SOTD_DATA_DIR set to a data dir holding all four files.
The production run path (match/run.py) passes explicit paths, but the
validator (validate/actual_matching_validator.py: _get_matcher and the
_validate_brush_batch worker, which passes data_path to everything else)
and the brush analysis tools construct BrushMatcher() bare. Defaults now
resolve from get_data_dir(), mirroring the correct_matches default fixed
in PR #35. These tests fail on the old code: the foreign-CWD cases raise
FileNotFoundError at construction.
"""

import shutil
from pathlib import Path

import pytest

from sotd.match.brush_matcher import BrushMatcher
from sotd.utils.data_dir import get_data_dir

REPO_ROOT = Path(__file__).resolve().parents[3]
REAL_DATA = REPO_ROOT / "data"
CATALOG_FILES = (
    "brushes.yaml",
    "handles.yaml",
    "knots.yaml",
    "brush_scoring_config.yaml",
)


@pytest.fixture
def fixture_data_dir(tmp_path):
    """A data dir holding copies of the real brush catalogs + empty CM dir."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    for name in CATALOG_FILES:
        shutil.copy(REAL_DATA / name, data_dir / name)
    (data_dir / "correct_matches").mkdir()
    return data_dir


class TestBrushMatcherDefaultPaths:
    def test_sotd_data_dir_from_foreign_cwd(self, tmp_path, fixture_data_dir, monkeypatch):
        """SOTD_DATA_DIR is honoured from a foreign CWD; all four paths resolve into it."""
        foreign_cwd = tmp_path / "elsewhere"
        foreign_cwd.mkdir()
        monkeypatch.chdir(foreign_cwd)
        monkeypatch.setenv("SOTD_DATA_DIR", str(fixture_data_dir))

        matcher = BrushMatcher()

        assert matcher.brushes_path == fixture_data_dir / "brushes.yaml"
        assert matcher.handles_path == fixture_data_dir / "handles.yaml"
        assert matcher.knots_path == fixture_data_dir / "knots.yaml"
        assert matcher.config.config_path == fixture_data_dir / "brush_scoring_config.yaml"
        assert matcher.correct_matches_path == fixture_data_dir / "correct_matches"

        result = matcher.match("Simpson Chubby 2 Best Badger")
        assert result is not None
        assert result.matched["brand"] == "Simpson"
        assert result.matched["model"] == "Chubby 2"

    def test_no_env_var_from_foreign_cwd_anchors_at_repo_root(
        self, tmp_path, monkeypatch
    ):
        """With no env var, a foreign CWD still resolves to the repo-root data dir."""
        foreign_cwd = tmp_path / "elsewhere"
        foreign_cwd.mkdir()
        monkeypatch.chdir(foreign_cwd)
        monkeypatch.delenv("SOTD_DATA_DIR", raising=False)

        matcher = BrushMatcher()

        expected = get_data_dir()
        assert matcher.brushes_path == expected / "brushes.yaml"
        assert matcher.handles_path == expected / "handles.yaml"
        assert matcher.knots_path == expected / "knots.yaml"
        assert matcher.config.config_path == expected / "brush_scoring_config.yaml"

    def test_explicit_paths_win(self, tmp_path, fixture_data_dir, monkeypatch):
        """Explicit paths still win over the data-dir default."""
        other_dir = tmp_path / "other"
        other_dir.mkdir()
        monkeypatch.chdir(other_dir)
        monkeypatch.setenv("SOTD_DATA_DIR", str(tmp_path / "does-not-exist"))

        matcher = BrushMatcher(
            brushes_path=fixture_data_dir / "brushes.yaml",
            handles_path=fixture_data_dir / "handles.yaml",
            knots_path=fixture_data_dir / "knots.yaml",
            brush_scoring_config_path=fixture_data_dir / "brush_scoring_config.yaml",
            correct_matches_path=fixture_data_dir / "correct_matches",
        )

        assert matcher.brushes_path == fixture_data_dir / "brushes.yaml"
        assert matcher.config.config_path == fixture_data_dir / "brush_scoring_config.yaml"
        result = matcher.match("Simpson Chubby 2 Best Badger")
        assert result is not None
        assert result.matched["brand"] == "Simpson"
