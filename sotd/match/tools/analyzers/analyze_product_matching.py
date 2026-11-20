#!/usr/bin/env python3
"""Unified analysis tool to analyze product matching for any product type.

This tool provides analysis of how product strings are processed through the SOTD
pipeline's matching phase. For brushes, it delegates to the sophisticated
analyze_brush_matching.py tool. For other products, it provides focused matching
analysis.

Usage:
    python tools/analyze_product_matching.py --type brush "product string here"
    python tools/analyze_product_matching.py --type razor "product string here"
    python tools/analyze_product_matching.py --type blade "product string here"
    python tools/analyze_product_matching.py --type soap "product string here"
    python tools/analyze_product_matching.py --debug --type brush "product string here"
    python tools/analyze_product_matching.py --bypass-correct-matches
    --type blade "product string here"
"""

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

# Add the project root to the path
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from sotd.match.blade_matcher import BladeMatcher
    from sotd.match.razor_matcher import RazorMatcher
    from sotd.match.soap_matcher import SoapMatcher
    from sotd.match.types import MatchResult
    from sotd.utils.data_dir import get_data_dir, get_default_correct_matches_path
except ImportError as e:
    print(f"Error: Could not import required modules: {e}")
    print("Make sure you're running from the project root.")
    sys.exit(1)


class ProductAnalyzer:
    """Unified analyzer for all product types."""

    # Product type configuration for non-brush products. The catalog
    # entries are filenames, resolved against the run's data dir in
    # _create_matcher -- never a bare CWD-relative "data/..." path, so the
    # tool works from any working directory (see #23).
    PRODUCT_CONFIGS = {
        "razor": {
            "matcher_class": RazorMatcher,
            "catalog_path": "razors.yaml",
        },
        "blade": {
            "matcher_class": BladeMatcher,
            "catalog_path": "blades.yaml",
        },
        "soap": {
            "matcher_class": SoapMatcher,
            "catalog_path": "soaps.yaml",
        },
    }

    def __init__(self, product_type: str, debug: bool = False):
        if product_type == "brush":
            # Brush analysis is delegated to the specialized tool
            raise ValueError("Brush analysis should use analyze_brush_matching.py directly")

        if product_type not in self.PRODUCT_CONFIGS:
            raise ValueError(f"Unsupported product type: {product_type}")

        self.product_type = product_type
        self.debug = debug
        self.config = self.PRODUCT_CONFIGS[product_type]

        # Initialize matcher
        self.matcher = self._create_matcher()

    def _create_matcher(self):
        """Create the appropriate matcher instance."""
        matcher_class = self.config["matcher_class"]
        # Resolve both data files against the run's data dir
        # (SOTD_DATA_DIR > repo-root-anchored "data"), so the tool works
        # from any working directory. The correct-matches path is the
        # directory, not a file: BaseMatcher appends "<field>.yaml" to it,
        # so the old Path("data/correct_matches.yaml") pointed at
        # "data/correct_matches.yaml/razor.yaml" -- which never exists --
        # and the tool silently ran regex-only even from the repo root.
        catalog_path = get_data_dir() / self.config["catalog_path"]

        return matcher_class(
            catalog_path=catalog_path,
            correct_matches_path=get_default_correct_matches_path(),
        )

    def analyze(self, product_string: str, bypass_correct_matches: bool = False) -> None:
        """Analyze how a product string is matched."""
        print(f"🔍 Analyzing {self.product_type.upper()} string: '{product_string}'")
        print("=" * 80)

        if bypass_correct_matches:
            print("\n🚫 BYPASSING correct_matches.yaml - Testing raw matchers only")
            print("=" * 80)

        # Test matching
        self._analyze_matching(product_string, bypass_correct_matches)

        # Show catalog information
        self._show_catalog_info()

    def _analyze_matching(self, product_string: str, bypass_correct_matches: bool) -> None:
        """Analyze the matching process."""
        print(f"\n🎯 MATCHING ANALYSIS for {self.product_type.upper()}")
        print("-" * 60)

        try:
            # Test matching with bypass option
            result = self.matcher.match(
                product_string, bypass_correct_matches=bypass_correct_matches
            )

            if result:
                self._display_match_result(result)
            else:
                print("  ❌ No match found (result is None)")

        except Exception as e:
            print(f"  ❌ Error during matching: {e}")
            if self.debug:
                import traceback

                traceback.print_exc()

    def _display_match_result(self, result: MatchResult) -> None:
        """Display detailed match result information."""
        print("  📊 Match Result:")
        print(f"    Original: {result.original}")
        print(f"    Match Type: {result.match_type}")
        print(f"    Pattern: {result.pattern or 'N/A'}")

        if result.matched:
            print("    Matched Data:")
            self._display_matched_data(result.matched)
        else:
            print("    ❌ No match data")

    def _display_matched_data(self, matched_data: Dict[str, Any]) -> None:
        """Display matched data in a structured way."""
        # Common fields to display
        common_fields = ["brand", "model", "format"]

        for field in common_fields:
            if field in matched_data and matched_data[field]:
                print(f"      {field.title()}: {matched_data[field]}")

        # Product-specific fields
        if self.product_type == "razor":
            self._display_razor_data(matched_data)
        elif self.product_type == "blade":
            self._display_blade_data(matched_data)
        elif self.product_type == "soap":
            self._display_soap_data(matched_data)

        # Show any other relevant fields
        for key, value in matched_data.items():
            if key not in common_fields and value and value != "Unknown":
                # Skip internal fields
                if not key.startswith("_"):
                    print(f"      {key.replace('_', ' ').title()}: {value}")

    def _display_razor_data(self, matched_data: Dict[str, Any]) -> None:
        """Display razor-specific data."""
        if "grind" in matched_data and matched_data["grind"]:
            print(f"      Grind: {matched_data['grind']}")

        if "width" in matched_data and matched_data["width"]:
            print(f"      Width: {matched_data['width']}")

        if "point" in matched_data and matched_data["point"]:
            print(f"      Point: {matched_data['point']}")

    def _display_blade_data(self, matched_data: Dict[str, Any]) -> None:
        """Display blade-specific data."""
        if "coating" in matched_data and matched_data["coating"]:
            print(f"      Coating: {matched_data['coating']}")

        if "material" in matched_data and matched_data["material"]:
            print(f"      Material: {matched_data['material']}")

    def _display_soap_data(self, matched_data: Dict[str, Any]) -> None:
        """Display soap-specific data."""
        if "scent" in matched_data and matched_data["scent"]:
            print(f"      Scent: {matched_data['scent']}")

        if "base" in matched_data and matched_data["base"]:
            print(f"      Base: {matched_data['base']}")

    def _show_catalog_info(self) -> None:
        """Show catalog information for the product type."""
        print(f"\n📚 CATALOG INFORMATION for {self.product_type.upper()}")
        print("-" * 60)

        try:
            catalog = self.matcher.catalog
            if catalog:
                total_brands = len(catalog)
                total_models = sum(len(brand_data) for brand_data in catalog.values())

                print("  📊 Catalog Statistics:")
                print(f"    Total Brands: {total_brands}")
                print(f"    Total Models: {total_models}")

                if self.debug:
                    print("\n  🔍 Sample Catalog Entries:")
                    # Show first few brands and models
                    for i, (brand, brand_data) in enumerate(catalog.items()):
                        if i >= 3:  # Limit to first 3 brands
                            break
                        print(f"    {brand}: {len(brand_data)} models")

                        # Show first few models for this brand
                        for j, (model, model_data) in enumerate(brand_data.items()):
                            if j >= 2:  # Limit to first 2 models per brand
                                break
                            patterns = model_data.get("patterns", [])
                            print(f"      {model}: {len(patterns)} patterns")
            else:
                print("  ❌ No catalog data available")

        except Exception as e:
            print(f"  ❌ Error accessing catalog: {e}")

    def test_patterns(self, product_string: str) -> None:
        """Test individual patterns against the product string."""
        print(f"\n🧪 PATTERN TESTING for {self.product_type.upper()}")
        print("-" * 60)

        try:
            # This is a simplified pattern test - actual implementation would depend
            # on the specific matcher's pattern structure
            if hasattr(self.matcher, "patterns"):
                patterns = self.matcher.patterns
                print(f"  📝 Testing {len(patterns)} patterns against: '{product_string}'")

                matches = []
                for pattern_info in patterns:
                    if self.product_type in ["razor", "blade"]:
                        # Razor and blade patterns have (brand, model, format,
                        # pattern, compiled, entry) structure
                        if len(pattern_info) >= 5:
                            brand, model, fmt, raw_pattern, compiled = pattern_info[:5]
                            if compiled.search(product_string):
                                matches.append(
                                    {
                                        "brand": brand,
                                        "model": model,
                                        "format": fmt,
                                        "pattern": raw_pattern,
                                    }
                                )
                    elif self.product_type == "soap":
                        # Soap patterns have a different structure
                        continue

                if matches:
                    print(f"  ✅ Found {len(matches)} pattern matches:")
                    for match in matches:
                        print(f"    {match['brand']} {match['model']} ({match['format']})")
                        print(f"      Pattern: {match['pattern']}")
                else:
                    print("  ❌ No pattern matches found")
            else:
                print("  ⚠️  Pattern testing not available for this matcher type")

        except Exception as e:
            print(f"  ❌ Error during pattern testing: {e}")
            if self.debug:
                import traceback

                traceback.print_exc()


def main():
    parser = argparse.ArgumentParser(
        description="Analyze product matching through the SOTD pipeline"
    )
    parser.add_argument("product_string", nargs="?", default="", help="Product string to test")
    parser.add_argument(
        "--type",
        choices=["brush", "razor", "blade", "soap"],
        required=True,
        help="Product type to analyze",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    parser.add_argument(
        "--bypass-correct-matches",
        action="store_true",
        help="Bypass correct_matches.yaml lookup to test raw matchers only",
    )
    parser.add_argument(
        "--test-patterns",
        action="store_true",
        help="Test individual patterns against the product string",
    )

    args = parser.parse_args()

    # Handle brush analysis by delegating to the specialized tool
    if args.type == "brush":
        print("🪮 Brush analysis detected - delegating to analyze_brush_matching.py")
        print("=" * 80)

        # Build command for the brush analysis tool
        brush_tool_path = Path(__file__).parent / "analyze_brush_matching.py"
        cmd = [sys.executable, str(brush_tool_path)]

        # Add flags
        if args.debug:
            cmd.append("--debug")
        if args.bypass_correct_matches:
            cmd.append("--bypass-correct-matches")
        if args.test_patterns:
            cmd.append("--test-patterns")

        # Add the product string
        if args.product_string:
            cmd.append(args.product_string)

        # Execute the brush analysis tool
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            print(f"❌ Error running brush analysis tool: {e}")
            sys.exit(1)
        return

    # Set default product string based on type if none provided
    if not args.product_string:
        defaults = {
            "razor": "Koraat Moarteen",
            "blade": "Feather Hi-Stainless",
            "soap": "Declaration Grooming Original",
        }
        args.product_string = defaults.get(args.type, "test string")

    try:
        analyzer = ProductAnalyzer(args.type, args.debug)
        analyzer.analyze(args.product_string, args.bypass_correct_matches)

        if args.test_patterns:
            analyzer.test_patterns(args.product_string)

    except Exception as e:
        print(f"❌ Error creating analyzer: {e}")
        if args.debug:
            import traceback

            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
