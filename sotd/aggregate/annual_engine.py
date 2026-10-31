"""
Annual aggregation engine for the SOTD Pipeline.

This module provides annual aggregation functionality by combining 12 months
of aggregated data into yearly summaries.
"""

import logging
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd
from tqdm import tqdm

from ..utils.logging_config import should_disable_tqdm
from ..utils.performance_base import BasePerformanceMetrics, BasePerformanceMonitor
from .aggregators.annual_aggregator import (
    aggregate_annual_blades,
    aggregate_annual_brushes,
    aggregate_annual_razor_blade_combinations,
    aggregate_annual_razors,
    aggregate_annual_soaps,
)
from .annual_loader import load_annual_data

logger = logging.getLogger(__name__)


@dataclass
class AnnualPerformanceMetrics(BasePerformanceMetrics):
    """Performance metrics for annual aggregation."""

    # Annual-specific fields
    year: str = field(default="")
    data_loading_time: float = field(default=0.0)
    aggregation_time: float = field(default=0.0)
    month_count: int = field(default=0)
    total_shaves: int = field(default=0)
    unique_shavers: int = field(default=0)

    def to_dict(self) -> Dict:
        """Convert metrics to dictionary for JSON serialization."""
        base_dict = super().to_dict()
        base_dict.update(
            {
                "year": self.year,
                "data_loading_time_seconds": self.data_loading_time,
                "aggregation_time_seconds": self.aggregation_time,
                "month_count": self.month_count,
                "total_shaves": self.total_shaves,
                "unique_shavers": self.unique_shavers,
            }
        )
        return base_dict


class AnnualPerformanceMonitor(BasePerformanceMonitor):
    """Performance monitor for annual aggregation."""

    def __init__(self, year: str, parallel_workers: int = 1):
        self.year = year
        super().__init__("annual_aggregation", parallel_workers)
        # Type annotation to help type checker
        self.metrics: AnnualPerformanceMetrics = self.metrics

    def _create_metrics(self, phase_name: str, parallel_workers: int) -> AnnualPerformanceMetrics:
        """Create annual performance metrics."""
        metrics = AnnualPerformanceMetrics()
        metrics.year = self.year
        metrics.phase_name = phase_name
        metrics.parallel_workers = parallel_workers
        return metrics

    def print_summary(self) -> None:
        """Print a human-readable performance summary."""
        metrics = self.metrics
        logger.info(f"\n=== Annual Aggregation Performance Summary ({metrics.year}) ===")
        logger.info(f"Total Processing Time: {metrics.total_processing_time:.2f}s")
        logger.info(f"Data Loading Time: {metrics.data_loading_time:.2f}s")
        logger.info(f"Aggregation Time: {metrics.aggregation_time:.2f}s")
        logger.info(f"File I/O Time: {metrics.file_io_time:.2f}s")
        logger.info(f"Months Processed: {metrics.month_count}")
        logger.info(f"Total Shaves: {metrics.total_shaves:,}")
        logger.info(f"Unique Shavers: {metrics.unique_shavers:,}")
        logger.info(f"Peak Memory Usage: {metrics.peak_memory_mb:.1f}MB")
        logger.info(f"Input File Size: {metrics.input_file_size_mb:.1f}MB")
        logger.info(f"Output File Size: {metrics.output_file_size_mb:.1f}MB")


class AnnualAggregationEngine:
    """Engine for aggregating monthly data into annual summaries."""

    def __init__(self, year: str, data_dir: Path):
        """
        Initialize the annual aggregation engine.

        Args:
            year: Year to process (YYYY format)
            data_dir: Data directory containing monthly aggregated files
        """
        if not year.isdigit():
            raise ValueError("Year must be numeric")
        if len(year) != 4:
            raise ValueError("Year must be in YYYY format")

        self.year = year
        self.data_dir = data_dir
        self.monitor = AnnualPerformanceMonitor(year)
        self._cached_enriched_records: Optional[List[Dict[str, Any]]] = (
            None  # Cache for enriched records
        )

    def aggregate_razors(self, monthly_data: Dict[str, Dict]) -> List[Dict[str, Any]]:
        """
        Aggregate razor data from monthly data.

        Args:
            monthly_data: Dictionary of monthly data keyed by month

        Returns:
            List of aggregated razor data sorted by shaves desc, unique_users desc
        """
        result = aggregate_annual_razors(monthly_data)
        # Recalculate unique_users and median from enriched records for accuracy
        if result:
            import pandas as pd

            df = pd.DataFrame(result)
            # Recalculate unique_users from enriched records for accuracy
            unique_users_values = self._calculate_unique_users_for_category(
                "razors", df, "name", "name"
            )
            df["unique_users"] = unique_users_values
            # Recalculate avg_shaves_per_user with accurate unique_users
            df["avg_shaves_per_user"] = (df["shaves"] / df["unique_users"].replace(0, 1)).round(1)
            df.loc[df["unique_users"] == 0, "avg_shaves_per_user"] = 0.0
            # Calculate median
            median_values = self._calculate_medians_for_category("razors", df, "name", "name")
            df["median_shaves_per_user"] = median_values.fillna(0.0)
            # Update result with recalculated values
            for idx, row in df.iterrows():
                idx_int = int(idx) if isinstance(idx, (int, float)) else 0
                if idx_int < len(result):
                    result[idx_int]["unique_users"] = int(row["unique_users"])
                    result[idx_int]["avg_shaves_per_user"] = float(row["avg_shaves_per_user"])
                    result[idx_int]["median_shaves_per_user"] = float(row["median_shaves_per_user"])
        return result

    def aggregate_blades(self, monthly_data: Dict[str, Dict]) -> List[Dict[str, Any]]:
        """
        Aggregate blade data from monthly data.

        Args:
            monthly_data: Dictionary of monthly data keyed by month

        Returns:
            List of aggregated blade data sorted by shaves desc, unique_users desc
        """
        result = aggregate_annual_blades(monthly_data)
        # Recalculate unique_users and median from enriched records for accuracy
        if result:
            import pandas as pd

            df = pd.DataFrame(result)
            # Recalculate unique_users from enriched records for accuracy
            unique_users_values = self._calculate_unique_users_for_category(
                "blades", df, "name", "name"
            )
            df["unique_users"] = unique_users_values
            # Recalculate avg_shaves_per_user with accurate unique_users
            df["avg_shaves_per_user"] = (df["shaves"] / df["unique_users"].replace(0, 1)).round(1)
            df.loc[df["unique_users"] == 0, "avg_shaves_per_user"] = 0.0
            # Calculate median
            median_values = self._calculate_medians_for_category("blades", df, "name", "name")
            df["median_shaves_per_user"] = median_values.fillna(0.0)
            # Update result with recalculated values
            for idx, row in df.iterrows():
                idx_int = int(idx) if isinstance(idx, (int, float)) else 0
                if idx_int < len(result):
                    result[idx_int]["unique_users"] = int(row["unique_users"])
                    result[idx_int]["avg_shaves_per_user"] = float(row["avg_shaves_per_user"])
                    result[idx_int]["median_shaves_per_user"] = float(row["median_shaves_per_user"])
        return result

    def aggregate_brushes(self, monthly_data: Dict[str, Dict]) -> List[Dict[str, Any]]:
        """
        Aggregate brush data from monthly data.

        Args:
            monthly_data: Dictionary of monthly data keyed by month

        Returns:
            List of aggregated brush data sorted by shaves desc, unique_users desc
        """
        result = aggregate_annual_brushes(monthly_data)
        # Recalculate unique_users and median from enriched records for accuracy
        if result:
            import pandas as pd

            df = pd.DataFrame(result)
            # Recalculate unique_users from enriched records for accuracy
            unique_users_values = self._calculate_unique_users_for_category(
                "brushes", df, "name", "name"
            )
            df["unique_users"] = unique_users_values
            # Recalculate avg_shaves_per_user with accurate unique_users
            df["avg_shaves_per_user"] = (df["shaves"] / df["unique_users"].replace(0, 1)).round(1)
            df.loc[df["unique_users"] == 0, "avg_shaves_per_user"] = 0.0
            # Calculate median
            median_values = self._calculate_medians_for_category("brushes", df, "name", "name")
            df["median_shaves_per_user"] = median_values.fillna(0.0)
            # Update result with recalculated values
            for idx, row in df.iterrows():
                idx_int = int(idx) if isinstance(idx, (int, float)) else 0
                if idx_int < len(result):
                    result[idx_int]["unique_users"] = int(row["unique_users"])
                    result[idx_int]["avg_shaves_per_user"] = float(row["avg_shaves_per_user"])
                    result[idx_int]["median_shaves_per_user"] = float(row["median_shaves_per_user"])
        return result

    def aggregate_soaps(self, monthly_data: Dict[str, Dict]) -> List[Dict[str, Any]]:
        """
        Aggregate soap data from monthly data.

        Args:
            monthly_data: Dictionary of monthly data keyed by month

        Returns:
            List of aggregated soap data sorted by shaves desc, unique_users desc
        """
        result = aggregate_annual_soaps(monthly_data)
        # Recalculate unique_users and median from enriched records for accuracy
        if result:
            import pandas as pd

            df = pd.DataFrame(result)
            # Recalculate unique_users from enriched records for accuracy
            unique_users_values = self._calculate_unique_users_for_category(
                "soaps", df, "name", "name"
            )
            df["unique_users"] = unique_users_values
            # Recalculate avg_shaves_per_user with accurate unique_users
            df["avg_shaves_per_user"] = (df["shaves"] / df["unique_users"].replace(0, 1)).round(1)
            df.loc[df["unique_users"] == 0, "avg_shaves_per_user"] = 0.0
            # Calculate median
            median_values = self._calculate_medians_for_category("soaps", df, "name", "name")
            df["median_shaves_per_user"] = median_values.fillna(0.0)
            # Update result with recalculated values
            for idx, row in df.iterrows():
                idx_int = int(idx) if isinstance(idx, (int, float)) else 0
                if idx_int < len(result):
                    result[idx_int]["unique_users"] = int(row["unique_users"])
                    result[idx_int]["avg_shaves_per_user"] = float(row["avg_shaves_per_user"])
                    result[idx_int]["median_shaves_per_user"] = float(row["median_shaves_per_user"])
        return result

    def aggregate_brush_fibers(self, monthly_data: Dict[str, Dict]) -> List[Dict[str, Any]]:
        """
        Aggregate brush fiber data from monthly data.

        Args:
            monthly_data: Dictionary of monthly data keyed by month

        Returns:
            List of aggregated brush fiber data sorted by shaves desc, unique_users desc
        """
        return self._aggregate_specialized_brush_category(monthly_data, "brush_fibers")

    def aggregate_brush_knot_sizes(self, monthly_data: Dict[str, Dict]) -> List[Dict[str, Any]]:
        """
        Aggregate brush knot size data from monthly data.

        Args:
            monthly_data: Dictionary of monthly data keyed by month

        Returns:
            List of aggregated brush knot size data sorted by shaves desc, unique_users desc
        """
        return self._aggregate_specialized_brush_category(monthly_data, "brush_knot_sizes")

    def aggregate_brush_handle_makers(self, monthly_data: Dict[str, Dict]) -> List[Dict[str, Any]]:
        """
        Aggregate brush handle maker data from monthly data.

        Args:
            monthly_data: Dictionary of monthly data keyed by month

        Returns:
            List of aggregated brush handle maker data sorted by shaves desc, unique_users desc
        """
        return self._aggregate_specialized_brush_category(monthly_data, "brush_handle_makers")

    def aggregate_brush_knot_makers(self, monthly_data: Dict[str, Dict]) -> List[Dict[str, Any]]:
        """
        Aggregate brush knot maker data from monthly data.

        Args:
            monthly_data: Dictionary of monthly data keyed by month

        Returns:
            List of aggregated brush knot maker data sorted by shaves desc, unique_users desc
        """
        return self._aggregate_specialized_brush_category(monthly_data, "brush_knot_makers")

    def aggregate_razor_blade_combinations(
        self, monthly_data: Dict[str, Dict]
    ) -> List[Dict[str, Any]]:
        """Aggregate annual razor-blade combinations from monthly data."""
        result = aggregate_annual_razor_blade_combinations(monthly_data)
        # Recalculate unique_users and median from enriched records for accuracy
        if result:
            import pandas as pd

            df = pd.DataFrame(result)
            # Recalculate unique_users from enriched records for accuracy
            unique_users_values = self._calculate_unique_users_for_category(
                "razor_blade_combinations", df, "name", "name"
            )
            df["unique_users"] = unique_users_values
            # Recalculate avg_shaves_per_user with accurate unique_users
            df["avg_shaves_per_user"] = (df["shaves"] / df["unique_users"].replace(0, 1)).round(1)
            df.loc[df["unique_users"] == 0, "avg_shaves_per_user"] = 0.0
            # Calculate median
            median_values = self._calculate_medians_for_category(
                "razor_blade_combinations", df, "name", "name"
            )
            df["median_shaves_per_user"] = median_values.fillna(0.0)
            # Update result with recalculated values
            for idx, row in df.iterrows():
                idx_int = int(idx) if isinstance(idx, (int, float)) else 0
                if idx_int < len(result):
                    result[idx_int]["unique_users"] = int(row["unique_users"])
                    result[idx_int]["avg_shaves_per_user"] = float(row["avg_shaves_per_user"])
                    result[idx_int]["median_shaves_per_user"] = float(row["median_shaves_per_user"])
        return result

    def aggregate_highest_use_count_per_blade(
        self, monthly_data: Dict[str, Dict]
    ) -> List[Dict[str, Any]]:
        """Aggregate annual highest use count per blade from monthly data.

        This table has a different structure (blade, format, user, uses) than standard
        product tables, so it needs special handling to find the maximum uses per
        blade+format+user combination across all months.
        """
        if not monthly_data:
            return []

        # Collect all records from all months
        all_records = []
        for month, data in monthly_data.items():
            if "data" in data and "highest_use_count_per_blade" in data["data"]:
                category_data = data["data"]["highest_use_count_per_blade"]
                if isinstance(category_data, list):
                    all_records.extend(category_data)

        if not all_records:
            return []

        # Use pandas to find maximum uses per blade+format+user combination
        import pandas as pd

        df = pd.DataFrame(all_records)

        # Group by blade, format, and user, and take the maximum uses
        # This handles cases where the same blade+format+user appears in multiple months
        max_uses = df.groupby(["blade", "format", "user"])["uses"].max().reset_index()

        # Sort by uses descending
        max_uses = max_uses.sort_values("uses", ascending=False).reset_index(drop=True)

        # Add competition ranking
        max_uses["rank"] = max_uses["uses"].rank(method="min", ascending=False).astype(int)

        # Reorder columns to put rank first
        cols = ["rank"] + [col for col in max_uses.columns if col != "rank"]
        max_uses = max_uses[cols]

        # Convert back to list of dicts
        return max_uses.to_dict("records")

    def _aggregate_specialized_brush_category(
        self, monthly_data: Dict[str, Dict], category: str
    ) -> List[Dict[str, Any]]:
        """
        Helper method to aggregate specialized brush categories from monthly data.

        Args:
            monthly_data: Dictionary of monthly data keyed by month
            category: Category name to aggregate (e.g., "brush_fibers")

        Returns:
            List of aggregated data sorted by shaves desc, unique_users desc
        """
        if not monthly_data:
            return []

        # Collect all records from all months
        all_records = []
        for month, data in monthly_data.items():
            if "data" in data and category in data["data"]:
                category_data = data["data"][category]
                if isinstance(category_data, list):
                    all_records.extend(category_data)

        if not all_records:
            return []

        # Determine identifier field based on category
        # Monthly aggregated data already has the correct structure with aggregated values
        # Check the first record to determine the identifier field name
        if not all_records:
            return []

        sample_record = all_records[0]
        # Map category to possible identifier field names
        identifier_field_candidates = {
            "brush_fibers": ["fiber"],
            "brush_knot_sizes": ["knot_size_mm"],
            "brush_handle_makers": ["handle_maker", "brand"],
            "brush_knot_makers": ["brand"],
        }

        candidates = identifier_field_candidates.get(category, [])
        identifier_field = None
        for candidate in candidates:
            if candidate in sample_record:
                identifier_field = candidate
                break

        if not identifier_field:
            # Fallback: try to find any field that looks like an identifier
            # (not shaves, unique_users, rank)
            excluded_fields = {"shaves", "unique_users", "rank"}
            for key in sample_record.keys():
                if key not in excluded_fields:
                    identifier_field = key
                    break

        if not identifier_field:
            return []

        # Use the same simple aggregation pattern as _aggregate_specialized_category
        # Group by identifier and sum shaves (unique_users will be recalculated from enriched records)
        import pandas as pd

        # Convert to DataFrame
        df = pd.DataFrame(all_records)

        # Group by identifier field and sum shaves (don't sum unique_users - recalculate from enriched records)
        grouped = df.groupby(identifier_field).agg({"shaves": "sum"}).reset_index()

        # Rename identifier_field to "name" for consistency with other aggregators
        grouped = grouped.rename(columns={identifier_field: "name"})

        # Recalculate unique_users from enriched records for accuracy
        # Determine the identifier field name in extracted data based on category
        identifier_field_map = {
            "brush_fibers": "fiber",
            "brush_knot_sizes": "knot_size_mm",
            "brush_handle_makers": "handle_maker",
            "brush_knot_makers": "brand",
        }
        identifier_in_extracted = identifier_field_map.get(category, "name")

        # Calculate accurate unique_users from enriched records
        unique_users_values = self._calculate_unique_users_for_category(
            category, grouped, "name", identifier_in_extracted
        )
        grouped["unique_users"] = unique_users_values

        # Sort by shaves desc, then by unique_users desc
        grouped = grouped.sort_values(["shaves", "unique_users"], ascending=[False, False])

        # Add rank column using competition ranking
        grouped["rank"] = grouped["shaves"].rank(method="min", ascending=False).astype(int)

        # Calculate avg_shaves_per_user using accurate unique_users
        grouped["avg_shaves_per_user"] = (
            grouped["shaves"] / grouped["unique_users"].replace(0, 1)
        ).round(1)
        # Handle division by zero: if unique_users is 0, set avg to 0.0
        grouped.loc[grouped["unique_users"] == 0, "avg_shaves_per_user"] = 0.0

        # Calculate median_shaves_per_user using accurate unique_users
        median_values = self._calculate_medians_for_category(
            category, grouped, "name", identifier_in_extracted
        )
        grouped["median_shaves_per_user"] = median_values.fillna(0.0)

        # Reorder columns: rank, identifier, then metrics
        column_order = ["rank", "name"]
        if "unique_users" in grouped.columns:
            column_order.append("unique_users")
        column_order.append("shaves")
        if "avg_shaves_per_user" in grouped.columns:
            column_order.append("avg_shaves_per_user")
        if "median_shaves_per_user" in grouped.columns:
            column_order.append("median_shaves_per_user")
        grouped = grouped[column_order]

        # Replace NaN with 0.0 for numeric columns before conversion
        if "median_shaves_per_user" in grouped.columns:
            # Ensure it's a Series before calling fillna
            median_col = grouped["median_shaves_per_user"]
            if isinstance(median_col, pd.Series):
                grouped["median_shaves_per_user"] = median_col.fillna(0.0)
            else:
                grouped["median_shaves_per_user"] = pd.Series(median_col).fillna(0.0)

        # Convert back to list of dicts
        return grouped.to_dict("records")

    def _aggregate_specialized_category(
        self, monthly_data: Dict[str, Dict], category: str, identifier_field: str
    ) -> List[Dict[str, Any]]:
        """
        Helper method to aggregate specialized categories from monthly data.

        This method works for categories that have a consistent structure across months
        with an identifier field (like 'format', 'brand', 'plate', etc.) and metric fields
        (shaves, unique_users).

        Args:
            monthly_data: Dictionary of monthly data keyed by month
            category: Category name to aggregate (e.g., "razor_formats")
            identifier_field: Field name used as identifier (e.g., "format", "brand", "plate")

        Returns:
            List of aggregated data sorted by shaves desc, unique_users desc
        """
        if not monthly_data:
            return []

        # Collect all records from all months
        all_records = []
        for month, data in monthly_data.items():
            if "data" in data and category in data["data"]:
                category_data = data["data"][category]
                if isinstance(category_data, list):
                    all_records.extend(category_data)

        if not all_records:
            return []

        # Use AnnualAggregator pattern: group by identifier and sum shaves
        # unique_users will be recalculated from enriched records for accuracy
        import pandas as pd

        # Convert to DataFrame
        df = pd.DataFrame(all_records)

        # Group by identifier field and sum shaves (don't sum unique_users - recalculate from enriched records)
        grouped = df.groupby(identifier_field).agg({"shaves": "sum"}).reset_index()

        # Rename identifier_field to "name" for consistency with other aggregators
        # Exception: keep "user" field name for users table
        if identifier_field != "user":
            grouped = grouped.rename(columns={identifier_field: "name"})
            final_identifier = "name"
        else:
            final_identifier = "user"

        # Recalculate unique_users from enriched records for accuracy
        # Determine the identifier field name in extracted data based on category
        identifier_field_map = {
            "razor_formats": "format",
            "razor_manufacturers": "brand",
            "blade_manufacturers": "brand",
            "soap_makers": "brand",
            "blackbird_plates": "plate",
            "christopher_bradley_plates": "plate",
            "game_changer_plates": "gap",
            "straight_widths": "width",
            "straight_grinds": "grind",
            "straight_points": "point",
        }
        identifier_in_extracted = identifier_field_map.get(category, identifier_field)

        # Calculate accurate unique_users from enriched records
        unique_users_values = self._calculate_unique_users_for_category(
            category, grouped, final_identifier, identifier_in_extracted
        )
        grouped["unique_users"] = unique_users_values

        # Sort by shaves desc, then by unique_users desc
        grouped = grouped.sort_values(["shaves", "unique_users"], ascending=[False, False])

        # Add rank column (1-based, with ties getting the same rank)
        grouped["rank"] = grouped["shaves"].rank(method="min", ascending=False).astype(int)

        # Calculate avg_shaves_per_user using accurate unique_users
        grouped["avg_shaves_per_user"] = (
            grouped["shaves"] / grouped["unique_users"].replace(0, 1)
        ).round(1)
        # Handle division by zero: if unique_users is 0, set avg to 0.0
        grouped.loc[grouped["unique_users"] == 0, "avg_shaves_per_user"] = 0.0

        # Calculate median_shaves_per_user using accurate unique_users
        median_values = self._calculate_medians_for_category(
            category, grouped, final_identifier, identifier_in_extracted
        )
        grouped["median_shaves_per_user"] = median_values.fillna(0.0)

        # Reorder columns: rank, identifier, then metrics
        column_order = ["rank", final_identifier]
        if "unique_users" in grouped.columns:
            column_order.append("unique_users")
        column_order.append("shaves")
        if "avg_shaves_per_user" in grouped.columns:
            column_order.append("avg_shaves_per_user")
        if "median_shaves_per_user" in grouped.columns:
            column_order.append("median_shaves_per_user")
        grouped = grouped[column_order]

        # Replace NaN with 0.0 for numeric columns before conversion
        if "median_shaves_per_user" in grouped.columns:
            # Ensure it's a Series before calling fillna
            median_col = grouped["median_shaves_per_user"]
            if isinstance(median_col, pd.Series):
                grouped["median_shaves_per_user"] = median_col.fillna(0.0)
            else:
                grouped["median_shaves_per_user"] = pd.Series(median_col).fillna(0.0)

        # Fill NaN for unique_users and avg_shaves_per_user
        if "unique_users" in grouped.columns:
            grouped["unique_users"] = grouped["unique_users"].fillna(0).astype(int)
        if "avg_shaves_per_user" in grouped.columns:
            grouped["avg_shaves_per_user"] = grouped["avg_shaves_per_user"].fillna(0.0)

        # Convert back to list of dicts
        result = grouped.to_dict("records")

        return result

    def _load_enriched_records(self) -> List[Dict[str, Any]]:
        """Load enriched records for all months in the year.

        Uses cached records if available to avoid redundant file I/O.

        Returns:
            List of enriched records from all months
        """
        # Return cached records if available
        if self._cached_enriched_records is not None:
            return self._cached_enriched_records

        from sotd.utils.file_io import load_json_data

        enriched_dir = self.data_dir / "enriched"
        all_enriched_records = []

        # Get all months in the year
        for month in range(1, 13):
            month_str = f"{self.year}-{month:02d}"
            enriched_file = enriched_dir / f"{month_str}.json"
            if enriched_file.exists():
                try:
                    enriched_data = load_json_data(enriched_file)
                    # Handle both list and dict structures
                    if isinstance(enriched_data, list):
                        all_enriched_records.extend(enriched_data)
                    elif isinstance(enriched_data, dict) and "data" in enriched_data:
                        if isinstance(enriched_data["data"], list):
                            all_enriched_records.extend(enriched_data["data"])
                except Exception:
                    # Skip corrupted files
                    continue

        # Deduplicate by comment ID: recovered/re-fetched month files can
        # repeat the same comment records, which would skew the per-user
        # math calculated from these records.
        from .load import dedupe_records_by_id

        all_enriched_records = dedupe_records_by_id(all_enriched_records)

        # Cache the loaded records
        self._cached_enriched_records = all_enriched_records
        return all_enriched_records

    def _calculate_medians_for_category(
        self,
        category: str,
        grouped: "pd.DataFrame",
        identifier_col: str,
        identifier_field_in_extracted: str = "name",
    ) -> "pd.Series":
        """
        Calculate median shaves per user for a category by loading enriched records and calculating directly.

        Args:
            category: Category name (e.g., "razors", "blades", "razor_manufacturers")
            grouped: DataFrame with name/identifier, shaves, unique_users already calculated
            identifier_col: Column name in grouped DataFrame (usually "name")
            identifier_field_in_extracted: Field name in extracted data (e.g., "name", "brand", "plate")

        Returns:
            Series with median_shaves_per_user values indexed by identifier
        """
        import pandas as pd

        # Type hint for grouped parameter
        if not isinstance(grouped, pd.DataFrame):
            return pd.Series(0.0, index=[])

        # Load enriched records
        all_enriched_records = self._load_enriched_records()

        if not all_enriched_records:
            # If no enriched records, return zeros
            return pd.Series(0.0, index=grouped[identifier_col])

        # Get the appropriate aggregator class to extract data
        aggregator_class = self._get_aggregator_class_for_category(category)
        if not aggregator_class:
            # If aggregator not found, return zeros
            return pd.Series(0.0, index=grouped[identifier_col])

        # Create aggregator instance and extract data
        aggregator = aggregator_class()
        extracted_data = aggregator._extract_data(all_enriched_records)

        if not extracted_data:
            return pd.Series(0.0, index=grouped[identifier_col])

        # Convert to DataFrame
        df = pd.DataFrame(extracted_data)

        # Create composite identifier using the aggregator's logic
        # This handles cases like brushes which group by name and fiber
        df["composite_identifier"] = aggregator._create_composite_name(df)

        # Group by composite identifier and author to get shaves per user per identifier
        user_shaves_per_identifier = (
            df.groupby(["composite_identifier", "author"]).size().reset_index()
        )
        user_shaves_per_identifier.columns = ["composite_identifier", "author", "user_shaves"]

        # Calculate median shaves per user for each composite identifier
        median_shaves = (
            user_shaves_per_identifier.groupby("composite_identifier")["user_shaves"]
            .median()
            .reset_index()
        )
        median_shaves.columns = ["composite_identifier", "median_shaves_per_user"]
        median_shaves["median_shaves_per_user"] = median_shaves["median_shaves_per_user"].round(1)

        # Create mapping from composite identifier to median
        identifier_to_median = dict(
            zip(median_shaves["composite_identifier"], median_shaves["median_shaves_per_user"])
        )

        # Map medians to grouped dataframe
        # Convert identifier column to string to match composite_identifier (which is always string)
        # For numeric identifiers (like knot sizes), normalize to float then string for consistent matching
        # This handles cases where monthly data might have 24 (int) vs enriched data having 24.0 (float)
        identifier_series = grouped[identifier_col]
        # Try to convert to float first for numeric values, then to string for consistent formatting
        try:
            identifier_series = identifier_series.astype(float).astype(str)
        except (ValueError, TypeError):
            # If conversion fails, just convert to string (for non-numeric identifiers)
            identifier_series = identifier_series.astype(str)
        median_series = identifier_series.map(identifier_to_median).fillna(0.0)

        return median_series

    def _calculate_unique_users_for_category(
        self,
        category: str,
        grouped: "pd.DataFrame",
        identifier_col: str,
        identifier_field_in_extracted: str = "name",
    ) -> "pd.Series":
        """
        Calculate accurate unique_users for a category by loading enriched records and counting unique authors.

        Args:
            category: Category name (e.g., "razors", "blades", "razor_manufacturers")
            grouped: DataFrame with name/identifier, shaves already calculated
            identifier_col: Column name in grouped DataFrame (usually "name")
            identifier_field_in_extracted: Field name in extracted data (e.g., "name", "brand", "plate")

        Returns:
            Series with unique_users values indexed by identifier
        """
        import pandas as pd

        # Type hint for grouped parameter
        if not isinstance(grouped, pd.DataFrame):
            return pd.Series(0, index=[], dtype=int)

        # Load enriched records
        all_enriched_records = self._load_enriched_records()

        if not all_enriched_records:
            # If no enriched records, return zeros with same index as grouped DataFrame
            return pd.Series(0, index=grouped.index, dtype=int)

        # Get the appropriate aggregator class to extract data
        aggregator_class = self._get_aggregator_class_for_category(category)
        if not aggregator_class:
            # If aggregator not found, return zeros with same index as grouped DataFrame
            return pd.Series(0, index=grouped.index, dtype=int)

        # Create aggregator instance and extract data
        aggregator = aggregator_class()
        extracted_data = aggregator._extract_data(all_enriched_records)

        if not extracted_data:
            # If no extracted data, return zeros with same index as grouped DataFrame
            return pd.Series(0, index=grouped.index, dtype=int)

        # Convert to DataFrame
        df = pd.DataFrame(extracted_data)

        # Create composite identifier using the aggregator's logic
        # This handles cases like brushes which group by name and fiber
        df["composite_identifier"] = aggregator._create_composite_name(df)

        # Group by composite identifier and author, then count unique authors per identifier
        unique_users_per_identifier = (
            df.groupby("composite_identifier")["author"].nunique().reset_index()
        )
        unique_users_per_identifier.columns = ["composite_identifier", "unique_users"]

        # Create mapping from composite identifier to unique_users count
        identifier_to_unique_users = dict(
            zip(
                unique_users_per_identifier["composite_identifier"],
                unique_users_per_identifier["unique_users"],
            )
        )

        # Map unique_users to grouped dataframe
        # Convert identifier column to string to match composite_identifier (which is always string)
        # For numeric identifiers (like knot sizes), normalize to float then string for consistent matching
        # This handles cases where monthly data might have 24 (int) vs enriched data having 24.0 (float)
        identifier_series = grouped[identifier_col]
        # Try to convert to float first for numeric values, then to string for consistent formatting
        try:
            identifier_series = identifier_series.astype(float).astype(str)
        except (ValueError, TypeError):
            # If conversion fails, just convert to string (for non-numeric identifiers)
            identifier_series = identifier_series.astype(str)
        unique_users_series = (
            identifier_series.map(identifier_to_unique_users).fillna(0).astype(int)
        )

        return unique_users_series

    def _get_aggregator_class_for_category(self, category: str):
        """Get the appropriate aggregator class for a category.

        Args:
            category: Category name

        Returns:
            Aggregator class or None if not found
        """
        # Map category names to their aggregator classes
        aggregator_class_map = {
            "razors": __import__(
                "sotd.aggregate.aggregators.core.razor_aggregator", fromlist=["RazorAggregator"]
            ).RazorAggregator,
            "blades": __import__(
                "sotd.aggregate.aggregators.core.blade_aggregator", fromlist=["BladeAggregator"]
            ).BladeAggregator,
            "brushes": __import__(
                "sotd.aggregate.aggregators.core.brush_aggregator", fromlist=["BrushAggregator"]
            ).BrushAggregator,
            "soaps": __import__(
                "sotd.aggregate.aggregators.core.soap_aggregator", fromlist=["SoapAggregator"]
            ).SoapAggregator,
            "razor_manufacturers": __import__(
                "sotd.aggregate.aggregators.manufacturers.razor_manufacturer_aggregator",
                fromlist=["RazorManufacturerAggregator"],
            ).RazorManufacturerAggregator,
            "blade_manufacturers": __import__(
                "sotd.aggregate.aggregators.manufacturers.blade_manufacturer_aggregator",
                fromlist=["BladeManufacturerAggregator"],
            ).BladeManufacturerAggregator,
            "soap_makers": __import__(
                "sotd.aggregate.aggregators.manufacturers.soap_maker_aggregator",
                fromlist=["SoapMakerAggregator"],
            ).SoapMakerAggregator,
            "brush_handle_makers": __import__(
                "sotd.aggregate.aggregators.brush_specialized.handle_maker_aggregator",
                fromlist=["HandleMakerAggregator"],
            ).HandleMakerAggregator,
            "brush_knot_makers": __import__(
                "sotd.aggregate.aggregators.brush_specialized.knot_maker_aggregator",
                fromlist=["KnotMakerAggregator"],
            ).KnotMakerAggregator,
            "brush_fibers": __import__(
                "sotd.aggregate.aggregators.brush_specialized.fiber_aggregator",
                fromlist=["FiberAggregator"],
            ).FiberAggregator,
            "brush_knot_sizes": __import__(
                "sotd.aggregate.aggregators.brush_specialized.knot_size_aggregator",
                fromlist=["KnotSizeAggregator"],
            ).KnotSizeAggregator,
            "blackbird_plates": __import__(
                "sotd.aggregate.aggregators.razor_specialized.blackbird_plate_aggregator",
                fromlist=["BlackbirdPlateAggregator"],
            ).BlackbirdPlateAggregator,
            "christopher_bradley_plates": __import__(
                "sotd.aggregate.aggregators.razor_specialized.christopher_bradley_plate_aggregator",
                fromlist=["ChristopherBradleyPlateAggregator"],
            ).ChristopherBradleyPlateAggregator,
            "game_changer_plates": __import__(
                "sotd.aggregate.aggregators.razor_specialized.game_changer_plate_aggregator",
                fromlist=["GameChangerPlateAggregator"],
            ).GameChangerPlateAggregator,
            "straight_widths": __import__(
                "sotd.aggregate.aggregators.razor_specialized.straight_width_aggregator",
                fromlist=["StraightWidthAggregator"],
            ).StraightWidthAggregator,
            "straight_grinds": __import__(
                "sotd.aggregate.aggregators.razor_specialized.straight_grind_aggregator",
                fromlist=["StraightGrindAggregator"],
            ).StraightGrindAggregator,
            "straight_points": __import__(
                "sotd.aggregate.aggregators.razor_specialized.straight_point_aggregator",
                fromlist=["StraightPointAggregator"],
            ).StraightPointAggregator,
            "razor_blade_combinations": __import__(
                "sotd.aggregate.aggregators.cross_product.razor_blade_combo_aggregator",
                fromlist=["RazorBladeComboAggregator"],
            ).RazorBladeComboAggregator,
            "razor_formats": __import__(
                "sotd.aggregate.aggregators.formats.razor_format_aggregator",
                fromlist=["RazorFormatAggregator"],
            ).RazorFormatAggregator,
        }

        return aggregator_class_map.get(category)

    def _calculate_razor_format_medians(
        self, grouped: "pd.DataFrame", identifier_col: str
    ) -> "pd.Series":
        """
        Calculate median shaves per user for each razor format by loading enriched records.

        Args:
            grouped: DataFrame with format/name, shaves, unique_users already calculated
            identifier_col: Column name for the format identifier ("name" or "format")

        Returns:
            Series with median_shaves_per_user values indexed by format
        """
        import pandas as pd

        # Type hint for grouped parameter
        if not isinstance(grouped, pd.DataFrame):
            return pd.Series(0.0, index=[])

        # Use the generic helper with format-specific mapping
        return self._calculate_medians_for_category(
            "razor_formats", grouped, identifier_col, identifier_field_in_extracted="format"
        )

    def _aggregate_users(self, monthly_data: Dict[str, Dict]) -> List[Dict[str, Any]]:
        """
        Aggregate users data from monthly data.

        Users table has special fields: user, shaves, missed_days, missed_dates.
        We sum shaves and missed_days across months, and keep the user field name.

        Args:
            monthly_data: Dictionary of monthly data keyed by month

        Returns:
            List of aggregated user data sorted by shaves desc
        """
        if not monthly_data:
            return []

        # Collect all records from all months
        all_records = []
        for month, data in monthly_data.items():
            if "data" in data and "users" in data["data"]:
                users_data = data["data"]["users"]
                if isinstance(users_data, list):
                    all_records.extend(users_data)

        if not all_records:
            return []

        from calendar import monthrange

        import pandas as pd

        # Convert to DataFrame
        df = pd.DataFrame(all_records)

        # Calculate unique days posted per user per month
        # unique_days_in_month = days_in_month - missed_days_in_month
        # Then sum unique_days across months to get total unique days
        # Annual missed_days = 365 - total_unique_days

        # Add month column to calculate days in month
        df["month"] = df.index.map(
            lambda i: list(monthly_data.keys())[i // 1000] if i < len(all_records) else None
        )
        # Actually, we need to track which month each record came from
        # Let's rebuild with month tracking, ensuring we account for ALL months
        # even if a user doesn't appear in some months
        records_with_month = []
        user_months_map = {}  # Track which months each user appears in

        for month, data in monthly_data.items():
            if "data" in data and "users" in data["data"]:
                users_data = data["data"]["users"]
                if isinstance(users_data, list):
                    year, month_num = int(month[:4]), int(month[5:7])
                    days_in_month = monthrange(year, month_num)[1]
                    for user_record in users_data:
                        user = user_record.get("user")
                        if user:
                            if user not in user_months_map:
                                user_months_map[user] = set()
                            user_months_map[user].add(month)

                            user_record_copy = user_record.copy()
                            user_record_copy["_month"] = month
                            user_record_copy["_days_in_month"] = days_in_month
                            records_with_month.append(user_record_copy)

        df = pd.DataFrame(records_with_month)

        # Calculate unique days posted per user per month
        df["unique_days_in_month"] = df["_days_in_month"] - df["missed_days"]

        # Group by user and sum shaves and unique_days
        grouped = (
            df.groupby("user").agg({"shaves": "sum", "unique_days_in_month": "sum"}).reset_index()
        )

        # For users who don't appear in all months, we need to add missed days for missing months
        # Get all months in the year
        all_months = set(monthly_data.keys())
        for user in grouped["user"]:
            user_months = user_months_map.get(user, set())
            missing_months = all_months - user_months
            # Add missed days for months where user didn't appear
            for _missing_month in missing_months:
                # User missed all days in this month; unique_days_in_month is already
                # summed (0 for missing months since user didn't appear)
                pass

        # Calculate annual missed_days: 365 - total_unique_days
        # This correctly accounts for months where user didn't appear (unique_days = 0)
        grouped["missed_days"] = 365 - grouped["unique_days_in_month"]

        # Drop the helper column
        grouped = grouped.drop("unique_days_in_month", axis=1)

        # Sort by missed_days asc, shaves desc (same as monthly version)
        grouped = grouped.sort_values(["missed_days", "shaves"], ascending=[True, False])

        # Add competition ranking based on both missed_days and shaves
        # Users with same missed_days AND same shaves get tied ranks
        grouped = grouped.reset_index(drop=True)
        grouped["temp_rank"] = range(1, len(grouped) + 1)
        grouped["rank"] = grouped.groupby(["missed_days", "shaves"], sort=False)[
            "temp_rank"
        ].transform("min")
        grouped = grouped.drop("temp_rank", axis=1)

        # Sort by ranking first, then by user for consistent ordering of tied entries
        grouped = grouped.sort_values(["rank", "user"], ascending=[True, True])

        # Reorder columns: rank, user, shaves, missed_days
        grouped = grouped[["rank", "user", "shaves", "missed_days"]]

        # Convert back to list of dicts
        result = grouped.to_dict("records")

        return result

    def _calculate_median_shaves_per_user(self, monthly_data: Dict[str, Dict]) -> float:
        """
        Calculate median shaves per user from monthly aggregated data.

        Args:
            monthly_data: Dictionary of monthly data keyed by month

        Returns:
            Median shaves per user (rounded to 1 decimal place)
        """
        if not monthly_data:
            return 0.0

        # Collect all user records from all months
        all_user_records = []
        for month, data in monthly_data.items():
            if "data" in data and "users" in data["data"]:
                users_data = data["data"]["users"]
                if isinstance(users_data, list):
                    all_user_records.extend(users_data)

        if not all_user_records:
            return 0.0

        import pandas as pd

        # Convert to DataFrame
        df = pd.DataFrame(all_user_records)

        # Group by user and sum shaves across all months
        user_shaves = df.groupby("user")["shaves"].sum().reset_index()

        # Get list of shave counts
        shave_counts = user_shaves["shaves"].tolist()
        shave_counts.sort()

        if not shave_counts:
            return 0.0

        # Calculate median
        n = len(shave_counts)
        if n % 2 == 0:
            # Even number of users, average of two middle values
            median = (shave_counts[n // 2 - 1] + shave_counts[n // 2]) / 2
        else:
            # Odd number of users, middle value
            median = shave_counts[n // 2]

        return round(median, 1)

    def _aggregate_user_diversity(
        self, monthly_data: Dict[str, Dict], category: str
    ) -> List[Dict[str, Any]]:
        """
        Aggregate user diversity data from monthly data.

        User diversity tables have special fields: user, unique_combinations, shaves, avg_shaves_per_combination,
        hhi, effective_soaps. We sum shaves and unique_combinations across months, then recalculate
        avg_shaves_per_combination. HHI and effective_soaps need to be recalculated from combined
        brand-scent distribution (cannot be accurately calculated from monthly summaries alone).

        Args:
            monthly_data: Dictionary of monthly data keyed by month
            category: Category name (e.g., "user_soap_brand_scent_diversity")

        Returns:
            List of aggregated user diversity data sorted by unique_combinations desc, shaves desc
        """
        if not monthly_data:
            return []

        # Collect all records from all months
        all_records = []
        for month, data in monthly_data.items():
            if "data" in data and category in data["data"]:
                category_data = data["data"][category]
                if isinstance(category_data, list):
                    all_records.extend(category_data)

        if not all_records:
            return []

        import pandas as pd

        # Convert to DataFrame
        df = pd.DataFrame(all_records)

        # Group by user and sum shaves
        # Note: unique_combinations cannot be summed - must be recalculated from enriched records
        # to avoid double-counting soaps that appear in multiple months
        grouped = (
            df.groupby("user")
            .agg(
                {
                    "shaves": "sum",
                }
            )
            .reset_index()
        )

        # Recalculate unique_combinations, HHI, and effective_soaps from enriched records
        # for accurate annual values. Load enriched records for all months and recalculate
        # from combined distribution to get true unique combinations across the year.
        try:
            from .aggregators.users.soap_brand_scent_diversity_aggregator import (
                SoapBrandScentDiversityAggregator,
            )
            from .load import load_enriched_data

            # Collect all enriched records for the year
            all_enriched_records = []
            for month in monthly_data.keys():
                try:
                    enriched_records = load_enriched_data(month, self.data_dir)
                    all_enriched_records.extend(enriched_records)
                except FileNotFoundError:
                    # Skip missing months gracefully
                    continue
                except Exception:
                    # Skip corrupted months gracefully
                    continue

            if all_enriched_records:
                # Recalculate unique_combinations, HHI, and effective_soaps from combined enriched records
                aggregator = SoapBrandScentDiversityAggregator()
                hhi_results = aggregator.aggregate(all_enriched_records)

                # Create mapping of user -> unique_combinations, hhi, effective_soaps
                hhi_map = {
                    result["user"]: {
                        "unique_combinations": result.get("unique_combinations", 0),
                        "hhi": result.get("hhi", 0.0),
                        "effective_soaps": result.get("effective_soaps", 0.0),
                    }
                    for result in hhi_results
                }

                # Merge values into grouped data
                grouped["unique_combinations"] = (
                    grouped["user"]
                    .map(lambda u: hhi_map.get(u, {}).get("unique_combinations", 0))
                    .fillna(0)
                    .astype(int)
                )
                grouped["hhi"] = (
                    grouped["user"].map(lambda u: hhi_map.get(u, {}).get("hhi", 0.0)).fillna(0.0)
                )
                grouped["effective_soaps"] = (
                    grouped["user"]
                    .map(lambda u: hhi_map.get(u, {}).get("effective_soaps", 0.0))
                    .fillna(0.0)
                )
            else:
                # Fallback if no enriched records available - use summed values (less accurate)
                # This should rarely happen, but provides a fallback
                unique_combinations_sum = (
                    df.groupby("user")["unique_combinations"].sum().reset_index()
                )
                grouped = grouped.merge(
                    unique_combinations_sum[["user", "unique_combinations"]], on="user", how="left"
                )
                grouped["unique_combinations"] = (
                    grouped["unique_combinations"].fillna(0).astype(int)
                )
                grouped["hhi"] = 0.0
                grouped["effective_soaps"] = 0.0

            # Recalculate avg_shaves_per_combination with accurate unique_combinations
            grouped["avg_shaves_per_combination"] = (
                grouped["shaves"] / grouped["unique_combinations"].replace(0, 1)
            ).round(1)
            grouped.loc[grouped["unique_combinations"] == 0, "avg_shaves_per_combination"] = 0.0
        except Exception:
            # Fallback if recalculation fails for any reason - use summed values (less accurate)
            unique_combinations_sum = df.groupby("user")["unique_combinations"].sum().reset_index()
            grouped = grouped.merge(
                unique_combinations_sum[["user", "unique_combinations"]], on="user", how="left"
            )
            grouped["unique_combinations"] = grouped["unique_combinations"].fillna(0).astype(int)
            grouped["avg_shaves_per_combination"] = (
                grouped["shaves"] / grouped["unique_combinations"].replace(0, 1)
            ).round(1)
            grouped.loc[grouped["unique_combinations"] == 0, "avg_shaves_per_combination"] = 0.0
            grouped["hhi"] = 0.0
            grouped["effective_soaps"] = 0.0

        # Sort by unique_combinations desc, shaves desc
        grouped = grouped.sort_values(["unique_combinations", "shaves"], ascending=[False, False])

        # Add rank column (1-based, with ties getting the same rank)
        grouped["rank"] = (
            grouped["unique_combinations"].rank(method="min", ascending=False).astype(int)
        )

        # Reorder columns: rank, user, unique_combinations, shaves, avg_shaves_per_combination, hhi, effective_soaps
        grouped = grouped[
            [
                "rank",
                "user",
                "unique_combinations",
                "shaves",
                "avg_shaves_per_combination",
                "hhi",
                "effective_soaps",
            ]
        ]

        # Convert back to list of dicts
        result = grouped.to_dict("records")

        return result

    def _aggregate_user_single_use_soaps(
        self, monthly_data: Dict[str, Dict]
    ) -> List[Dict[str, Any]]:
        """Recalculate exclusive-use soap points from full-year enriched records."""
        if not monthly_data:
            return []

        try:
            from .aggregators.users.user_single_use_soaps_aggregator import (
                UserSingleUseSoapsAggregator,
            )
            from .load import load_enriched_data

            all_enriched_records = []
            for month in monthly_data.keys():
                try:
                    all_enriched_records.extend(load_enriched_data(month, self.data_dir))
                except FileNotFoundError:
                    continue
                except Exception:
                    continue

            if not all_enriched_records:
                return []

            return UserSingleUseSoapsAggregator().aggregate(all_enriched_records)
        except Exception:
            return []

    def _aggregate_soap_mashup_users(self, monthly_data: Dict[str, Dict]) -> List[Dict[str, Any]]:
        """Recalculate the soap-mashup-users table from full-year enriched records."""
        if not monthly_data:
            return []

        try:
            from .aggregators.users.soap_mashup_user_aggregator import aggregate_soap_mashup_users
            from .load import load_enriched_data

            all_enriched_records = []
            for month in monthly_data.keys():
                try:
                    all_enriched_records.extend(load_enriched_data(month, self.data_dir))
                except FileNotFoundError:
                    continue
                except Exception:
                    continue

            if not all_enriched_records:
                return []

            return aggregate_soap_mashup_users(all_enriched_records)
        except Exception:
            return []

    def generate_metadata(
        self,
        monthly_data: Dict[str, Dict],
        included_months: Optional[List[str]] = None,
        missing_months: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Generate metadata for annual aggregation.

        Args:
            monthly_data: Dictionary of monthly data keyed by month
            included_months: List of months that were successfully loaded
            missing_months: List of months that were missing

        Returns:
            Dictionary with annual metadata
        """
        total_shaves = 0

        # Calculate total shaves from included months
        for month, data in monthly_data.items():
            if "meta" in data and isinstance(data["meta"], dict):
                meta = data["meta"]
                total_shaves += meta.get("total_shaves", 0)

        # Calculate accurate unique_shavers from enriched records (not summing monthly counts)
        all_enriched_records = self._load_enriched_records()
        if all_enriched_records:
            # Count unique authors across all enriched records
            import pandas as pd

            df = pd.DataFrame(all_enriched_records)
            total_unique_shavers = int(df["author"].nunique()) if "author" in df.columns else 0
        else:
            total_unique_shavers = 0

        # Calculate average shaves per user
        avg_shaves_per_user = 0.0
        if total_unique_shavers > 0:
            avg_shaves_per_user = round(total_shaves / total_unique_shavers, 1)

        # Calculate median shaves per user by aggregating user data from monthly records
        median_shaves_per_user = self._calculate_median_shaves_per_user(monthly_data)

        # Calculate sample-related metrics from enriched records
        from sotd.aggregate.utils.metrics import (
            calculate_mashup_users,
            calculate_sample_brands,
            calculate_sample_users,
            calculate_total_mashup_shaves,
            calculate_total_samples,
            calculate_unique_sample_soaps,
        )

        total_samples = 0
        sample_users = 0
        sample_brands = 0
        unique_sample_soaps = 0
        total_mashup_shaves = 0
        mashup_users = 0

        if all_enriched_records:
            total_samples = calculate_total_samples(all_enriched_records)
            sample_users = calculate_sample_users(all_enriched_records)
            sample_brands = calculate_sample_brands(all_enriched_records)
            unique_sample_soaps = calculate_unique_sample_soaps(all_enriched_records)
            total_mashup_shaves = calculate_total_mashup_shaves(all_enriched_records)
            mashup_users = calculate_mashup_users(all_enriched_records)

        # Calculate sample percentage
        sample_percentage = 0.0
        if total_shaves > 0:
            sample_percentage = round((total_samples / total_shaves) * 100, 1)

        # Calculate mashup percentage
        mashup_percentage = 0.0
        if total_shaves > 0:
            mashup_percentage = round((total_mashup_shaves / total_shaves) * 100, 1)

        # Use provided lists or calculate from monthly_data keys
        if included_months is None:
            included_months = sorted(monthly_data.keys())
        if missing_months is None:
            # Calculate missing months if not provided
            missing_months = []
            for month_num in range(1, 13):
                month_key = f"{self.year}-{month_num:02d}"
                if month_key not in monthly_data:
                    missing_months.append(month_key)

        # Update performance metrics
        self.monitor.metrics.total_shaves = total_shaves
        self.monitor.metrics.unique_shavers = total_unique_shavers
        self.monitor.metrics.month_count = len(included_months)

        return {
            "year": self.year,
            "aggregated_at": datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(),
            "total_shaves": total_shaves,
            "unique_shavers": total_unique_shavers,
            "avg_shaves_per_user": avg_shaves_per_user,
            "median_shaves_per_user": median_shaves_per_user,
            "total_samples": total_samples,
            "sample_users": sample_users,
            "sample_brands": sample_brands,
            "unique_sample_soaps": unique_sample_soaps,
            "sample_percentage": sample_percentage,
            "total_mashup_shaves": total_mashup_shaves,
            "mashup_users": mashup_users,
            "mashup_percentage": mashup_percentage,
            "included_months": sorted(included_months),
            "missing_months": sorted(missing_months),
        }

    def aggregate_all_categories(
        self,
        monthly_data: Dict[str, Dict],
        included_months: Optional[List[str]] = None,
        missing_months: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Aggregate all product categories from monthly data.

        Args:
            monthly_data: Dictionary of monthly data keyed by month
            included_months: List of months that were successfully loaded
            missing_months: List of months that were missing

        Returns:
            Dictionary with all aggregated data and metadata
        """
        # Pre-load enriched records once to cache them for all category calculations
        # This eliminates redundant file I/O when calculating medians and unique_users
        _ = self._load_enriched_records()

        metadata = self.generate_metadata(monthly_data, included_months, missing_months)

        # Aggregate basic categories first
        soaps = self.aggregate_soaps(monthly_data)
        soap_makers = self._aggregate_specialized_category(monthly_data, "soap_makers", "brand")

        # Calculate brand_diversity from aggregated soap_makers and soaps
        from sotd.aggregate.aggregators.manufacturers.brand_diversity_aggregator import (
            aggregate_brand_diversity,
        )

        brand_diversity = aggregate_brand_diversity(soap_makers, soaps)

        return {
            "metadata": metadata,
            "razors": self.aggregate_razors(monthly_data),
            "blades": self.aggregate_blades(monthly_data),
            "brushes": self.aggregate_brushes(monthly_data),
            "soaps": soaps,
            "soap_makers": soap_makers,
            "brand_diversity": brand_diversity,
            "brush_fibers": self.aggregate_brush_fibers(monthly_data),
            "brush_knot_sizes": self.aggregate_brush_knot_sizes(monthly_data),
            "brush_handle_makers": self.aggregate_brush_handle_makers(monthly_data),
            "brush_knot_makers": self.aggregate_brush_knot_makers(monthly_data),
            "razor_blade_combinations": self.aggregate_razor_blade_combinations(monthly_data),
            "highest_use_count_per_blade": self.aggregate_highest_use_count_per_blade(monthly_data),
            # Format aggregations
            "razor_formats": self._aggregate_specialized_category(
                monthly_data, "razor_formats", "format"
            ),
            # Manufacturer aggregations
            "razor_manufacturers": self._aggregate_specialized_category(
                monthly_data, "razor_manufacturers", "brand"
            ),
            # Razor specialized aggregations
            "blackbird_plates": self._aggregate_specialized_category(
                monthly_data, "blackbird_plates", "plate"
            ),
            "christopher_bradley_plates": self._aggregate_specialized_category(
                monthly_data, "christopher_bradley_plates", "plate"
            ),
            "game_changer_plates": self._aggregate_specialized_category(
                monthly_data, "game_changer_plates", "gap"
            ),
            "straight_widths": self._aggregate_specialized_category(
                monthly_data, "straight_widths", "width"
            ),
            "straight_grinds": self._aggregate_specialized_category(
                monthly_data, "straight_grinds", "grind"
            ),
            "straight_points": self._aggregate_specialized_category(
                monthly_data, "straight_points", "point"
            ),
            # User aggregations (special handling - keep "user" field name and sum missed_days)
            "users": self._aggregate_users(monthly_data),
            # User diversity aggregations (special handling for unique_combinations and avg_shaves_per_combination)
            "user_soap_brand_scent_diversity": self._aggregate_user_diversity(
                monthly_data, "user_soap_brand_scent_diversity"
            ),
            "user_single_use_soaps": self._aggregate_user_single_use_soaps(monthly_data),
            "soap_mashup_users": self._aggregate_soap_mashup_users(monthly_data),
        }


def aggregate_monthly_data(
    year: str,
    monthly_data: Dict[str, Dict],
    included_months: Optional[List[str]] = None,
    missing_months: Optional[List[str]] = None,
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Aggregate monthly data into annual summaries.

    Args:
        year: Year being aggregated (YYYY format)
        monthly_data: Dictionary of monthly data keyed by month
        included_months: List of months that were successfully loaded
        missing_months: List of months that were missing
        data_dir: Data directory for loading enriched records (optional)

    Returns:
        Dictionary with annual aggregated data and metadata
    """
    engine = AnnualAggregationEngine(year, data_dir or Path("/dummy"))
    return engine.aggregate_all_categories(monthly_data, included_months, missing_months)


def save_annual_data(aggregated_data: Dict[str, Any], year: str, data_dir: Path) -> None:
    """
    Save annual aggregated data to file using unified file I/O patterns.

    Args:
        aggregated_data: Annual aggregated data to save
        year: Year being saved (YYYY format)
        data_dir: Data directory to save to
    """
    # Validate year format
    if not year.isdigit() or len(year) != 4:
        raise ValueError("Year must be in YYYY format")

    # Validate data structure
    if not isinstance(aggregated_data, dict):
        raise ValueError("Invalid annual data structure")

    if "metadata" not in aggregated_data:
        raise ValueError("Invalid annual data structure")

    required_categories = ["razors", "blades", "brushes", "soaps"]
    for category in required_categories:
        if category not in aggregated_data:
            raise ValueError("Invalid annual data structure")

    # Create output directory structure
    output_dir = data_dir / "aggregated" / "annual"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Define output file path
    file_path = output_dir / f"{year}.json"

    # Use unified file I/O utilities for atomic write
    from sotd.utils.file_io import save_json_data

    save_json_data(aggregated_data, file_path, indent=2)


def process_annual(year: str, data_dir: Path, debug: bool = False, force: bool = False) -> None:
    """
    Process annual aggregation for a single year with performance monitoring.

    Args:
        year: Year to process (YYYY format)
        data_dir: Data directory containing monthly aggregated files
        debug: Enable debug logging
        force: Force regeneration of existing files
    """
    monitor = AnnualPerformanceMonitor(year)
    monitor.start_total_timing()

    try:
        if debug:
            logger.debug(f"Processing annual aggregation for {year}")
            logger.debug(f"Data directory: {data_dir}")
            logger.debug(f"Force: {force}")

        # Load monthly data from the aggregated subdirectory
        monthly_data_dir = data_dir / "aggregated"

        monitor.start_file_io_timing()
        load_result = load_annual_data(year, monthly_data_dir)
        monitor.end_file_io_timing()

        monthly_data = load_result["monthly_data"]
        included_months = load_result["included_months"]
        missing_months = load_result["missing_months"]

        if debug:
            logger.debug(f"Loaded {len(monthly_data)} months of data")
            logger.debug(f"Included months: {included_months}")
            logger.debug(f"Missing months: {missing_months}")

        # Aggregate monthly data (will handle empty data gracefully)
        monitor.start_processing_timing()
        aggregated_data = aggregate_monthly_data(
            year, monthly_data, included_months, missing_months, data_dir
        )
        monitor.end_processing_timing()

        if debug:
            logger.debug("Aggregated data generated")
            logger.debug(f"Total shaves: {aggregated_data['metadata']['total_shaves']}")
            logger.debug(f"Unique shavers: {aggregated_data['metadata']['unique_shavers']}")

        # Save aggregated data
        monitor.start_file_io_timing()
        save_annual_data(aggregated_data, year, data_dir)
        monitor.end_file_io_timing()

        # Update performance metrics
        monitor.metrics.total_shaves = aggregated_data["metadata"]["total_shaves"]
        monitor.metrics.unique_shavers = aggregated_data["metadata"]["unique_shavers"]
        monitor.metrics.month_count = len(included_months)

        if debug:
            logger.debug(f"Annual aggregation for {year} completed")

    finally:
        monitor.end_total_timing()
        if debug:
            monitor.print_summary()


def process_single_annual(
    year: str, data_dir: Path, debug: bool = False, force: bool = False
) -> dict | None:
    """Process a single year for parallel processing.

    Args:
        year: Year to process (YYYY format)
        data_dir: Data directory containing monthly aggregated files
        debug: Enable debug logging
        force: Force regeneration of existing files

    Returns:
        Dictionary with processing results or error information, or None if skipped
    """
    try:
        process_annual(year, data_dir, debug=debug, force=force)
        return {
            "year": year,
            "status": "completed",
        }
    except FileNotFoundError as e:
        return {
            "status": "error",
            "year": year,
            "error": f"{e}. Run monthly aggregation first.",
        }
    except Exception as e:
        return {
            "status": "error",
            "year": year,
            "error": f"Failed to process {year}: {e}",
        }


def process_annual_range_parallel(
    years: Sequence[str],
    data_dir: Path,
    debug: bool = False,
    force: bool = False,
    max_workers: int = 8,
) -> bool:
    """Process multiple years in parallel using ProcessPoolExecutor.

    Args:
        years: List of years to process (YYYY format)
        data_dir: Data directory containing monthly aggregated files
        debug: Enable debug logging
        force: Force regeneration of existing files
        max_workers: Maximum number of parallel workers

    Returns:
        True if there were errors, False otherwise
    """
    logger.info(f"Processing {len(years)} years in parallel...")

    wall_clock_start = time.time()

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        future_to_year = {
            executor.submit(process_single_annual, year, data_dir, debug, force): year
            for year in years
        }

        results = []
        for future in tqdm(
            as_completed(future_to_year),
            total=len(years),
            desc="Processing",
            unit="year",
            disable=should_disable_tqdm(),
        ):
            year = future_to_year[future]
            try:
                result = future.result()
                if result:
                    results.append(result)
            except Exception as e:
                logger.error(f"Failed to process {year}: {e}")

    # Filter results and check for errors
    errors = [r for r in results if r and r.get("status") == "error"]
    completed = [r for r in results if r and r.get("status") == "completed"]

    # Display error details
    if errors:
        logger.error("\n❌ Error Details:")
        for error_result in errors:
            year = error_result.get("year", "unknown")
            error_msg = error_result.get("error", "unknown error")
            logger.error(f"  {year}: {error_msg}")

    # Print summary
    wall_clock_time = time.time() - wall_clock_start
    if completed:
        logger.info(
            f"Annual aggregation complete for {years[0]}…{years[-1]}: "
            f"{len(completed)} year(s) processed"
        )
    logger.info(f"Parallel processing completed in {wall_clock_time:.2f}s")

    return len(errors) > 0


def process_annual_range(
    years: Sequence[str], data_dir: Path, debug: bool = False, force: bool = False
) -> None:
    """
    Process annual aggregation for multiple years with performance monitoring.

    Args:
        years: List of years to process (YYYY format)
        data_dir: Data directory containing monthly aggregated files
        debug: Enable debug logging
        force: Force regeneration of existing files
    """
    if debug:
        logger.info(f"Processing annual aggregation for years: {years}")
        logger.info(f"Data directory: {data_dir}")
        logger.info(f"Force: {force}")

    logger.info(f"Processing annual aggregation for {len(years)} year(s)...")
    for year in tqdm(years, desc="Annual aggregation", unit="year", disable=should_disable_tqdm()):
        try:
            process_annual(year, data_dir, debug=debug, force=force)
        except Exception as e:
            logger.error(f"Failed to process year {year}: {e}")
            if debug:
                import traceback

                logger.error(traceback.format_exc())
