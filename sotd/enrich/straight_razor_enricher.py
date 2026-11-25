import re
from typing import Any, Dict, Optional

from .enricher import BaseEnricher
from .override_manager import EnrichmentOverrideManager


class StraightRazorEnricher(BaseEnricher):
    """Enricher for extracting straight razor specifications from user comments.

    Extracts grind type, width, and point type from patterns like:
    - "full hollow 6/8 round point" -> grind: "full_hollow", width_eighths: 6, point: "round"
    - "wedge 7/8 square" -> grind: "wedge", width_eighths: 7, point: "square"
    - "half hollow 5/8" -> grind: "half_hollow", width_eighths: 5, point: null
    """

    def __init__(self, override_manager: Optional[EnrichmentOverrideManager] = None):
        """Initialize StraightRazorEnricher.

        Args:
            override_manager: Optional enrichment override manager for forcing catalog values
        """
        super().__init__()
        self.override_manager = override_manager

    @property
    def target_field(self) -> str:
        return "razor"

    def applies_to(self, record: Dict[str, Any]) -> bool:
        """Determine if this enricher applies to the given record.

        Applies to records that have a matched razor product that is a straight razor.
        Only validates on format field - straight razors should have format="Straight".
        """
        if "razor" not in record or record["razor"] is None:
            return False

        # Check if the razor is identified as a straight razor
        razor_data = record["razor"]
        if not isinstance(razor_data, dict):
            return False

        # Accept either top-level format or matched.format
        if razor_data.get("format") == "Straight":
            return True
        matched_data = razor_data.get("matched", {})
        if matched_data:
            return matched_data.get("format") == "Straight"
        return False

    def enrich(
        self,
        field_data: Dict[str, Any],
        original_comment: str,
        record: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Extract straight razor specifications from the user-supplied razor_extracted field.

        Args:
            field_data: The matched razor data from the match phase
            original_comment: The user-supplied razor_extracted field (not the full comment)

        Returns:
            Dictionary with grind, width (as string), point, and steel if found, or None if no
            specs detected. Includes _enriched_by and _extraction_source metadata fields.
            Preserves existing specifications from the match phase catalog data.
        """
        # Extract specifications from the razor_extracted field
        user_grind = self._extract_grind(original_comment)
        user_width = self._extract_width_str(original_comment)
        user_point = self._extract_point(original_comment)
        user_steel = self._extract_steel(original_comment)

        # Get existing specifications from match phase catalog data
        catalog_grind = field_data.get("grind") if isinstance(field_data, dict) else None
        catalog_width = field_data.get("width") if isinstance(field_data, dict) else None
        catalog_point = field_data.get("point") if isinstance(field_data, dict) else None
        catalog_steel = field_data.get("steel") if isinstance(field_data, dict) else None

        # Check for enrichment overrides if override_manager and record are available
        if self.override_manager and record:
            month = record.get("_month")
            comment_id = record.get("id")
            if month and comment_id:
                # Check for grind override
                grind_override = self.override_manager.get_override(
                    month, comment_id, "razor", "grind"
                )
                if grind_override == "use_catalog":
                    user_grind = None
                elif grind_override is not None and grind_override != "use_catalog":
                    user_grind = grind_override
                    catalog_grind = grind_override

                # Check for width override
                width_override = self.override_manager.get_override(
                    month, comment_id, "razor", "width"
                )
                if width_override == "use_catalog":
                    user_width = None
                elif width_override is not None and width_override != "use_catalog":
                    user_width = width_override
                    catalog_width = width_override

                # Check for point override
                point_override = self.override_manager.get_override(
                    month, comment_id, "razor", "point"
                )
                if point_override == "use_catalog":
                    user_point = None
                elif point_override is not None and point_override != "use_catalog":
                    user_point = point_override
                    catalog_point = point_override

                # Check for steel override
                steel_override = self.override_manager.get_override(
                    month, comment_id, "razor", "steel"
                )
                if steel_override == "use_catalog":
                    user_steel = None
                elif steel_override is not None and steel_override != "use_catalog":
                    user_steel = steel_override
                    catalog_steel = steel_override

        # Merge specifications: user comment takes precedence over catalog data
        final_grind = user_grind or catalog_grind
        final_width = user_width or catalog_width
        final_point = user_point or catalog_point

        # For steel, only record what the user comment, the catalog, or an
        # override actually says. There is no Carbon default: an unobserved
        # steel is not an enrichment, and a default here also forced this
        # enricher to return a dict (and count as enriched) for every
        # straight razor even when nothing was found.
        final_steel = user_steel or catalog_steel

        # Determine extraction source for metadata
        extraction_sources = []
        if user_grind or user_width or user_point or user_steel:
            extraction_sources.append("user_comment")
        if catalog_grind or catalog_width or catalog_point or catalog_steel:
            extraction_sources.append("catalog_data")

        # Only return enriched data if we have specifications from any source
        if any([final_grind, final_width, final_point, final_steel]):
            enriched_data: Dict[str, Any] = {
                "_enriched_by": self.get_enricher_name(),
                "_extraction_source": (
                    " + ".join(extraction_sources) if extraction_sources else "none"
                ),
            }

            if final_grind:
                enriched_data["grind"] = final_grind
            if final_width:
                enriched_data["width"] = final_width
            if final_point:
                enriched_data["point"] = final_point
            if final_steel:
                enriched_data["steel"] = final_steel

            return enriched_data

        return None

    def _extract_width_str(self, text: str) -> Optional[str]:
        """Extract width as a string fraction from text using regex patterns.

        Args:
            text: The text to search for width patterns

        Returns:
            The extracted width as a string (e.g., '15/16', '5/8'), or None if not found
        """
        # Look for common fractional patterns
        match = re.search(r"\b(\d{1,2})/(8|16)\b", text)
        if match:
            return f"{match.group(1)}/{match.group(2)}"
        # Optionally, handle decimal patterns (e.g., 0.75)
        match = re.search(r"\b(0\.5|0\.625|0\.75|0\.875|1\.0)\b", text)
        if match:
            decimal_map = {
                "0.5": "4/8",
                "0.625": "5/8",
                "0.75": "6/8",
                "0.875": "7/8",
                "1.0": "8/8",
            }
            return decimal_map.get(match.group(1))
        return None

    def _parse_catalog_width(self, width_str: str) -> Optional[int]:
        """Parse width specification from catalog data into eighths.

        Args:
            width_str: Width string from catalog (e.g., "15/16", "6/8", "0.75")

        Returns:
            Width in eighths as integer, or None if cannot parse
        """
        if not width_str:
            return None

        # Handle fractional formats
        fractional_match = re.match(r"(\d+)/(\d+)", width_str)
        if fractional_match:
            numerator = int(fractional_match.group(1))
            denominator = int(fractional_match.group(2))

            if denominator == 8:
                return numerator
            elif denominator == 16:
                return numerator // 2
            else:
                # Convert to eighths (assuming inches)
                return int((numerator / denominator) * 8)

        # Handle decimal formats
        try:
            width_float = float(width_str)
            return int(width_float * 8)
        except ValueError:
            return None

    def _extract_grind(self, text: str) -> Optional[str]:
        """Extract grind type from text using regex patterns.

        Args:
            text: The text to search for grind patterns

        Returns:
            The extracted grind type as a string in Title Case, or None if not found
        """
        # Grind patterns in order of specificity (most specific first)
        # Return Title Case values for better readability in reports
        grind_patterns = [
            # Fractional notation patterns (most specific first)
            (r"(?i)\b1/4\s*hollow\b", "Quarter Hollow"),
            (r"(?i)\b2/4\s*hollow\b", "Half Hollow"),
            (r"(?i)\b3/4\s*hollow\b", "Three Quarter Hollow"),
            (r"(?i)\b4/4\s*hollow\b", "Full Hollow"),
            # Word-based patterns
            (r"(?i)\bextra\s*hollow\b", "Extra Hollow"),
            (r"(?i)\bfull\s*hollow\b", "Full Hollow"),
            (r"(?i)\bpretty\s*hollow\b", "Pretty Hollow"),
            (r"(?i)\bthree\s*quarter\s*hollow\b", "Three Quarter Hollow"),
            (r"(?i)\bhalf\s*hollow\b", "Half Hollow"),
            (r"(?i)\bquarter\s*hollow\b", "Quarter Hollow"),
            (r"(?i)\bhollow\b", "Hollow"),  # Generic hollow
            (r"(?i)\bnear\s*wedge\b", "Near Wedge"),
            (r"(?i)\bwedge\b", "Wedge"),
            (r"(?i)\bframeback\b", "Frameback"),
        ]

        for pattern, grind_type in grind_patterns:
            if re.search(pattern, text):
                return grind_type

        return None

    def _extract_width(self, text: str) -> Optional[int]:
        """Extract width from text using regex patterns.

        Args:
            text: The text to search for width patterns

        Returns:
            The extracted width in eighths as an integer, or None if not found
        """
        # Width patterns - look for fractional and decimal formats
        width_patterns = [
            # Direct eighth patterns (4/8, 5/8, etc.) - most specific first
            (r"\b(4|5|6|7|8)/8\b", lambda m: int(m.group(1))),
            # Direct sixteenth patterns (8/16, 10/16, etc.)
            (r"\b(8|10|12|14|16)/16\b", lambda m: round(int(m.group(1)) / 2)),
            # Fractional patterns (4/8, 5/8, 6/8, 7/8, 8/8, etc.)
            (
                r"\b(\d{1,2})/(8|16)\b",
                lambda m: int(m.group(1)) if m.group(2) == "8" else round(int(m.group(1)) / 2),
            ),
            # Decimal patterns (0.5, 0.625, 0.75, 0.875, 1.0, etc.)
            (
                r"\b(0\.5|0\.625|0\.75|0\.875|1\.0)\b",
                lambda m: {"0.5": 4, "0.625": 5, "0.75": 6, "0.875": 7, "1.0": 8}[m.group(1)],
            ),
        ]

        for pattern, converter in width_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    return converter(match)
                except (ValueError, KeyError):
                    continue

        return None

    def _extract_point(self, text: str) -> Optional[str]:
        """Extract point type from text using regex patterns.

        Args:
            text: The text to search for point patterns

        Returns:
            The extracted point type as a string in Title Case, or None if not found
        """
        # Point patterns in order of specificity
        # Return Title Case values for better readability in reports
        point_patterns = [
            (r"(?i)\bround\s*(?:point|tip)\b", "Round"),
            (r"(?i)\bsquare\s*(?:point|tip)\b", "Square"),
            (r"(?i)\bspike\s*(?:point|tip)\b", "Spike"),
            (r"(?i)\bfrench\s*(?:point|tip)\b", "French"),
            (r"(?i)\bspanish\s*(?:point|tip)\b", "Spanish"),
            (r"(?i)\bbarber['']?s\s*notch\b", "Barber's Notch"),
            (r"(?i)\bspear\s*(?:point|tip)\b", "Spear"),
            (r"(?i)\bround\b", "Round"),  # Generic round
            (r"(?i)\bsquare\b", "Square"),  # Generic square
            (r"(?i)\bspike\b", "Spike"),  # Generic spike
        ]

        for pattern, point_type in point_patterns:
            if re.search(pattern, text):
                return point_type

        return None

    def _extract_steel(self, text: str) -> Optional[str]:
        """Extract steel type from text using regex patterns.

        Args:
            text: The text to search for steel patterns

        Returns:
            The extracted steel type as a string, or None if not found.
            Returns "Stainless" for stainless steel terms (stainless, SS, inox, rostfrei, friodur).
            Returns "Carbon" for carbon steel terms (carbon, carbon steel).
        """
        # Normalize text for case-insensitive matching
        text_lower = text.lower()

        # Steel patterns in order of specificity (case insensitive)
        steel_patterns = [
            (r"(?i)\bstainless\s*steel\b", "Stainless"),
            (r"(?i)\bcarbon\s*steel\b", "Carbon"),
            (r"(?i)\bstainless\b", "Stainless"),
            (r"(?i)\bcarbon\b", "Carbon"),
            (r"(?i)\binox\b", "Stainless"),  # French/German for stainless steel
            (r"(?i)\brostfrei\b", "Stainless"),  # German for stainless steel
            (r"(?i)\bfriodur\b", "Stainless"),  # Henckels proprietary stainless steel
            (r"(?i)\bss\b", "Stainless"),  # Abbreviation for Stainless Steel
        ]

        for pattern, steel_type in steel_patterns:
            if re.search(pattern, text_lower):
                return steel_type

        return None
