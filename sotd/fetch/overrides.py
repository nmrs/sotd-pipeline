"""Manual include / exclude overrides for SOTD thread discovery.

YAML file ``thread_overrides.yaml`` in the run's data directory (see
``get_default_override_path``) with schema:

```yaml
include:
  2016-05-01:
    - https://www.reddit.com/r/Wetshaving/comments/...
exclude:
  2026-06-01:
    - https://www.reddit.com/r/Wetshaving/comments/1ttrafo/...
```
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, TypeVar
from urllib.parse import urlparse

from sotd.utils.data_dir import get_data_dir
from sotd.utils.yaml_loader import load_yaml_with_nfc

logger = logging.getLogger(__name__)


def _repo_root() -> Path:
    """Repo root, anchored at this file (``sotd/fetch/overrides.py``)."""
    return Path(__file__).resolve().parent.parent.parent


def get_default_override_path() -> Path:
    """Default thread-overrides path: ``<data dir>/thread_overrides.yaml``.

    The data dir is the run's data dir (``get_data_dir()``: ``--data-dir`` >
    ``SOTD_DATA_DIR`` env var > ``"data"``). A relative data dir is anchored
    at the repo root so the path does not depend on the process working
    directory — previously this was a bare CWD-relative
    ``Path("data/thread_overrides.yaml")``, so running fetch from any
    directory but the repo root silently dropped every include and exclude.
    """
    data_dir = get_data_dir()
    if not data_dir.is_absolute():
        data_dir = _repo_root() / data_dir
    return data_dir / "thread_overrides.yaml"


OVERRIDE_PATH = get_default_override_path()

_DATE_KEY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

T = TypeVar("T")


def extract_thread_id_from_url(url: str) -> Optional[str]:
    """Extract Reddit submission ID from a thread or comment permalink."""
    if not isinstance(url, str) or not url.strip():
        return None
    parsed = urlparse(url.strip())
    match = re.search(r"/comments/([a-z0-9]+)", parsed.path, re.IGNORECASE)
    if match:
        return match.group(1).lower()
    return None


def _date_key_to_str(date_key: Any) -> str:
    if hasattr(date_key, "isoformat"):
        return date_key.isoformat()
    return str(date_key)


def is_date_key(date_key: Any) -> bool:
    """Return True when *date_key* is a YYYY-MM-DD date."""
    return bool(_DATE_KEY_RE.match(_date_key_to_str(date_key)))


def warn_if_legacy_override_schema(data: Mapping[Any, Any], *, path: Path = OVERRIDE_PATH) -> None:
    """Warn when root-level date keys suggest a pre-migration override file."""
    legacy_keys = [k for k in data if is_date_key(k)]
    if legacy_keys:
        logger.warning(
            "Legacy thread override schema detected in %s "
            "(root date keys like %s). Move entries under include:/exclude:.",
            path,
            _date_key_to_str(legacy_keys[0]),
        )


def iter_month_urls(section: Mapping[Any, Any] | None, month: str) -> list[tuple[str, str]]:
    """Yield (date_str, url) pairs from a date→URL map for *month* (YYYY-MM)."""
    if not section:
        return []

    pairs: list[tuple[str, str]] = []
    for date_key, url_list in section.items():
        if not is_date_key(date_key):
            continue
        date_str = _date_key_to_str(date_key)
        if not date_str.startswith(month):
            continue
        if url_list is None:
            continue
        if isinstance(url_list, list):
            for url in url_list:
                if isinstance(url, str) and url.strip():
                    pairs.append((date_str, url.strip()))
        elif isinstance(url_list, str) and url_list.strip():
            pairs.append((date_str, url_list.strip()))
    return pairs


def load_thread_overrides_data(path: Path = OVERRIDE_PATH) -> dict[Any, Any]:
    """Load the overrides YAML file. Returns {} if missing or empty.

    A missing file is warned about (with the resolved path) instead of
    silently returning {}: the file is operator-authored match input, and a
    run that proceeds without it fetches without the manual includes and
    without dropping the excluded junk threads.
    """
    if not path.is_file():
        logger.warning(
            "Thread overrides file not found: %s — proceeding without "
            "include/exclude overrides",
            path,
        )
        return {}
    try:
        data = load_yaml_with_nfc(path)
    except Exception as e:
        logger.warning("Failed to load thread overrides from %s: %s", path, e)
        return {}
    if not data:
        return {}
    if not isinstance(data, dict):
        logger.warning("Thread overrides root must be a mapping in %s", path)
        return {}
    warn_if_legacy_override_schema(data, path=path)
    return data


def load_thread_exclude_ids(month: str, path: Path = OVERRIDE_PATH) -> set[str]:
    """Load bare submission IDs to exclude for *month* from YAML exclude URLs."""
    data = load_thread_overrides_data(path)
    exclude_section = data.get("exclude")
    if not isinstance(exclude_section, dict):
        return set()

    ids: set[str] = set()
    for _date_str, url in iter_month_urls(exclude_section, month):
        thread_id = extract_thread_id_from_url(url)
        if thread_id:
            ids.add(thread_id)
        else:
            logger.warning("Could not extract thread id from exclude URL: %s", url)
    return ids


def _thread_id(thread: Any) -> Optional[str]:
    if isinstance(thread, dict):
        tid = thread.get("id")
        return str(tid).lower() if tid is not None else None
    tid = getattr(thread, "id", None)
    return str(tid).lower() if tid is not None else None


def apply_thread_excludes(
    threads: Sequence[T],
    exclude_ids: set[str],
    *,
    debug: bool = False,
) -> list[T]:
    """Remove threads whose id appears in *exclude_ids* (PRAW or dict threads)."""
    if not exclude_ids:
        return list(threads)

    normalized = {eid.lower().removeprefix("t3_") for eid in exclude_ids}
    kept: list[T] = []
    for thread in threads:
        tid = _thread_id(thread)
        if tid is not None and tid.removeprefix("t3_") in normalized:
            if debug:
                logger.debug("Excluded thread override id %s", tid)
            continue
        kept.append(thread)
    return kept
