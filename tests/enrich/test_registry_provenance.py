"""Provenance collision in EnricherRegistry.enrich_record (#25(c)).

When several enrichers fire on one field, the registry merged their results
with dict.update(), so only the LAST enricher's ``_enriched_by`` /
``_extraction_source`` stamps survived in the saved record (Game Changer +
RazorFormat both fire, the record named only RazorFormatEnricher). The soap
enrichers stamp no provenance at all, so their records carried none.
"""

from sotd.enrich.game_changer_enricher import GameChangerEnricher
from sotd.enrich.razor_format_enricher import RazorFormatEnricher
from sotd.enrich.registry import EnricherRegistry
from sotd.enrich.soap_mashup_enricher import SoapMashupEnricher
from sotd.enrich.soap_sample_enricher import SoapSampleEnricher


def _game_changer_record():
    return {
        "razor": {
            "original": "RazoRock Game Changer .84",
            "normalized": "razorock game changer .84",
            "matched": {"brand": "RazoRock", "model": "Game Changer", "format": "DE"},
        },
        "blade": {
            "original": "Feather",
            "normalized": "feather",
            "matched": {"brand": "Feather", "model": "Hi-Stainless", "format": "DE"},
        },
        "razor_extracted": "RazoRock Game Changer .84",
        "blade_extracted": "Feather",
    }


def test_two_razor_enrichers_both_named_in_provenance():
    """Both contributing enrichers are named; neither stamp overwrites."""
    registry = EnricherRegistry()
    registry.register(GameChangerEnricher())
    registry.register(RazorFormatEnricher())

    enriched = registry.enrich_record(_game_changer_record(), "RazoRock Game Changer .84")
    razor_enriched = enriched["razor"]["enriched"]

    # Both findings survive the merge ...
    assert razor_enriched["gap"] == ".84"
    assert razor_enriched["format"] == "DE"
    # ... and so does both enrichers' provenance, in registration order.
    assert razor_enriched["_enriched_by"] == ["GameChangerEnricher", "RazorFormatEnricher"]
    assert razor_enriched["_extraction_source"] == ["user_comment", "blade_format"]


def test_soap_enrichers_without_stamps_are_named():
    """Enrichers that stamp no provenance are still named by the registry."""
    registry = EnricherRegistry()
    registry.register(SoapSampleEnricher())
    registry.register(SoapMashupEnricher())

    record = {
        "soap": {
            "original": "Soap mashup (sample)",
            "normalized": "soap mashup",
            "matched": {"brand": "Unknown", "scent": "Smush"},
        },
        "soap_extracted": "Soap mashup (sample)",
    }
    enriched = registry.enrich_record(record, "Soap mashup (sample)")
    soap_enriched = enriched["soap"]["enriched"]

    assert soap_enriched["sample_type"] == "sample"
    assert soap_enriched["is_mashup"] is True
    assert soap_enriched["_enriched_by"] == ["SoapSampleEnricher", "SoapMashupEnricher"]
    # Neither soap enricher stamps a source; none is invented.
    assert "_extraction_source" not in soap_enriched


def test_single_enricher_keeps_string_provenance():
    """One contributor keeps the historical plain-string provenance shape."""
    registry = EnricherRegistry()
    registry.register(RazorFormatEnricher())

    record = {
        "razor": {"matched": {"format": "Shavette"}},
        "blade": {"matched": {"format": "AC"}},
    }
    enriched = registry.enrich_record(record, "")
    razor_enriched = enriched["razor"]["enriched"]

    assert razor_enriched["format"] == "Shavette (AC)"
    assert razor_enriched["_enriched_by"] == "RazorFormatEnricher"
    assert razor_enriched["_extraction_source"] == "blade_format_inference"
