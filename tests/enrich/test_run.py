"""Tests for the enrich phase runner (sotd/enrich/run.py)."""

import json

from sotd.enrich.run import _process_month


def _write_matched_month(base_path, record):
    matched_dir = base_path / "matched"
    matched_dir.mkdir(parents=True, exist_ok=True)
    (matched_dir / "2026-01.json").write_text(
        json.dumps({"meta": {"month": "2026-01"}, "data": [record]})
    )


def _read_saved_record(base_path):
    saved = json.loads((base_path / "enriched" / "2026-01.json").read_text())
    assert len(saved["data"]) == 1
    return saved["data"][0]


def test_process_month_strips_month_stamp_from_saved_records(tmp_path):
    """_month is stamped for override lookups and must not leak into the
    saved enriched file."""
    record = {
        "id": "t1",
        "author": "tester",
        "created_utc": "2026-01-05T12:00:00",
        "razor": {"brand": "Test", "model": "Razor", "original": "Test Razor"},
        "razor_extracted": "Test Razor",
    }
    _write_matched_month(tmp_path, record)

    result = _process_month(2026, 1, tmp_path, debug=False, force=True)

    assert result["status"] == "completed"
    saved = _read_saved_record(tmp_path)
    assert "_month" not in saved
    # Everything else survives unchanged.
    assert saved["id"] == "t1"
    assert saved["razor"]["original"] == "Test Razor"


def test_process_month_override_still_sees_month_during_enrichment(tmp_path):
    """Guard against over-stripping: the _month stamp must still be present
    while enrichers run, so a month-scoped override applies."""
    (tmp_path / "enrichment_overrides.yaml").write_text(
        """
2026-01:
  m99b8f9:
    brush:
      fiber: "Mixed Badger/Horse"
      knot_size_mm: 28.0
"""
    )
    record = {
        "id": "m99b8f9",
        "_month": "2026-01",
        "brush": {
            "matched": {
                "brand": "Vie-Long",
                "model": "Mixed Badger & Horse",
                "knot": {
                    "brand": "Vie-Long",
                    "model": "Mixed Badger & Horse",
                    "fiber": "Mixed Badger/Horse",
                    "knot_size_mm": 21.0,
                },
            }
        },
        "brush_extracted": "Vielong Mixed Hair BADGER",
    }
    _write_matched_month(tmp_path, record)

    result = _process_month(2026, 1, tmp_path, debug=False, force=True)

    assert result["status"] == "completed"
    saved = _read_saved_record(tmp_path)
    assert "_month" not in saved
    # The month-scoped override fired during enrichment.
    assert saved["brush"]["enriched"]["fiber"] == "Mixed Badger/Horse"
    assert saved["brush"]["enriched"]["knot_size_mm"] == 28.0
