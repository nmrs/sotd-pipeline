#!/usr/bin/env python3
"""Tests for soap sample enricher."""

from sotd.enrich.soap_sample_enricher import SoapSampleEnricher


class TestSoapSampleEnricher:
    """Test soap sample enricher functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.enricher = SoapSampleEnricher()

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

    def test_enrich_empty_input(self):
        """Test enrich with empty input."""
        field_data = {}
        result = self.enricher.enrich(field_data, "")
        assert result == {}

    def test_enrich_missing_original(self):
        """Test enrich with missing original field."""
        field_data = {"normalized": "summer break soaps - steady"}
        result = self.enricher.enrich(field_data, "")
        assert result == {}

    def test_enrich_missing_normalized(self):
        """Test enrich with missing normalized field."""
        field_data = {"original": "summer break soaps - steady (sample)"}
        result = self.enricher.enrich(field_data, "")
        assert result == {}

    def test_enrich_no_sample_indicators(self):
        """Test enrich with no sample indicators: no finding, no dict."""
        field_data = {
            "original": "summer break soaps - steady",
            "normalized": "summer break soaps - steady",
        }
        result = self.enricher.enrich(field_data, "")
        assert result == {}

    def test_enrich_basic_sample(self):
        """Test enrich with basic sample indicator."""
        field_data = {
            "original": "summer break soaps - steady (sample)",
            "normalized": "summer break soaps - steady",
        }
        result = self.enricher.enrich(field_data, "")
        assert result == {
            "sample_type": "sample",
            "sample_number": None,
            "total_samples": None,
            "extraction_remainder": "(sample)",
        }

    def test_enrich_tester(self):
        """Test enrich with tester indicator."""
        field_data = {
            "original": "summer break soaps - steady (tester)",
            "normalized": "summer break soaps - steady",
        }
        result = self.enricher.enrich(field_data, "")
        assert result == {
            "sample_type": "tester",
            "sample_number": None,
            "total_samples": None,
            "extraction_remainder": "(tester)",
        }

    def test_enrich_basic_smush(self):
        """Test enrich with basic smush indicator - should normalize to sample."""
        field_data = {
            "original": "summer break soaps - steady (smush)",
            "normalized": "summer break soaps - steady",
        }
        result = self.enricher.enrich(field_data, "")
        assert result == {
            "sample_type": "sample",
            "sample_number": None,
            "total_samples": None,
            "extraction_remainder": "(smush)",
        }

    def test_enrich_numbered_sample(self):
        """Test enrich with numbered sample."""
        field_data = {
            "original": "summer break soaps - steady (sample #23)",
            "normalized": "summer break soaps - steady",
        }
        result = self.enricher.enrich(field_data, "")
        assert result == {
            "sample_type": "sample",
            "sample_number": 23,
            "total_samples": None,
            "extraction_remainder": "(sample #23)",
        }

    def test_enrich_numbered_smush(self):
        """Test enrich with numbered smush - should normalize to sample."""
        field_data = {
            "original": "summer break soaps - steady (smush #23)",
            "normalized": "summer break soaps - steady",
        }
        result = self.enricher.enrich(field_data, "")
        assert result == {
            "sample_type": "sample",
            "sample_number": 23,
            "total_samples": None,
            "extraction_remainder": "(smush #23)",
        }

    def test_enrich_range_sample(self):
        """Test enrich with range sample."""
        field_data = {
            "original": "summer break soaps - steady (sample 5 of 10)",
            "normalized": "summer break soaps - steady",
        }
        result = self.enricher.enrich(field_data, "")
        assert result == {
            "sample_type": "sample",
            "sample_number": 5,
            "total_samples": 10,
            "extraction_remainder": "(sample 5 of 10)",
        }

    def test_enrich_range_smush(self):
        """Test enrich with range smush - should normalize to sample."""
        field_data = {
            "original": "summer break soaps - steady (smush 5 of 10)",
            "normalized": "summer break soaps - steady",
        }
        result = self.enricher.enrich(field_data, "")
        assert result == {
            "sample_type": "sample",
            "sample_number": 5,
            "total_samples": 10,
            "extraction_remainder": "(smush 5 of 10)",
        }

    def test_enrich_fraction_smush(self):
        """Test enrich with fraction smush - should normalize to sample."""
        field_data = {
            "original": "summer break soaps - steady (smush 3/15)",
            "normalized": "summer break soaps - steady",
        }
        result = self.enricher.enrich(field_data, "")
        assert result == {
            "sample_type": "sample",
            "sample_number": 3,
            "total_samples": 15,
            "extraction_remainder": "(smush 3/15)",
        }

    def test_enrich_trailing_sample(self):
        """Test enrich with trailing sample."""
        field_data = {
            "original": "summer break soaps - steady - sample",
            "normalized": "summer break soaps - steady",
        }
        result = self.enricher.enrich(field_data, "")
        assert result == {
            "sample_type": "sample",
            "sample_number": None,
            "total_samples": None,
            "extraction_remainder": "- sample",
        }

    def test_enrich_gratitude_sample(self):
        """Test enrich with gratitude sample pattern."""
        field_data = {
            "original": "summer break soaps - steady (sample -- thanks!!)",
            "normalized": "summer break soaps - steady",
        }
        result = self.enricher.enrich(field_data, "")
        assert result == {
            "sample_type": "sample",
            "sample_number": None,
            "total_samples": None,
            "extraction_remainder": "(sample -- thanks!!)",
        }

    def test_enrich_real_world_example(self):
        """Test enrich with real world example."""
        field_data = {
            "original": "summer break soaps - steady - soap (sample -- thanks!!)",
            "normalized": "summer break soaps - steady",
        }
        result = self.enricher.enrich(field_data, "")
        assert result == {
            "sample_type": "sample",
            "sample_number": None,
            "total_samples": None,
            "extraction_remainder": "- soap (sample -- thanks!!)",
        }

    def test_enrich_case_insensitive(self):
        """Test enrich with case insensitive input."""
        field_data = {
            "original": "SUMMER BREAK SOAPS - STEADY (SAMPLE)",
            "normalized": "summer break soaps - steady",
        }
        result = self.enricher.enrich(field_data, "")
        assert result == {
            "sample_type": "sample",
            "sample_number": None,
            "total_samples": None,
            "extraction_remainder": "(SAMPLE)",
        }

    def test_enrich_case_insensitive_smush(self):
        """Test enrich with case insensitive smush input - should normalize to sample."""
        field_data = {
            "original": "SUMMER BREAK SOAPS - STEADY (SMUSH)",
            "normalized": "summer break soaps - steady",
        }
        result = self.enricher.enrich(field_data, "")
        assert result == {
            "sample_type": "sample",
            "sample_number": None,
            "total_samples": None,
            "extraction_remainder": "(SMUSH)",
        }

    def test_enrich_mashup_of_sized_samples_same_original_normalized(self):
        """Detect sample when mashup text keeps '1oz samples' in original and normalized."""
        text = "Stirling VarenBury (combined Varen and Glastonbury 1oz samples)"
        field_data = {"original": text, "normalized": text}
        result = self.enricher.enrich(field_data, "")
        assert result["sample_type"] == "sample"
        assert result["sample_number"] is None
        assert result["total_samples"] is None
        assert result["extraction_remainder"] == ""

    def test_enrich_unknown_smush_forces_sample(self):
        """Mystery smushes map to Unknown/Smush with no (sample) marker in original."""
        field_data = {
            "original": "Snooting - Blind Date",
            "normalized": "Snooting - Blind Date",
            "matched": {"brand": "Unknown", "scent": "Smush"},
        }
        result = self.enricher.enrich(field_data, "")
        assert result["sample_type"] == "sample"
        assert result["sample_number"] is None
        assert result["total_samples"] is None

    def test_enrich_unknown_smush_case_insensitive(self):
        """Unknown/Smush special-case is case-insensitive on matched brand/scent."""
        field_data = {
            "original": "Unknown Something From u/hugbckt",
            "normalized": "Unknown Something From u/hugbckt",
            "matched": {"brand": "unknown", "scent": "smush"},
        }
        result = self.enricher.enrich(field_data, "")
        assert result["sample_type"] == "sample"

    def test_enrich_unknown_other_scent_not_forced(self):
        """Other Unknown scents are not forced to sample without text markers."""
        field_data = {
            "original": "Unknown - Something Else",
            "normalized": "Unknown - Something Else",
            "matched": {"brand": "Unknown", "scent": "Something Else"},
        }
        result = self.enricher.enrich(field_data, "")
        assert result == {}
