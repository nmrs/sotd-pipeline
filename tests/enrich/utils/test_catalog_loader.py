"""Tests for catalog_loader.py."""

import pytest
from unittest.mock import patch, mock_open

from sotd.enrich.utils.catalog_loader import CatalogLoader


class TestCatalogLoader:
    """Test the CatalogLoader class."""

    def test_enhanced_regex_error_reporting(self):
        """Test that malformed regex patterns produce detailed error messages."""
        # Create a mock catalog with malformed regex
        mock_catalog_content = """
artisan_handles:
  Test Brand:
    Test Model:
      patterns:
        - "invalid[regex"  # Malformed regex - missing closing bracket
"""

        with patch("builtins.open", mock_open(read_data=mock_catalog_content)):
            with patch(
                "yaml.safe_load",
                return_value={
                    "artisan_handles": {
                        "Test Brand": {"Test Model": {"patterns": ["invalid[regex"]}}
                    }
                },
            ):
                loader = CatalogLoader()

                # This should raise an error when compiling patterns
                with pytest.raises(ValueError) as exc_info:
                    loader.load_compiled_handle_patterns("Test Brand", "Test Model")

                error_message = str(exc_info.value)
                assert "Invalid regex pattern" in error_message
                assert "invalid[regex" in error_message
                assert "File: data/handles.yaml" in error_message
                assert "Brand: Test Brand" in error_message
                assert "Model: Test Model" in error_message
                assert "unterminated character set" in error_message  # The actual regex error

    def test_set_data_path_repoints_and_drops_cache(self, tmp_path):
        """set_data_path must re-point the loader and drop cached patterns
        so the next load reads from the new directory; a same-path call is
        a no-op that keeps the cache."""
        from pathlib import Path

        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        (dir_a / "handles.yaml").write_text(
            "artisan_handles:\n  BrandA:\n    ModelA:\n      patterns:\n        - 'a.*handle'\n"
        )
        (dir_b / "handles.yaml").write_text(
            "artisan_handles:\n  BrandB:\n    ModelB:\n      patterns:\n        - 'b.*handle'\n"
        )

        loader = CatalogLoader(dir_a)
        assert loader.load_handle_patterns("BrandA", "ModelA") == ["a.*handle"]

        loader.set_data_path(dir_b)
        assert loader.data_path == dir_b
        # Cache dropped: BrandA no longer resolves, BrandB does.
        assert loader.load_handle_patterns("BrandA", "ModelA") == []
        assert loader.load_handle_patterns("BrandB", "ModelB") == ["b.*handle"]

        # Same-path call keeps the cache (no reload, no error).
        loader.set_data_path(dir_b)
        assert loader.load_handle_patterns("BrandB", "ModelB") == ["b.*handle"]
