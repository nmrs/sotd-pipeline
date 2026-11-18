"""Production-catalog tests: the match-layer correct_matches default resolves
to the run's data dir, not the process working directory (#23 instance 4).

These tests assert against live production catalog entries ("Above the Tie"
S1, Feather Pro, 345 Soap Co. Cairn), so they live here under
``tests/integration/`` with the ``production`` marker (run with
``make test-production``) rather than in the default unit suite: a routine
data edit must not break ``make test`` with failures unrelated to any code
change. The path-resolution tests (no catalog content asserted) stay in
``tests/match/test_correct_matches_default_path.py``.

Note: CI's default ``pytest tests/`` invocation still runs this file (it
only deselects ``-m "not perf"``), so a data edit can still surface here --
the marker + location is the repo convention for catalog-asserting tests,
not an exclusion from the default suite.
"""

from pathlib import Path

import pytest

from sotd.match.base_matcher import clear_catalog_cache
from sotd.match.blade_matcher import BladeMatcher
from sotd.match.brush.matcher import clear_brush_catalog_cache
from sotd.match.brush_matcher import BrushMatcher
from sotd.match.loaders import CatalogLoader, clear_yaml_cache
from sotd.match.razor_matcher import RazorMatcher
from sotd.match.soap_matcher import SoapMatcher

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = REPO_ROOT / "data"


@pytest.fixture(autouse=True)
def _clear_caches():
    clear_catalog_cache()
    clear_yaml_cache()
    clear_brush_catalog_cache()
    yield
    clear_catalog_cache()
    clear_yaml_cache()
    clear_brush_catalog_cache()


@pytest.fixture
def foreign_cwd(monkeypatch, tmp_path):
    """Run the test from a directory with no data/ in it."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SOTD_DATA_DIR", raising=False)
    return tmp_path


@pytest.mark.production
def test_razor_matcher_default_cm_loads_from_foreign_cwd(foreign_cwd):
    matcher = RazorMatcher(catalog_path=DATA_DIR / "razors.yaml")
    assert matcher.correct_matches_path == DATA_DIR / "correct_matches"
    assert len(matcher.correct_matches) > 0
    assert "Above the Tie" in matcher.correct_matches
    result = matcher.match("above the tie - atlas s1")
    assert result.matched is not None
    assert result.matched["brand"] == "Above the Tie"
    assert result.matched["model"] == "S1"
    assert result.match_type == "exact"


@pytest.mark.production
def test_blade_matcher_default_cm_loads_from_foreign_cwd(foreign_cwd):
    matcher = BladeMatcher(catalog_path=DATA_DIR / "blades.yaml")
    assert matcher.correct_matches_path == DATA_DIR / "correct_matches"
    assert len(matcher.correct_matches) > 0
    result = matcher.match("feather ac professional")
    assert result.matched is not None
    assert result.matched["brand"] == "Feather"
    assert result.matched["model"] == "Pro"
    assert result.match_type == "exact"


@pytest.mark.production
def test_soap_matcher_default_cm_loads_from_foreign_cwd(foreign_cwd):
    pytest.importorskip("rich")
    matcher = SoapMatcher(catalog_path=DATA_DIR / "soaps.yaml")
    assert matcher.correct_matches_path == DATA_DIR / "correct_matches"
    assert len(matcher.correct_matches) > 0
    assert "345 Soap Co." in matcher.correct_matches
    result = matcher.match("345 soap co. - cairn")
    assert result.matched is not None
    assert result.matched["brand"] == "345 Soap Co."
    assert result.matched["scent"] == "Cairn"
    assert result.match_type == "exact"


@pytest.mark.production
def test_loader_default_cm_loads_from_foreign_cwd(foreign_cwd):
    loader = CatalogLoader()
    razor_cm = loader.load_correct_matches(field_type="razor")
    assert len(razor_cm) > 0
    assert "Above the Tie" in razor_cm
    blade_cm = loader.load_correct_matches(field_type="blade")
    assert len(blade_cm) > 0


@pytest.mark.production
def test_brush_matcher_default_cm_loads_from_foreign_cwd(foreign_cwd):
    """BrushMatcher was the one matcher the original fix missed: its
    ``correct_matches_path`` default stayed a bare CWD-relative
    ``Path("data/correct_matches")``, so from any directory but the repo
    root brush correct-matches silently loaded as {} while razor/blade/soap
    in the same run loaded theirs."""
    matcher = BrushMatcher(
        brushes_path=DATA_DIR / "brushes.yaml",
        handles_path=DATA_DIR / "handles.yaml",
        knots_path=DATA_DIR / "knots.yaml",
        brush_scoring_config_path=DATA_DIR / "brush_scoring_config.yaml",
    )
    assert matcher.correct_matches_path == DATA_DIR / "correct_matches"
    brush_cm = matcher._catalogs["correct_matches"]
    assert len(brush_cm.get("brush", {})) > 0
    assert "Simpson" in brush_cm["brush"]
