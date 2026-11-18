"""
Tests for aggregate phase CLI functionality.

Tests the CLI interface for the aggregate phase, including argument parsing,
validation, and integration with the aggregation logic.
"""

import pytest
from pathlib import Path
from unittest.mock import patch

from sotd.aggregate.cli import get_parser, main
from sotd.aggregate.run import run
from sotd.utils.data_dir import get_data_dir


class TestAggregateCLI:
    """Test aggregate CLI functionality."""

    def test_get_parser_creates_parser(self):
        """Test that get_parser creates a valid parser."""
        parser = get_parser()
        assert parser is not None
        assert parser.description is not None

    # Phase-specific tests only - basic validation covered by BaseCLIParser tests
    def test_annual_argument_default_false(self):
        """Test that annual flag defaults to False."""
        parser = get_parser()
        args = parser.parse_args(["--month", "2023-01"])
        assert args.annual is False

    def test_annual_argument_enabled(self):
        """Test that annual flag can be enabled."""
        parser = get_parser()
        args = parser.parse_args(["--annual", "--year", "2023"])
        assert args.annual is True
        assert args.year == "2023"

    def test_annual_with_month_raises_error(self):
        """Test that annual flag with month raises error."""
        parser = get_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--annual", "--month", "2023-01"])

    def test_annual_with_range_raises_error(self):
        """Test that annual flag with range raises error."""
        parser = get_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--annual", "--range", "2023-01:2023-03"])

    def test_annual_with_start_end_raises_error(self):
        """Test that annual flag with start/end raises error."""
        parser = get_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--annual", "--start", "2023-01", "--end", "2023-03"])

    def test_annual_requires_year_argument(self):
        """Test that annual flag requires year argument."""
        parser = get_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--annual"])

    def test_annual_with_year_valid(self):
        """Test that annual flag with year is valid."""
        parser = get_parser()
        args = parser.parse_args(["--annual", "--year", "2023"])
        assert args.annual is True
        assert args.year == "2023"

    def test_annual_range_support_valid(self):
        """Test that annual flag supports year ranges."""
        parser = get_parser()
        args = parser.parse_args(["--annual", "--range", "2021:2024"])
        assert args.annual is True
        assert args.range == "2021:2024"

    def test_annual_range_validation_invalid_format(self):
        """Test that annual range validation works for invalid formats."""
        parser = get_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--annual", "--range", "2021-2024"])

    def test_annual_range_validation_invalid_year(self):
        """Test that annual range validation works for invalid years."""
        parser = get_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--annual", "--range", "2021-13:2024-01"])

    def test_help_text_includes_annual_option(self):
        """Test that help text includes annual option."""
        parser = get_parser()
        help_text = parser.format_help()
        assert "--annual" in help_text
        assert "annual" in help_text.lower()


class TestAggregateRun:
    """Test aggregate run function integration."""

    @patch("sotd.aggregate.run.process_months")
    def test_run_with_month(self, mock_process_months):
        """Test run function with month argument."""
        parser = get_parser()
        args = parser.parse_args(["--month", "2023-01"])

        run(args)

        mock_process_months.assert_called_once_with(
            months=["2023-01"],
            data_dir=get_data_dir(args.data_dir),
            debug=args.debug,
            force=args.force,
            annual_mode=None,
        )

    @patch("sotd.aggregate.run.process_months_parallel")
    def test_run_with_year(self, mock_process_months_parallel):
        """Test run function with year argument."""
        parser = get_parser()
        args = parser.parse_args(["--year", "2023"])

        run(args)

        # Should process all months in 2023 using parallel processing
        expected_months = [
            "2023-01",
            "2023-02",
            "2023-03",
            "2023-04",
            "2023-05",
            "2023-06",
            "2023-07",
            "2023-08",
            "2023-09",
            "2023-10",
            "2023-11",
            "2023-12",
        ]
        mock_process_months_parallel.assert_called_once_with(
            months=expected_months,
            data_dir=get_data_dir(args.data_dir),
            debug=args.debug,
            force=args.force,
            max_workers=8,
            annual_mode=True,
        )

    @patch("sotd.aggregate.run.process_months_parallel")
    def test_run_with_range(self, mock_process_months_parallel):
        """Test run function with range argument."""
        parser = get_parser()
        args = parser.parse_args(["--range", "2023-01:2023-03"])

        run(args)

        expected_months = ["2023-01", "2023-02", "2023-03"]
        mock_process_months_parallel.assert_called_once_with(
            months=expected_months,
            data_dir=get_data_dir(args.data_dir),
            debug=args.debug,
            force=args.force,
            max_workers=8,
            annual_mode=True,
        )

    @patch("sotd.aggregate.run.process_months_parallel")
    def test_run_with_start_end(self, mock_process_months_parallel):
        """Test run function with start/end arguments."""
        parser = get_parser()
        args = parser.parse_args(["--start", "2023-01", "--end", "2023-03"])

        run(args)

        expected_months = ["2023-01", "2023-02", "2023-03"]
        mock_process_months_parallel.assert_called_once_with(
            months=expected_months,
            data_dir=get_data_dir(args.data_dir),
            debug=args.debug,
            force=args.force,
            max_workers=8,
            annual_mode=None,
        )

    @patch("sotd.aggregate.run.process_months")
    def test_run_with_debug(self, mock_process_months):
        """Test run function with debug flag."""
        parser = get_parser()
        args = parser.parse_args(["--month", "2023-01", "--debug"])

        run(args)

        mock_process_months.assert_called_once_with(
            months=["2023-01"],
            data_dir=get_data_dir(args.data_dir),
            debug=True,
            force=args.force,
            annual_mode=None,
        )

    @patch("sotd.aggregate.run.process_months")
    def test_run_with_custom_data_dir(self, mock_process_months):
        """Test run function with custom data directory."""
        parser = get_parser()
        args = parser.parse_args(["--month", "2023-01", "--data-dir", "/custom/path"])

        run(args)

        mock_process_months.assert_called_once_with(
            months=["2023-01"],
            data_dir=Path("/custom/path"),
            debug=args.debug,
            force=args.force,
            annual_mode=None,
        )

    @patch("sotd.aggregate.run.process_annual")
    def test_run_with_annual_year(self, mock_process_annual):
        """Test run function with annual and year arguments."""
        parser = get_parser()
        args = parser.parse_args(["--annual", "--year", "2023"])

        run(args)

        mock_process_annual.assert_called_once_with(
            year="2023", data_dir=get_data_dir(args.data_dir), debug=args.debug, force=args.force
        )

    @patch("sotd.aggregate.run.process_annual_range_parallel")
    def test_run_with_annual_range(self, mock_process_annual_range_parallel):
        """Test run function with annual and range arguments."""
        parser = get_parser()
        args = parser.parse_args(["--annual", "--range", "2021:2024"])

        run(args)

        # With multiple years, parallel processing is used by default
        mock_process_annual_range_parallel.assert_called_once_with(
            years=["2021", "2022", "2023", "2024"],
            data_dir=get_data_dir(args.data_dir),
            debug=args.debug,
            force=args.force,
            max_workers=8,
        )

    @patch("sotd.aggregate.run.process_annual")
    def test_run_with_annual_debug(self, mock_process_annual):
        """Test run function with annual and debug flags."""
        parser = get_parser()
        args = parser.parse_args(["--annual", "--year", "2023", "--debug"])

        run(args)

        mock_process_annual.assert_called_once_with(
            year="2023", data_dir=get_data_dir(args.data_dir), debug=True, force=args.force
        )

    @patch("sotd.aggregate.run.process_annual")
    def test_run_with_annual_force(self, mock_process_annual):
        """Test run function with annual and force flags."""
        parser = get_parser()
        args = parser.parse_args(["--annual", "--year", "2023", "--force"])

        run(args)

        mock_process_annual.assert_called_once_with(
            year="2023", data_dir=get_data_dir(args.data_dir), debug=args.debug, force=True
        )


class TestAggregateMain:
    """Test aggregate main function integration."""

    @patch("sotd.aggregate.run.process_months")
    def test_main_with_month(self, mock_process_months):
        """Test main function with month argument."""
        with patch("sys.argv", ["aggregate", "--month", "2023-01"]):
            main()
        mock_process_months.assert_called_once()

    @patch("sotd.aggregate.run.process_months_parallel")
    def test_main_with_year(self, mock_process_months_parallel):
        """Test main function with year argument."""
        with patch("sys.argv", ["aggregate", "--year", "2023"]):
            main()
        mock_process_months_parallel.assert_called_once()

    @patch("sotd.aggregate.run.process_months_parallel")
    def test_main_with_range(self, mock_process_months_parallel):
        """Test main function with range argument."""
        with patch("sys.argv", ["aggregate", "--range", "2023-01:2023-03"]):
            main()
        mock_process_months_parallel.assert_called_once()

    @patch("sotd.aggregate.run.process_months_parallel")
    def test_main_with_start_end(self, mock_process_months_parallel):
        """Test main function with start/end arguments."""
        with patch("sys.argv", ["aggregate", "--start", "2023-01", "--end", "2023-03"]):
            main()
        mock_process_months_parallel.assert_called_once()

    @patch("sotd.aggregate.run.process_months")
    def test_main_with_debug_and_force(self, mock_process_months):
        """Test main function with debug and force flags."""
        with patch("sys.argv", ["aggregate", "--month", "2023-01", "--debug", "--force"]):
            main()
        mock_process_months.assert_called_once()

    @patch("sotd.aggregate.run.process_annual")
    def test_main_with_annual_year(self, mock_process_annual):
        """Test main function with annual and year arguments."""
        with patch("sys.argv", ["aggregate", "--annual", "--year", "2023"]):
            main()
        mock_process_annual.assert_called_once()

    @patch("sotd.aggregate.run.process_annual_range_parallel")
    def test_main_with_annual_range(self, mock_process_annual_range_parallel):
        """Test main function with annual and range arguments."""
        with patch("sys.argv", ["aggregate", "--annual", "--range", "2021:2024"]):
            main()
        mock_process_annual_range_parallel.assert_called_once()

    @patch("sotd.aggregate.run.process_annual")
    def test_main_with_annual_debug_force(self, mock_process_annual):
        """Test main function with annual, debug, and force flags."""
        with patch("sys.argv", ["aggregate", "--annual", "--year", "2023", "--debug", "--force"]):
            main()
        mock_process_annual.assert_called_once()
