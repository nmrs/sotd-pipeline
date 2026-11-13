"""Tests for the enrich phase CLI and main functionality."""

import json
from pathlib import Path
from unittest.mock import patch
import argparse

import pytest

from sotd.enrich.enrich import enrich_comments, setup_enrichers
from sotd.enrich.run import _process_month, main, run


def test_setup_enrichers():
    """Test that all enrichers are properly registered."""
    setup_enrichers()
    # This should not raise any exceptions


def _brush_enricher():
    """Return the registered BrushEnricher (setup_enrichers must have run)."""
    from sotd.enrich.brush_enricher import BrushEnricher
    from sotd.enrich.registry import enricher_registry

    for enricher in enricher_registry.get_all_enrichers():
        if isinstance(enricher, BrushEnricher):
            return enricher
    raise AssertionError("BrushEnricher not registered")


def _handles_yaml(brand="ReproBrand", model="ReproModel", knot_size_mm=26):
    return (
        "artisan_handles:\n"
        f"  {brand}:\n"
        f"    {model}:\n"
        "      patterns:\n"
        "        - 'repro.*handle'\n"
        f"      knot_size_mm: {knot_size_mm}\n"
    )


def _matched_brush_record():
    """Composite brush record with no knot size anywhere but the handle defaults."""
    return {
        "id": "c1",
        "brush": {
            "original": "ReproBrand ReproModel with ReproKnot",
            "normalized": "ReproBrand ReproModel with ReproKnot",
            "matched": {
                "handle": {
                    "brand": "ReproBrand",
                    "model": "ReproModel",
                    "source_text": "ReproBrand ReproModel",
                },
                "knot": {
                    "brand": "ReproKnot",
                    "model": "ReproKnotModel",
                    "source_text": "ReproKnot",
                },
            },
        },
        "brush_extracted": "ReproBrand ReproModel with ReproKnot",
    }


def test_setup_enrichers_data_path_repoints_brush_catalog_loader(tmp_path):
    """setup_enrichers(data_path=...) must point the BrushEnricher's
    CatalogLoader at that dir (not CWD-relative Path("data")).

    Regression test for #23 instance 2: setup_enrichers() hardcoded
    data_path=None, so from any CWD but the repo root the loader silently
    found no handles.yaml/knots.yaml and brush inference degraded to empty.
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "handles.yaml").write_text(_handles_yaml())
    (data_dir / "knots.yaml").write_text(
        "known_knots:\n  ReproKnot:\n    ReproKnotModel:\n      patterns:\n        - 'repro.*knot'\n"
    )

    setup_enrichers(data_path=data_dir)
    try:
        brush = _brush_enricher()
        assert brush.catalog_loader.data_path == data_dir
        assert brush.catalog_loader.load_handle_patterns(
            "ReproBrand", "ReproModel"
        ) == ["repro.*handle"]
        assert brush.catalog_loader.load_handle_maker_defaults(
            "ReproBrand", "ReproModel"
        ) == {"knot_size_mm": 26}
    finally:
        # Restore the shared loader to the repo default so later tests in
        # this process see the real catalogs again.
        _brush_enricher().catalog_loader.set_data_path(Path("data"))


def test_process_month_uses_data_dir_for_brush_catalogs(tmp_path, monkeypatch):
    """_process_month must enrich from the run's data dir even when the
    process CWD has no data/ directory.

    End-to-end regression test for #23 instance 2: with handles.yaml in the
    run's data dir only, the handle-maker knot-size inference must fire.
    On unmodified code the loader read CWD-relative ./data, found nothing,
    and the record enriched with knot_size_mm absent.
    """
    base_path = tmp_path / "data"
    work_dir = tmp_path / "work"
    (base_path / "matched").mkdir(parents=True)
    work_dir.mkdir()
    (base_path / "handles.yaml").write_text(_handles_yaml())
    (base_path / "knots.yaml").write_text(
        "known_knots:\n  ReproKnot:\n    ReproKnotModel:\n      patterns:\n        - 'repro.*knot'\n"
    )
    (base_path / "matched" / "2025-01.json").write_text(
        json.dumps({"meta": {"month": "2025-01"}, "data": [_matched_brush_record()]})
    )

    monkeypatch.chdir(work_dir)
    assert not (work_dir / "data").exists()

    try:
        result = _process_month(2025, 1, base_path, debug=False, force=True)
        assert result["status"] == "completed"
        out = json.loads((base_path / "enriched" / "2025-01.json").read_text())
        enriched = out["data"][0]["brush"]["enriched"]
        assert enriched["knot_size_mm"] == 26
        assert enriched["_extraction_source"] == "handle_maker_default"
        assert enriched["_handle_maker_inference"] == "ReproBrand"
    finally:
        _brush_enricher().catalog_loader.set_data_path(Path("data"))


def test_enrich_comments_basic():
    """Test basic enrichment functionality."""
    comments = [
        {
            "comment_id": "test1",
            "blade": {
                "original": "Feather blade (3rd use)",
                "normalized": "Feather blade",
                "matched": {"brand": "Feather", "model": "Hi-Stainless"},
            },
            "razor": {
                "original": "RazoRock Game Changer .84",
                "normalized": "RazoRock Game Changer",
                "matched": {"brand": "RazoRock", "model": "Game Changer"},
            },
            "blade_extracted": "Feather blade (3rd use)",
            "razor_extracted": "RazoRock Game Changer .84",
        }
    ]
    original_comments = ["Feather blade (3rd use), RazoRock Game Changer .84"]

    enriched = enrich_comments(comments, original_comments)

    assert len(enriched) == 1
    # Check for unified structure: enriched data under product fields
    assert "enriched" in enriched[0]["blade"]
    # Should have blade enrichment (use count)
    assert "use_count" in enriched[0]["blade"]["enriched"]


def test_process_month_missing_file(tmp_path):
    """Test processing a month with missing input file."""
    base_path = Path(tmp_path)
    result = _process_month(2025, 1, base_path, debug=True, force=False)
    assert result is not None
    assert result["status"] == "error"
    assert result["month"] == "2025-01"
    assert "Missing input file" in result["error"]


def test_process_month_invalid_json(tmp_path):
    """Test processing a month with invalid JSON."""
    base_path = Path(tmp_path)
    matched_dir = base_path / "matched"
    matched_dir.mkdir(parents=True)

    # Create invalid JSON file
    invalid_file = matched_dir / "2025-01.json"
    invalid_file.write_text("invalid json")

    result = _process_month(2025, 1, base_path, debug=True, force=False)
    assert result is not None
    assert result["status"] == "error"
    assert result["month"] == "2025-01"
    assert "Failed to load matched data" in result["error"]


def test_process_month_valid_data(tmp_path):
    """Test processing a month with valid data."""
    base_path = Path(tmp_path)
    matched_dir = base_path / "matched"
    matched_dir.mkdir(parents=True)

    # Create valid matched data
    matched_data = {
        "meta": {"month": "2025-01"},
        "data": [
            {
                "comment_id": "test1",
                "blade": {
                    "original": "Feather blade (3rd use)",
                    "normalized": "Feather blade",
                    "matched": {"brand": "Feather", "model": "Hi-Stainless"},
                },
                "razor": {
                    "original": "RazoRock Game Changer .84",
                    "normalized": "RazoRock Game Changer",
                    "matched": {"brand": "RazoRock", "model": "Game Changer"},
                },
                "blade_extracted": "Feather blade (3rd use)",
                "razor_extracted": "RazoRock Game Changer .84",
            }
        ],
    }

    matched_file = matched_dir / "2025-01.json"
    with matched_file.open("w") as f:
        json.dump(matched_data, f, ensure_ascii=False)

    result = _process_month(2025, 1, base_path, debug=True, force=False)

    assert result is not None
    assert result["month"] == "2025-01"
    assert result["records_processed"] == 1

    # Check that output file was created
    enriched_file = base_path / "enriched" / "2025-01.json"
    assert enriched_file.exists()


def test_main_cli_help():
    """Test that the CLI help works."""
    with patch("sys.argv", ["test", "--help"]):
        with pytest.raises(SystemExit):
            main()


def test_run_with_no_months():
    """Test running with no valid months."""
    with patch("sotd.enrich.run.month_span") as mock_span:
        mock_span.return_value = []

        args = argparse.Namespace(month="2025-05", data_dir="data", debug=True, force=False)

        # Should not raise any exceptions
        run(args)
