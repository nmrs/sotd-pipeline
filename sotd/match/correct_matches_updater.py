"""Correct matches updater for managing correct_matches directory operations."""

import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from sotd.utils.data_dir import get_default_correct_matches_path


class CorrectMatchesUpdater:
    """Handle YAML file operations for correct_matches directory."""

    def __init__(self, correct_matches_path: Optional[Path] = None):
        """Initialize updater with path to correct_matches directory."""
        self.correct_matches_path = correct_matches_path or get_default_correct_matches_path()
        self._ensure_directory_exists()

    def _ensure_directory_exists(self) -> None:
        """Ensure the directory for correct_matches exists."""
        self.correct_matches_path.mkdir(parents=True, exist_ok=True)

    def load_correct_matches(self, field_type: Optional[str] = None) -> Dict[str, Any]:
        """Load existing correct_matches data from directory structure."""
        if not self.correct_matches_path.exists():
            return {}

        data = {}

        if field_type:
            # Load specific field file
            field_file = self.correct_matches_path / f"{field_type}.yaml"
            if field_file.exists():
                try:
                    with field_file.open("r", encoding="utf-8") as f:
                        field_data = yaml.safe_load(f)
                        if field_data:
                            data[field_type] = field_data
                except (yaml.YAMLError, FileNotFoundError):
                    pass
        else:
            # Load all field files
            for field_file in self.correct_matches_path.glob("*.yaml"):
                field_name = field_file.stem
                # Skip backup and report files
                if (
                    field_file.name.endswith((".backup", ".bk"))
                    or "duplicates_report" in field_file.name
                ):
                    continue
                try:
                    with field_file.open("r", encoding="utf-8") as f:
                        field_data = yaml.safe_load(f)
                        if field_data:
                            data[field_name] = field_data
                except (yaml.YAMLError, FileNotFoundError):
                    pass

        return data

    def add_or_update_entry(
        self,
        input_text: str,
        result_data: Dict[str, Any],
        action_type: str,
        field_type: str = "brush",
    ) -> None:
        """
        Add new entry or update existing one in correct_matches directory.

        Args:
            input_text: The input text to match (preserves original casing)
            result_data: The result data to store
            action_type: Type of action ("validated" or "overridden")
            field_type: Field type ("brush", "handle", "knot", etc.)
        """
        import logging

        logger = logging.getLogger(__name__)

        try:
            logger.debug(
                f"Adding/updating entry: input_text='{input_text}', field_type='{field_type}'"
            )

            # Load existing data for the specific field
            all_data = self.load_correct_matches()
            data = {field_type: all_data.get(field_type, {})}

            # Preserve original casing for storage, but normalize for lookup
            original_text = input_text.strip()
            normalized_text = input_text.lower().strip()

            # For brush field, use the hierarchical structure
            if field_type == "brush":
                logger.debug("Processing brush field type")
                # Ensure field section exists
                if field_type not in data:
                    data[field_type] = {}

                # Extract brand and model from result data
                brand = result_data.get("brand")
                model = result_data.get("model")

                if brand:
                    # Ensure brand section exists
                    if brand not in data[field_type]:
                        data[field_type][brand] = {}

                    # Handle dual-component brushes where model is null
                    if model is None:
                        # For dual-component brushes, use a special model identifier
                        # This allows them to be stored in correct_matches directory
                        model_key = "dual_component"
                    else:
                        model_key = model

                    # Ensure model section exists
                    if model_key not in data[field_type][brand]:
                        data[field_type][brand][model_key] = []

                    # Add the original text as a pattern if not already present
                    # Check for case-insensitive duplicates to avoid storing the same text
                    # multiple times
                    existing_patterns = data[field_type][brand][model_key]
                    if not any(pattern.lower() == normalized_text for pattern in existing_patterns):
                        existing_patterns.append(original_text)
                        logger.debug(
                            f"Added pattern '{original_text}' to brush/{brand}/{model_key}"
                        )

            # For handle and knot fields, use flat structure
            elif field_type in ["handle", "knot"]:
                logger.debug(f"Processing {field_type} field type")
                # Ensure field section exists
                if field_type not in data:
                    data[field_type] = {}

                # Add entry with original text as key, but check for case-insensitive duplicates
                if not any(key.lower() == normalized_text for key in data[field_type]):
                    data[field_type][original_text] = result_data
                    logger.debug(f"Added entry '{original_text}' to {field_type} section")

            # For split_brush field, store handle/knot mapping
            elif field_type == "split_brush":
                logger.debug("Processing split_brush field type")
                # Extract handle and knot components from the dual-component brush
                handle_data = result_data.get("handle", {})
                knot_data = result_data.get("knot", {})

                logger.debug(f"Handle data: {handle_data}")
                logger.debug(f"Knot data: {knot_data}")

                # Handle both string and dict formats for backward compatibility
                if isinstance(handle_data, str):
                    handle_data = {"brand": "Unknown", "model": handle_data}
                if isinstance(knot_data, str):
                    knot_data = {"brand": "Unknown", "model": knot_data}

                if handle_data and knot_data:
                    # Store handle component in handle section
                    handle_brand = handle_data.get("brand")
                    handle_model = handle_data.get("model")

                    logger.debug(
                        f"Processing handle: brand='{handle_brand}', model='{handle_model}'"
                    )

                    if handle_brand and handle_model:
                        # Ensure handle section exists
                        if "handle" not in data:
                            data["handle"] = {}
                        if handle_brand not in data["handle"]:
                            data["handle"][handle_brand] = {}
                        if handle_model not in data["handle"][handle_brand]:
                            data["handle"][handle_brand][handle_model] = []

                        # Add the original text to handle section if not already present
                        existing_patterns = data["handle"][handle_brand][handle_model]
                        if not any(
                            pattern.lower() == normalized_text for pattern in existing_patterns
                        ):
                            existing_patterns.append(original_text)
                            logger.debug(
                                f"Added pattern '{original_text}' to "
                                f"handle/{handle_brand}/{handle_model}"
                            )

                    # Store knot component in knot section
                    knot_brand = knot_data.get("brand")
                    knot_model = knot_data.get("model")

                    logger.debug(f"Processing knot: brand='{knot_brand}', model='{knot_model}'")

                    if knot_brand and knot_model:
                        # Ensure knot section exists
                        if "knot" not in data:
                            data["knot"] = {}
                        if knot_brand not in data["knot"]:
                            data["knot"][knot_brand] = {}
                        if knot_model not in data["knot"][knot_brand]:
                            data["knot"][knot_brand][knot_model] = []

                        # Add the original text to knot section if not already present
                        existing_patterns = data["knot"][knot_brand][knot_model]
                        if not any(
                            pattern.lower() == normalized_text for pattern in existing_patterns
                        ):
                            existing_patterns.append(original_text)
                            logger.debug(
                                f"Added pattern '{original_text}' to knot/{knot_brand}/{knot_model}"
                            )
                else:
                    logger.warning(
                        f"Missing handle or knot data for split_brush: "
                        f"handle={handle_data}, knot={knot_data}"
                    )
                    # Fallback: if we can't extract components, store as regular brush
                    # This shouldn't happen with proper dual-component data
                    if "brush" not in data:
                        data["brush"] = {}
                    if "dual_component" not in data["brush"]:
                        data["brush"]["dual_component"] = []

                    existing_patterns = data["brush"]["dual_component"]
                    if not any(pattern.lower() == normalized_text for pattern in existing_patterns):
                        existing_patterns.append(original_text)
                        logger.debug(
                            f"Added pattern '{original_text}' to brush/dual_component (fallback)"
                        )

            # Save the updated data
            # For split_brush, save handle and knot separately (not split_brush field)
            if field_type == "split_brush":
                logger.debug("Saving handle and knot sections for split_brush")
                # Save handle and knot sections separately
                if "handle" in data:
                    self.save_correct_matches({"handle": data["handle"]}, "handle")
                if "knot" in data:
                    self.save_correct_matches({"knot": data["knot"]}, "knot")
            else:
                logger.debug(f"Saving updated correct_matches/{field_type}.yaml")
                self.save_correct_matches(data, field_type)
                logger.debug(f"Successfully saved correct_matches/{field_type}.yaml")

        except Exception as e:
            logger.error(f"Error in add_or_update_entry: {e}")
            raise

    def save_correct_matches(
        self, data: Optional[Dict[str, Any]] = None, field_type: Optional[str] = None
    ) -> None:
        """
        Save data to correct_matches directory using atomic write operations.

        Args:
            data: Data to save, or None to use current data
            field_type: Field type to save (if None, saves all fields in data)
        """
        if data is None:
            data = self.load_correct_matches()

        # Save each field to its own file
        for field_name, field_data in data.items():
            if field_type and field_name != field_type:
                continue

            field_file = self.correct_matches_path / f"{field_name}.yaml"

            # Create temporary file for atomic write
            temp_file = tempfile.NamedTemporaryFile(
                mode="w", suffix=".yaml", delete=False, encoding="utf-8"
            )
            temp_file_path = None

            try:
                # Write to temporary file
                yaml.dump(
                    field_data,
                    temp_file,
                    default_flow_style=False,
                    sort_keys=True,
                    allow_unicode=True,
                    indent=2,
                )
                temp_file.close()
                temp_file_path = temp_file.name

                # Atomic move to final location
                shutil.move(temp_file_path, field_file)

            except Exception as e:
                # Clean up temporary file on error
                if temp_file_path:
                    try:
                        Path(temp_file_path).unlink(missing_ok=True)
                    except Exception:
                        pass
                raise e

    def remove_entry(self, input_text: str, field_type: str = "brush") -> bool:
        """
        Remove an entry from correct_matches directory.

        Args:
            input_text: The input text to remove
            field_type: Field type to remove from

        Returns:
            True if entry was removed, False if not found
        """
        all_data = self.load_correct_matches()
        data = {field_type: all_data.get(field_type, {})}
        normalized_text = input_text.lower().strip()

        if field_type not in data:
            return False

        if field_type == "brush":
            # Search through brand/model hierarchy with case-insensitive lookup
            for brand in data[field_type]:
                for model in data[field_type][brand]:
                    # Find the actual text (preserving case) to remove
                    for pattern in data[field_type][brand][model]:
                        if pattern.lower() == normalized_text:
                            data[field_type][brand][model].remove(pattern)
                            # Remove empty model sections
                            if not data[field_type][brand][model]:
                                del data[field_type][brand][model]
                            # Remove empty brand sections
                            if not data[field_type][brand]:
                                del data[field_type][brand]
                            self.save_correct_matches(data, field_type)
                            return True
        else:
            # For flat structures like handle, knot, split_brush
            # Find the actual key (preserving case) to remove
            for key in list(data[field_type].keys()):
                if key.lower() == normalized_text:
                    del data[field_type][key]
                    self.save_correct_matches(data, field_type)
                    return True

        return False

    def get_entry(self, input_text: str, field_type: str = "brush") -> Optional[Dict[str, Any]]:
        """
        Get an entry from correct_matches directory.

        Args:
            input_text: The input text to look up
            field_type: Field type to search in

        Returns:
            Entry data if found, None otherwise
        """
        all_data = self.load_correct_matches()
        data = {field_type: all_data.get(field_type, {})}
        normalized_text = input_text.lower().strip()

        if field_type not in data:
            return None

        if field_type == "brush":
            # Search through brand/model hierarchy with case-insensitive lookup
            for brand in data[field_type]:
                for model in data[field_type][brand]:
                    for pattern in data[field_type][brand][model]:
                        if pattern.lower() == normalized_text:
                            return {"brand": brand, "model": model, "pattern": pattern}
        else:
            # For flat structures like handle, knot, split_brush
            # Find the actual key (preserving case)
            for key in data[field_type]:
                if key.lower() == normalized_text:
                    return data[field_type][key]

        return None

    def has_entry(self, input_text: str, field_type: str = "brush") -> bool:
        """
        Check if an entry exists in correct_matches directory.

        Args:
            input_text: The input text to check
            field_type: Field type to search in

        Returns:
            True if entry exists, False otherwise
        """
        all_data = self.load_correct_matches()
        data = {field_type: all_data.get(field_type, {})}

        # For split_brush, also check handle and knot sections
        if field_type == "split_brush":
            if "handle" not in data:
                data["handle"] = all_data.get("handle", {})
            if "knot" not in data:
                data["knot"] = all_data.get("knot", {})
        normalized_text = input_text.lower().strip()

        if field_type not in data and field_type != "split_brush":
            return False

        if field_type == "brush":
            # Search through brand/model hierarchy with case-insensitive lookup
            for brand in data[field_type]:
                for model in data[field_type][brand]:
                    for pattern in data[field_type][brand][model]:
                        if pattern.lower() == normalized_text:
                            return True
        elif field_type == "split_brush":
            # For split_brush, check both handle and knot sections
            # since the entry is stored in both sections
            if "handle" in data:
                for brand in data["handle"]:
                    for model in data["handle"][brand]:
                        for pattern in data["handle"][brand][model]:
                            if pattern.lower() == normalized_text:
                                return True

            if "knot" in data:
                for brand in data["knot"]:
                    for model in data["knot"][brand]:
                        for pattern in data["knot"][brand][model]:
                            if pattern.lower() == normalized_text:
                                return True
        else:
            # For flat structures like handle, knot
            # Find the actual key (preserving case)
            for key in data[field_type]:
                if key.lower() == normalized_text:
                    return True

        return False
