"""Tests for catalog_loader.py."""

from unittest.mock import mock_open, patch

import pytest

from sotd.enrich.utils.catalog_loader import CatalogLoader
from sotd.utils.data_dir import get_data_dir


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
                # The default data path resolves via get_data_dir()
                # (SOTD_DATA_DIR env var > "data", repo-root anchored),
                # so assert the catalog filename, not a literal
                # CWD-relative path.
                assert "handles.yaml" in error_message
                assert "Brand: Test Brand" in error_message
                assert "Model: Test Model" in error_message
                assert "unterminated character set" in error_message  # The actual regex error

    def test_set_data_path_repoints_and_drops_cache(self, tmp_path):
        """set_data_path must re-point the loader and drop cached patterns
        so the next load reads from the new directory; a same-path call is
        a no-op that keeps the cache."""

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


class TestCatalogLoaderDefaults:
    """The default data_path must resolve like every other data-dir
    consumer (get_data_dir: SOTD_DATA_DIR env var > "data", repo-root
    anchored) so both enrichers registered by setup_enrichers() read one
    tree when no data_path is passed."""

    def test_default_honors_sotd_data_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SOTD_DATA_DIR", str(tmp_path))
        loader = CatalogLoader()
        assert loader.data_path == tmp_path

    def test_default_without_env_var_is_run_data_dir(self, monkeypatch):
        monkeypatch.delenv("SOTD_DATA_DIR", raising=False)
        loader = CatalogLoader()
        assert loader.data_path == get_data_dir()

    def test_explicit_path_wins_over_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SOTD_DATA_DIR", "/env/data")
        loader = CatalogLoader(tmp_path)
        assert loader.data_path == tmp_path
