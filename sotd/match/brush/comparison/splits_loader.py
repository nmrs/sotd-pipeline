"""
Brush splits loader for human-curated split data.

This module loads and manages brush_splits.yaml data, providing
human-curated splits that take precedence over automated splitting.
"""

import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from sotd.utils.yaml_loader import UniqueKeyLoader, load_yaml_with_nfc


class BrushSplit:
    """Represents a human-curated brush split."""

    def __init__(
        self,
        original: str,
        handle: str,
        knot: str,
        match_type: str,
        validated: bool = False,
        corrected: bool = False,
        should_not_split: bool = False,
    ):
        self.original = original
        self.handle = handle
        self.knot = knot
        self.match_type = match_type
        self.validated = validated
        self.corrected = corrected
        self.should_not_split = should_not_split

    @classmethod
    def from_dict(cls, data: Dict) -> "BrushSplit":
        """Create BrushSplit from dictionary."""
        return cls(
            original=data["original"],
            handle=data.get("handle", ""),
            knot=data.get("knot", ""),
            match_type=data.get("match_type", "unknown"),
            validated=data.get("validated", False),
            corrected=data.get("corrected", False),
            should_not_split=data.get("should_not_split", False),
        )


class BrushSplitsLoader:
    """Loads and manages human-curated brush splits from brush_splits.yaml."""

    def __init__(self, brush_splits_path: Optional[Path] = None, data: Optional[Dict] = None):
        self.brush_splits_path = brush_splits_path or Path("data/brush_splits.yaml")
        self._splits: Dict[str, BrushSplit] = {}
        self._loaded = False
        if data is not None:
            # Preloaded YAML data — BrushMatcher passes its already-parsed
            # catalogs["brush_splits"] so brush_splits.yaml is read once per
            # matcher instead of twice (once into the catalogs dict, once
            # here), and both consumers see the same UniqueKeyLoader-validated
            # parse.
            self._build_splits(data)
            self._loaded = True

    def _build_splits(self, data: Any) -> None:
        """Populate _splits from parsed brush_splits.yaml data."""
        self._splits.clear()

        # Handle current structure: brush names as top-level keys
        if isinstance(data, dict):
            for brush_name, split_data in data.items():
                try:
                    # Add the original brush name to the split data
                    split_data_with_original = split_data.copy()
                    split_data_with_original["original"] = brush_name

                    split = BrushSplit.from_dict(split_data_with_original)
                    self._splits[split.original] = split
                except (KeyError, ValueError, AttributeError) as e:
                    print(f"Warning: Skipping invalid split data for {brush_name}: {e}")
                    continue

        # Handle legacy structure: splits is a dict with brush names as keys
        elif isinstance(data, dict) and "splits" in data:
            splits_data = data.get("splits", {})

            if isinstance(splits_data, dict):
                for brush_name, entries in splits_data.items():
                    if isinstance(entries, list):
                        for split_data in entries:
                            try:
                                split = BrushSplit.from_dict(split_data)
                                self._splits[split.original] = split
                            except (KeyError, ValueError) as e:
                                print(
                                    f"Warning: Skipping invalid split data "
                                    f"for {brush_name}: {e}"
                                )
                                continue
                    else:
                        print(f"Warning: Invalid entries format for {brush_name}")

            # Handle old structure: splits is a list (backward compatibility)
            elif isinstance(splits_data, list):
                for split_data in splits_data:
                    try:
                        split = BrushSplit.from_dict(split_data)
                        self._splits[split.original] = split
                    except (KeyError, ValueError) as e:
                        print(f"Warning: Skipping invalid split data: {e}")
                        continue

    def load_splits(self) -> None:
        """Load brush splits from YAML file."""
        if not self.brush_splits_path.exists():
            self._loaded = True
            return

        try:
            data = load_yaml_with_nfc(self.brush_splits_path, loader_cls=UniqueKeyLoader)
        except Exception as e:
            print(f"Warning: Could not load brush splits from {self.brush_splits_path}: {e}")
            self._loaded = True
            return

        self._build_splits(data)
        self._loaded = True

    def find_split(self, brush_string: str) -> Optional[BrushSplit]:
        """
        Find a brush split for the given brush string.

        Args:
            brush_string: The brush string to look up

        Returns:
            BrushSplit if found, None otherwise
        """
        if not self._loaded:
            self.load_splits()

        # Direct match
        if brush_string in self._splits:
            return self._splits[brush_string]

        # Case-insensitive match
        brush_lower = brush_string.lower()
        for original, split in self._splits.items():
            if original.lower() == brush_lower:
                return split

        # Normalized match (remove extra whitespace)
        normalized = re.sub(r"\s+", " ", brush_string.strip())
        if normalized in self._splits:
            return self._splits[normalized]

        return None

    def get_handle_and_knot(self, brush_string: str) -> Optional[Tuple[str, str]]:
        """
        Get handle and knot components for a brush string.

        Args:
            brush_string: The brush string to split

        Returns:
            Tuple of (handle, knot) if found in curated splits, None otherwise
        """
        split = self.find_split(brush_string)
        if split and not split.should_not_split:
            return split.handle, split.knot
        return None

    def should_not_split(self, brush_string: str) -> bool:
        """
        Check if a brush string should not be split.

        Args:
            brush_string: The brush string to check

        Returns:
            True if the brush should not be split, False otherwise
        """
        split = self.find_split(brush_string)
        return split.should_not_split if split else False

    def get_splits_count(self) -> int:
        """Get the number of loaded splits."""
        if not self._loaded:
            self.load_splits()
        return len(self._splits)
