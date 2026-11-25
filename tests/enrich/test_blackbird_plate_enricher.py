import pytest

from sotd.enrich.blackbird_plate_enricher import BlackbirdPlateEnricher


class TestBlackbirdPlateEnricher:
    """Test cases for BlackbirdPlateEnricher."""

    @pytest.fixture
    def enricher(self):
        """Create a BlackbirdPlateEnricher instance for testing."""
        return BlackbirdPlateEnricher()

    def test_target_field(self, enricher):
        """Test that the target field is correctly set to 'razor'."""
        assert enricher.target_field == "razor"

    def test_applies_to_blackland_blackbird(self, enricher):
        """Test that enricher applies to Blackland Blackbird razors."""
        record = {"razor": {"matched": {"brand": "Blackland", "model": "Blackbird"}}}
        assert enricher.applies_to(record) is True

    def test_applies_to_blackland_blackbird_with_extra_text(self, enricher):
        """Test that enricher applies to Blackland Blackbird razors with extra model text."""
        record = {"razor": {"matched": {"brand": "Blackland", "model": "Blackbird Ti"}}}
        assert enricher.applies_to(record) is True

    def test_does_not_apply_to_other_blackland(self, enricher):
        """Test that enricher does not apply to other Blackland razors."""
        record = {"razor": {"matched": {"brand": "Blackland", "model": "Vector"}}}
        assert enricher.applies_to(record) is False

    def test_does_not_apply_to_other_brands(self, enricher):
        """Test that enricher does not apply to other brands."""
        record = {"razor": {"matched": {"brand": "RazoRock", "model": "Game Changer"}}}
        assert enricher.applies_to(record) is False

    def test_does_not_apply_to_no_razor(self, enricher):
        """Test that enricher does not apply when no razor is present."""
        record = {"blade": {"matched": {"brand": "Feather"}}}
        assert enricher.applies_to(record) is False

    def test_does_not_apply_to_none_razor(self, enricher):
        """Test that enricher does not apply when razor is None."""
        record = {"razor": None}
        assert enricher.applies_to(record) is False

    def test_does_not_apply_to_invalid_razor_structure(self, enricher):
        """Test that enricher does not apply when razor structure is invalid."""
        record = {"razor": "not a dict"}
        assert enricher.applies_to(record) is False

    def test_does_not_apply_to_no_matched_data(self, enricher):
        """Test that enricher does not apply when no matched data is present."""
        record = {"razor": {}}
        assert enricher.applies_to(record) is False

    def test_extract_plate_standard(self, enricher):
        """Test extraction of Standard plate."""
        comment = "Blackland Blackbird Standard"
        result = enricher.enrich({}, comment)
        assert result is not None
        assert result["plate"] == "Standard"
        assert result["_enriched_by"] == "BlackbirdPlateEnricher"
        assert result["_extraction_source"] == "user_comment"

    def test_extract_plate_lite(self, enricher):
        """Test extraction of Lite plate."""
        comment = "Blackland Blackbird Lite"
        result = enricher.enrich({}, comment)
        assert result is not None
        assert result["plate"] == "Lite"

    def test_extract_plate_oc(self, enricher):
        """Test extraction of OC plate."""
        comment = "Blackland Blackbird OC"
        result = enricher.enrich({}, comment)
        assert result is not None
        assert result["plate"] == "OC"

    def test_extract_plate_open_comb(self, enricher):
        """Test extraction of Open Comb plate (synonym for OC)."""
        comment = "Blackland Blackbird Open Comb"
        result = enricher.enrich({}, comment)
        assert result is not None
        assert result["plate"] == "OC"

    def test_extract_plate_open_comb_with_spaces(self, enricher):
        """Test extraction of Open Comb plate with extra spaces."""
        comment = "Blackland Blackbird Open   Comb"
        result = enricher.enrich({}, comment)
        assert result is not None
        assert result["plate"] == "OC"

    def test_case_insensitive_extraction(self, enricher):
        """Test that extraction works regardless of case."""
        test_cases = [
            ("BLACKLAND BLACKBIRD STANDARD", "Standard"),
            ("blackland blackbird lite", "Lite"),
            ("Blackland Blackbird Oc", "OC"),
            ("Blackland Blackbird OPEN COMB", "OC"),
        ]

        for comment, expected in test_cases:
            result = enricher.enrich({}, comment)
            assert result is not None, f"Failed for comment: {comment}"
            assert result["plate"] == expected, f"Failed for comment: {comment}"

    def test_no_plate_found(self, enricher):
        """Test that None is returned when no specific plate is mentioned.

        No plate is invented: a bare Blackbird carries no plate
        information, so the enricher reports nothing.
        """
        comment = "Blackland Blackbird"
        result = enricher.enrich({}, comment)
        assert result is None

    def test_empty_comment(self, enricher):
        """Test that None is returned for an empty comment."""
        comment = ""
        result = enricher.enrich({}, comment)
        assert result is None

    def test_priority_order(self, enricher):
        """Test that OC takes priority over other matches when both are present."""
        comment = "Blackland Blackbird OC Standard"
        result = enricher.enrich({}, comment)
        assert result is not None
        assert result["plate"] == "OC"  # OC should take priority

    def test_real_world_examples(self, enricher):
        """Test with real-world comment examples."""
        test_cases = [
            ("Blackland Blackbird Standard", "Standard"),
            ("Blackbird Lite", "Lite"),
            ("Blackland Blackbird OC", "OC"),
            ("Blackbird Open Comb", "OC"),
        ]

        for comment, expected in test_cases:
            result = enricher.enrich({}, comment)
            assert result is not None, f"Failed for comment: {comment}"
            assert result["plate"] == expected, f"Failed for comment: {comment}"

    def test_enrich_preserves_field_data(self, enricher):
        """Test that field_data is preserved when enriching."""
        field_data = {"brand": "Blackland", "model": "Blackbird"}
        comment = "Blackland Blackbird Standard"

        result = enricher.enrich(field_data, comment)

        assert result is not None
        assert result["plate"] == "Standard"
        # Field data should not be modified
        assert field_data == {"brand": "Blackland", "model": "Blackbird"}
