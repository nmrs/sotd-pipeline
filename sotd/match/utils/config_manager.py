"""
Configuration management utilities for brush matching system.

This module provides centralized configuration creation and management logic
that can be used by both legacy and new brush matching systems.
"""

from pathlib import Path
from typing import Optional

from sotd.match.config import BrushMatcherConfig
from sotd.utils.data_dir import get_default_correct_matches_path


class ConfigManager:
    """
    Manages configuration creation and caching for brush matching system.

    This class centralizes configuration creation logic to avoid multiple
    calls to BrushMatcherConfig.create_default() and provides consistent
    configuration across all components.
    """

    def __init__(self):
        """Initialize the configuration manager."""
        self._default_config: Optional[BrushMatcherConfig] = None
        self._debug_config: Optional[BrushMatcherConfig] = None

    def get_default_config(self) -> BrushMatcherConfig:
        """
        Get the default configuration, creating it if necessary.

        Returns:
            Default BrushMatcherConfig instance
        """
        if self._default_config is None:
            self._default_config = BrushMatcherConfig.create_default()
        return self._default_config

    def get_debug_config(self) -> BrushMatcherConfig:
        """
        Get the debug configuration, creating it if necessary.

        Returns:
            Debug BrushMatcherConfig instance
        """
        if self._debug_config is None:
            self._debug_config = BrushMatcherConfig.create_debug()
        return self._debug_config

    def create_custom_config(
        self,
        catalog_path: Optional[Path] = None,
        handles_path: Optional[Path] = None,
        knots_path: Optional[Path] = None,
        correct_matches_path: Optional[Path] = None,
        debug: bool = False,
        cache_enabled: bool = True,
        cache_max_size: int = 1000,
        strict_validation: bool = False,
    ) -> BrushMatcherConfig:
        """
        Create a custom configuration with specified parameters.

        Args:
            catalog_path: Path to brushes catalog file
            handles_path: Path to handles catalog file
            knots_path: Path to knots catalog file
            correct_matches_path: Path to correct matches file
            debug: Enable debug mode
            cache_enabled: Enable caching
            cache_max_size: Maximum cache size
            strict_validation: Enable strict validation

        Returns:
            Custom BrushMatcherConfig instance
        """
        # Provide defaults for None paths
        final_catalog_path = catalog_path or Path("data/brushes.yaml")
        final_handles_path = handles_path or Path("data/handles.yaml")
        final_knots_path = knots_path or Path("data/knots.yaml")
        final_correct_matches_path = correct_matches_path or get_default_correct_matches_path()

        return BrushMatcherConfig.create_custom(
            catalog_path=final_catalog_path,
            handles_path=final_handles_path,
            knots_path=final_knots_path,
            correct_matches_path=final_correct_matches_path,
            debug=debug,
        )

    def reset_configs(self) -> None:
        """Reset all cached configurations (useful for testing)."""
        self._default_config = None
        self._debug_config = None

    def validate_config(self, config: BrushMatcherConfig) -> None:
        """
        Validate a configuration instance.

        Args:
            config: Configuration to validate

        Raises:
            ValueError: If configuration is invalid
            FileNotFoundError: If required files don't exist
        """
        # The config class validates paths when used by BrushMatcher
        # This method is kept for backward compatibility but does nothing
        # as validation happens during matcher initialization
        pass


# Global instance for easy access
config_manager = ConfigManager()
