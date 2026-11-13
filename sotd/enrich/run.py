import argparse
import json
import logging
from pathlib import Path
from typing import Optional, Sequence

from sotd.cli_utils.date_span import month_span
from sotd.enrich.cli import get_parser
from sotd.enrich.enrich import enrich_comments, setup_enrichers
from sotd.enrich.override_manager import EnrichmentOverrideManager
from sotd.enrich.save import calculate_enrichment_stats, load_matched_data, save_enriched_data
from sotd.utils.data_dir import get_data_dir
from sotd.utils.logging_config import setup_pipeline_logging
from sotd.utils.parallel_processor import create_parallel_processor
from sotd.utils.performance import PerformanceMonitor, PipelineOutputFormatter

logger = logging.getLogger(__name__)


def _process_month(
    year: int, month: int, base_path: Path, debug: bool, force: bool
) -> Optional[dict]:
    """Process enrichment for a single month."""
    ym = f"{year:04d}-{month:02d}"
    monitor = PerformanceMonitor("enrich")
    monitor.start_total_timing()
    in_path = base_path / "matched" / f"{year:04d}-{month:02d}.json"
    out_path = base_path / "enriched" / f"{year:04d}-{month:02d}.json"

    if not in_path.exists():
        return {
            "status": "error",
            "month": ym,
            "error": f"Missing input file: {in_path}. Run match phase first.",
        }

    # Check if output already exists and force is not set
    if out_path.exists() and not force:
        return {"status": "skipped", "month": ym, "reason": "output exists"}

    monitor.start_file_io_timing()
    try:
        original_metadata, comments = load_matched_data(in_path)
    except (FileNotFoundError, ValueError, json.JSONDecodeError, OSError) as e:
        monitor.end_file_io_timing()
        return {
            "status": "error",
            "month": ym,
            "error": f"Failed to load matched data from {in_path}: {e}",
        }
    monitor.end_file_io_timing()

    # Initialize enrichment override manager
    override_file_path = base_path / "enrichment_overrides.yaml"
    override_manager = EnrichmentOverrideManager(override_file_path)
    try:
        override_manager.load_overrides()
        if override_manager.has_overrides():
            logger.info("Loaded enrichment overrides from: %s", override_file_path)
    except Exception as e:
        logger.warning("Failed to load enrichment overrides from %s: %s", override_file_path, e)
        # Continue without overrides if file doesn't exist or has errors

    # Extract original comment texts for enrichment - optimized version
    original_comments = []
    for comment in comments:
        # Get the original comment text from the extracted field if available
        # This is the user's original input that we want to enrich from
        original_text = (
            comment.get("razor_extracted")
            or comment.get("blade_extracted")
            or comment.get("brush_extracted")
            or comment.get("soap_extracted")
            or ""
        )
        original_comments.append(original_text)
        # Add month to record metadata for override lookups
        comment["_month"] = ym

    # Setup enrichers with override manager and the run's data dir, so the
    # BrushEnricher's CatalogLoader reads handles.yaml/knots.yaml from the
    # configured data dir instead of CWD-relative Path("data").
    setup_enrichers(override_manager=override_manager, data_path=base_path)

    # Enrich the comments
    enriched_comments = enrich_comments(comments, original_comments)

    # Calculate enrichment statistics
    enrichment_stats = calculate_enrichment_stats(enriched_comments)

    monitor.set_record_count(len(enriched_comments))
    monitor.set_file_sizes(in_path, out_path)

    monitor.start_file_io_timing()
    save_enriched_data(
        out_path, enriched_comments, original_metadata, enrichment_stats, force=force
    )
    monitor.end_file_io_timing()
    monitor.end_total_timing()

    if debug:
        monitor.print_summary()
        logger.debug(f"Enriched {len(enriched_comments)} records for {ym}")
        logger.debug(f"  Blade enriched: {enrichment_stats['blade_enriched']}")
        logger.debug(f"  Razor enriched: {enrichment_stats['razor_enriched']}")
        logger.debug(f"  Brush enriched: {enrichment_stats['brush_enriched']}")
        logger.debug(f"  Soap enriched: {enrichment_stats['soap_enriched']}")

    return {
        "status": "completed",
        "month": ym,
        "records_processed": len(enriched_comments),
        **enrichment_stats,
        "performance": monitor.get_summary(),
    }


def run(args: argparse.Namespace) -> bool:
    """Run the enrich phase for the specified date range."""
    months = list(month_span(args))
    base_path = get_data_dir(args.data_dir)

    # Set up enrichers once at the start - this is a major performance optimization
    # Pass the resolved data dir so catalog-backed enrichers (BrushEnricher)
    # read from the run's data dir, not CWD-relative Path("data").
    setup_enrichers(data_path=base_path)

    # Create parallel processor for enrich phase
    processor = create_parallel_processor("enrich")

    # Determine if we should use parallel processing
    use_parallel = processor.should_use_parallel(months, args, args.debug)

    if use_parallel:
        # Get max workers for parallel processing
        max_workers = processor.get_max_workers(months, args, default=8)

        # Process months in parallel
        results = processor.process_months_parallel(
            months, _process_month, (base_path, args.debug, args.force), max_workers, "Processing"
        )

        # Print parallel processing summary
        processor.print_parallel_summary(results, "enrich")

    else:
        # Process months sequentially
        results = processor.process_months_sequential(
            months, _process_month, (base_path, args.debug, args.force), "Months"
        )

    # Filter out None results and check for errors
    valid_results = [r for r in results if r is not None]
    errors = [r for r in valid_results if "error" in r]
    skipped = [r for r in valid_results if r.get("status") == "skipped"]
    completed = [r for r in valid_results if r.get("status") == "completed"]

    # Display error details for failed months
    if errors:
        logger.error("\n❌ Error Details:")
        for error_result in errors:
            month = error_result.get("month", "unknown")
            error_msg = error_result.get("error", "unknown error")
            logger.error(f"  {month}: {error_msg}")

    if skipped:
        logger.warning("\n⚠️  Skipped Months:")
        for skipped_result in skipped:
            month = skipped_result.get("month", "unknown")
            reason = skipped_result.get("reason", "unknown reason")
            logger.warning(f"  {month}: {reason}")

    # Print summary using standardized formatter
    if not months:
        return len(errors) > 0
    if len(months) == 1:
        # Single month summary
        year, month = months[0]
        month_str = f"{year:04d}-{month:02d}"
        if completed:
            stats = completed[0]
            summary = PipelineOutputFormatter.format_single_month_summary(
                "enrich", month_str, stats
            )
            logger.info(summary)
    else:
        # Multi-month summary
        start_year, start_month = months[0]
        end_year, end_month = months[-1]
        start_str = f"{start_year:04d}-{start_month:02d}"
        end_str = f"{end_year:04d}-{end_month:02d}"

        total_stats = {
            "total_records": sum(r.get("records_processed", 0) for r in completed),
            "total_enriched": sum(r.get("total_enriched", 0) for r in completed),
        }
        summary = PipelineOutputFormatter.format_multi_month_summary(
            "enrich", start_str, end_str, total_stats
        )
        logger.info(summary)

    if args.debug and completed:
        logger.debug("\nEnrichment Summary:")
        total_records = sum(r.get("records_processed", 0) for r in completed)
        total_enriched = sum(r.get("total_enriched", 0) for r in completed)
        logger.debug(f"  Total records processed: {total_records}")
        logger.debug(f"  Total records enriched: {total_enriched}")

    # Return True if there were errors, False otherwise
    return len(errors) > 0


def main(argv: Sequence[str] | None = None) -> int:
    """Main CLI entry point for the enrich phase."""
    # Setup logging with timestamp format matching shell script
    setup_pipeline_logging(level=logging.INFO)

    try:
        parser = get_parser()
        args = parser.parse_args(argv)

        # Update logging level if debug is enabled
        if args.debug:
            logging.getLogger().setLevel(logging.DEBUG)

        has_errors = run(args)
        return 1 if has_errors else 0
    except KeyboardInterrupt:
        logger.info("Enrich phase interrupted by user")
        return 1  # Interrupted
    except Exception as e:
        logger.error(f"Enrich phase failed: {e}")
        return 1  # Error


if __name__ == "__main__":
    main()
