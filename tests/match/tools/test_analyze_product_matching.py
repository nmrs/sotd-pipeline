"""Regression tests: analyze_product_matching resolves its data files from
the run's data dir, not the process working directory (#23 instance 8).

Previously ``ProductAnalyzer`` built its matchers from bare CWD-relative
paths -- ``Path("data/razors.yaml")`` etc. in ``PRODUCT_CONFIGS`` -- so
running the tool from any directory but the repo root raised
``FileNotFoundError: 'data/razors.yaml'`` even with ``SOTD_DATA_DIR`` set.
It also passed ``correct_matches_path=Path("data/correct_matches.yaml")``,
a file path that does not exist: ``BaseMatcher`` appends
``"<field>.yaml"`` to it, so the tool silently loaded no correct matches
and reported regex matches for CM-covered strings even from the repo
root. Both paths now resolve through ``get_data_dir()`` /
``get_default_correct_matches_path()``.
"""

from pathlib import Path

import pytest

from sotd.match.base_matcher import clear_catalog_cache
from sotd.match.loaders import clear_yaml_cache
from sotd.match.tools.analyzers.analyze_product_matching import ProductAnalyzer

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
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


def test_razor_analyzer_uses_data_dir_from_foreign_cwd(monkeypatch, foreign_cwd):
    """Catalog + CM resolve from SOTD_DATA_DIR outside the repo root."""
    monkeypatch.setenv("SOTD_DATA_DIR", str(DATA_DIR))

    analyzer = ProductAnalyzer("razor")
    assert analyzer.matcher.catalog_path == DATA_DIR / "razors.yaml"
    assert analyzer.matcher.correct_matches_path == DATA_DIR / "correct_matches"

    # "above the tie - atlas s1" has a CM entry (data/correct_matches/
    # razor.yaml); exact match proves CM loaded, not just the catalog.
    result = analyzer.matcher.match("above the tie - atlas s1")
    assert result is not None
    assert result.match_type == "exact"
    assert result.matched["brand"] == "Above the Tie"
    assert result.matched["model"] == "S1"


def test_razor_analyzer_loads_correct_matches_from_repo_root(monkeypatch):
    """At the repo root the tool used to report regex for CM strings."""
    monkeypatch.chdir(REPO_ROOT)
    monkeypatch.delenv("SOTD_DATA_DIR", raising=False)

    analyzer = ProductAnalyzer("razor")
    result = analyzer.matcher.match("above the tie - atlas s1")
    assert result is not None
    assert result.match_type == "exact"


def test_blade_and_soap_analyzers_use_data_dir_from_foreign_cwd(monkeypatch, foreign_cwd):
    """The other two product types resolve the same way."""
    monkeypatch.setenv("SOTD_DATA_DIR", str(DATA_DIR))

    blade = ProductAnalyzer("blade")
    assert blade.matcher.catalog_path == DATA_DIR / "blades.yaml"
    blade_result = blade.matcher.match("Feather Hi-Stainless")
    assert blade_result is not None
    assert blade_result.match_type == "exact"
    assert blade_result.matched["brand"] == "Feather"

    soap = ProductAnalyzer("soap")
    assert soap.matcher.catalog_path == DATA_DIR / "soaps.yaml"
    soap_result = soap.matcher.match("Declaration Grooming Original")
    assert soap_result is not None
    assert soap_result.match_type == "exact"
    assert soap_result.matched["brand"] == "Declaration Grooming"
