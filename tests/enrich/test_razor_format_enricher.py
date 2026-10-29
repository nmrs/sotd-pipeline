"""Unit tests for RazorFormatEnricher."""

import pytest

from sotd.enrich.razor_format_enricher import RazorFormatEnricher


@pytest.fixture
def enricher():
    """Create a RazorFormatEnricher instance for testing."""
    return RazorFormatEnricher()


class TestRazorFormatEnricherAppliesTo:
    """Test applies_to() method."""

    def test_applies_to_with_razor_match(self, enricher):
        """Test that enricher applies to records with matched razor."""
        record = {
            "razor": {
                "matched": {
                    "brand": "Gillette",
                    "model": "Tech",
                    "format": "DE",
                }
            }
        }
        assert enricher.applies_to(record) is True

    def test_applies_to_without_razor(self, enricher):
        """Test that enricher does not apply to records without razor."""
        record = {"blade": {"matched": {"format": "DE"}}}
        assert enricher.applies_to(record) is False

    def test_applies_to_with_none_razor(self, enricher):
        """Test that enricher does not apply to records with None razor."""
        record = {"razor": None}
        assert enricher.applies_to(record) is False

    def test_applies_to_without_matched(self, enricher):
        """Test that enricher does not apply to records without matched razor data."""
        record = {"razor": {"original": "Gillette Tech"}}
        assert enricher.applies_to(record) is False

    def test_applies_to_does_not_store_record(self, enricher):
        """applies_to() must not keep record state; enrich() reads its record parameter."""
        record = {
            "razor": {
                "matched": {
                    "format": "Shavette",
                }
            },
            "blade": {
                "matched": {
                    "format": "AC",
                }
            },
        }
        enricher.applies_to(record)
        assert not hasattr(enricher, "_current_record")

    def test_enrich_uses_record_parameter_not_stale_state(self, enricher):
        """Regression: enrich() must read blade format from its record parameter.

        A prior applies_to() call for a different record must not influence
        enrich(). Previously enrich() read blade format from a record stored
        by applies_to(), so enriching an AC-blade record after checking a
        DE-blade record wrongly produced format "DE".
        """
        de_record = {
            "razor": {"matched": {"brand": "Generic", "model": "Razor", "format": ""}},
            "blade": {"matched": {"format": "DE"}},
        }
        ac_record = {
            "razor": {"matched": {"brand": "Generic", "model": "Razor", "format": ""}},
            "blade": {"matched": {"format": "AC"}},
        }
        assert enricher.applies_to(de_record) is True
        result = enricher.enrich(ac_record["razor"], "", ac_record)
        assert result["format"] == "AC"
        assert result["_extraction_source"] == "blade_format"

    def test_enrich_with_no_record_falls_back_to_default(self, enricher):
        """enrich() with record=None has no blade format to read and falls back."""
        result = enricher.enrich({"matched": {"brand": "Generic", "format": ""}}, "", None)
        assert result["format"] == "DE"
        assert result["_extraction_source"] == "default"


class TestRazorFormatEnricherCartridgeDisposable:
    """Test Cartridge/Disposable format handling."""

    def test_cartridge_disposable_stays_as_is(self, enricher):
        """Test that Cartridge/Disposable format never changes."""
        record = {
            "razor": {
                "matched": {
                    "format": "Cartridge/Disposable",
                }
            },
            "blade": {
                "matched": {
                    "format": "DE",
                }
            },
        }
        enricher.applies_to(record)
        field_data = record["razor"]
        result = enricher.enrich(field_data, "", record)

        assert result is not None
        assert result["format"] == "Cartridge/Disposable"
        assert result["_enriched_by"] == "RazorFormatEnricher"
        assert result["_extraction_source"] == "catalog_data"


class TestRazorFormatEnricherShavette:
    """Test Shavette format handling."""

    def test_generic_shavette_with_ac_blade(self, enricher):
        """Test generic Shavette with AC blade becomes Shavette (AC)."""
        record = {
            "razor": {
                "matched": {
                    "format": "Shavette",
                }
            },
            "blade": {
                "matched": {
                    "format": "AC",
                }
            },
        }
        enricher.applies_to(record)
        field_data = record["razor"]
        result = enricher.enrich(field_data, "", record)

        assert result is not None
        assert result["format"] == "Shavette (AC)"
        assert result["_extraction_source"] == "blade_format_inference"

    def test_generic_shavette_with_de_blade(self, enricher):
        """Test generic Shavette with DE blade becomes Shavette (Half DE)."""
        record = {
            "razor": {
                "matched": {
                    "format": "Shavette",
                }
            },
            "blade": {
                "matched": {
                    "format": "DE",
                }
            },
        }
        enricher.applies_to(record)
        field_data = record["razor"]
        result = enricher.enrich(field_data, "", record)

        assert result is not None
        assert result["format"] == "Shavette (Half DE)"
        assert result["_extraction_source"] == "blade_format_inference"

    def test_generic_shavette_with_gem_blade(self, enricher):
        """Test generic Shavette with GEM blade becomes Shavette (GEM)."""
        record = {
            "razor": {
                "matched": {
                    "format": "Shavette",
                }
            },
            "blade": {
                "matched": {
                    "format": "GEM",
                }
            },
        }
        enricher.applies_to(record)
        field_data = record["razor"]
        result = enricher.enrich(field_data, "", record)

        assert result is not None
        assert result["format"] == "Shavette (GEM)"
        assert result["_extraction_source"] == "blade_format_inference"

    def test_generic_shavette_with_injector_blade(self, enricher):
        """Test generic Shavette with Injector blade becomes Shavette (Injector)."""
        record = {
            "razor": {
                "matched": {
                    "format": "Shavette",
                }
            },
            "blade": {
                "matched": {
                    "format": "Injector",
                }
            },
        }
        enricher.applies_to(record)
        field_data = record["razor"]
        result = enricher.enrich(field_data, "", record)

        assert result is not None
        assert result["format"] == "Shavette (Injector)"
        assert result["_extraction_source"] == "blade_format_inference"

    def test_generic_shavette_with_no_blade(self, enricher):
        """Test generic Shavette with no blade becomes Shavette (Unspecified)."""
        record = {
            "razor": {
                "matched": {
                    "format": "Shavette",
                }
            },
        }
        enricher.applies_to(record)
        field_data = record["razor"]
        result = enricher.enrich(field_data, "", record)

        assert result is not None
        assert result["format"] == "Shavette (Unspecified)"
        assert result["_extraction_source"] == "blade_format_inference"

    def test_generic_shavette_with_missing_blade_field(self, enricher):
        """Test generic Shavette with missing blade field becomes Shavette (Unspecified)."""
        record = {
            "razor": {
                "matched": {
                    "format": "Shavette",
                }
            },
        }
        enricher.applies_to(record)
        field_data = record["razor"]
        result = enricher.enrich(field_data, "", record)

        assert result is not None
        assert result["format"] == "Shavette (Unspecified)"
        assert result["_extraction_source"] == "blade_format_inference"

    def test_generic_shavette_with_blade_no_format(self, enricher):
        """Test generic Shavette with blade but no format becomes Shavette (Unspecified)."""
        record = {
            "razor": {
                "matched": {
                    "format": "Shavette",
                }
            },
            "blade": {
                "matched": {
                    "brand": "Feather",
                }
            },
        }
        enricher.applies_to(record)
        field_data = record["razor"]
        result = enricher.enrich(field_data, "", record)

        assert result is not None
        assert result["format"] == "Shavette (Unspecified)"
        assert result["_extraction_source"] == "blade_format_inference"

    def test_specific_shavette_ac_stays_as_is(self, enricher):
        """Test specific Shavette (AC) format stays as-is."""
        record = {
            "razor": {
                "matched": {
                    "format": "Shavette (AC)",
                }
            },
            "blade": {
                "matched": {
                    "format": "DE",
                }
            },
        }
        enricher.applies_to(record)
        field_data = record["razor"]
        result = enricher.enrich(field_data, "", record)

        assert result is not None
        assert result["format"] == "Shavette (AC)"
        assert result["_extraction_source"] == "catalog_data"

    def test_specific_shavette_de_stays_as_is(self, enricher):
        """Test specific Shavette (DE) format stays as-is."""
        record = {
            "razor": {
                "matched": {
                    "format": "Shavette (DE)",
                }
            },
            "blade": {
                "matched": {
                    "format": "AC",
                }
            },
        }
        enricher.applies_to(record)
        field_data = record["razor"]
        result = enricher.enrich(field_data, "", record)

        assert result is not None
        assert result["format"] == "Shavette (DE)"
        assert result["_extraction_source"] == "catalog_data"

    def test_case_insensitive_shavette(self, enricher):
        """Test case-insensitive matching for Shavette."""
        record = {
            "razor": {
                "matched": {
                    "format": "shavette",
                }
            },
            "blade": {
                "matched": {
                    "format": "AC",
                }
            },
        }
        enricher.applies_to(record)
        field_data = record["razor"]
        result = enricher.enrich(field_data, "", record)

        assert result is not None
        assert result["format"] == "Shavette (AC)"


class TestRazorFormatEnricherHalfDE:
    """Test Half DE format handling."""

    def test_half_de_stays_as_is(self, enricher):
        """Test Half DE format stays as-is."""
        record = {
            "razor": {
                "matched": {
                    "format": "Half DE",
                }
            },
            "blade": {
                "matched": {
                    "format": "DE",
                }
            },
        }
        enricher.applies_to(record)
        field_data = record["razor"]
        result = enricher.enrich(field_data, "", record)

        assert result is not None
        assert result["format"] == "Half DE"
        assert result["_extraction_source"] == "catalog_data"


class TestRazorFormatEnricherFallback:
    """Test fallback logic."""

    def test_de_blade_with_generic_razor(self, enricher):
        """Test DE blade with generic razor becomes DE."""
        record = {
            "razor": {
                "matched": {
                    "format": "Other",
                }
            },
            "blade": {
                "matched": {
                    "format": "DE",
                }
            },
        }
        enricher.applies_to(record)
        field_data = record["razor"]
        result = enricher.enrich(field_data, "", record)

        assert result is not None
        assert result["format"] == "DE"
        assert result["_extraction_source"] == "blade_format"

    def test_gem_blade_with_generic_razor(self, enricher):
        """Test GEM blade with generic razor becomes GEM."""
        record = {
            "razor": {
                "matched": {
                    "format": "Other",
                }
            },
            "blade": {
                "matched": {
                    "format": "GEM",
                }
            },
        }
        enricher.applies_to(record)
        field_data = record["razor"]
        result = enricher.enrich(field_data, "", record)

        assert result is not None
        assert result["format"] == "GEM"
        assert result["_extraction_source"] == "blade_format"

    def test_no_blade_format_has_razor_format(self, enricher):
        """Test no blade format but has razor format uses razor format."""
        record = {
            "razor": {
                "matched": {
                    "format": "Straight",
                }
            },
            "blade": {
                "matched": {
                    "brand": "Feather",
                }
            },
        }
        enricher.applies_to(record)
        field_data = record["razor"]
        result = enricher.enrich(field_data, "", record)

        assert result is not None
        assert result["format"] == "Straight"
        assert result["_extraction_source"] == "catalog_data"

    def test_no_blade_format_no_razor_format(self, enricher):
        """Test no blade format and no razor format defaults to DE."""
        record = {
            "razor": {
                "matched": {
                    "brand": "Gillette",
                }
            },
            "blade": {
                "matched": {
                    "brand": "Feather",
                }
            },
        }
        enricher.applies_to(record)
        field_data = record["razor"]
        result = enricher.enrich(field_data, "", record)

        assert result is not None
        assert result["format"] == "DE"
        assert result["_extraction_source"] == "default"

    def test_empty_razor_format_empty_blade_format(self, enricher):
        """Test empty razor format and empty blade format defaults to DE."""
        record = {
            "razor": {
                "matched": {
                    "format": "",
                }
            },
            "blade": {
                "matched": {
                    "format": "",
                }
            },
        }
        enricher.applies_to(record)
        field_data = record["razor"]
        result = enricher.enrich(field_data, "", record)

        assert result is not None
        assert result["format"] == "DE"
        assert result["_extraction_source"] == "default"
