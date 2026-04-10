---
name: create-adapter  
description: "Create a new data source adapter with complete boilerplate code, configuration, registration, and unit tests. Use this to scaffold a new adapter implementation following the project's adapter pattern."
---

# Create Data Source Adapter

This prompt helps you create a complete, production-ready adapter for importing service alerts from external data sources into EchoGTFS.

## Required Information

Please provide the following information about the new adapter:

1. **Adapter Name**: What is the name of the adapter? (e.g., "MyCustomFeed", "ApiService")
   - This will be used to generate the class name (e.g., MyCustomFeedAdapter)
   - Internally it will be registered with lowercase name (e.g., "mycustomfeed")

2. **Configuration Parameters**: What configuration parameters does this adapter need?
   For each parameter, specify:
   - **name**: Internal field name
   - **type**: Field type (text, url, password, number, select)
   - **label**: Translation key for the label (e.g., "adapter.myname.field.label")
   - **required**: Is this field required? (true/false)
   - **placeholder**: Translation key for placeholder text
   - **help_text**: Translation key for help text
   - **options**: (Only for select type) List of option values

   Example:
   - endpoint (url, required)
   - api_key (password, required)
   - timeout (number, optional)

3. **Dialect Support**: Does this adapter need to support multiple dialects/variants? (yes/no)
   If yes, provide dialect names (e.g., "variant_a", "variant_b")

4. **Documentation Details**:
   - **Purpose**: Brief description of what this adapter does (1-2 sentences)
   - **Dialect Descriptions** (if applicable): For each dialect, describe what makes it specific/different

   Note: Detailed documentation can be added manually after generation. The prompt will create a basic structure with placeholders.

## What This Prompt Will Create

### 1. Adapter Implementation
**File**: `backend/src/echogtfs/services/adapters/{adapter_name}.py`

The adapter class will:
- Inherit from `BaseAdapter`
- Define `CONFIG_SCHEMA` with the provided configuration parameters
- Implement `_validate_config()` for configuration validation
- Implement `fetch_alerts()` with NotImplementedError placeholder
- Include support for multiple dialects if requested
- Include proper docstrings and logging

**Important**: The `fetch_alerts()` method will contain NotImplementedError. You must implement the actual logic for:
- Fetching data from the external source
- Parsing the response format
- Transforming data to ServiceAlert structure

The adapter automatically inherits `sync_alerts()` from BaseAdapter, which handles:
- Comparing fetched alerts with database alerts
- Creating new alerts according to InvalidReferencePolicy
- Updating existing alerts (including relations, **EXCEPT is_active flag**)
- Deleting alerts that no longer exist in the source

### 2. Registration
The adapter will be registered in:
- `backend/src/echogtfs/services/adapters/__init__.py`
  - Added to imports
  - Added to `__all__` list
  - Added to `ADAPTER_REGISTRY` dict **at the end** (preserves display order)

**Critical**: Existing adapters and their order in ADAPTER_REGISTRY will NOT be modified.

### 3. Unit Tests
**File**: `backend/tests/adapters/test_{adapter_name}.py`

Test suite will include:
- Configuration validation tests (valid config, missing fields, invalid types)
- Test for each configuration parameter
- Config schema validation test
- Placeholder tests for fetch_alerts (to be implemented)
- If dialects: tests for dialect-specific behavior

**Critical**: Existing test files will NOT be modified.

### 4. Frontend Translation Keys
Translation keys for configuration fields will be added to:
- `frontend/js/languages.js`
  - German (de) and English (en) translations
  - Keys for labels, placeholders, and help texts

### 5. Documentation
**File**: `docs/manual/adapters.md`

Documentation will be added in the "Available Adapters" section following this structure:

```markdown
### N. {Adapter Name} Adapter (`{adapter_type}`)
- **Purpose:** {Brief description of what the adapter does}
- **Config options:**
  - `param1`: Description (required/optional)
  - `param2`: Description (required/optional)
  
**Available Dialects:** (if applicable)
- **`dialect1`**: Description of dialect1 specifics
- **`dialect2`**: Description of dialect2 specifics

{Dialect Name} Dialect Specifics: (if applicable)
- Specific behaviors
- Data extraction rules
- Special handling
```

The documentation will be:
- Written in **English only**
- Inserted before the "Adding/Editing Adapters" section
- Numbered sequentially after existing adapters
- Include placeholder descriptions that need to be filled with specific details

### 6. Required Manual Steps (Post-Generation)

After the adapter is created, you must:

1. **Implement fetch_alerts()**: Replace NotImplementedError with actual data fetching and transformation logic
2. **Add translations**: Review and update the auto-generated translation keys with proper text
3. **Review documentation**: Update the auto-generated documentation with specific details about:
   - Detailed purpose/use case description
   - External data format specifics
   - Dialect-specific behaviors (if applicable)
   - Any special considerations or limitations
4. **Test the adapter**: Run unit tests and add integration tests if needed
5. **Verify registration**: Check that the adapter appears in the frontend adapter selection

## Generation Rules

### Code Quality
- Follow PEP 8 style guidelines
- Use type hints throughout
- Include comprehensive docstrings
- Add logging statements for debugging
- **All code must be in English** (variable names, comments, docstrings, error messages)
- Only user-facing text in the frontend may be in other languages (via localization)

### Backward Compatibility
- **Do NOT modify** existing adapter files (base.py, gtfsrt.py, sirilite.py, sirisx.py)
- **Do NOT change** the order of existing adapters in ADAPTER_REGISTRY
- **Do NOT modify** existing unit test files
- Only add new code, never change existing implementations

### Testing Requirements
- All tests use `unittest` module only
- Tests must be runnable with `python -m unittest discover`
- Test class inherits from `unittest.TestCase`
- Each configuration parameter gets dedicated test cases

### Documentation Requirements
- Documentation must be written in **English only**
- Follow the existing format in `docs/manual/adapters.md`
- Insert new adapter documentation before the "Adding/Editing Adapters" section
- Include:
  - Numbered header with adapter name and type identifier
  - Purpose description
  - Configuration options (with required/optional markers)
  - Dialect sections (if applicable)
- Use placeholder text where specific implementation details are unknown
- Manual review and enhancement required after generation

### Alert Synchronization
The adapter uses the inherited `sync_alerts()` method which:
- **Creates** new alerts based on InvalidReferencePolicy settings
- **Updates** existing alerts and their relations (active_periods, translations, informed_entities)
- **Preserves** the `is_active` flag during updates (never modified by sync)
- **Deletes** alerts that no longer exist in the external source
- Applies data source mappings and enrichments
- Validates entity references against GTFS data

You typically don't need to implement sync logic yourself unless the adapter has special requirements.

## Example Usage

**Adapter Name**: `Transitland`

**Configuration Parameters**:
1. endpoint (url, required) - API endpoint URL
2. api_key (password, required) - Authentication key
3. feed_id (text, required) - Feed identifier
4. timeout (number, optional) - Request timeout in seconds

**Dialect Support**: No

**Documentation**:
- Purpose: "Import real-time service alerts from the Transitland API v2"

This would generate:
- `backend/src/echogtfs/services/adapters/transitland.py` with TransitlandAdapter class
- Registration in `__init__.py` as "transitland": TransitlandAdapter
- `backend/tests/adapters/test_transitland.py` with full test suite
- Translation keys in `frontend/js/languages.js`
- Documentation section in `docs/manual/adapters.md`

## Ready to Generate?

Once you provide the required information above, the adapter scaffold will be generated following all project conventions and constraints.
