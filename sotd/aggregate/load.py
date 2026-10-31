import json
import logging
from pathlib import Path
from typing import Any

from sotd.utils.file_io import load_json_data

logger = logging.getLogger(__name__)


def dedupe_records_by_id(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove duplicate enriched comment records by comment ID.

    Recovered or re-fetched month files can contain the same comment record
    more than once; without deduplication every aggregated table and
    ``total_shaves`` is silently inflated. Keeps the first occurrence,
    preserves order, and keeps records that carry no ID (they cannot be
    proven duplicates).
    """
    seen_ids: set[Any] = set()
    deduped: list[dict[str, Any]] = []
    for record in records:
        record_id = record.get("id") if isinstance(record, dict) else None
        if not record_id:
            deduped.append(record)
            continue
        if record_id in seen_ids:
            continue
        seen_ids.add(record_id)
        deduped.append(record)
    dropped = len(records) - len(deduped)
    if dropped:
        logger.debug(f"Dropped {dropped} duplicate enriched record(s) by comment ID")
    return deduped


def load_enriched_data(month: str, data_dir: Path) -> list[dict[str, Any]]:
    """Load enriched SOTD data for a given month from JSON file.
    Returns a list of enriched comment records.
    Raises FileNotFoundError if the file does not exist.
    Raises ValueError if the file is malformed or missing required fields.
    """
    file_path = data_dir / "enriched" / f"{month}.json"
    if not file_path.exists():
        raise FileNotFoundError(f"Enriched data file not found: {file_path}")

    try:
        content = load_json_data(file_path)
    except (json.JSONDecodeError, OSError) as e:
        # Re-raise with the same error messages expected by tests
        if isinstance(e, json.JSONDecodeError):
            raise ValueError(f"Malformed JSON in {file_path}: {e}")
        else:
            raise e

    # Handle both direct list format and wrapped format with 'data' key
    if isinstance(content, list):
        data = content
    elif isinstance(content, dict) and "data" in content:
        data = content["data"]
    else:
        raise ValueError(f"Expected a list of records or dict with 'data' key in {file_path}")

    if not isinstance(data, list):
        raise ValueError(f"Expected a list of records in {file_path}")

    # Type assertion to help type checker understand data is a list
    data_list: list[dict[str, Any]] = data

    # Basic validation: check for required fields in at least one record
    if data_list and not isinstance(data_list[0], dict):  # type: ignore
        raise ValueError(f"Malformed record structure in {file_path}")
    # Recovered or re-fetched month files can repeat the same comment records;
    # deduplicate by comment ID so no table or total_shaves is inflated.
    return dedupe_records_by_id(data_list)
