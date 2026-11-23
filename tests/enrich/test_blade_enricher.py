import pytest

from sotd.enrich.blade_enricher import BladeCountEnricher


class TestBladeCountEnricher:
    """Test cases for the BladeCountEnricher."""

    @pytest.fixture
    def enricher(self):
        """Create a BladeCountEnricher instance for testing."""
        return BladeCountEnricher()

    def test_target_field(self, enricher):
        """Test that target_field returns 'blade'."""
        assert enricher.target_field == "blade"

    def test_applies_to_with_blade(self, enricher):
        """Test applies_to when record has a blade field."""
        record = {"blade": {"matched": {"brand": "Astra", "model": "SP"}}}
        assert enricher.applies_to(record) is True

    def test_applies_to_without_blade(self, enricher):
        """Test applies_to when record has no blade field."""
        record = {"razor": {"matched": {"brand": "Merkur", "model": "34C"}}}
        assert enricher.applies_to(record) is False

    def test_applies_to_with_none_blade(self, enricher):
        """Test applies_to when blade field is None."""
        record = {"blade": None}
        assert enricher.applies_to(record) is False

    def test_enrich_with_parentheses_count(self, enricher):
        """Test extraction of use count in parentheses format."""
        field_data = {
            "original": "Astra SP (3)",
            "normalized": "Astra SP",
            "matched": {"brand": "Astra", "model": "SP"},
        }
        original_comment = "Astra SP (3)"

        result = enricher.enrich(field_data, original_comment)

        assert result is not None
        assert result["use_count"] == 3
        assert result["extraction_remainder"] == "(3)"

    def test_enrich_with_brackets_count(self, enricher):
        """Test extraction of use count in brackets format."""
        field_data = {
            "original": "Feather [5]",
            "normalized": "Feather",
            "matched": {"brand": "Feather", "model": "Hi-Stainless"},
        }
        original_comment = "Feather [5]"

        result = enricher.enrich(field_data, original_comment)

        assert result is not None
        assert result["use_count"] == 5
        assert result["extraction_remainder"] == "[5]"

    def test_enrich_with_braces_count(self, enricher):
        """Test extraction of use count in braces format."""
        field_data = {
            "original": "Gillette Platinum {2}",
            "normalized": "Gillette Platinum",
            "matched": {"brand": "Gillette", "model": "Platinum"},
        }
        original_comment = "Gillette Platinum {2}"

        result = enricher.enrich(field_data, original_comment)

        assert result is not None
        assert result["use_count"] == 2
        assert result["extraction_remainder"] == "{2}"

    def test_enrich_with_x_prefix(self, enricher):
        """Test extraction of use count with x prefix."""
        field_data = {
            "original": "Personna x4",
            "normalized": "Personna",
            "matched": {"brand": "Personna", "model": "Platinum"},
        }
        original_comment = "Personna x4"

        result = enricher.enrich(field_data, original_comment)

        assert result is not None
        assert result["use_count"] == 4
        assert result["extraction_remainder"] == "x4"

    def test_enrich_with_x_suffix(self, enricher):
        """Test extraction of use count with x suffix."""
        field_data = {
            "original": "Voskhod Teflon Coated 2x",
            "normalized": "Voskhod Teflon Coated",
            "matched": {"brand": "Voskhod", "model": "Teflon Coated"},
        }
        original_comment = "Voskhod Teflon Coated 2x"

        result = enricher.enrich(field_data, original_comment)

        assert result is not None
        assert result["use_count"] == 2
        assert result["extraction_remainder"] == "2x"

    def test_enrich_with_parentheses_and_x(self, enricher):
        """Test extraction of use count with parentheses and x."""
        field_data = {
            "original": "Derby (x2)",
            "normalized": "Derby",
            "matched": {"brand": "Derby", "model": "Extra"},
        }
        original_comment = "Derby (x2)"

        result = enricher.enrich(field_data, original_comment)

        assert result is not None
        assert result["use_count"] == 2
        assert result["extraction_remainder"] == "(x2)"

    def test_enrich_with_no_count(self, enricher):
        """Test enrichment when no use count is found: no finding, no dict."""
        field_data = {
            "original": "Astra SP",
            "normalized": "Astra SP",
            "matched": {"brand": "Astra", "model": "SP"},
        }
        original_comment = "Astra SP"

        result = enricher.enrich(field_data, original_comment)

        assert result == {}

    def test_enrich_with_multiple_numbers(self, enricher):
        """Test extraction when multiple numbers are present (should get first match)."""
        field_data = {
            "original": "Feather (3) shave #5",
            "normalized": "Feather",
            "matched": {"brand": "Feather", "model": "Hi-Stainless"},
        }
        original_comment = "Feather (3) shave #5"

        result = enricher.enrich(field_data, original_comment)

        assert result is not None
        assert result["use_count"] == 3
        assert result["extraction_remainder"] == "(3) shave #5"

    def test_enrich_with_large_number(self, enricher):
        """Test extraction with large use count numbers."""
        field_data = {
            "original": "Astra SP (15)",
            "normalized": "Astra SP",
            "matched": {"brand": "Astra", "model": "SP"},
        }
        original_comment = "Astra SP (15)"

        result = enricher.enrich(field_data, original_comment)

        assert result is not None
        assert result["use_count"] == 15
        assert result["extraction_remainder"] == "(15)"

    def test_enrich_with_single_digit(self, enricher):
        """Test extraction with single digit use count."""
        field_data = {
            "original": "Gillette Silver Blue (1)",
            "normalized": "Gillette Silver Blue",
            "matched": {"brand": "Gillette", "model": "Silver Blue"},
        }
        original_comment = "Gillette Silver Blue (1)"

        result = enricher.enrich(field_data, original_comment)

        assert result is not None
        assert result["use_count"] == 1
        assert result["extraction_remainder"] == "(1)"
