#!/usr/bin/env python3
"""Tests for soap mashup enricher.

The live-catalog default-path test (Mama Bear's / Sample Mashup) lives in
``tests/integration/test_soap_mashup_enricher.py`` under the production
marker; this file keeps only synthetic-fixture tests.
"""

from pathlib import Path

import pytest

from sotd.enrich.soap_mashup_enricher import SoapMashupEnricher, get_default_soaps_path


REPO_ROOT = Path(__file__).resolve().parents[2]

FIXTURE_SOAPS = """
Repro Brand:
  scents:
    Sample Mashup:
      countable: false
      patterns: []
    Normal Scent:
      countable: true
      patterns: []
"""

CATALOG_ONLY_FIELD_DATA = {
    "original": "Repro Brand Tri-Mix",
    "normalized": "repro brand tri-mix",
    # matched has brand+scent but NO countable (e.g. exact match from
    # correct_matches): the catalog lookup is the only mashup signal,
    # and the text deliberately contains no "mashup" word.
    "matched": {"brand": "Repro Brand", "scent": "Sample Mashup"},
}


class TestSoapMashupEnricherDefaultPath:
    """Default soaps.yaml resolves from the run's data dir, not the CWD."""

    def test_default_uses_run_data_dir_from_foreign_cwd(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """SOTD_DATA_DIR is honoured when constructed from another directory."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "soaps.yaml").write_text(FIXTURE_SOAPS)
        monkeypatch.setenv("SOTD_DATA_DIR", str(data_dir))
        monkeypatch.chdir(tmp_path)  # no data/ here

        enricher = SoapMashupEnricher()
        assert enricher.soaps_path == data_dir / "soaps.yaml"
        assert enricher.enrich(CATALOG_ONLY_FIELD_DATA, "") == {"is_mashup": True}

    def test_default_honours_relative_data_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """A relative SOTD_DATA_DIR is anchored at the repo root, not the CWD."""
        monkeypatch.setenv("SOTD_DATA_DIR", "data")
        monkeypatch.chdir(tmp_path)

        assert get_default_soaps_path() == REPO_ROOT / "data" / "soaps.yaml"

    def test_explicit_path_wins_over_data_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """An explicit soaps_path still wins over SOTD_DATA_DIR."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "soaps.yaml").write_text(FIXTURE_SOAPS)
        monkeypatch.setenv("SOTD_DATA_DIR", str(data_dir))
        explicit = tmp_path / "explicit.yaml"
        explicit.write_text(FIXTURE_SOAPS)

        enricher = SoapMashupEnricher(soaps_path=explicit)
        assert enricher.soaps_path == explicit
        assert enricher.enrich(CATALOG_ONLY_FIELD_DATA, "") == {"is_mashup": True}


class TestSoapMashupEnricher:
    """Test soap mashup enricher functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.enricher = SoapMashupEnricher()

    def test_target_field(self):
        """Test target field property."""
        assert self.enricher.target_field == "soap"

    def test_applies_to_with_soap(self):
        """Test applies_to when soap field is present."""
        record = {"soap": {"original": "test", "normalized": "test"}}
        assert self.enricher.applies_to(record) is True

    def test_applies_to_without_soap(self):
        """Test applies_to when soap field is missing."""
        record = {"blade": {"original": "test", "normalized": "test"}}
        assert self.enricher.applies_to(record) is False

    def test_applies_to_with_none_soap(self):
        """Test applies_to when soap field is None."""
        record = {"soap": None}
        assert self.enricher.applies_to(record) is False

    def test_enrich_from_countable_false(self):
        """Test is_mashup True when matched.countable is False."""
        field_data = {
            "original": "Mama Bear Sample Mashup",
            "normalized": "mama bear sample mashup",
            "matched": {"brand": "Mama Bear", "scent": "Sample Mashup", "countable": False},
        }
        result = self.enricher.enrich(field_data, "")
        assert result == {"is_mashup": True}

    def test_enrich_from_text_mashup(self):
        """Test is_mashup True when text contains mashup (unbranded)."""
        field_data = {
            "original": "soap mashup",
            "normalized": "soap mashup",
            "matched": None,
        }
        result = self.enricher.enrich(field_data, "")
        assert result == {"is_mashup": True}

    def test_enrich_from_text_sample_mashup(self):
        """Test is_mashup True when text contains Sample mashup (matched null)."""
        field_data = {
            "original": "Sample mashup",
            "normalized": "sample mashup",
            "matched": None,
        }
        result = self.enricher.enrich(field_data, "")
        assert result == {"is_mashup": True}

    def test_enrich_from_text_mash_up(self):
        """Test is_mashup True when text contains mash up."""
        field_data = {
            "original": "mash up",
            "normalized": "mash up",
            "matched": {},
        }
        result = self.enricher.enrich(field_data, "")
        assert result == {"is_mashup": True}

    def test_enrich_from_text_mash_hyphen_up(self):
        """Test is_mashup True when text contains mash-up."""
        field_data = {
            "original": "mash-up",
            "normalized": "mash-up",
            "matched": {},
        }
        result = self.enricher.enrich(field_data, "")
        assert result == {"is_mashup": True}

    def test_enrich_no_mashup(self):
        """Test is_mashup False when no catalog or text mashup."""
        field_data = {
            "original": "Barrister and Mann - Seville",
            "normalized": "barrister and mann - seville",
            "matched": {"brand": "Barrister and Mann", "scent": "Seville", "countable": True},
        }
        result = self.enricher.enrich(field_data, "")
        assert result == {"is_mashup": False}

    def test_enrich_matched_null_no_mashup_text(self):
        """Test is_mashup False when matched is null and no mashup in text."""
        field_data = {
            "original": "Unknown soap",
            "normalized": "unknown soap",
            "matched": None,
        }
        result = self.enricher.enrich(field_data, "")
        assert result == {"is_mashup": False}

    def test_enrich_from_catalog_lookup_when_countable_absent(self, tmp_path: Path):
        """Test is_mashup True when matched has brand+scent but no countable (e.g. correct_matches)."""
        soaps_yaml = tmp_path / "soaps.yaml"
        soaps_yaml.write_text("""
Mama Bear's Soaps:
  scents:
    Sample Mashup:
      countable: false
      patterns: []
""")
        enricher = SoapMashupEnricher(soaps_path=soaps_yaml)
        field_data = {
            "original": "Mama Bear's Soap Tri-Mix",
            "normalized": "mama bear's soap tri-mix",
            "matched": {"brand": "Mama Bear's Soaps", "scent": "Sample Mashup"},
        }
        result = enricher.enrich(field_data, "")
        assert result == {"is_mashup": True}

    def test_enrich_from_catalog_lookup_countable_true_not_mashup(self, tmp_path: Path):
        """Test is_mashup False when catalog lookup returns countable true."""
        soaps_yaml = tmp_path / "soaps.yaml"
        soaps_yaml.write_text("""
Some Brand:
  scents:
    Normal Scent:
      countable: true
      patterns: []
""")
        enricher = SoapMashupEnricher(soaps_path=soaps_yaml)
        field_data = {
            "original": "Some Brand - Normal Scent",
            "normalized": "some brand - normal scent",
            "matched": {"brand": "Some Brand", "scent": "Normal Scent"},
        }
        result = enricher.enrich(field_data, "")
        assert result == {"is_mashup": False}
