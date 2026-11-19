#!/usr/bin/env python3
"""Regression tests: Razor/Blade/SoapMatcher catalog defaults resolve from
the run's data dir (#23 remaining instance).

RazorMatcher, BladeMatcher and SoapMatcher defaulted ``catalog_path`` to a
bare CWD-relative ``Path("data/<name>.yaml")``, so a bare construction from
any directory but the repo root raised ``FileNotFoundError`` naming the
CWD-relative path -- even with ``SOTD_DATA_DIR`` set to a data dir holding
the catalogs. The concrete victim is
``validate/actual_matching_validator.py`` ``_get_matcher``, which constructs
all three bare (the production run path in ``match/run.py`` passes explicit
paths and is unaffected). Defaults now resolve through
``get_default_catalog_path()`` (run's data dir via ``get_data_dir()``,
relative data dirs anchored at the repo root), mirroring the
correct_matches default fixed in PR #35 and the BrushMatcher defaults
fixed in PR #39.

These tests fail on the old code: the foreign-CWD cases raise
FileNotFoundError at construction.
"""

import shutil
from pathlib import Path

import pytest

from sotd.match.base_matcher import clear_catalog_cache
from sotd.match.blade_matcher import BladeMatcher
from sotd.match.loaders import clear_yaml_cache
from sotd.match.razor_matcher import RazorMatcher
from sotd.match.soap_matcher import SoapMatcher
from sotd.utils.data_dir import get_default_catalog_path

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_DATA = REPO_ROOT / "data"
CATALOG_FILES = ("razors.yaml", "blades.yaml", "soaps.yaml")


@pytest.fixture(autouse=True)
def _clear_caches():
    clear_catalog_cache()
    clear_yaml_cache()
    yield
    clear_catalog_cache()
    clear_yaml_cache()


@pytest.fixture
def fixture_data_dir(tmp_path):
    """A data dir holding copies of the real catalogs + empty CM dir."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    for name in CATALOG_FILES:
        shutil.copy(REAL_DATA / name, data_dir / name)
    (data_dir / "correct_matches").mkdir()
    return data_dir


@pytest.fixture
def foreign_cwd(monkeypatch, tmp_path):
    """Run the test from a directory with no data/ in it."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    monkeypatch.delenv("SOTD_DATA_DIR", raising=False)
    return elsewhere


def _assert_matches(razor, blade, soap):
    result = razor.match("Above The Tie SE1 Atlas")
    assert result is not None
    assert result.matched["brand"] == "Above the Tie"
    assert result.matched["model"] == "SE1"
    assert result.matched["format"] == "AC"

    result = blade.match("Gillette Silver Blue")
    assert result is not None
    assert result.matched["brand"] == "Gillette"
    assert result.matched["model"] == "Silver Blue"
    assert result.matched["format"] == "DE"

    result = soap.match("Barrister and Mann Seville")
    assert result is not None
    assert result.matched["brand"] == "Barrister and Mann"
    assert result.matched["scent"] == "Seville"


class TestMatcherDefaultCatalogPaths:
    def test_sotd_data_dir_from_foreign_cwd(
        self, foreign_cwd, fixture_data_dir, monkeypatch
    ):
        """SOTD_DATA_DIR is honoured from a foreign CWD; all three paths
        resolve into it and the matchers match."""
        monkeypatch.setenv("SOTD_DATA_DIR", str(fixture_data_dir))

        razor = RazorMatcher()
        blade = BladeMatcher()
        soap = SoapMatcher()

        assert razor.catalog_path == fixture_data_dir / "razors.yaml"
        assert blade.catalog_path == fixture_data_dir / "blades.yaml"
        assert soap.catalog_path == fixture_data_dir / "soaps.yaml"
        _assert_matches(razor, blade, soap)

    def test_no_env_var_from_foreign_cwd_anchors_at_repo_root(
        self, foreign_cwd
    ):
        """With no env var, a foreign CWD still resolves to the repo-root
        data dir."""
        razor = RazorMatcher()
        blade = BladeMatcher()
        soap = SoapMatcher()

        assert razor.catalog_path == REAL_DATA / "razors.yaml"
        assert blade.catalog_path == REAL_DATA / "blades.yaml"
        assert soap.catalog_path == REAL_DATA / "soaps.yaml"
        _assert_matches(razor, blade, soap)

    def test_explicit_path_wins(
        self, foreign_cwd, fixture_data_dir, monkeypatch
    ):
        """An explicit catalog_path still wins over SOTD_DATA_DIR."""
        monkeypatch.setenv("SOTD_DATA_DIR", str(fixture_data_dir / "other"))

        razor = RazorMatcher(catalog_path=fixture_data_dir / "razors.yaml")
        blade = BladeMatcher(catalog_path=fixture_data_dir / "blades.yaml")
        soap = SoapMatcher(catalog_path=fixture_data_dir / "soaps.yaml")

        assert razor.catalog_path == fixture_data_dir / "razors.yaml"
        assert blade.catalog_path == fixture_data_dir / "blades.yaml"
        assert soap.catalog_path == fixture_data_dir / "soaps.yaml"
        _assert_matches(razor, blade, soap)


class TestGetDefaultCatalogPath:
    def test_default_is_repo_root_data_dir(self, foreign_cwd):
        assert get_default_catalog_path("razors.yaml") == REAL_DATA / "razors.yaml"
        assert get_default_catalog_path("razors.yaml").is_absolute()

    def test_honours_sotd_data_dir(self, monkeypatch, tmp_path):
        data_dir = tmp_path / "custom_data"
        monkeypatch.setenv("SOTD_DATA_DIR", str(data_dir))
        assert get_default_catalog_path("blades.yaml") == data_dir / "blades.yaml"

    def test_anchors_relative_data_dir_at_repo_root(self, monkeypatch):
        monkeypatch.setenv("SOTD_DATA_DIR", "data")
        assert get_default_catalog_path("soaps.yaml") == REAL_DATA / "soaps.yaml"
