"""Tests that MismatchAnalyzer loads catalog patterns from the run data dir.

Regression tests for the #23 CWD-relative-path instance in
``MismatchAnalyzer._load_catalog_patterns``: it used a bare CWD-relative
``Path("data") / catalog_file``, so constructing the analyzer from any
directory but the repo root silently loaded zero catalog patterns (the
mismatch analysis then ran with no patterns at all) even with
``SOTD_DATA_DIR`` set. The loader now resolves through ``get_data_dir()``
(the ``--data-dir`` > ``SOTD_DATA_DIR`` > ``<repo root>/data``
convention shared by the rest of the #23 series).
"""

import os
from pathlib import Path

import pytest

from sotd.match.tools.analyzers.mismatch_analyzer import MismatchAnalyzer

# Minimal but structurally valid catalogs (one entry per field), written
# into the fixture data dir so the tests prove the loader reads the run
# data dir rather than the repo-root catalogs.
RAZOR_CATALOG = """\
ReproBrand:
  ReproModel:
    patterns:
      - reprobrand.*repromodel
"""

BLADE_CATALOG = """\
DE:
  ReproBrand:
    ReproModel:
      patterns:
        - reprobrand.*repromodel
"""

BRUSH_CATALOG = """\
ReproBrand:
  ReproModel:
    patterns:
      - reprobrand.*repromodel
"""

SOAP_CATALOG = """\
ReproMaker:
  scents:
    ReproScent:
      patterns:
        - repro.*scent
"""

CATALOGS = {
    "razors.yaml": RAZOR_CATALOG,
    "blades.yaml": BLADE_CATALOG,
    "brushes.yaml": BRUSH_CATALOG,
    "soaps.yaml": SOAP_CATALOG,
}


@pytest.fixture
def fixture_data_dir(tmp_path):
    """A data dir holding only the minimal fixture catalogs."""
    data_dir = tmp_path / "fixture_data"
    data_dir.mkdir()
    for filename, content in CATALOGS.items():
        (data_dir / filename).write_text(content, encoding="utf-8")
    return data_dir


@pytest.fixture
def foreign_cwd(tmp_path, monkeypatch):
    """Run from a directory with no data/ subtree."""
    cwd = tmp_path / "elsewhere"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    return cwd


class TestMismatchAnalyzerDefaultPaths:
    def test_loads_from_sotd_data_dir_foreign_cwd(
        self, fixture_data_dir, foreign_cwd, monkeypatch
    ):
        """Catalog patterns load from SOTD_DATA_DIR, not the CWD."""
        monkeypatch.setenv("SOTD_DATA_DIR", str(fixture_data_dir))
        analyzer = MismatchAnalyzer()
        patterns = analyzer._load_catalog_patterns("razor")
        assert len(patterns) == 1
        assert patterns[0]["pattern"] == "reprobrand.*repromodel"
        assert patterns[0]["brand"] == "ReproBrand"
        assert patterns[0]["model"] == "ReproModel"

    def test_loads_all_fields_from_sotd_data_dir(
        self, fixture_data_dir, foreign_cwd, monkeypatch
    ):
        """Every field resolves its catalog from the run data dir."""
        monkeypatch.setenv("SOTD_DATA_DIR", str(fixture_data_dir))
        analyzer = MismatchAnalyzer()
        expected = {
            "razor": "reprobrand.*repromodel",
            "blade": "reprobrand.*repromodel",
            "brush": "reprobrand.*repromodel",
            "soap": "repro.*scent",
        }
        for field, pattern in expected.items():
            patterns = analyzer._load_catalog_patterns(field)
            assert [p["pattern"] for p in patterns] == [pattern], field

    def test_no_env_var_anchors_at_repo_root_foreign_cwd(self, foreign_cwd, monkeypatch):
        """Without SOTD_DATA_DIR the repo-root catalogs load from anywhere."""
        monkeypatch.delenv("SOTD_DATA_DIR", raising=False)
        analyzer = MismatchAnalyzer()
        patterns = analyzer._load_catalog_patterns("razor")
        assert len(patterns) > 100
        assert any(p.get("brand") == "Merkur" for p in patterns)

    def test_missing_catalog_returns_empty(
        self, tmp_path, foreign_cwd, monkeypatch
    ):
        """A data dir with no catalog file still loads [] (no raise)."""
        empty_dir = tmp_path / "empty_data"
        empty_dir.mkdir()
        monkeypatch.setenv("SOTD_DATA_DIR", str(empty_dir))
        analyzer = MismatchAnalyzer()
        assert analyzer._load_catalog_patterns("razor") == []
