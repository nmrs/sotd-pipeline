"""Regression tests: the match-layer correct_matches default resolves to the
run's data dir, not the process working directory (#23 instance 4).

Previously every matcher defaulted to a bare CWD-relative
``Path("data/correct_matches")``, so constructing a matcher from any
directory but the repo root silently loaded no correct matches and the
matcher fell back to regex-only matching. The default is now
``get_default_correct_matches_path()`` (run's data dir via ``get_data_dir()``,
relative data dirs anchored at the repo root inside ``get_data_dir()``),
applied in ``BaseMatcher``, ``CatalogLoader.load_correct_matches``,
``SoapMatcher`` (via BaseMatcher), ``BrushMatcher``, the brush config
manager, ``CorrectMatchesUpdater`` and ``CorrectMatchesManager``.

The tests asserting against live production catalog entries live in
``tests/integration/test_correct_matches_default_path.py`` (production
marker); this file keeps only path-resolution and synthetic-data tests,
plus the loud-failure tests for corrupt correct_matches files.
"""

from pathlib import Path

import pytest
import yaml

from sotd.match.base_matcher import clear_catalog_cache
from sotd.match.loaders import CatalogLoader, clear_yaml_cache
from sotd.match.razor_matcher import RazorMatcher
from sotd.utils.data_dir import get_default_correct_matches_path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = REPO_ROOT / "data"


@pytest.fixture(autouse=True)
def _clear_caches():
    clear_catalog_cache()
    clear_yaml_cache()
    yield
    clear_catalog_cache()
    clear_yaml_cache()


@pytest.fixture
def foreign_cwd(monkeypatch, tmp_path):
    """Run the test from a directory with no data/ in it."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SOTD_DATA_DIR", raising=False)
    return tmp_path


def test_default_cm_path_is_run_data_dir(foreign_cwd):
    assert get_default_correct_matches_path() == DATA_DIR / "correct_matches"
    assert get_default_correct_matches_path().is_absolute()


def test_default_cm_path_honours_sotd_data_dir(monkeypatch, tmp_path):
    data_dir = tmp_path / "elsewhere"
    monkeypatch.setenv("SOTD_DATA_DIR", str(data_dir))
    assert get_default_correct_matches_path() == data_dir / "correct_matches"


def test_default_cm_path_anchors_relative_data_dir_at_repo_root(monkeypatch):
    monkeypatch.setenv("SOTD_DATA_DIR", "data")
    assert get_default_correct_matches_path() == DATA_DIR / "correct_matches"


def test_sotd_data_dir_cm_is_used(monkeypatch, tmp_path):
    data_dir = tmp_path / "custom_data"
    cm_dir = data_dir / "correct_matches"
    cm_dir.mkdir(parents=True)
    (cm_dir / "razor.yaml").write_text(
        yaml.safe_dump({"MarkerBrand": {"MarkerModel": ["marker razor string"]}}),
        encoding="utf-8",
    )
    catalog_path = tmp_path / "razors.yaml"
    catalog_path.write_text(
        yaml.safe_dump(
            {"MarkerBrand": {"MarkerModel": {"patterns": ["marker"], "format": "DE"}}}
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SOTD_DATA_DIR", str(data_dir))
    monkeypatch.chdir(tmp_path)

    matcher = RazorMatcher(catalog_path=catalog_path)
    assert matcher.correct_matches_path == cm_dir
    assert "MarkerBrand" in matcher.correct_matches
    result = matcher.match("marker razor string")
    assert result.matched is not None
    assert result.matched["brand"] == "MarkerBrand"
    assert result.match_type == "exact"


def test_explicit_cm_path_wins_over_default(monkeypatch, tmp_path):
    empty_cm = tmp_path / "empty_cm"
    empty_cm.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SOTD_DATA_DIR", raising=False)

    matcher = RazorMatcher(
        catalog_path=DATA_DIR / "razors.yaml", correct_matches_path=empty_cm
    )
    assert matcher.correct_matches_path == empty_cm
    assert matcher.correct_matches == {}


def test_loader_corrupt_yaml_raises(tmp_path):
    """A corrupt field file raises instead of silently returning {}.

    Mirrors BaseMatcher._load_correct_matches: a syntax error in
    data/correct_matches/razor.yaml must fail the run loudly, not degrade
    it to regex-only matching.
    """
    cm_dir = tmp_path / "correct_matches"
    cm_dir.mkdir()
    # Tab-indented YAML triggers yaml.scanner.ScannerError
    (cm_dir / "razor.yaml").write_text("Brand:\n\tModel: []\n", encoding="utf-8")

    loader = CatalogLoader()
    with pytest.raises(ValueError, match="Failed to load correct matches"):
        loader.load_correct_matches(cm_dir, field_type="razor")


def test_loader_corrupt_legacy_file_raises(tmp_path):
    """A corrupt legacy single file raises instead of silently returning {}."""
    legacy = tmp_path / "correct_matches.yaml"
    legacy.write_text("Brand:\n\tModel: []\n", encoding="utf-8")

    loader = CatalogLoader()
    with pytest.raises(ValueError, match="Failed to load correct matches"):
        loader.load_correct_matches(legacy, field_type="razor")


def test_loader_missing_field_file_returns_empty(tmp_path):
    """Missing field file is fine -- returns {} (control for the raises above)."""
    cm_dir = tmp_path / "correct_matches"
    cm_dir.mkdir()

    loader = CatalogLoader()
    assert loader.load_correct_matches(cm_dir, field_type="razor") == {}
    assert loader.load_correct_matches(tmp_path / "no_such_dir", field_type="razor") == {}
