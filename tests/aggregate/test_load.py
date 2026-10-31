#!/usr/bin/env python3
"""Tests for aggregate load: dedupe of duplicate enriched records by comment ID."""

import json
from pathlib import Path

import pytest

from sotd.aggregate.aggregators.core import aggregate_razors
from sotd.aggregate.load import dedupe_records_by_id, load_enriched_data
from sotd.aggregate.utils.metrics import calculate_metadata, calculate_shaves


def _record(comment_id, author="user1", razor=None):
    record = {"id": comment_id, "author": author}
    if razor is not None:
        record["razor"] = {"matched": {"brand": razor[0], "model": razor[1], "format": "DE"}}
    return record


class TestDedupeRecordsById:
    """Unit tests for dedupe_records_by_id."""

    def test_removes_duplicates_keeping_first(self):
        records = [
            _record("t1_aaa", razor=("Gillette", "Tech")),
            _record("t1_bbb", razor=("Fatip", "Grande")),
            _record("t1_aaa", razor=("Gillette", "Tech")),
        ]
        result = dedupe_records_by_id(records)
        assert [r["id"] for r in result] == ["t1_aaa", "t1_bbb"]

    def test_empty_list(self):
        assert dedupe_records_by_id([]) == []

    def test_records_without_id_are_kept(self):
        records = [{"author": "user1"}, {"author": "user1"}]
        assert dedupe_records_by_id(records) == records

    def test_none_id_records_are_kept(self):
        records = [_record(None), _record(None)]
        assert len(dedupe_records_by_id(records)) == 2

    def test_first_occurrence_wins(self):
        records = [_record("t1_aaa", author="user1"), _record("t1_aaa", author="user2")]
        result = dedupe_records_by_id(records)
        assert len(result) == 1
        assert result[0]["author"] == "user1"

    def test_non_dict_records_are_kept(self):
        records = [_record("t1_aaa"), "not-a-record", _record("t1_aaa")]
        assert dedupe_records_by_id(records) == [_record("t1_aaa"), "not-a-record"]


class TestLoadEnrichedDataDedupe:
    """load_enriched_data must dedupe a month file that repeats comment records."""

    def _write_month_file(self, tmp_path: Path, records, wrapped: bool):
        enriched_dir = tmp_path / "enriched"
        enriched_dir.mkdir()
        payload = {"data": records} if wrapped else records
        (enriched_dir / "2020-01.json").write_text(json.dumps(payload))
        return tmp_path

    def test_dedupes_wrapped_format(self, tmp_path):
        records = [_record("t1_aaa"), _record("t1_bbb"), _record("t1_aaa")]
        data_dir = self._write_month_file(tmp_path, records, wrapped=True)
        assert [r["id"] for r in load_enriched_data("2020-01", data_dir)] == [
            "t1_aaa",
            "t1_bbb",
        ]

    def test_dedupes_direct_list_format(self, tmp_path):
        records = [_record("t1_aaa"), _record("t1_aaa")]
        data_dir = self._write_month_file(tmp_path, records, wrapped=False)
        assert len(load_enriched_data("2020-01", data_dir)) == 1

    def test_distinct_records_untouched(self, tmp_path):
        records = [_record("t1_aaa"), _record("t1_bbb")]
        data_dir = self._write_month_file(tmp_path, records, wrapped=True)
        assert len(load_enriched_data("2020-01", data_dir)) == 2


class TestDuplicateRecordDoesNotInflateCounts:
    """End to end: one duplicated enriched record leaves shaves/total_shaves unchanged."""

    def test_shaves_and_total_shaves_unchanged(self, tmp_path):
        records = [
            _record("t1_aaa", razor=("Gillette", "Tech")),
            _record("t1_bbb", razor=("Fatip", "Grande")),
            _record("t1_aaa", razor=("Gillette", "Tech")),  # duplicated month file entry
        ]
        enriched_dir = tmp_path / "enriched"
        enriched_dir.mkdir()
        (enriched_dir / "2020-01.json").write_text(json.dumps({"data": records}))

        loaded = load_enriched_data("2020-01", tmp_path)
        assert calculate_shaves(loaded) == 2
        metadata = calculate_metadata(loaded, "2020-01")
        assert metadata["total_shaves"] == 2

        razor_rows = aggregate_razors(loaded)
        tech_row = next(r for r in razor_rows if r["name"] == "Gillette Tech")
        assert tech_row["shaves"] == 1


class TestAnnualEngineDedupe:
    """AnnualAggregationEngine._load_enriched_records dedupes by comment ID too."""

    def test_load_enriched_records_dedupes(self, tmp_path):
        import sys
        import types

        if "tqdm" not in sys.modules:
            # annual_engine imports tqdm and psutil at module level; stub them so
            # the test can run where those optional dependencies are not installed.
            tqdm_stub = types.ModuleType("tqdm")
            tqdm_stub.tqdm = lambda iterable=None, *a, **k: (
                iterable if iterable is not None else iter(())
            )
            sys.modules["tqdm"] = tqdm_stub
        if "psutil" not in sys.modules:
            psutil_stub = types.ModuleType("psutil")

            class _Mem:
                rss = 0

            class _Proc:
                def memory_info(self):
                    return _Mem()

            psutil_stub.Process = lambda: _Proc()
            sys.modules["psutil"] = psutil_stub

        from sotd.aggregate.annual_engine import AnnualAggregationEngine

        records = [_record("t1_aaa"), _record("t1_bbb"), _record("t1_aaa")]
        enriched_dir = tmp_path / "enriched"
        enriched_dir.mkdir()
        (enriched_dir / "2020-01.json").write_text(json.dumps({"data": records}))
        (enriched_dir / "2020-02.json").write_text(json.dumps(records))

        engine = AnnualAggregationEngine("2020", tmp_path)
        loaded = engine._load_enriched_records()
        assert sorted(r["id"] for r in loaded) == ["t1_aaa", "t1_bbb"]
