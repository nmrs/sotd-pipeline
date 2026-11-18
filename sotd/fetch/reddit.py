"""Reddit‐helpers: authentication, searching, comment harvesting – plus
a small `safe_call` wrapper that handles Reddit rate limits.
"""

from __future__ import annotations

import calendar
import logging
import os
import time
from datetime import date as _date
from pathlib import Path
from typing import List, Optional, Sequence, TypeVar, cast

import praw
from praw.models import Comment, Submission
from prawcore.exceptions import NotFound, RequestException, ResponseException

logger = logging.getLogger(__name__)


T = TypeVar("T")


# --------------------------------------------------------------------------- #
# rate-limit wrapper                                                          #
# --------------------------------------------------------------------------- #
RETRY_429_DELAYS = (1.0, 2.0, 4.0)  # exponential floor (seconds); Retry-After can only raise


def _429_wait(exc: BaseException) -> float | None:
    """Return Reddit's Retry-After seconds when *exc* carries a 429, else None.

    Detection is by the HTTP status on the carried response, not by exception
    class — any future praw/prawcore exception shape that wraps a 429 response
    is retried. An explicit ``retry_after``/``sleep_time`` attribute (set by
    tests and some praw versions) wins over the response header.
    """
    response = getattr(exc, "response", None)
    if getattr(response, "status_code", None) != 429:
        return None
    wait = getattr(exc, "retry_after", None)
    if wait is None:
        wait = getattr(exc, "sleep_time", None)
    if wait is None:
        wait = getattr(response, "headers", {}).get("retry-after")
    if wait is None:
        return 0.0
    try:
        return max(float(wait), 0.0)
    except (TypeError, ValueError):
        return 0.0


def safe_call(fn, *args, **kwargs):  # type: ignore[no-untyped-def]
    """Call *fn*, retrying 429s with exponential backoff.

    Any exception whose carried HTTP response has status 429 is retried —
    detection is by status code, not exception class, so future praw exception
    shapes need no new handling. Delays are the exponential floor
    1s/2s/4s (three retries, four attempts total); Reddit's Retry-After can
    only raise the floor. A 429 that survives all retries is re-raised.
    Non-429 HTTP statuses, network errors, and other failures are not retried:
    they log a warning and return None.
    """
    max_retries = len(RETRY_429_DELAYS)
    for attempt in range(max_retries + 1):
        try:
            call_start = time.time()
            result = fn(*args, **kwargs)
            call_duration = time.time() - call_start

            # Detect rate limits from slow response times (> 2 seconds)
            if call_duration > 2.0 and attempt > 0:
                logger.warning(f"Slow response detected ({call_duration:.1f}s); brief delay")
                time.sleep(5)  # Brief delay for slow responses
                continue

            return result

        except ResponseException as exc:
            header_wait = _429_wait(exc)
            if header_wait is None:
                logger.warning(f"Reddit API error: {exc}")
                return None
            if attempt >= max_retries:
                logger.warning(f"429 persisted after {max_retries} retries (max attempts reached)")
                raise
            delay = max(RETRY_429_DELAYS[attempt], header_wait)
            mins, secs = divmod(int(delay), 60)
            logger.warning(
                f"Reddit 429 (attempt {attempt + 1}/{max_retries + 1}); waiting {mins}m {secs}s…"
            )
            time.sleep(delay)

        except (ConnectionError, RuntimeError, RequestException, NotFound, ValueError) as exc:
            logger.warning(f"Reddit API error: {exc}")
            return None


# --------------------------------------------------------------------------- #
def _require_env(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise RuntimeError(f"Missing environment variable: {key}")
    return val


def get_reddit() -> praw.Reddit:  # noqa: D401
    """Return a PRAW instance using the section in praw.ini."""
    try:
        reddit = praw.Reddit()
        return reddit
    except Exception:
        raise


# --------------------------------------------------------------------------- #
# searching & filtering                                                       #
# --------------------------------------------------------------------------- #
def search_threads(
    subreddit_name: str,
    year: int,
    month: int,
    *,
    debug: bool = False,
    override_path: Optional[Path] = None,
) -> List[Submission]:
    reddit = get_reddit()
    subreddit = reddit.subreddit(subreddit_name)

    month_abbr = calendar.month_abbr[month].lower()
    month_name = calendar.month_name[month].lower()

    # Broad queries use month abbreviation only. Including the full month name
    # (e.g. "august") biases Reddit relevance toward titles like "Austere August
    # SOTD Thread" and can crowd regular "SOTD Thread - Aug NN" results out of
    # the 100-result window.
    # Day-specific fallback still uses both abbr and full name below.
    broad_queries = [
        f"flair:SOTD {month_abbr} {year}",
        f"flair:SOTD {month_abbr} {year}SOTD",
    ]

    all_results = {}
    hit_limit = False

    # Try broad searches first
    for query in broad_queries:
        if debug:
            logger.debug(f"Search query: {query!r}")
        raw_results = safe_call(subreddit.search, query, sort="relevance", syntax="lucene")
        if raw_results is None:
            raw_results = []
        raw_results = list(raw_results)
        if debug:
            logger.debug(f"PRAW raw results for {query!r}: {len(raw_results)}")

        # Check if we hit the 100-result limit (indicates there might be more results)
        if len(raw_results) >= 100:
            hit_limit = True
            if debug:
                logger.debug(f"Hit 100-result limit with {query!r}, will use day-specific searches")

        for sub in raw_results:
            all_results[sub.id] = sub  # dedupe by Reddit submission ID

    # Completeness check: relevance ranking can crowd days out of the broad
    # results without hitting the 100-result window, so always verify every
    # calendar day is present and day-search the gaps — the day-specific
    # fallback used to run only when a broad query hit the limit.
    if debug:
        logger.debug("Analyzing thread patterns to identify missing days")

    # First filter the broad results to only current year/month
    filtered_results = filter_valid_threads(
        list(all_results.values()), year, month, debug=debug
    )

    # Analyze filtered results to determine expected threads per day
    from collections import defaultdict

    from sotd.utils import parse_thread_date

    # Group filtered threads by day
    threads_by_day = defaultdict(list)
    for sub in filtered_results:
        d = parse_thread_date(sub.title, year)
        if d is not None and d.month == month:
            threads_by_day[d.day].append(sub)

    # Find the maximum number of threads per day
    max_threads_per_day = (
        max(len(threads) for threads in threads_by_day.values()) if threads_by_day else 0
    )
    # Floor at 2 only when the broad search was truncated: parallel daily
    # threads (Austere August + regular SOTD, Theme Thursday, etc.) are often
    # missing from the top-100 even when every calendar day already has one
    # hit. Otherwise one thread per day means the day is covered — a floor
    # of 2 here would day-search every day of a normal 1-thread/day month.
    expected_threads_per_day = max(max_threads_per_day, 2) if hit_limit else 1

    if debug:
        logger.debug(
            f"Found max {max_threads_per_day} threads per day "
            f"(expecting {expected_threads_per_day}"
            f"{' after hit-limit floor' if hit_limit else ''})"
        )
        for day in sorted(threads_by_day.keys()):
            count = len(threads_by_day[day])
            logger.debug(f"Day {day}: {count} threads")

    # Find days that are missing threads
    # For current month, only check up to current date
    from datetime import date

    today = date.today()
    is_current_month = year == today.year and month == today.month
    max_day_to_check = today.day if is_current_month else 31

    missing_days = []
    for day in range(
        1, max_day_to_check + 1
    ):  # Only check up to current date for current month
        current_count = len(threads_by_day[day])
        if current_count < expected_threads_per_day:
            missing_count = expected_threads_per_day - current_count
            missing_days.append((day, missing_count))
            if debug:
                logger.debug(
                    f"Day {day}: missing {missing_count} threads "
                    f"(has {current_count}, need {expected_threads_per_day})"
                )

    # Search for missing threads on specific days
    if missing_days:
        if debug:
            logger.debug(f"Searching for missing threads on {len(missing_days)} days")

        for day, missing_count in missing_days:
            day_queries = [
                f"flair:SOTD {month_abbr} {day:02d} {year}",
                f"flair:SOTD {month_abbr} {day} {year}",
                f"flair:SOTD {month_name} {day:02d} {year}",
                f"flair:SOTD {month_name} {day} {year}",
            ]

            for query in day_queries:
                if debug:
                    logger.debug(f"Missing thread query: {query!r}")
                raw_results = safe_call(
                    subreddit.search, query, sort="relevance", syntax="lucene"
                )
                if raw_results is None:
                    raw_results = []
                raw_results = list(raw_results)
                if debug:
                    logger.debug(f"PRAW raw results for {query!r}: {len(raw_results)}")

                for sub in raw_results:
                    all_results[sub.id] = sub  # dedupe by Reddit submission ID

    combined = list(all_results.values())
    if debug:
        logger.debug(f"Combined raw results (deduped): {len(combined)}")

    # Process thread overrides (includes)
    month_str = f"{year:04d}-{month:02d}"
    override_threads = process_thread_overrides(
        month_str, reddit, debug=debug, override_path=override_path
    )

    # Add override threads to results (existing deduplication will handle duplicates)
    for override_thread in override_threads:
        all_results[override_thread.id] = override_thread

    if debug and override_threads:
        logger.debug(f"Added {len(override_threads)} override threads")

    # Apply excludes from YAML before date filtering
    from sotd.fetch.overrides import (
        OVERRIDE_PATH,
        apply_thread_excludes,
        load_thread_exclude_ids,
    )

    exclude_ids = load_thread_exclude_ids(month_str, path=override_path or OVERRIDE_PATH)
    combined = apply_thread_excludes(list(all_results.values()), exclude_ids, debug=debug)
    if debug and exclude_ids:
        logger.debug(f"Applied {len(exclude_ids)} thread excludes")

    if debug:
        logger.debug(f"Combined results with overrides: {len(combined)}")

    valid = filter_valid_threads(combined, year, month, debug=debug)
    return valid


def filter_valid_threads(
    threads: Sequence[Submission], year: int, month: int, *, debug: bool = False
) -> List[Submission]:
    from datetime import datetime

    from sotd.utils import parse_thread_date

    kept: List[Submission] = []
    for sub in threads:
        d = parse_thread_date(sub.title, year)
        # --- CHANGED: Fallback to _override_date if present and title is unparsable ---
        if d is None and hasattr(sub, "_override_date"):
            try:
                d = datetime.strptime(sub._override_date, "%Y-%m-%d").date()
                if debug:
                    logger.debug(f"Used fallback date for {sub.title}: {d}")
            except Exception:
                d = None
        if d is None:
            if debug:
                logger.debug(f"Skip (no-date) {sub.title}")
            continue
        if (d.year, d.month) != (year, month):
            if debug:
                logger.debug(f"Skip (wrong-month) {sub.title}")
            continue
        kept.append(sub)

    # --- CHANGED: Sort using fallback date if present ---
    def sort_key(s):
        d = parse_thread_date(s.title, year)
        if d is None and hasattr(s, "_override_date"):
            try:
                d = datetime.strptime(s._override_date, "%Y-%m-%d").date()
            except Exception:
                d = None
        return d or _date.min

    kept.sort(key=sort_key)
    if debug:
        logger.debug(f"Valid threads:     {len(kept)}")
    return kept


# --------------------------------------------------------------------------- #
# comments                                                                    #
# --------------------------------------------------------------------------- #
def fetch_top_level_comments(submission: Submission) -> List[Comment]:
    """Return only root comments (shaves)."""
    safe_call(submission.comments.replace_more, limit=None)

    return cast(
        List[Comment],
        [c for c in submission.comments.list() if getattr(c, "is_root", False)],
    )


# --------------------------------------------------------------------------- #
# parallel comment fetching                                                   #
# --------------------------------------------------------------------------- #
def fetch_top_level_comments_parallel(
    submissions: Sequence[Submission],
    max_workers: int = 3,
    chunk_size: int = 1,
    timeout: int = 30,
    adaptive_workers: bool = False,
    fallback_to_sequential: bool = True,
    return_metrics: bool = False,
) -> List[List[Comment]] | tuple[List[List[Comment]], dict]:
    """Fetch top-level comments for multiple submissions in parallel.

    Args:
        submissions: List of Reddit submissions to fetch comments for
        max_workers: Maximum number of worker threads (default: 3)
        chunk_size: Number of submissions per worker chunk (default: 1)
        timeout: Timeout in seconds for each submission's fetch (default: 30).
            This is a per-future wait, NOT a budget for the whole batch — the
            batch always runs to completion and completed work is retained.
        adaptive_workers: Whether to adjust worker count based on rate limits
        fallback_to_sequential: Whether to fall back to sequential processing if parallel fails
        return_metrics: Whether to return performance metrics along with results

    Returns:
        List of comment lists (one per submission) or tuple of (results, metrics)
    """
    import concurrent.futures
    import time
    from typing import Tuple

    if not submissions:
        return ([], {}) if return_metrics else []

    # Initialize metrics
    start_time = time.time()
    rate_limit_hits = 0
    worker_utilization = 0.0

    def fetch_comments_worker(submission: Submission) -> Tuple[str, List[Comment]]:
        """Worker function to fetch comments for a single submission."""
        nonlocal rate_limit_hits

        try:
            # Use safe_call to handle rate limits properly
            comments = safe_call(fetch_top_level_comments, submission)
            if comments is None:
                # safe_call returned None due to error
                return (submission.id, [])
            return (submission.id, comments)
        except Exception as e:
            # Handle rate limits and other errors gracefully
            if "rate limit" in str(e).lower() or "429" in str(e):
                rate_limit_hits += 1
            logger.warning(f"Error fetching comments for {submission.id}: {e}")
            return (submission.id, [])

    # Determine optimal worker count
    if max_workers <= 0:
        if fallback_to_sequential:
            # Fall back to sequential processing
            sequential_results: List[List[Comment]] = []
            for submission in submissions:
                try:
                    comments = safe_call(fetch_top_level_comments, submission)
                    if comments is None:
                        sequential_results.append([])
                    else:
                        sequential_results.append(comments)
                except Exception as e:
                    logger.warning(f"Error in sequential fallback for {submission.id}: {e}")
                    sequential_results.append([])

            if return_metrics:
                total_time = time.time() - start_time
                metrics = {
                    "total_time": total_time,
                    "worker_utilization": 1.0,  # Sequential = 100% utilization
                    "rate_limit_hits": 0,
                    "processing_mode": "sequential_fallback",
                }
                return sequential_results, metrics
            return sequential_results
        else:
            raise ValueError("max_workers must be > 0 when fallback_to_sequential=False")

    # Adjust worker count based on rate limit frequency if adaptive
    if adaptive_workers and rate_limit_hits > 0:
        # Reduce workers if we're hitting rate limits
        adjusted_workers = max(1, max_workers - min(rate_limit_hits, max_workers - 1))
        if adjusted_workers != max_workers:
            logger.info(
                f"Adjusting workers from {max_workers} to {adjusted_workers} due to rate limits"
            )
            max_workers = adjusted_workers

    # Process submissions in parallel
    parallel_results: List[Optional[List[Comment]]] = [None] * len(
        submissions
    )  # Pre-allocate results list

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_index = {
                executor.submit(fetch_comments_worker, submission): i
                for i, submission in enumerate(submissions)
            }

            # Collect results as they complete. There is intentionally no
            # total-batch timeout here: as_completed(timeout=...) is a budget
            # for the ENTIRE batch, and exceeding it used to raise TimeoutError
            # that discarded completed work and re-fetched every submission
            # sequentially. Containment is per-future instead — a submission
            # that fails contributes [] but never aborts the batch. (Same
            # shape as community._fetch_comment_records.)
            completed_count = 0
            for future in concurrent.futures.as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    submission_id, comments = future.result(timeout=timeout)
                    parallel_results[index] = comments
                    completed_count += 1
                except concurrent.futures.TimeoutError:
                    logger.warning(
                        f"Timeout while fetching comments for submission at index {index}"
                    )
                    parallel_results[index] = []
                except Exception as e:
                    logger.warning(f"Exception in worker for submission at index {index}: {e}")
                    parallel_results[index] = []

            # Calculate worker utilization
            worker_utilization = completed_count / len(submissions) if submissions else 0.0

    except Exception as e:
        logger.warning(f"Parallel processing failed: {e}")
        if fallback_to_sequential:
            logger.info("Falling back to sequential processing")
            return fetch_top_level_comments_parallel(
                submissions,
                max_workers=0,
                fallback_to_sequential=True,
                return_metrics=return_metrics,
            )
        else:
            raise

    # Convert None values to empty lists and ensure proper typing
    final_results: List[List[Comment]] = [r if r is not None else [] for r in parallel_results]

    # Calculate final metrics
    total_time = time.time() - start_time

    if return_metrics:
        metrics = {
            "total_time": total_time,
            "worker_utilization": worker_utilization,
            "rate_limit_hits": rate_limit_hits,
            "processing_mode": "parallel",
            "submissions_processed": len(submissions),
            "successful_fetches": sum(1 for r in final_results if r),
            "average_time_per_submission": total_time / len(submissions) if submissions else 0.0,
        }
        return final_results, metrics

    return final_results


# --------------------------------------------------------------------------- #
# thread override functionality                                               #
# --------------------------------------------------------------------------- #


def load_thread_overrides(month: str, override_path: Optional[Path] = None) -> List[str]:
    """Load manual include URLs from YAML ``include`` section for *month*.

    Args:
        month: Month in YYYY-MM format (e.g., "2025-06")
        override_path: Explicit overrides file; defaults to the run's
            default overrides path (``--data-dir`` > ``SOTD_DATA_DIR`` >
            ``"data"``, anchored at the repo root).

    Returns:
        List of Reddit URLs for manual override threads
    """
    from sotd.fetch.overrides import (
        OVERRIDE_PATH,
        iter_month_urls,
        load_thread_overrides_data,
    )

    data = load_thread_overrides_data(override_path or OVERRIDE_PATH)
    include = data.get("include")
    if not isinstance(include, dict):
        return []
    return [url for _date_str, url in iter_month_urls(include, month)]


def validate_thread_override(url: str, reddit) -> Submission:
    """Validate a thread override URL with PRAW.

    Args:
        url: Reddit thread URL
        reddit: PRAW Reddit instance

    Returns:
        Submission object if valid

    Raises:
        ValueError: If thread is not found or not accessible
    """
    try:
        submission = reddit.submission(url=url)

        # Basic validation that thread exists and is accessible. A deleted
        # AUTHOR does not disqualify: hero-day threads outlive their authors
        # (account deleted, post and comments still live). Only a missing
        # title means the thread itself is gone.
        if not submission.title:
            raise ValueError(f"Thread not accessible: {url}")

        return submission
    except Exception as e:
        raise ValueError(f"Failed to fetch thread override: {url} - {e}")


def process_thread_overrides(
    month: str, reddit, debug: bool = False, override_path: Optional[Path] = None
) -> List[Submission]:
    """Load and validate include URLs from YAML for *month*."""
    from sotd.fetch.overrides import (
        OVERRIDE_PATH,
        iter_month_urls,
        load_thread_overrides_data,
    )

    data = load_thread_overrides_data(override_path or OVERRIDE_PATH)
    include = data.get("include")
    if not isinstance(include, dict):
        if debug:
            logger.debug(f"No thread overrides found for {month}")
        return []

    url_date_pairs = iter_month_urls(include, month)
    if not url_date_pairs:
        if debug:
            logger.debug(f"No thread overrides found for {month}")
        return []

    if debug:
        logger.debug(f"Processing {len(url_date_pairs)} thread overrides for {month}")

    valid_submissions = []

    for date_str, url in url_date_pairs:
        try:
            submission = validate_thread_override(url, reddit)
            # Attach the YAML date as _override_date for fallback
            setattr(submission, "_override_date", date_str)
            valid_submissions.append(submission)
            if debug:
                logger.debug(f"Validated override: {submission.title}")
        except ValueError as e:
            logger.warning(f"Failed to fetch thread override: {url} - {e}")
            continue

    if debug:
        logger.debug(
            f"Successfully processed {len(valid_submissions)}/{len(url_date_pairs)} overrides"
        )

    return valid_submissions
