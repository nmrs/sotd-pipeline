"""JSON-based fetch phase - Complete implementation.

Phase 1: Authentication validation ✅
Phase 2: Thread discovery ✅
Phase 3: Comment fetching ✅

This implementation uses Reddit's public JSON endpoints instead of PRAW.
No OAuth or client credentials required - just HTTP GET requests.
"""

from __future__ import annotations

import argparse
import calendar
import logging
import sys
from datetime import datetime, timezone
from typing import Sequence

from tqdm import tqdm

from sotd.cli_utils.date_span import month_span
from sotd.fetch.merge import merge_records
from sotd.fetch.overrides import get_default_override_path
from sotd.fetch.save import load_month_file, write_month_file
from sotd.fetch_via_json.comments import fetch_comments_for_threads_json
from sotd.fetch_via_json.json_scraper import get_reddit_cookies, get_reddit_session
from sotd.fetch_via_json.search import search_threads_json
from sotd.utils.data_dir import get_data_dir
from sotd.utils.logging_config import setup_pipeline_logging, should_disable_tqdm

logger = logging.getLogger(__name__)


def get_parser() -> argparse.ArgumentParser:
    """Get argument parser for fetch_json phase."""
    parser = argparse.ArgumentParser(description="JSON-based Reddit fetch (no PRAW dependency)")

    # Date arguments (same as existing fetch phase)
    date_group = parser.add_mutually_exclusive_group()
    date_group.add_argument("--month", type=str, help="Single month in YYYY-MM format")
    date_group.add_argument("--year", type=int, help="All months in year YYYY")
    date_group.add_argument("--start", type=str, help="Start month in YYYY-MM format")
    date_group.add_argument("--end", type=str, help="End month in YYYY-MM format")
    date_group.add_argument("--range", type=str, help="Month range in YYYY-MM:YYYY-MM format")

    parser.add_argument(
        "--data-dir",
        type=str,
        default="data",
        help="Data directory (default: data, or SOTD_DATA_DIR env var)",
    )
    parser.add_argument("--force", action="store_true", help="Force re-fetch even if files exist")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument(
        "--parallel-comments",
        action="store_true",
        help="Use parallel processing for comment fetching",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=5,
        help="Max worker threads for parallel comment fetching (default: 5)",
    )
    parser.add_argument(
        "--skip-unchanged",
        action="store_true",
        help="Skip fetching comments for threads where num_comments hasn't increased. "
        "Risk: If a comment is deleted and a new one is added (same count), changes may be missed.",
    )

    return parser


def _process_month(
    year: int,
    month: int,
    args: argparse.Namespace,
) -> dict:
    """Fetch threads for one calendar month using JSON API."""
    cookies = get_reddit_cookies()

    if args.debug:
        logger.debug(f"Searching for threads in {year:04d}-{month:02d}")

    # Search for threads
    # Thread the --data-dir value to the overrides path so a custom data dir
    # gets its own include/exclude overrides (not the repo's data/ copy).
    override_path = get_default_override_path(args.data_dir)
    threads = search_threads_json(
        "wetshaving",
        year,
        month,
        debug=args.debug,
        cookies=cookies,
        override_path=override_path,
    )

    if args.debug:
        logger.debug(f"Found {len(threads)} valid threads")

    data_dir = get_data_dir(args.data_dir)
    threads_path = data_dir / "threads" / f"{year:04d}-{month:02d}.json"
    comments_path = data_dir / "comments" / f"{year:04d}-{month:02d}.json"

    if args.force:
        if threads_path.exists():
            threads_path.unlink()
        if comments_path.exists():
            comments_path.unlink()

    # Convert to thread records (same format as PRAW implementation)
    new_thread_records = [
        {
            "id": thread["id"],
            "title": thread["title"],
            "url": thread["url"],
            "author": thread["author"],
            "created_utc": thread["created_utc"],
            "num_comments": thread["num_comments"],
            "flair": thread.get("flair"),
        }
        for thread in threads
    ]

    # Merge with existing records (if any)
    existing_t = None if args.force else load_month_file(threads_path)
    merged_threads = (
        merge_records(existing_t[1], new_thread_records)
        if existing_t is not None
        else sorted(new_thread_records, key=lambda r: r["created_utc"])
    )

    if not merged_threads:
        logger.warning(f"No threads found for {year:04d}-{month:02d}; skipping file writes.")
        # Calculate missing days
        from datetime import date as _date

        from sotd.utils import parse_thread_date

        last_day = calendar.monthrange(year, month)[1]
        expected: set[_date] = {_date(year, month, d) for d in range(1, last_day + 1)}
        present: set[_date] = set()
        for t in threads:
            d = parse_thread_date(t["title"], year)
            if d is not None:
                present.add(d)
        missing = sorted(expected - present)

        return {
            "year": year,
            "month": month,
            "threads": 0,
            "comments": 0,
            "missing_days": [d.isoformat() for d in missing],
        }

    # Calculate missing days
    from datetime import date as _date

    from sotd.utils import parse_thread_date

    last_day = calendar.monthrange(year, month)[1]
    expected: set[_date] = {_date(year, month, d) for d in range(1, last_day + 1)}
    present: set[_date] = set()
    for t in merged_threads:
        d = parse_thread_date(t["title"], year)
        if d is not None:
            present.add(d)
    missing = sorted(expected - present)

    # Load existing data for skip-unchanged optimization
    existing_threads = None
    existing_comments = None
    if args.skip_unchanged and not args.force:
        existing_threads_data = load_month_file(threads_path)
        existing_comments_data = load_month_file(comments_path)
        if existing_threads_data:
            existing_threads = existing_threads_data[1]
        if existing_comments_data:
            existing_comments = existing_comments_data[1]

    # Fetch comments (Phase 3)
    if args.verbose:
        logger.info(f"Fetching comments for {len(merged_threads)} threads...")

    # Warning for skip-unchanged optimization
    if args.skip_unchanged:
        logger.warning(
            "Using --skip-unchanged optimization. "
            "Risk: If a comment is deleted and a new one is added (same count), changes may be missed."
        )

    cookies = get_reddit_cookies()
    session = get_reddit_session(cookies=cookies)

    comment_records = fetch_comments_for_threads_json(
        merged_threads,
        cookies=cookies,
        session=session,
        verbose=args.verbose,
        parallel=args.parallel_comments,
        max_workers=args.max_workers,
        skip_unchanged=args.skip_unchanged,
        existing_threads=existing_threads,
        existing_comments=existing_comments,
    )

    # Merge with existing comments
    existing_c = None if args.force else load_month_file(comments_path)
    merged_comments = (
        merge_records(existing_c[1], comment_records)
        if existing_c is not None
        else sorted(comment_records, key=lambda r: r["created_utc"])
    )

    # Write threads file
    ts_iso = datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()
    threads_meta = {
        "month": f"{year:04d}-{month:02d}",
        "extracted_at": ts_iso,
        "thread_count": len(merged_threads),
        "expected_days": calendar.monthrange(year, month)[1],
        "missing_days": [d.isoformat() for d in missing],
    }
    write_month_file(threads_path, threads_meta, merged_threads)

    # Write comments file
    threads_with_comments = {c["thread_id"] for c in merged_comments}
    comments_meta = {
        "month": threads_meta["month"],
        "extracted_at": ts_iso,
        "comment_count": len(merged_comments),
        "thread_count_with_comments": len(threads_with_comments),
        "missing_days": threads_meta["missing_days"],
        "threads_missing_comments": [
            t["id"] for t in merged_threads if t["id"] not in threads_with_comments
        ],
    }
    write_month_file(comments_path, comments_meta, merged_comments)

    if args.verbose:
        logger.info(
            f"Fetched {len(merged_threads)} threads, {len(merged_comments)} comments "
            f"for {year:04d}-{month:02d} ({len(missing)} missing days)"
        )

    # Print skip-unchanged statistics if enabled
    if args.skip_unchanged and not args.force and existing_threads:
        # Build lookup map for comparison
        existing_thread_map = {
            t.get("id"): t.get("num_comments", 0) for t in existing_threads if t.get("id")
        }
        existing_thread_ids = set(existing_thread_map.keys())

        # Calculate statistics
        total_threads = len(merged_threads)
        fetched_count = sum(
            1
            for t in merged_threads
            if t.get("id") in existing_thread_ids
            and t.get("num_comments", 0) > existing_thread_map.get(t.get("id"), 0)
        )
        skipped_count = sum(
            1
            for t in merged_threads
            if t.get("id") in existing_thread_ids
            and t.get("num_comments", 0) <= existing_thread_map.get(t.get("id"), 0)
        )
        new_threads_count = sum(1 for t in merged_threads if t.get("id") not in existing_thread_ids)

        if skipped_count > 0 or fetched_count < total_threads:
            logger.info(
                f"Skip-unchanged summary: "
                f"{fetched_count} threads fetched, "
                f"{skipped_count} threads skipped, "
                f"{new_threads_count} new threads"
            )

    return {
        "year": year,
        "month": month,
        "threads": len(merged_threads),
        "comments": len(merged_comments),
        "missing_days": [d.isoformat() for d in missing],
    }


def main(argv: Sequence[str] | None = None) -> int:
    """JSON-based fetch via Reddit's public JSON endpoints.

    This implementation:
    1. Searches Reddit using JSON API (no PRAW)
    2. Parses thread data from JSON responses
    3. Filters threads by date
    4. Fetches comments via JSON API
    5. Saves to same format as PRAW implementation

    No OAuth or client credentials required - uses public JSON endpoints.
    """
    # Setup logging
    setup_pipeline_logging(level=logging.INFO)

    try:
        parser = get_parser()
        args = parser.parse_args(argv)

        # Update logging level if debug is enabled
        if args.debug:
            logging.getLogger().setLevel(logging.DEBUG)

        # Compute month span
        months = month_span(args)

        if not months:
            logger.error("No months specified. Use --month, --year, --start/--end, or --range")
            return 1

        cookies = get_reddit_cookies()
        if not cookies:
            logger.warning("No cookie found. Using unauthenticated requests (10 QPM limit)")
            logger.info("Set REDDIT_SESSION_COOKIE for better rate limits (60+ QPM)")

        results = []
        for year, month in tqdm(months, desc="Months", unit="month", disable=should_disable_tqdm()):
            result = _process_month(year, month, args)
            results.append(result)

        # Print summary
        if len(results) == 1:
            res = results[0]
            year = res["year"]
            month = res["month"]
            missing_days = res["missing_days"]
            if args.verbose:
                logger.info(
                    f"JSON fetch complete for {year:04d}-{month:02d}: "
                    f"{res['threads']} threads, "
                    f"{len(missing_days)} missing day{'s' if len(missing_days) != 1 else ''}"
                )
        elif len(results) > 1:
            all_missing_days = sorted(d for res in results for d in (res.get("missing_days") or []))
            start_ym = results[0]["year"], results[0]["month"]
            end_ym = results[-1]["year"], results[-1]["month"]
            total_threads = sum(res["threads"] for res in results)
            total_missing = len(all_missing_days)

            if args.verbose:
                logger.info(
                    f"JSON fetch complete for "
                    f"{start_ym[0]:04d}-{start_ym[1]:02d}…{end_ym[0]:04d}-{end_ym[1]:02d}: "
                    f"{total_threads} threads, "
                    f"{total_missing} missing day{'s' if total_missing != 1 else ''}"
                )

        logger.info("JSON-based fetch complete! (Thread discovery + comment fetching)")
        return 0
    except KeyboardInterrupt:
        logger.info("Fetch phase interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Fetch phase failed: {e}")
        import traceback

        if args.debug if "args" in locals() else False:
            logger.debug("Full traceback:\n%s", traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main())
