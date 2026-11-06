"""
Tests for the annual aggregation engine.

Tests the functionality for combining monthly aggregated data into annual summaries.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from sotd.aggregate.annual_engine import (
    AnnualAggregationEngine,
    aggregate_monthly_data,
    process_annual,
    process_annual_range,
)


def create_enriched_records_for_razors(razor_data: list[dict]) -> list[dict]:
    """Create enriched records that match the razor data for testing.

    Args:
        razor_data: List of dicts with "name", "shaves", "unique_users"

    Returns:
        List of enriched records with appropriate razor matches and authors
    """
    enriched_records = []
    for razor in razor_data:
        name = razor["name"]
        unique_users = razor["unique_users"]
        shaves = razor["shaves"]

        # Parse name into brand and model (assume "Brand Model" format)
        parts = name.split(" ", 1)
        brand = parts[0]
        model = parts[1] if len(parts) > 1 else ""

        # Create unique_users number of unique authors
        for user_idx in range(unique_users):
            # Create multiple shaves per user if needed
            shaves_per_user = shaves // unique_users
            remaining_shaves = shaves % unique_users
            user_shaves = shaves_per_user + (1 if user_idx < remaining_shaves else 0)

            for _ in range(user_shaves):
                enriched_records.append(
                    {
                        "author": f"user_{name}_{user_idx}",
                        "razor": {
                            "matched": {
                                "brand": brand,
                                "model": model,
                                "format": "DE",
                            }
                        },
                    }
                )

    return enriched_records


def create_enriched_records_for_category(category: str, product_data: list[dict]) -> list[dict]:
    """Create enriched records for a product category.

    Args:
        category: "razors", "blades", "brushes", or "soaps"
        product_data: List of dicts with "name", "shaves", "unique_users"

    Returns:
        List of enriched records
    """
    if category == "razors":
        return create_enriched_records_for_razors(product_data)
    elif category == "blades":
        # Similar structure for blades
        enriched_records = []
        for blade in product_data:
            name = blade["name"]
            unique_users = blade["unique_users"]
            shaves = blade["shaves"]
            parts = name.split(" ", 1)
            brand = parts[0]
            model = parts[1] if len(parts) > 1 else ""
            for user_idx in range(unique_users):
                shaves_per_user = shaves // unique_users
                remaining_shaves = shaves % unique_users
                user_shaves = shaves_per_user + (1 if user_idx < remaining_shaves else 0)
                for _ in range(user_shaves):
                    enriched_records.append(
                        {
                            "author": f"user_{name}_{user_idx}",
                            "blade": {
                                "matched": {
                                    "brand": brand,
                                    "model": model,
                                    "format": "DE",
                                }
                            },
                        }
                    )
        return enriched_records
    elif category == "brushes":
        # Brushes have handle_maker and knot_maker structure
        enriched_records = []
        for brush in product_data:
            name = brush["name"]
            unique_users = brush["unique_users"]
            shaves = brush["shaves"]
            # Assume format like "HandleMaker KnotMaker" or just "Brand"
            parts = name.split(" ", 1)
            brand = parts[0]
            model = parts[1] if len(parts) > 1 else ""
            for user_idx in range(unique_users):
                shaves_per_user = shaves // unique_users
                remaining_shaves = shaves % unique_users
                user_shaves = shaves_per_user + (1 if user_idx < remaining_shaves else 0)
                for _ in range(user_shaves):
                    enriched_records.append(
                        {
                            "author": f"user_{name}_{user_idx}",
                            "brush": {
                                "matched": {
                                    "brand": brand,
                                    "model": model,
                                }
                            },
                        }
                    )
        return enriched_records
    elif category == "soaps":
        enriched_records = []
        for soap in product_data:
            name = soap["name"]
            unique_users = soap["unique_users"]
            shaves = soap["shaves"]
            # Soaps use "Brand Scent" format in monthly data, but enriched creates "Brand - Scent"
            # Handle both formats for matching
            if " - " in name:
                # Already in "Brand - Scent" format
                parts = name.split(" - ", 1)
                brand = parts[0]
                scent = parts[1] if len(parts) > 1 else ""
            else:
                # "Brand Scent" format - split on first space
                parts = name.split(" ", 1)
                brand = parts[0]
                scent = parts[1] if len(parts) > 1 else ""
            for user_idx in range(unique_users):
                shaves_per_user = shaves // unique_users
                remaining_shaves = shaves % unique_users
                user_shaves = shaves_per_user + (1 if user_idx < remaining_shaves else 0)
                for _ in range(user_shaves):
                    enriched_records.append(
                        {
                            "author": f"user_{name}_{user_idx}",
                            "soap": {
                                "matched": {
                                    "brand": brand,
                                    "scent": scent,
                                }
                            },
                        }
                    )
        return enriched_records
    else:
        return []


class TestAnnualAggregationEngine:
    """Test the AnnualAggregationEngine class."""

    def test_init_with_valid_year(self):
        """Test initialization with valid year."""
        engine = AnnualAggregationEngine("2024", Path("/data"))
        assert engine.year == "2024"
        assert engine.data_dir == Path("/data")

    def test_init_with_invalid_year_format(self):
        """Test initialization with invalid year format."""
        with pytest.raises(ValueError, match="Year must be in YYYY format"):
            AnnualAggregationEngine("24", Path("/data"))

    def test_init_with_non_numeric_year(self):
        """Test initialization with non-numeric year."""
        with pytest.raises(ValueError, match="Year must be numeric"):
            AnnualAggregationEngine("abcd", Path("/data"))

    @patch.object(AnnualAggregationEngine, "_load_enriched_records")
    def test_aggregate_razors_single_month(self, mock_load_enriched):
        """Test aggregating razors from a single month."""
        engine = AnnualAggregationEngine("2024", Path("/data"))

        monthly_data = {
            "2024-01": {
                "meta": {"total_shaves": 100, "unique_shavers": 50},
                "data": {
                    "razors": [
                        {"name": "Razor A", "shaves": 30, "unique_users": 25},
                        {"name": "Razor B", "shaves": 20, "unique_users": 15},
                    ],
                },
            }
        }

        # Mock enriched records to match the monthly data
        enriched_records = create_enriched_records_for_category(
            "razors",
            [
                {"name": "Razor A", "shaves": 30, "unique_users": 25},
                {"name": "Razor B", "shaves": 20, "unique_users": 15},
            ],
        )
        mock_load_enriched.return_value = enriched_records

        result = engine.aggregate_razors(monthly_data)

        assert len(result) == 2
        assert result[0]["name"] == "Razor A"
        assert result[0]["shaves"] == 30
        assert result[0]["unique_users"] == 25
        assert result[0]["rank"] == 1
        assert result[1]["name"] == "Razor B"
        assert result[1]["shaves"] == 20
        assert result[1]["unique_users"] == 15
        assert result[1]["rank"] == 2

    @patch.object(AnnualAggregationEngine, "_load_enriched_records")
    def test_aggregate_razors_multiple_months(self, mock_load_enriched):
        """Test aggregating razors from multiple months."""
        engine = AnnualAggregationEngine("2024", Path("/data"))

        monthly_data = {
            "2024-01": {
                "meta": {"total_shaves": 100, "unique_shavers": 50},
                "data": {
                    "razors": [
                        {"name": "Razor A", "shaves": 30, "unique_users": 25},
                        {"name": "Razor B", "shaves": 20, "unique_users": 15},
                    ],
                },
            },
            "2024-02": {
                "meta": {"total_shaves": 80, "unique_shavers": 40},
                "data": {
                    "razors": [
                        {"name": "Razor A", "shaves": 25, "unique_users": 20},
                        {"name": "Razor C", "shaves": 15, "unique_users": 10},
                    ],
                },
            },
        }

        # Mock enriched records - aggregate across months (45 unique users for Razor A)
        # Need to create records that when aggregated give the correct unique_users
        enriched_records = []
        # Razor A: 25 users from month 1 + 20 users from month 2 (some overlap possible, but we'll create 45 unique)
        for user_idx in range(45):
            enriched_records.append(
                {
                    "author": f"user_Razor_A_{user_idx}",
                    "razor": {"matched": {"brand": "Razor", "model": "A", "format": "DE"}},
                }
            )
        # Razor B: 15 users
        for user_idx in range(15):
            enriched_records.append(
                {
                    "author": f"user_Razor_B_{user_idx}",
                    "razor": {"matched": {"brand": "Razor", "model": "B", "format": "DE"}},
                }
            )
        # Razor C: 10 users
        for user_idx in range(10):
            enriched_records.append(
                {
                    "author": f"user_Razor_C_{user_idx}",
                    "razor": {"matched": {"brand": "Razor", "model": "C", "format": "DE"}},
                }
            )
        mock_load_enriched.return_value = enriched_records

        result = engine.aggregate_razors(monthly_data)

        assert len(result) == 3
        # Razor A should be first (30+25=55 shaves)
        assert result[0]["name"] == "Razor A"
        assert result[0]["shaves"] == 55
        assert result[0]["unique_users"] == 45  # 25+20 unique users
        assert result[0]["rank"] == 1
        # Razor B should be second (20 shaves)
        assert result[1]["name"] == "Razor B"
        assert result[1]["shaves"] == 20
        assert result[1]["unique_users"] == 15
        assert result[1]["rank"] == 2
        # Razor C should be third (15 shaves)
        assert result[2]["name"] == "Razor C"
        assert result[2]["shaves"] == 15
        assert result[2]["unique_users"] == 10
        assert result[2]["rank"] == 3

    def test_aggregate_razors_empty_data(self):
        """Test aggregating razors with empty data."""
        engine = AnnualAggregationEngine("2024", Path("/data"))

        monthly_data = {}
        result = engine.aggregate_razors(monthly_data)
        assert result == []

    def test_aggregate_razors_no_razor_data(self):
        """Test aggregating razors when no razor data exists."""
        engine = AnnualAggregationEngine("2024", Path("/data"))

        monthly_data = {
            "2024-01": {"meta": {"total_shaves": 100, "unique_shavers": 50}, "data": {"razors": []}}
        }

        result = engine.aggregate_razors(monthly_data)
        assert result == []

    @patch.object(AnnualAggregationEngine, "_load_enriched_records")
    def test_aggregate_blades_single_month(self, mock_load_enriched):
        """Test aggregating blades from a single month."""
        engine = AnnualAggregationEngine("2024", Path("/data"))

        monthly_data = {
            "2024-01": {
                "meta": {"total_shaves": 100, "unique_shavers": 50},
                "data": {
                    "blades": [
                        {"name": "Blade A", "shaves": 40, "unique_users": 30},
                        {"name": "Blade B", "shaves": 30, "unique_users": 20},
                    ],
                },
            }
        }

        # Mock enriched records
        enriched_records = create_enriched_records_for_category(
            "blades",
            [
                {"name": "Blade A", "shaves": 40, "unique_users": 30},
                {"name": "Blade B", "shaves": 30, "unique_users": 20},
            ],
        )
        mock_load_enriched.return_value = enriched_records

        result = engine.aggregate_blades(monthly_data)

        assert len(result) == 2
        assert result[0]["name"] == "Blade A"
        assert result[0]["shaves"] == 40
        assert result[0]["unique_users"] == 30
        assert result[0]["rank"] == 1
        assert result[1]["name"] == "Blade B"
        assert result[1]["shaves"] == 30
        assert result[1]["unique_users"] == 20
        assert result[1]["rank"] == 2

    @patch.object(AnnualAggregationEngine, "_load_enriched_records")
    def test_aggregate_brushes_single_month(self, mock_load_enriched):
        """Test aggregating brushes from a single month."""
        engine = AnnualAggregationEngine("2024", Path("/data"))

        monthly_data = {
            "2024-01": {
                "meta": {"total_shaves": 100, "unique_shavers": 50},
                "data": {
                    "brushes": [
                        {"name": "Brush A", "shaves": 35, "unique_users": 25},
                        {"name": "Brush B", "shaves": 25, "unique_users": 15},
                    ],
                },
            }
        }

        # Mock enriched records
        enriched_records = create_enriched_records_for_category(
            "brushes",
            [
                {"name": "Brush A", "shaves": 35, "unique_users": 25},
                {"name": "Brush B", "shaves": 25, "unique_users": 15},
            ],
        )
        mock_load_enriched.return_value = enriched_records

        result = engine.aggregate_brushes(monthly_data)

        assert len(result) == 2
        assert result[0]["name"] == "Brush A"
        assert result[0]["shaves"] == 35
        assert result[0]["unique_users"] == 25
        assert result[0]["rank"] == 1
        assert result[1]["name"] == "Brush B"
        assert result[1]["shaves"] == 25
        assert result[1]["unique_users"] == 15
        assert result[1]["rank"] == 2

    @patch.object(AnnualAggregationEngine, "_load_enriched_records")
    def test_aggregate_soaps_single_month(self, mock_load_enriched):
        """Test aggregating soaps from a single month."""
        engine = AnnualAggregationEngine("2024", Path("/data"))

        monthly_data = {
            "2024-01": {
                "meta": {"total_shaves": 100, "unique_shavers": 50},
                "data": {
                    "soaps": [
                        {"name": "Soap - A", "shaves": 45, "unique_users": 35},
                        {"name": "Soap - B", "shaves": 35, "unique_users": 25},
                    ],
                },
            }
        }

        # Mock enriched records
        enriched_records = create_enriched_records_for_category(
            "soaps",
            [
                {"name": "Soap - A", "shaves": 45, "unique_users": 35},
                {"name": "Soap - B", "shaves": 35, "unique_users": 25},
            ],
        )
        mock_load_enriched.return_value = enriched_records

        result = engine.aggregate_soaps(monthly_data)

        assert len(result) == 2
        assert result[0]["name"] == "Soap - A"
        assert result[0]["shaves"] == 45
        assert result[0]["unique_users"] == 35
        assert result[0]["rank"] == 1
        assert result[1]["name"] == "Soap - B"
        assert result[1]["shaves"] == 35
        assert result[1]["unique_users"] == 25
        assert result[1]["rank"] == 2

    @patch.object(AnnualAggregationEngine, "_load_enriched_records")
    def test_generate_metadata_single_month(self, mock_load_enriched):
        """Test generating metadata from a single month."""
        engine = AnnualAggregationEngine("2024", Path("/data"))

        monthly_data = {
            "2024-01": {
                "meta": {"total_shaves": 100, "unique_shavers": 50},
                "data": {
                    "razors": [{"name": "Razor A", "shaves": 30, "unique_users": 25}],
                },
            }
        }

        # Mock enriched records with 50 unique authors
        enriched_records = [{"author": f"user_{i}"} for i in range(50)]
        mock_load_enriched.return_value = enriched_records

        result = engine.generate_metadata(monthly_data)

        assert result["year"] == "2024"
        assert result["total_shaves"] == 100
        assert result["unique_shavers"] == 50
        assert result["included_months"] == ["2024-01"]
        # All other months should be missing
        expected_missing = [f"2024-{month:02d}" for month in range(2, 13)]
        assert result["missing_months"] == expected_missing

    @patch.object(AnnualAggregationEngine, "_load_enriched_records")
    def test_generate_metadata_multiple_months(self, mock_load_enriched):
        """Test generating metadata from multiple months."""
        engine = AnnualAggregationEngine("2024", Path("/data"))

        monthly_data = {
            "2024-01": {
                "meta": {"total_shaves": 100, "unique_shavers": 50},
                "data": {
                    "razors": [{"name": "Razor A", "shaves": 30, "unique_users": 25}],
                },
            },
            "2024-02": {
                "meta": {"total_shaves": 80, "unique_shavers": 40},
                "data": {
                    "razors": [{"name": "Razor B", "shaves": 25, "unique_users": 20}],
                },
            },
        }

        # Mock enriched records with 90 unique authors (50+40, some overlap possible)
        enriched_records = [{"author": f"user_{i}"} for i in range(90)]
        mock_load_enriched.return_value = enriched_records

        result = engine.generate_metadata(monthly_data)

        assert result["year"] == "2024"
        assert result["total_shaves"] == 180  # 100 + 80
        assert result["unique_shavers"] == 90  # 50 + 40
        assert result["included_months"] == ["2024-01", "2024-02"]
        # All other months should be missing
        expected_missing = [f"2024-{month:02d}" for month in range(3, 13)]
        assert result["missing_months"] == expected_missing

    @patch.object(AnnualAggregationEngine, "_load_enriched_records")
    def test_generate_metadata_with_missing_months(self, mock_load_enriched):
        """Test generating metadata with missing months."""
        engine = AnnualAggregationEngine("2024", Path("/data"))

        monthly_data = {
            "2024-01": {
                "meta": {"total_shaves": 100, "unique_shavers": 50},
                "data": {
                    "razors": [{"name": "Razor A", "shaves": 30, "unique_users": 25}],
                },
            },
            "2024-03": {
                "meta": {"total_shaves": 80, "unique_shavers": 40},
                "data": {
                    "razors": [{"name": "Razor B", "shaves": 25, "unique_users": 20}],
                },
            },
        }

        # Mock enriched records with 90 unique authors
        enriched_records = [{"author": f"user_{i}"} for i in range(90)]
        mock_load_enriched.return_value = enriched_records

        result = engine.generate_metadata(monthly_data)

        assert result["year"] == "2024"
        assert result["total_shaves"] == 180  # 100 + 80
        assert result["unique_shavers"] == 90  # 50 + 40
        assert result["included_months"] == ["2024-01", "2024-03"]
        # All months except 2024-01 and 2024-03 should be missing
        expected_missing = ["2024-02"] + [f"2024-{month:02d}" for month in range(4, 13)]
        assert result["missing_months"] == expected_missing

    @patch.object(AnnualAggregationEngine, "_load_enriched_records")
    def test_aggregate_all_categories(self, mock_load_enriched):
        """Test aggregating all categories."""
        engine = AnnualAggregationEngine("2024", Path("/data"))

        monthly_data = {
            "2024-01": {
                "meta": {"total_shaves": 100, "unique_shavers": 50},
                "data": {
                    "razors": [{"name": "Razor A", "shaves": 30, "unique_users": 25}],
                    "blades": [{"name": "Blade A", "shaves": 40, "unique_users": 30}],
                    "brushes": [{"name": "Brush A", "shaves": 35, "unique_users": 25}],
                    "soaps": [{"name": "Soap - A", "shaves": 45, "unique_users": 35}],
                },
            }
        }

        # Mock enriched records for all categories
        # We need exactly 50 unique authors total for unique_shavers
        # Create records where authors overlap across categories to reach exactly 50 unique
        enriched_records = []

        # Create 50 unique authors that use different combinations of products
        # This simulates real-world where users use multiple product types
        all_authors = [f"user_{i}" for i in range(50)]

        # Distribute authors across categories (with overlap)
        # Razor A: first 25 authors
        for author in all_authors[:25]:
            enriched_records.append(
                {
                    "author": author,
                    "razor": {"matched": {"brand": "Razor", "model": "A", "format": "DE"}},
                }
            )

        # Blade A: authors 10-39 (overlaps with razors)
        for author in all_authors[10:40]:
            enriched_records.append(
                {
                    "author": author,
                    "blade": {"matched": {"brand": "Blade", "model": "A", "format": "DE"}},
                }
            )

        # Brush A: authors 15-39 (overlaps with razors and blades)
        for author in all_authors[15:40]:
            enriched_records.append(
                {"author": author, "brush": {"matched": {"brand": "Brush", "model": "A"}}}
            )

        # Soap A: authors 0-34 (overlaps with all)
        for author in all_authors[0:35]:
            enriched_records.append(
                {"author": author, "soap": {"matched": {"brand": "Soap", "scent": "A"}}}
            )

        # Add remaining authors (40-49) with just author field to reach 50 total unique
        for author in all_authors[40:50]:
            enriched_records.append({"author": author})

        mock_load_enriched.return_value = enriched_records

        result = engine.aggregate_all_categories(monthly_data)

        assert "metadata" in result
        assert "razors" in result
        assert "blades" in result
        assert "brushes" in result
        assert "soaps" in result

        assert result["metadata"]["year"] == "2024"
        assert result["metadata"]["total_shaves"] == 100
        assert result["metadata"]["unique_shavers"] == 50

        assert len(result["razors"]) == 1
        assert result["razors"][0]["name"] == "Razor A"
        assert len(result["blades"]) == 1
        assert result["blades"][0]["name"] == "Blade A"
        assert len(result["brushes"]) == 1
        assert result["brushes"][0]["name"] == "Brush A"
        assert len(result["soaps"]) == 1
        assert result["soaps"][0]["name"] == "Soap - A"

    def test_aggregate_all_categories_empty_data(self):
        """Test aggregating all categories with empty data."""
        engine = AnnualAggregationEngine("2024", Path("/data"))

        monthly_data = {}
        result = engine.aggregate_all_categories(monthly_data)

        assert "metadata" in result
        assert result["metadata"]["year"] == "2024"
        assert result["metadata"]["total_shaves"] == 0
        assert result["metadata"]["unique_shavers"] == 0
        assert result["metadata"]["included_months"] == []
        # All 12 months should be missing when no data
        expected_missing = [f"2024-{month:02d}" for month in range(1, 13)]
        assert result["metadata"]["missing_months"] == expected_missing

    def test_aggregate_user_diversity_with_hhi(self):
        """Test annual aggregation of user diversity includes HHI and effective_soaps fields."""
        engine = AnnualAggregationEngine("2024", Path("/data"))

        monthly_data = {
            "2024-01": {
                "meta": {"total_shaves": 100, "unique_shavers": 50},
                "data": {
                    "user_soap_brand_scent_diversity": [
                        {
                            "user": "user1",
                            "unique_combinations": 3,
                            "shaves": 10,
                            "avg_shaves_per_combination": 3.33,
                            "hhi": 0.5,
                            "effective_soaps": 2.0,
                        },
                        {
                            "user": "user2",
                            "unique_combinations": 2,
                            "shaves": 5,
                            "avg_shaves_per_combination": 2.5,
                            "hhi": 0.6,
                            "effective_soaps": 1.67,
                        },
                    ],
                },
            },
            "2024-02": {
                "meta": {"total_shaves": 80, "unique_shavers": 40},
                "data": {
                    "user_soap_brand_scent_diversity": [
                        {
                            "user": "user1",
                            "unique_combinations": 2,
                            "shaves": 8,
                            "avg_shaves_per_combination": 4.0,
                            "hhi": 0.4,
                            "effective_soaps": 2.5,
                        },
                        {
                            "user": "user2",
                            "unique_combinations": 1,
                            "shaves": 6,
                            "avg_shaves_per_combination": 6.0,
                            "hhi": 1.0,
                            "effective_soaps": 1.0,
                        },
                    ],
                },
            },
        }

        result = engine._aggregate_user_diversity(monthly_data, "user_soap_brand_scent_diversity")

        assert len(result) == 2
        # user1 should be first (3+2=5 unique combinations, 10+8=18 shaves)
        assert result[0]["user"] == "user1"
        assert result[0]["unique_combinations"] == 5
        assert result[0]["shaves"] == 18
        assert result[0]["avg_shaves_per_combination"] == 3.6
        # HHI and effective_soaps are set to 0.0 as placeholders
        # (cannot be accurately recalculated from monthly summaries alone)
        assert result[0]["hhi"] == 0.0
        assert result[0]["effective_soaps"] == 0.0

        # user2 should be second (2+1=3 unique combinations, 5+6=11 shaves)
        assert result[1]["user"] == "user2"
        assert result[1]["unique_combinations"] == 3
        assert result[1]["shaves"] == 11
        # Rounding: 11 / 3 = 3.666... rounds to 3.7 with round(1)
        assert abs(result[1]["avg_shaves_per_combination"] - 3.7) < 0.01
        assert result[1]["hhi"] == 0.0
        assert result[1]["effective_soaps"] == 0.0

    @patch("sotd.aggregate.load.load_enriched_data")
    def test_aggregate_user_single_use_soaps_from_enriched(self, mock_load_enriched):
        """Annual exclusive-use soaps are recalculated from combined enriched records."""
        engine = AnnualAggregationEngine("2024", Path("/data"))
        monthly_data = {"2024-01": {"data": {}}, "2024-02": {"data": {}}}

        mock_load_enriched.side_effect = [
            [
                {
                    "author": "alice",
                    "soap": {"matched": {"brand": "A", "scent": "1", "countable": True}},
                },
            ],
            [
                {
                    "author": "alice",
                    "soap": {"matched": {"brand": "A", "scent": "1", "countable": True}},
                },
                {
                    "author": "bob",
                    "soap": {"matched": {"brand": "B", "scent": "2", "countable": True}},
                },
            ],
        ]

        result = engine._aggregate_user_single_use_soaps(monthly_data)

        by_user = {row["user"]: row for row in result}
        # Soap A used only by alice across the year -> 1 point (not 2 from summing months)
        assert by_user["alice"]["single_use_soaps"] == 1
        assert by_user["alice"]["shaves"] == 2
        assert by_user["bob"]["single_use_soaps"] == 1

    @patch("sotd.aggregate.load.load_enriched_data")
    def test_aggregate_soap_mashup_users_from_enriched(self, mock_load_enriched):
        """Annual soap-mashup-users table is recalculated from combined enriched records.

        Mirrors the monthly processor's data.soap_mashup_users key; the annual
        software template renders a soap-mashup-users table, so the annual
        aggregate must carry the same key.
        """
        engine = AnnualAggregationEngine("2024", Path("/data"))
        monthly_data = {"2024-01": {"data": {}}, "2024-02": {"data": {}}}

        mock_load_enriched.side_effect = [
            [
                {
                    "author": "alice",
                    "soap": {
                        "matched": {"brand": "A", "scent": "1"},
                        "enriched": {"is_mashup": True},
                    },
                },
                {
                    "author": "bob",
                    "soap": {
                        "matched": {"brand": "B", "scent": "2"},
                        "enriched": {"is_mashup": True},
                    },
                },
            ],
            [
                {
                    "author": "alice",
                    "soap": {
                        "matched": {"brand": "C", "scent": "3"},
                        "enriched": {"is_mashup": True},
                    },
                },
                {
                    # non-mashup: must not count
                    "author": "alice",
                    "soap": {"matched": {"brand": "D", "scent": "4"}, "enriched": {}},
                },
            ],
        ]

        result = engine._aggregate_soap_mashup_users(monthly_data)

        by_user = {row["user"]: row for row in result}
        assert by_user["alice"]["shaves"] == 2
        assert by_user["bob"]["shaves"] == 1
        assert result[0]["user"] == "alice"  # sorted by shaves desc


class TestAggregateMonthlyData:
    """Test the aggregate_monthly_data function."""

    @patch("sotd.aggregate.annual_engine.AnnualAggregationEngine._load_enriched_records")
    def test_aggregate_monthly_data_success(self, mock_load_enriched):
        """Test successful aggregation of monthly data."""
        monthly_data = {
            "2024-01": {
                "meta": {"total_shaves": 100, "unique_shavers": 50},
                "data": {
                    "razors": [{"name": "Razor A", "shaves": 30, "unique_users": 25}],
                },
            },
            "2024-02": {
                "meta": {"total_shaves": 80, "unique_shavers": 40},
                "data": {
                    "razors": [{"name": "Razor A", "shaves": 25, "unique_users": 20}],
                },
            },
        }

        # Mock enriched records - 45 unique users for Razor A, 90 unique shavers total
        enriched_records = []
        razor_authors = set()
        for user_idx in range(45):
            author = f"user_Razor_A_{user_idx}"
            enriched_records.append(
                {
                    "author": author,
                    "razor": {"matched": {"brand": "Razor", "model": "A", "format": "DE"}},
                }
            )
            razor_authors.add(author)

        # Add additional authors to reach 90 unique shavers total
        # Some may overlap, so ensure we have exactly 90 unique
        for i in range(len(razor_authors), 90):
            author = f"user_extra_{i}"
            enriched_records.append({"author": author})

        mock_load_enriched.return_value = enriched_records

        result = aggregate_monthly_data("2024", monthly_data)

        assert "metadata" in result
        assert "razors" in result
        assert result["metadata"]["year"] == "2024"
        assert result["metadata"]["total_shaves"] == 180
        assert result["metadata"]["unique_shavers"] == 90
        assert result["metadata"]["included_months"] == ["2024-01", "2024-02"]
        # All other months should be missing
        expected_missing = [f"2024-{month:02d}" for month in range(3, 13)]
        assert result["metadata"]["missing_months"] == expected_missing

    def test_aggregate_monthly_data_empty(self):
        """Test aggregation with empty monthly data."""
        result = aggregate_monthly_data("2024", {})

        assert "metadata" in result
        assert result["metadata"]["year"] == "2024"
        assert result["metadata"]["total_shaves"] == 0
        assert result["metadata"]["unique_shavers"] == 0
        assert result["metadata"]["included_months"] == []
        # All 12 months should be missing when no data
        expected_missing = [f"2024-{month:02d}" for month in range(1, 13)]
        assert result["metadata"]["missing_months"] == expected_missing


class TestProcessAnnual:
    """Test the process_annual function."""

    @patch("sotd.aggregate.annual_engine.load_annual_data")
    @patch("sotd.aggregate.annual_engine.aggregate_monthly_data")
    @patch("sotd.aggregate.annual_engine.save_annual_data")
    def test_process_annual_success(self, mock_save, mock_aggregate, mock_load):
        """Test successful annual processing."""
        # Mock the load function
        mock_load.return_value = {
            "year": "2024",
            "monthly_data": {
                "2024-01": {
                    "meta": {"total_shaves": 100, "unique_shavers": 50},
                    "data": {"razors": []},
                },
                "2024-02": {
                    "meta": {"total_shaves": 80, "unique_shavers": 40},
                    "data": {"razors": []},
                },
            },
            "included_months": ["2024-01", "2024-02"],
            "missing_months": [],
            "validation_errors": [],
        }

        # Mock the aggregate function
        mock_aggregate.return_value = {
            "metadata": {"year": "2024", "total_shaves": 180, "unique_shavers": 90},
            "razors": [],
        }

        # Mock the save function
        mock_save.return_value = None

        process_annual("2024", Path("/data"), debug=True, force=True)

        # Verify calls
        mock_load.assert_called_once_with("2024", Path("/data/aggregated"))
        # aggregate_monthly_data now includes data_dir parameter
        mock_aggregate.assert_called_once()
        call_args = mock_aggregate.call_args
        assert call_args[0][0] == "2024"
        assert call_args[0][1] == mock_load.return_value["monthly_data"]
        assert call_args[0][2] == mock_load.return_value["included_months"]
        assert call_args[0][3] == mock_load.return_value["missing_months"]
        mock_save.assert_called_once_with(mock_aggregate.return_value, "2024", Path("/data"))

    @patch("sotd.aggregate.annual_engine.load_annual_data")
    def test_process_annual_load_error(self, mock_load):
        """Test annual processing with load error."""
        mock_load.side_effect = FileNotFoundError("No data found")

        with pytest.raises(FileNotFoundError):
            process_annual("2024", Path("/data"), debug=True, force=True)

    @patch("sotd.aggregate.annual_engine.load_annual_data")
    @patch("sotd.aggregate.annual_engine.aggregate_monthly_data")
    def test_process_annual_aggregate_error(self, mock_aggregate, mock_load):
        """Test annual processing with aggregation error."""
        mock_load.return_value = {
            "year": "2024",
            "monthly_data": {"2024-01": {"meta": {"total_shaves": 100}, "data": {"razors": []}}},
            "included_months": ["2024-01"],
            "missing_months": [],
            "validation_errors": [],
        }
        mock_aggregate.side_effect = ValueError("Aggregation failed")

        with pytest.raises(ValueError):
            process_annual("2024", Path("/data"), debug=True, force=True)


class TestProcessAnnualRange:
    """Test the process_annual_range function."""

    @patch("sotd.aggregate.annual_engine.process_annual")
    def test_process_annual_range_success(self, mock_process):
        """Test successful annual range processing."""
        years = ["2023", "2024"]
        data_dir = Path("/data")

        process_annual_range(years, data_dir, debug=True, force=True)

        # Verify process_annual called for each year
        assert mock_process.call_count == 2
        mock_process.assert_any_call("2023", data_dir, debug=True, force=True)
        mock_process.assert_any_call("2024", data_dir, debug=True, force=True)

    @patch("sotd.aggregate.annual_engine.process_annual")
    def test_process_annual_range_with_errors(self, mock_process):
        """Test annual range processing with some errors."""
        years = ["2023", "2024", "2025"]
        data_dir = Path("/data")

        # Mock process_annual to fail for 2024
        def mock_process_side_effect(year, data_dir, debug, force):
            if year == "2024":
                raise FileNotFoundError(f"No data for {year}")

        mock_process.side_effect = mock_process_side_effect

        # Should not raise exception, should continue processing other years
        process_annual_range(years, data_dir, debug=True, force=True)

        # Verify process_annual called for all years
        assert mock_process.call_count == 3
        mock_process.assert_any_call("2023", data_dir, debug=True, force=True)
        mock_process.assert_any_call("2024", data_dir, debug=True, force=True)
        mock_process.assert_any_call("2025", data_dir, debug=True, force=True)

    def test_process_annual_range_empty_years(self):
        """Test annual range processing with empty years list."""
        data_dir = Path("/data")

        # Should not raise exception
        process_annual_range([], data_dir, debug=True, force=True)


class TestAnnualSpecializedRankTieBreak:
    """Annual specialized tables must rank ties the way monthly does.

    Monthly BaseAggregator._sort_and_rank ranks on (shaves, unique_users);
    the annual specialized helpers ranked on shaves only, so two products
    tied on shaves but differing on users shared an annual rank while
    holding distinct monthly ranks.
    """

    @patch.object(AnnualAggregationEngine, "_load_enriched_records")
    def test_specialized_category_tie_broken_by_unique_users(self, mock_load_enriched):
        """Equal shaves, different users -> distinct annual ranks, like monthly."""
        engine = AnnualAggregationEngine("2024", Path("/data"))
        monthly_data = {
            "2024-01": {
                "data": {
                    "razor_manufacturers": [
                        {"brand": "BrandA", "shaves": 10, "unique_users": 5, "rank": 1},
                        {"brand": "BrandB", "shaves": 10, "unique_users": 2, "rank": 2},
                    ]
                }
            }
        }
        enriched = create_enriched_records_for_razors(
            [
                {"name": "BrandA Model", "shaves": 10, "unique_users": 5},
                {"name": "BrandB Model", "shaves": 10, "unique_users": 2},
            ]
        )
        mock_load_enriched.return_value = enriched

        result = engine._aggregate_specialized_category(
            monthly_data, "razor_manufacturers", "brand"
        )
        ranks = {row["name"]: row["rank"] for row in result}
        assert ranks == {"BrandA": 1, "BrandB": 2}

        # Cross-check: the monthly aggregator on the same records agrees.
        from sotd.aggregate.aggregators.manufacturers.razor_manufacturer_aggregator import (
            RazorManufacturerAggregator,
        )

        monthly = RazorManufacturerAggregator().aggregate(enriched)
        monthly_ranks = {row["brand"]: row["rank"] for row in monthly}
        assert ranks == monthly_ranks

    @patch.object(AnnualAggregationEngine, "_load_enriched_records")
    def test_specialized_brush_category_tie_broken_by_unique_users(self, mock_load_enriched):
        """Equal shaves, different users -> distinct ranks in brush tables too."""
        engine = AnnualAggregationEngine("2024", Path("/data"))
        monthly_data = {
            "2024-01": {
                "data": {
                    "brush_fibers": [
                        {"fiber": "Badger", "shaves": 10, "unique_users": 5, "rank": 1},
                        {"fiber": "Synthetic", "shaves": 10, "unique_users": 2, "rank": 2},
                    ]
                }
            }
        }
        enriched = []
        for fiber, users, shaves in [("Badger", 5, 10), ("Synthetic", 2, 10)]:
            for user_idx in range(users):
                per_user = shaves // users + (1 if user_idx < shaves % users else 0)
                for _ in range(per_user):
                    enriched.append(
                        {
                            "author": f"user_{fiber}_{user_idx}",
                            "brush": {"matched": {"knot": {"fiber": fiber}}},
                        }
                    )
        mock_load_enriched.return_value = enriched

        result = engine._aggregate_specialized_brush_category(monthly_data, "brush_fibers")
        ranks = {row["name"]: row["rank"] for row in result}
        assert ranks == {"Badger": 1, "Synthetic": 2}

        # Cross-check: the monthly aggregator on the same records agrees.
        from sotd.aggregate.aggregators.brush_specialized.fiber_aggregator import (
            FiberAggregator,
        )

        monthly = FiberAggregator().aggregate(enriched)
        monthly_ranks = {row["fiber"]: row["rank"] for row in monthly}
        assert ranks == monthly_ranks

    @patch.object(AnnualAggregationEngine, "_load_enriched_records")
    def test_specialized_category_full_tie_shares_rank(self, mock_load_enriched):
        """Equal shaves AND equal users still share a rank (competition ranking)."""
        engine = AnnualAggregationEngine("2024", Path("/data"))
        monthly_data = {
            "2024-01": {
                "data": {
                    "razor_manufacturers": [
                        {"brand": "BrandA", "shaves": 10, "unique_users": 5, "rank": 1},
                        {"brand": "BrandB", "shaves": 10, "unique_users": 5, "rank": 1},
                        {"brand": "BrandC", "shaves": 8, "unique_users": 3, "rank": 3},
                    ]
                }
            }
        }
        mock_load_enriched.return_value = create_enriched_records_for_razors(
            [
                {"name": "BrandA Model", "shaves": 10, "unique_users": 5},
                {"name": "BrandB Model", "shaves": 10, "unique_users": 5},
                {"name": "BrandC Model", "shaves": 8, "unique_users": 3},
            ]
        )

        result = engine._aggregate_specialized_category(
            monthly_data, "razor_manufacturers", "brand"
        )
        ranks = {row["name"]: row["rank"] for row in result}
        assert ranks == {"BrandA": 1, "BrandB": 1, "BrandC": 3}
