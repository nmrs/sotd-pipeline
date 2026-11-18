"""
Enhanced Brush Scoring Matcher.

This module provides an enhanced brush matching system using scoring components.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from sotd.match.types import MatchResult
from sotd.utils.data_dir import get_default_correct_matches_path
from sotd.utils.yaml_loader import UniqueKeyLoader, load_yaml_with_nfc

from .config import BrushScoringConfig
from .handle_matcher import HandleMatcher
from .knot_matcher import KnotMatcher
from .knot_matcher_factory import KnotMatcherFactory
from .scoring.dependencies.strategy_dependency_manager import (
    DependencyType,
    StrategyDependency,
    StrategyDependencyManager,
)
from .scoring.engine import ScoringEngine
from .scoring.matcher import CorrectMatchesMatcher
from .scoring.orchestrator import StrategyOrchestrator
from .scoring.performance.performance_monitor import PerformanceMonitor
from .scoring.performance.strategy_performance_optimizer import (
    StrategyPerformanceOptimizer,
)
from .scoring.resolver import ResultConflictResolver
from .strategies.correct_matches_strategy import (
    CorrectMatchesStrategy,
)
from .strategies.known.known_brush_strategy import (
    KnownBrushMatchingStrategy,
)
from .strategies.known.known_knot_based_brush_strategy import (
    KnownKnotBasedBrushMatchingStrategy,
)
from .strategies.known.known_split_wrapper_strategy import (
    KnownSplitWrapperStrategy,
)
from .strategies.other_brushes_strategy import (
    OtherBrushMatchingStrategy,
)
from .strategies.specialized.omega_semogue_strategy import (
    OmegaSemogueBrushMatchingStrategy,
)
from .strategies.specialized.zenith_strategy import (
    ZenithBrushMatchingStrategy,
)
from .strategies.utils.subdict_builders import build_handle_subdict, build_knot_subdict

# Module-level cache for catalogs to avoid redundant loading.
# KEYED BY RESOLVED CATALOG PATHS: a BrushMatcher built for tests/test_data
# must never serve catalogs to one built for data/ (or any other data dir).
# An unkeyed cache here made matches depend on which paths were used first in
# the process — a nondeterministic failure under pytest-xdist depending on
# worker assignment (seen in CI as test_brush_matcher_bypass failing only on
# some runs). Key shape: (brushes_path, handles_path, knots_path,
# correct_matches_path) as resolved strings.
_catalog_cache: Dict[tuple, Dict[str, Any]] = {}


def clear_brush_catalog_cache() -> None:
    """Clear the module-level catalog cache for brush matcher."""
    global _catalog_cache
    _catalog_cache = {}

    # Also clear related caches
    from .scoring.engine import ScoringEngine
    from .splitter import BrushSplitter

    BrushSplitter.clear_brands_cache()
    ScoringEngine.clear_knots_cache()


def load_correct_matches(correct_matches_path: Path | None = None) -> dict:
    """Load correct matches data from YAML file or directory structure using CatalogLoader."""
    from sotd.match.loaders import CatalogLoader

    loader = CatalogLoader()
    return loader.load_correct_matches(correct_matches_path)


class BrushMatcher:
    """Main brush matcher that orchestrates all matching strategies."""

    def __init__(
        self,
        correct_matches_path: Optional[Path] = None,
        brushes_path: Optional[Path] = None,
        handles_path: Optional[Path] = None,
        knots_path: Optional[Path] = None,
        brush_scoring_config_path: Optional[Path] = None,
        debug: bool = False,
    ):
        """Initialize the brush matcher with catalog paths."""
        # Store debug flag
        self.debug = debug

        # Store catalog paths FIRST (before validation)
        self.brushes_path = brushes_path
        self.handles_path = handles_path
        self.knots_path = knots_path
        self.correct_matches_path = correct_matches_path

        # Set default paths if not provided (AFTER storing)
        if self.brushes_path is None:
            self.brushes_path = Path("data/brushes.yaml")
        if self.handles_path is None:
            self.handles_path = Path("data/handles.yaml")
        if self.knots_path is None:
            self.knots_path = Path("data/knots.yaml")
        if self.correct_matches_path is None:
            self.correct_matches_path = get_default_correct_matches_path()

        # FAIL FAST: Validate that all catalog files exist and are readable
        # Only validate in debug mode to avoid expensive validation overhead in parallel workers
        # In production, loading will fail fast if catalogs are missing/corrupted
        if self.debug and all(
            [self.brushes_path, self.handles_path, self.knots_path, self.correct_matches_path]
        ):
            self._validate_catalog_paths()

        # Initialize configuration with provided path or default
        if brush_scoring_config_path is None:
            brush_scoring_config_path = Path("data/brush_scoring_config.yaml")

        # FAIL FAST: Validate scoring configuration exists and is readable
        if not brush_scoring_config_path.exists():
            raise FileNotFoundError(
                f"Brush scoring configuration file not found: "
                f"{brush_scoring_config_path.absolute()}"
            )

        self.config = BrushScoringConfig(config_path=brush_scoring_config_path)

        # FAIL FAST: Validate that scoring configuration has required structure
        self._validate_scoring_config()

        # Load correct matches data
        correct_matches_data = load_correct_matches(self.correct_matches_path)
        self.correct_matches_data = correct_matches_data

        # Initialize HandleMatcher and KnotMatcher first (needed for strategies)
        # Use provided paths instead of hardcoded ones
        self.handle_matcher = HandleMatcher(self.handles_path)

        # Initialize KnotMatcher with knot-specific strategies
        # Load catalogs once and cache at instance level to avoid repeated calls
        # Cache catalogs at instance level to avoid repeated _load_catalogs_directly() calls
        self._catalogs = self._load_catalogs_directly()

        # Create knot strategies using factory for better separation of concerns
        knot_strategies = KnotMatcherFactory.create_knot_strategies(self._catalogs)
        self.knot_matcher = KnotMatcher(knot_strategies)

        # Initialize components
        self.correct_matches_matcher = CorrectMatchesMatcher(correct_matches_data)
        self.strategy_orchestrator = StrategyOrchestrator(self._create_strategies())
        self.scoring_engine = ScoringEngine(self.config, debug=self.debug)

        self.performance_monitor = PerformanceMonitor()
        self.conflict_resolver = ResultConflictResolver()
        self.performance_optimizer = StrategyPerformanceOptimizer()
        self.strategy_dependency_manager = StrategyDependencyManager()

        # Configure handle/knot dependencies for automated split strategies

        # HandleMatcher and KnotMatcher depend on BrushSplitter success
        self.strategy_dependency_manager.add_dependency(
            StrategyDependency("HandleMatcher", "BrushSplitter", DependencyType.REQUIRES_SUCCESS)
        )
        self.strategy_dependency_manager.add_dependency(
            StrategyDependency("KnotMatcher", "BrushSplitter", DependencyType.REQUIRES_SUCCESS)
        )

        # Dual Component depends on both HandleMatcher and KnotMatcher success
        self.strategy_dependency_manager.add_dependency(
            StrategyDependency(
                "FullInputComponentMatchingStrategy",
                "HandleMatcher",
                DependencyType.REQUIRES_SUCCESS,
            )
        )
        self.strategy_dependency_manager.add_dependency(
            StrategyDependency(
                "FullInputComponentMatchingStrategy", "KnotMatcher", DependencyType.REQUIRES_SUCCESS
            )
        )

        # Single Component depends on any of HandleMatcher or KnotMatcher
        self.strategy_dependency_manager.add_dependency(
            StrategyDependency(
                "FullInputComponentMatchingStrategy",
                "HandleMatcher",
                DependencyType.REQUIRES_ANY,
            )
        )
        self.strategy_dependency_manager.add_dependency(
            StrategyDependency(
                "FullInputComponentMatchingStrategy",
                "KnotMatcher",
                DependencyType.REQUIRES_ANY,
            )
        )

        # HandleMatcher and KnotMatcher are now initialized above

    def _validate_scoring_config(self):
        """Validate that scoring configuration has required structure. Fail fast if not."""
        if not hasattr(self.config, "weights"):
            raise ValueError("Scoring configuration missing 'weights' attribute")

        if not isinstance(self.config.weights, dict):
            raise ValueError("Scoring configuration 'weights' must be a dictionary")

        if "base_strategies" not in self.config.weights:
            raise ValueError("Scoring configuration missing 'base_strategies' section")

        if "strategy_modifiers" not in self.config.weights:
            raise ValueError("Scoring configuration missing 'strategy_modifiers' section")

        # Validate that all required strategies have base scores
        required_strategies = [
            "known_brush",
            "known_knot_based_brush",
            "other_brush",
            "omega_semogue_brush",
            "zenith_brush",
            "automated_split",
            "full_input_component_matching",
            "known_split",
        ]

        base_strategies = self.config.weights["base_strategies"]
        missing_strategies = [s for s in required_strategies if s not in base_strategies]

        if missing_strategies:
            raise ValueError(
                f"Scoring configuration missing base scores for strategies: {missing_strategies}"
            )

        # Validate that all base strategy scores are positive numbers
        for strategy_name, score in base_strategies.items():
            if not isinstance(score, (int, float)) or score <= 0:
                raise ValueError(
                    f"Invalid base score for strategy '{strategy_name}': {score} "
                    f"(must be positive number)"
                )

        if self.debug:
            print("✅ Scoring configuration validated successfully:")
            for strategy_name, score in base_strategies.items():
                print(f"   {strategy_name}: {score}")

    def _validate_catalog_paths(self):
        """Validate that all catalog paths exist and are readable. Fail fast if not."""
        # Type guards: ensure paths are not None (they should be set by __init__)
        if (
            self.brushes_path is None
            or self.handles_path is None
            or self.knots_path is None
            or self.correct_matches_path is None
        ):
            raise ValueError("Catalog paths must be set before validation")

        catalog_paths = [
            ("brushes", self.brushes_path),
            ("handles", self.handles_path),
            ("knots", self.knots_path),
        ]

        # Validate single file catalogs
        for name, path in catalog_paths:
            if path is None:  # Type guard
                continue
            if not path.exists():
                raise FileNotFoundError(f"Catalog file '{name}' not found at: {path.absolute()}")

            if not path.is_file():
                raise ValueError(f"Catalog path '{name}' is not a file: {path.absolute()}")

            # Test if we can actually read and parse the YAML file
            try:
                with open(path, "r", encoding="utf-8") as f:
                    # Test YAML parsing to catch syntax errors early
                    yaml.safe_load(f)
            except (PermissionError, UnicodeDecodeError) as e:
                raise ValueError(f"Catalog file '{name}' is not readable: {path.absolute()} - {e}")
            except yaml.YAMLError as e:
                raise ValueError(
                    f"YAML syntax error in catalog file '{name}': {path.absolute()} - {e}"
                )

        # Validate correct_matches (can be directory or file)
        if self.correct_matches_path is None:  # Type guard
            raise ValueError("Correct matches path must be set")
        if not self.correct_matches_path.exists():
            raise FileNotFoundError(
                f"Correct matches path not found at: {self.correct_matches_path.absolute()}"
            )

        if self.correct_matches_path.is_file():
            # Legacy single file mode
            try:
                with open(self.correct_matches_path, "r", encoding="utf-8") as f:
                    f.read(1)
            except (PermissionError, UnicodeDecodeError) as e:
                raise ValueError(
                    f"Correct matches file is not readable: "
                    f"{self.correct_matches_path.absolute()} - {e}"
                )
        elif self.correct_matches_path.is_dir():
            # New directory structure mode - validate required files exist
            required_files = ["brush.yaml", "handle.yaml", "knot.yaml"]
            for filename in required_files:
                file_path = self.correct_matches_path / filename
                if not file_path.exists():
                    raise FileNotFoundError(
                        f"Required correct matches file '{filename}' not found "
                        f"at: {file_path.absolute()}"
                    )
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        f.read(1)
                except (PermissionError, UnicodeDecodeError) as e:
                    raise ValueError(
                        f"Correct matches file '{filename}' is not readable: "
                        f"{file_path.absolute()} - {e}"
                    )
        else:
            raise ValueError(
                f"Correct matches path is neither file nor directory: "
                f"{self.correct_matches_path.absolute()}"
            )

        if self.debug:
            print("✅ All catalog paths validated successfully:")
            for name, path in catalog_paths:
                print(f"   {name}: {path.absolute()}")
            print(f"   correct_matches: {self.correct_matches_path.absolute()}")

    @property
    def _brush_splits_path(self) -> Path:
        """Single source for the run's brush_splits.yaml location.

        brush_splits.yaml lives beside brushes.yaml in the run's data dir.
        The catalogs load, both split strategies, and the precompute all
        derive it from here so the path can never drift between sites.
        """
        return self.brushes_path.parent / "brush_splits.yaml"

    def _load_catalogs_directly(self) -> dict:
        """Load catalogs directly without legacy config dependencies.

        Uses instance-level cache if available, otherwise falls back to module-level cache.
        """
        # Return instance-level cached catalogs if available (fastest path)
        # This should be the common case after initialization
        if hasattr(self, "_catalogs") and self._catalogs is not None:
            return self._catalogs

        global _catalog_cache

        # Return module-level cached catalogs if available for THESE paths
        cache_key = (
            str(self.brushes_path.resolve()),
            str(self.handles_path.resolve()),
            str(self.knots_path.resolve()),
            str(self.correct_matches_path.resolve()) if self.correct_matches_path else None,
        )
        if cache_key in _catalog_cache:
            return _catalog_cache[cache_key]

        # Load catalogs and cache them using the stored paths
        # Type guards: paths should be set by __init__, but check for safety
        if self.brushes_path is None or self.handles_path is None or self.knots_path is None:
            raise ValueError("Catalog paths must be set before loading")
        catalogs = {}
        catalogs["brushes"] = self._load_yaml_file(self.brushes_path)
        catalogs["handles"] = self._load_yaml_file(self.handles_path)
        catalogs["knots"] = self._load_yaml_file(self.knots_path)
        catalogs["correct_matches"] = self._load_correct_matches_catalog()
        # brush_splits.yaml lives beside brushes.yaml in the run's data dir.
        # Parsed with UniqueKeyLoader (not _load_yaml_file) so duplicate keys
        # fail the load loudly — the same validation BrushSplitsLoader applies
        # — and this one parse feeds both consumers: KnownSplitWrapperStrategy
        # gets the dict, the split strategies get it via BrushSplitsLoader(data=...).
        if self._brush_splits_path.exists():
            try:
                catalogs["brush_splits"] = load_yaml_with_nfc(
                    self._brush_splits_path, loader_cls=UniqueKeyLoader
                )
            except yaml.YAMLError as e:
                # FAIL FAST: YAML syntax errors should cause immediate failure
                raise ValueError(f"YAML syntax error in {self._brush_splits_path.absolute()}: {e}")
        else:
            catalogs["brush_splits"] = {}

        # Validate patterns format for all catalog files
        from sotd.utils.catalog_validator import validate_patterns_format

        validate_patterns_format(catalogs["brushes"], self.brushes_path)
        validate_patterns_format(catalogs["handles"], self.handles_path)
        validate_patterns_format(catalogs["knots"], self.knots_path)

        # Cache the catalogs for future use
        _catalog_cache[cache_key] = catalogs
        return catalogs

    def _load_yaml_file(self, path: Path) -> dict:
        """Load a YAML file with error handling."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            return {}
        except yaml.YAMLError as e:
            # FAIL FAST: YAML syntax errors should cause immediate failure
            raise ValueError(f"YAML syntax error in {path.absolute()}: {e}")

    def _load_correct_matches_catalog(self) -> dict:
        """Load correct matches catalog from directory structure or legacy
        file using CatalogLoader."""
        from sotd.match.loaders import CatalogLoader

        loader = CatalogLoader()
        return loader.load_correct_matches(self.correct_matches_path)

    def _create_strategies(self) -> List:
        """
        Create list of strategies for Phase 3.2 with individual brush strategies.

        Returns:
            List of strategy objects
        """
        # Use instance-level cached catalogs to avoid repeated loading
        catalogs = self._catalogs

        # Create brush-level strategies (not knot strategies)
        strategies = []

        # Note: Correct matches strategy is handled separately, not in the strategy orchestrator
        # It runs first with highest priority when not bypassed

        # Add the known split wrapper strategy for brush splits
        strategies.append(
            KnownSplitWrapperStrategy(
                catalogs.get("brush_splits", {}), self.handle_matcher, self.knot_matcher
            )
        )

        # Add the known brush matching strategy for complete brushes
        strategies.append(
            KnownBrushMatchingStrategy(
                catalogs["brushes"].get("known_brushes", {}), self.handle_matcher
            )
        )

        # Add the known knot-based brush matching strategy for knot-based brushes
        strategies.append(
            KnownKnotBasedBrushMatchingStrategy(
                catalogs["brushes"].get("known_knot_based_brushes", {}), self.handle_matcher
            )
        )

        # Add the automated split strategy for high/medium priority splitting
        # This should run BEFORE OtherBrushMatchingStrategy to allow splitting
        # of strings like "Elite Razor Trustone W/Long Shaving 26mm Reserve VI Badger"
        # Both brush-split strategies share one BrushSplitsLoader, seeded
        # with the already-parsed catalogs["brush_splits"] (loaded above
        # from the run's data-dir path beside brushes.yaml with duplicate-key
        # validation) so brush_splits.yaml is parsed once per matcher, not
        # once per strategy -- and, before this change, once per match()
        # call in _precompute_handle_knot_results. Passing the seeded
        # loader, never a bare path, keeps the strategies off the
        # CWD-relative data/brush_splits.yaml default, which silently drops
        # every curated should_not_split entry from any working directory
        # but the repo root.
        from .comparison.splits_loader import BrushSplitsLoader
        from .strategies.automated.automated_split_strategy import (
            AutomatedSplitStrategy,
        )

        splits_loader = BrushSplitsLoader(
            self._brush_splits_path, data=catalogs.get("brush_splits", {})
        )

        strategies.append(
            AutomatedSplitStrategy(
                catalogs,
                self.config,
                self.handle_matcher,
                self.knot_matcher,
                splits_loader=splits_loader,
            )
        )

        # Add strategies that expect the correct catalog structure
        strategies.append(OtherBrushMatchingStrategy(catalogs["brushes"].get("other_brushes", {})))

        # Add specialized strategies
        strategies.append(ZenithBrushMatchingStrategy())
        strategies.append(OmegaSemogueBrushMatchingStrategy())

        # Skip other strategies for now - they may expect different catalog structure
        # strategies.append(
        #     ZenithBrushMatchingStrategy(
        #         catalogs["brushes"].get("zenith_brushes", {})
        #     )
        # )
        # strategies.append(
        #     OmegaSemogueBrushMatchingStrategy(
        #         catalogs["brushes"].get("omega_semogue_brushes", {})
        #     )
        # )
        # strategies.append(
        #     FiberFallbackStrategy(
        #         catalogs["brushes"].get("fiber_fallback_brushes", {})
        #     )
        # )

        # Add the unified component matching strategy
        from .strategies.full_input_component_matching_strategy import (
            FullInputComponentMatchingStrategy,
        )

        strategies.append(
            FullInputComponentMatchingStrategy(
                self.handle_matcher,
                self.knot_matcher,
                catalogs,
                splits_loader=splits_loader,
            )
        )

        # Skip problematic component strategies for now - they expect
        # component-level data, not brush-level data
        # These strategies are now deprecated and replaced by component
        # strategies within unified strategies

        return strategies

    def _create_temp_strategies(self) -> List:
        """
        Create temporary strategy list for knot matcher initialization.

        This creates strategies without the unified component strategy to avoid circular dependency.

        Returns:
            List of strategy objects (without unified component strategy)
        """
        # Use instance-level cached catalogs to avoid repeated loading
        catalogs = self._catalogs

        # Create strategies using factory for better separation of concerns
        strategies = KnotMatcherFactory.create_knot_strategies(catalogs)

        return strategies

    def _convert_handle_result_to_brush_result(self, handle_result: MatchResult) -> MatchResult:
        """
        Convert HandleMatcher result to brush format for processing.

        Args:
            handle_result: MatchResult from HandleMatcher

        Returns:
            MatchResult in brush format
        """
        # Extract handle data from HandleMatcher result
        handle_data = handle_result.matched or {}

        # Create brush format result with nested handle/knot structure
        src = handle_data.get("_source_text", handle_result.original)
        pat = handle_data.get("_pattern_used")
        brush_data = {
            "brand": handle_data.get("handle_maker"),
            "model": handle_data.get("handle_model"),
            "source_text": src,
            "_matched_by": "HandleMatcher",
            "_pattern": pat,
            "handle": build_handle_subdict(
                handle_data.get("handle_maker"),
                handle_data.get("handle_model"),
                source_text=src,
                matched_by="HandleMatcher",
                pattern=pat,
            ),
            "knot": build_knot_subdict(
                None,
                None,
                source_text=src,
                matched_by="HandleMatcher",
                pattern=pat,
            ),
        }

        return MatchResult(
            original=handle_result.original,
            matched=brush_data,
            match_type="handle",
            pattern=handle_data.get("_pattern_used"),
            strategy="handle_matching",
        )

    def _combine_handle_and_knot_results(
        self, handle_result: MatchResult, knot_result: MatchResult
    ) -> MatchResult:
        """
        Combine HandleMatcher and KnotMatcher results into a single brush result.

        Args:
            handle_result: MatchResult from HandleMatcher
            knot_result: MatchResult from KnotMatcher

        Returns:
            MatchResult with combined handle and knot data
        """
        handle_data = handle_result.matched or {}
        knot_data = knot_result.matched or {}

        # Get handle and knot brands
        handle_brand = handle_data.get("handle_maker")
        knot_brand = knot_data.get("brand")

        # Business rule: If handle and knot have the same brand,
        # set that brand at the top level
        top_level_brand = None
        if handle_brand and knot_brand and handle_brand == knot_brand:
            top_level_brand = handle_brand
        else:
            # Fall back to handle brand if brands don't match
            top_level_brand = handle_brand

        # Create combined brush data with nested handle/knot structure
        brush_data = {
            "brand": top_level_brand,
            "model": handle_data.get("handle_model"),
            "source_text": handle_data.get("_source_text", handle_result.original),
            "_matched_by": "HandleMatcher+KnotMatcher",
            "_pattern": handle_data.get("_pattern_used"),
            "handle": build_handle_subdict(
                handle_data.get("handle_maker"),
                handle_data.get("handle_model"),
                source_text=handle_data.get("_source_text", handle_result.original),
                matched_by="HandleMatcher",
                pattern=handle_data.get("_pattern_used"),
            ),
            "knot": build_knot_subdict(
                knot_data.get("brand"),
                knot_data.get("model"),
                knot_data.get("fiber"),
                knot_data.get("knot_size_mm"),
                source_text=knot_data.get("source_text", handle_result.original),
                matched_by="KnotMatcher",
                pattern=knot_data.get("_pattern_used"),
            ),
        }

        return MatchResult(
            original=handle_result.original,
            matched=brush_data,
            match_type="composite",
            pattern=handle_data.get("_pattern_used"),
            strategy="dual_component_matching",
        )

    def _convert_knot_result_to_brush_result(self, knot_result: MatchResult) -> MatchResult:
        """
        Convert KnotMatcher result to brush format for processing.

        Args:
            knot_result: MatchResult from KnotMatcher

        Returns:
            MatchResult in brush format
        """
        knot_data = knot_result.matched or {}

        # Create brush format result with nested handle/knot structure
        src = knot_data.get("source_text", knot_result.original)
        pat = knot_data.get("_pattern_used")
        brush_data = {
            "brand": knot_data.get("brand"),
            "model": knot_data.get("model"),
            "fiber": knot_data.get("fiber"),
            "knot_size_mm": knot_data.get("knot_size_mm"),
            "source_text": src,
            "_matched_by": "KnotMatcher",
            "_pattern": pat,
            "handle": build_handle_subdict(
                None,
                None,
                source_text=src,
                matched_by="KnotMatcher",
                pattern=pat,
            ),
            "knot": build_knot_subdict(
                knot_data.get("brand"),
                knot_data.get("model"),
                knot_data.get("fiber"),
                knot_data.get("knot_size_mm"),
                source_text=src,
                matched_by="KnotMatcher",
                pattern=pat,
            ),
        }

        return MatchResult(
            original=knot_result.original,
            matched=brush_data,
            match_type="knot",
            pattern=knot_data.get("_pattern_used"),
            strategy="knot_matching",
        )

    def _track_strategy_performance(self, strategy_results: List[MatchResult], value: str):
        """
        Track performance of individual strategies and update the optimizer.

        Args:
            strategy_results: List of MatchResult objects from strategies
            value: The brush string being matched
        """
        # Track which strategies produced results
        for result in strategy_results:
            strategy_name = result.strategy or "unknown_strategy"
            success = result.matched is not None and bool(result.matched)
            score = result.score or 0.0

            # For now, use a simple execution time estimate
            # In a real implementation, this would be measured during strategy execution
            execution_time = 0.01  # Placeholder - would be actual measured time

            # Record the strategy execution
            self.performance_optimizer.record_strategy_execution(
                strategy_name, execution_time, success, score
            )

    def _get_optimized_execution_order(self, strategy_names: List[str]) -> List[str]:
        """
        Get an optimized execution order based on strategy dependencies and performance.

        Args:
            strategy_names: List of strategy names to optimize

        Returns:
            List of strategy names in optimized order
        """
        # Use the strategy dependency manager to get the optimized order
        return self.strategy_dependency_manager.get_execution_order(strategy_names)

    def _apply_dependency_constraints(
        self, strategy_results: List[MatchResult]
    ) -> List[MatchResult]:
        """
        Apply dependency constraints to filter out strategies that cannot execute.

        Args:
            strategy_results: List of strategy results

        Returns:
            Filtered list of strategy results that can execute
        """
        # Convert results to dictionary for dependency checking
        results_dict = {result.strategy: result for result in strategy_results if result.strategy}

        # Filter out strategies that cannot execute due to dependencies
        executable_results = []
        for result in strategy_results:
            if not result.strategy:
                executable_results.append(result)
                continue

            if self.strategy_dependency_manager.can_execute_strategy(result.strategy, results_dict):
                executable_results.append(result)

        return executable_results

    def _precompute_handle_knot_results(self, value: str) -> dict:
        """
        Pre-compute HandleMatcher and KnotMatcher results for optimization.

        Args:
            value: The brush string to match

        Returns:
            Dictionary with cached handle and knot results
        """
        cached_results = {}

        # Pre-compute HandleMatcher result
        try:
            handle_result = self.handle_matcher.match_handle_maker(value)
            if handle_result:
                cached_results["handle_result"] = handle_result
        except Exception:
            # Handle matcher failed, continue without handle result
            pass

        # Pre-compute KnotMatcher result
        try:
            knot_result = self.knot_matcher.match(value)
            if knot_result:
                cached_results["knot_result"] = knot_result
        except Exception:
            # Knot matcher failed, continue without knot result
            pass

        # Pre-compute FullInputComponentMatchingStrategy result for unified strategy caching
        try:
            # Reuse the wired FullInputComponentMatchingStrategy from the
            # orchestrator instead of constructing a new one (with a fresh
            # BrushSplitsLoader that re-parses brush_splits.yaml) on every
            # match() call. The orchestrator's instance shares the matcher's
            # single BrushSplitsLoader.
            from .strategies.full_input_component_matching_strategy import (
                FullInputComponentMatchingStrategy,
            )

            unified_strategy = next(
                (
                    strategy
                    for strategy in self.strategy_orchestrator.strategies
                    if isinstance(strategy, FullInputComponentMatchingStrategy)
                ),
                None,
            )
            if unified_strategy is None:
                # Should not happen: _create_strategies always registers
                # one. Fall back to a temporary instance on the run's
                # data-dir path so the precompute still runs rather than
                # failing the match.
                unified_strategy = FullInputComponentMatchingStrategy(
                    self.handle_matcher,
                    self.knot_matcher,
                    self._catalogs,
                    brush_splits_path=self._brush_splits_path,
                )
            unified_result = unified_strategy.match(value)
            if unified_result:
                cached_results["full_input_component_matching_result"] = unified_result
        except Exception:
            # FullInputComponentMatchingStrategy failed, continue without result
            pass

        return cached_results

    def _try_correct_matches_strategies(
        self, value: str, cached_results: dict
    ) -> Optional[MatchResult]:
        """
        Try correct matches strategy first (highest priority).

        Args:
            value: The brush string to match
            cached_results: Pre-computed results for optimization

        Returns:
            MatchResult if correct match found, None otherwise
        """
        # Use the already-loaded correct matches data from initialization
        # (This method is only called when correct_matches.yaml should be used)
        # Reuse the same instance to avoid rebuilding the O(1) lookup dictionary
        if not hasattr(self, "_correct_matches_strategy"):
            self._correct_matches_strategy = CorrectMatchesStrategy(
                self.correct_matches_data, self._catalogs
            )
        correct_strategy = self._correct_matches_strategy

        try:
            result = correct_strategy.match(value)
            if result and result.matched:
                # Correct match found - return immediately
                return result
        except Exception as e:
            # Log error but continue
            print(f"Correct matches strategy {correct_strategy.__class__.__name__} failed: {e}")

        # No correct match found
        return None

    def match(
        self,
        value: str,
        original: Optional[str] = None,
        bypass_correct_matches: Optional[bool] = None,
    ) -> Optional[MatchResult]:
        """
        Match a brush string using the enhanced scoring system.

        Args:
            value: The normalized brush string to match
            original: The original brush string (defaults to value if not provided)
            bypass_correct_matches: If True, bypass correct_matches.yaml.
                If None or False, use correct_matches.yaml.

        Returns:
            MatchResult if found, None otherwise
        """
        if not value:
            return None

        # Use parameter if provided, otherwise default to False (use correct_matches.yaml)
        should_bypass = bypass_correct_matches if bypass_correct_matches is not None else False

        # Start performance monitoring
        self.performance_monitor.start_timing()

        try:
            # PHASE 1: Check correct matches strategies first (highest priority) if not bypassed
            # Check BEFORE pre-computing handle/knot results to avoid unnecessary work
            if not should_bypass:
                # Pass empty dict since correct matches strategy doesn't use cached_results
                correct_match_result = self._try_correct_matches_strategies(value, {})
                if correct_match_result:
                    # Correct match found - return immediately, don't run other strategies
                    if original is not None:
                        correct_match_result.original = original
                    return correct_match_result

            # Pre-compute HandleMatcher and KnotMatcher results for optimization
            # Only do this if we didn't find a correct match (performance optimization)
            cached_results = self._precompute_handle_knot_results(value)

            # PHASE 2: Run all other strategies (excluding correct matches if bypassed)
            strategy_results = self.strategy_orchestrator.run_all_strategies(value, cached_results)

            # If no strategy results, return None
            if not strategy_results:
                return None

            # Track strategy performance for optimization
            self._track_strategy_performance(strategy_results, value)

            # Apply dependency constraints to filter executable strategies
            executable_results = self._apply_dependency_constraints(strategy_results)

            # Get optimized execution order based on dependencies and performance
            strategy_names = [result.strategy for result in executable_results if result.strategy]
            # Note: optimized_order is calculated but not yet used for reordering
            # This will be used in future iterations when we implement actual reordering
            self.strategy_dependency_manager.get_execution_order(strategy_names)

            # Score the results
            scored_results = self.scoring_engine.score_results(
                executable_results, value, cached_results
            )

            # Get the best result based on score
            best_result = self.scoring_engine.get_best_result(scored_results)

            # Phase 4.1: Capture all strategy results for persistence
            # Store full MatchResult objects to preserve detailed data for API
            all_strategies = []
            for result in scored_results:  # Use scored_results from ScoringEngine
                # Store the full MatchResult object to preserve all data
                all_strategies.append(result)

            # Note: We no longer create separate best_result_data since strategy and score
            # are now added directly to the matched data

            # Return the result directly (no processing needed since
            # strategies produce correct structure)
            final_result = best_result

            # Add strategy persistence fields
            if final_result:
                # Update the original field to use the provided original text
                if original is not None:
                    final_result.original = original

                final_result.all_strategies = all_strategies

                # Add strategy and score directly to the matched data instead of
                # separate best_result
                if final_result.matched and best_result:
                    final_result.matched["strategy"] = best_result.strategy
                    final_result.matched["score"] = best_result.score

            return final_result

        except Exception as e:
            # Log error but don't fail completely
            print(f"Error during brush matching: {e}")
            return None
        finally:
            # End performance monitoring
            self.performance_monitor.end_timing()

    def get_cache_stats(self) -> dict:
        """
        Get cache and performance statistics.

        Returns:
            Dictionary containing cache and performance statistics
        """
        return {
            "performance": self.performance_monitor.get_performance_stats(),
            "total_time": self.performance_monitor.get_total_time(),
        }

    def get_performance_stats(self) -> dict:
        """
        Get comprehensive performance statistics including strategy optimization data.

        Returns:
            Dictionary containing performance statistics and optimization data
        """
        # Get basic performance stats
        basic_stats = self.get_cache_stats()

        # Get strategy performance data
        strategy_performance = self.performance_optimizer.get_performance_report()

        return {
            **basic_stats,
            "strategy_performance": strategy_performance,
            "optimization_recommendations": strategy_performance.get(
                "optimization_recommendations", {}
            ),
            "slow_strategies": strategy_performance.get("slow_strategies", []),
        }

    def get_dependency_info(self) -> dict:
        """
        Get dependency information and status.

        Returns:
            Dictionary containing dependency information and status
        """
        return {
            "dependency_manager": self.strategy_dependency_manager,
            "dependencies": self.strategy_dependency_manager.dependencies,
            "dependency_graph": self.strategy_dependency_manager.dependency_graph,
            "topological_graph": self.strategy_dependency_manager.topological_graph,
        }

    # Methods required by wrapper strategies to maintain compatibility
    # These methods implement the legacy interface using the new system

    def _match_correct_complete_brush(self, value: str) -> Optional["MatchResult"]:
        """
        Match using correct complete brush logic.

        This method is required by wrapper strategies and implements
        the legacy interface using the new scoring system.

        Args:
            value: The brush string to match

        Returns:
            MatchResult if found, None otherwise
        """
        # Use the correct matches strategy directly
        for strategy in self.strategy_orchestrator.strategies:
            if (
                hasattr(strategy, "__class__")
                and "CorrectCompleteBrush" in strategy.__class__.__name__
            ):
                return strategy.match(value)
        return None

    def _match_correct_split_brush(self, value: str) -> Optional["MatchResult"]:
        """
        Match using correct split brush logic.

        This method is required by wrapper strategies and implements
        the legacy interface using the new scoring system.

        Args:
            value: The brush string to match

        Returns:
            MatchResult if found, None otherwise
        """
        # Use the correct split brush strategy directly
        for strategy in self.strategy_orchestrator.strategies:
            if (
                hasattr(strategy, "__class__")
                and "CorrectSplitBrush" in strategy.__class__.__name__
            ):
                return strategy.match(value)
        return None

    def _match_known_split(self, value: str) -> Optional["MatchResult"]:
        """
        Match using known split logic.

        This method is required by wrapper strategies and implements
        the legacy interface using the new scoring system.

        Args:
            value: The brush string to match

        Returns:
            MatchResult if found, None otherwise
        """
        # Use the known split strategy directly
        for strategy in self.strategy_orchestrator.strategies:
            if hasattr(strategy, "__class__") and "KnownSplit" in strategy.__class__.__name__:
                return strategy.match(value)
        return None

    def _match_complete_brush(self, value: str) -> Optional["MatchResult"]:
        """
        Match using complete brush logic.

        This method is required by wrapper strategies and implements
        the legacy interface using the new scoring system.

        Args:
            value: The brush string to match

        Returns:
            MatchResult if found, None otherwise
        """
        # Use the complete brush strategies directly
        for strategy in self.strategy_orchestrator.strategies:
            if hasattr(strategy, "__class__") and any(
                name in strategy.__class__.__name__
                for name in ["KnownBrush", "OmegaSemogue", "Zenith", "OtherBrush"]
            ):
                result = strategy.match(value)
                if result:
                    return result
        return None

    def _match_high_priority_automated_split(self, value: str) -> Optional["MatchResult"]:
        """
        Match using high priority automated split logic.

        This method is required by wrapper strategies and implements
        the legacy interface using the new scoring system.

        Args:
            value: The brush string to match

        Returns:
            MatchResult if found, None otherwise
        """
        # Use the automated split strategy with high priority
        for strategy in self.strategy_orchestrator.strategies:
            if hasattr(strategy, "__class__") and "AutomatedSplit" in strategy.__class__.__name__:
                # The automated split strategy handles both high and medium priority
                # We'll need to modify it to support this legacy interface
                result = strategy.match(value)
                if (
                    result
                    and hasattr(result, "_delimiter_priority")
                    and result._delimiter_priority == "high"
                ):
                    return result
        return None

    def _match_medium_priority_automated_split(self, value: str) -> Optional["MatchResult"]:
        """
        Match using medium priority automated split logic.

        This method is required by wrapper strategies and implements
        the legacy interface using the new scoring system.

        Args:
            value: The brush string to match

        Returns:
            MatchResult if found, None otherwise
        """
        # Use the automated split strategy with medium priority
        for strategy in self.strategy_orchestrator.strategies:
            if hasattr(strategy, "__class__") and "AutomatedSplit" in strategy.__class__.__name__:
                # The automated split strategy handles both high and medium priority
                # We'll need to modify it to support this legacy interface
                result = strategy.match(value)
                if (
                    result
                    and hasattr(result, "_delimiter_priority")
                    and result._delimiter_priority == "medium"
                ):
                    return result
        return None

    def create_dual_component_result(
        self, handle_result: "MatchResult", knot_result: "MatchResult", value: str
    ) -> "MatchResult":
        """
        Create a dual component result combining handle and knot.

        This method is required by wrapper strategies and implements
        the legacy interface using the new scoring system.

        Args:
            handle_result: HandleMatcher result
            knot_result: KnotMatcher result
            value: Original input string

        Returns:
            Combined MatchResult
        """
        return self._combine_handle_and_knot_results(handle_result, knot_result)

    def create_single_component_result(
        self, component_result: "MatchResult", value: str, component_type: str
    ) -> "MatchResult":
        """
        Create a single component result.

        This method is required by wrapper strategies and implements
        the legacy interface using the new scoring system.

        Args:
            component_result: Component matcher result
            value: Original input string
            component_type: Type of component ("handle" or "knot")

        Returns:
            Converted MatchResult
        """
        if component_type == "handle":
            return self._convert_handle_result_to_brush_result(component_result)
        elif component_type == "knot":
            return self._convert_knot_result_to_brush_result(component_result)
        else:
            return component_result
