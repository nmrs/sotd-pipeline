# Enrichment Overrides for SOTD Pipeline

## Overview

The SOTD Pipeline includes an enrichment override system that allows data analysts to force catalog values over user-extracted values for specific records. This is particularly useful for cases where user text extraction is incorrect but the catalog has authoritative data.

## How It Works

The override system integrates into the **enrich phase** of the pipeline, allowing you to override user-extracted enrichment values with catalog values or explicit values for specific comment records. Overrides are applied during field enrichment and take precedence over default behavior (where user data overrides catalog data).

## Configuration

### Override File Location

By default, the system looks for overrides in:
```
data/enrichment_overrides.yaml
```

The override file is optional - the pipeline continues normally if it doesn't exist.

### Override File Format

The override file uses YAML format with the following structure:

```yaml
# Month in YYYY-MM format
2026-01:
  # Reddit comment ID
  m99b8f9:
    # Field-specific overrides
    brush:
      # Option 1: Use catalog value (flag-based)
      fiber:
        use_catalog: true
      # Option 2: Specify exact value
      knot_size_mm: 28.0
```

### Override Priority

1. **Explicit value** (if specified) - highest priority
2. **use_catalog flag** (if true) - use catalog value, ignore user extraction
3. **Default behavior** (no override) - user data overrides catalog data

### Valid Fields

The override system supports the brush and razor field types. Blade and
soap have no supported override keys: no enricher reads an override for
them, so any key under `blade` or `soap` fails validation. Adding a key
for those fields means wiring an enricher to read it, not just listing
it as valid — a listed-but-unread key loads fine and silently does
nothing.

#### Brush Enrichment (`brush`)
- `fiber` - Fiber type (string, e.g., "Mixed Badger/Horse", "Badger", "Synthetic")
- `knot_size_mm` - Knot size in millimeters (float, e.g., 21.0, 28.0)

#### Razor Enrichment (`razor`)
- `grind` - Straight razor grind type (string, e.g., "full_hollow", "wedge")
- `width` - Straight razor width (string fraction, e.g., "6/8", "15/16")
- `point` - Straight razor point type (string, e.g., "round", "square", "french")
- `steel` - Straight razor steel type (string, e.g., "Carbon", "Stainless")

## Usage Examples

### Example 1: Use Catalog Fiber

Force use of catalog fiber value, ignoring user extraction:

```yaml
2026-01:
  m99b8f9:
    brush:
      fiber:
        use_catalog: true
```

**Use Case**: User comment "Vielong Mixed Hair BADGER" incorrectly extracts "Mixed Badger/Boar" but catalog has "Mixed Badger/Horse".

### Example 2: Explicit Fiber Value

Specify exact fiber value to use:

```yaml
2026-01:
  m99b8f9:
    brush:
      fiber: "Mixed Badger/Horse"
```

### Example 3: Multiple Overrides

Override multiple enrichment fields:

```yaml
2026-01:
  m99b8f9:
    brush:
      fiber:
        use_catalog: true
      knot_size_mm: 21.0
```

### Example 4: Razor Enrichment Overrides

Override straight razor specifications:

```yaml
2026-01:
  m99b8f9:
    razor:
      grind:
        use_catalog: true
      width: "15/16"
      point: "round"
```

### Example 5: Multiple Field Types

Override enrichment fields across multiple product types:

```yaml
2026-01:
  m99b8f9:
    brush:
      fiber:
        use_catalog: true
    razor:
      grind: "full_hollow"
      steel: "Carbon"
```

## Validation and Error Handling

### Automatic Validation

The system automatically validates:
- YAML syntax
- Month format (YYYY-MM)
- Comment ID format
- Field name validity (razor, blade, brush, soap)
- Enrichment key validity (field-specific keys)
- Value type validation (strings and floats based on enrichment key)
- `use_catalog` flag validation (boolean)

### Error Handling

The system follows a **fail-fast** approach:
- Invalid override files cause immediate pipeline failure
- Clear error messages explain what went wrong
- Debug logging provides troubleshooting information

### Common Error Scenarios

**Invalid field name:**
```yaml
2026-01:
  m99b8f9:
    invalid_field:
      fiber: "test"  # Error: Invalid field 'invalid_field'
```

**Invalid enrichment key:**
```yaml
2026-01:
  m99b8f9:
    brush:
      invalid_key: "test"  # Error: Invalid enrichment key 'invalid_key' for field 'brush'
```

**Invalid value type:**
```yaml
2026-01:
  m99b8f9:
    brush:
      knot_size_mm: "28.0"  # Warning: String will be converted to float
```

**Invalid use_catalog type:**
```yaml
2026-01:
  m99b8f9:
    brush:
      fiber:
        use_catalog: "true"  # Error: use_catalog must be boolean
```

## Integration with Pipeline

The enrichment override system integrates seamlessly into the enrich phase:

1. **Loading**: Overrides are loaded during enrich phase initialization
2. **Application**: Overrides are checked before merging user/catalog data
3. **Priority**: Explicit values > use_catalog flags > default behavior
4. **Metadata**: Override application is tracked in enrichment metadata

## Best Practices

1. **Use `use_catalog: true`** when the catalog has authoritative data and user extraction is incorrect
2. **Use explicit values** when you need to specify a value that differs from both user extraction and catalog
3. **Validate overrides** by running the enrich phase and checking enriched output
4. **Document overrides** with comments explaining why the override is needed
5. **Review overrides periodically** to ensure they're still needed as extraction improves

## Differences from Extract Overrides

Enrichment overrides differ from extract overrides in several ways:

- **Scope**: Enrichment overrides affect enrichment fields (fiber, knot_size_mm, grind, etc.), not extracted product names
- **Structure**: Enrichment overrides use nested structure (field → enrichment_key → override_spec)
- **Options**: Enrichment overrides support both explicit values and `use_catalog` flags
- **Types**: Enrichment overrides support strings and floats

## Troubleshooting

### Override Not Applied

1. Check that month format is correct (YYYY-MM)
2. Verify comment ID matches exactly (case-sensitive)
3. Ensure field and enrichment_key are valid
4. Check that override file is in the correct location (`data/enrichment_overrides.yaml`)
5. Review enrich phase logs for override loading messages

### Override Applied Incorrectly

1. Verify override priority (explicit value > use_catalog > default)
2. Check for duplicate keys in YAML (last one wins)
3. Ensure value types match expected types
4. Review enriched output to see which source was used

## Related Documentation

- [Field Overrides](./field_overrides.md) - Extract phase overrides
- [Enrich Phase Specification](./enrich_phase_spec.md) - Enrich phase details
