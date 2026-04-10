---
description: "Backend development instructions for Python/FastAPI service. Use when: modifying Python code, API endpoints, database models, migrations, adapters, backend services, or backend tests."
applyTo:
  - "backend/**/*.py"
  - "backend/pyproject.toml"
  - "backend/Dockerfile"
---

# Backend Development Instructions

## Python Version Compatibility

- **Target Python version**: >= 3.10
- All code must remain compatible with Python 3.10 and newer versions
- Do not use Python features that require versions newer than 3.10 unless explicitly approved
- Test compatibility when using modern Python features

## Dependency Management

- **Explicit approval required** before adding new packages to `pyproject.toml`
- Dependencies are managed via `pyproject.toml` in the `[project.dependencies]` section
- When suggesting new dependencies, explicitly ask for approval and explain why the dependency is needed
- Prefer using existing dependencies when possible

## Testing Requirements

### Test Framework
- **Use only `unittest` module** from Python standard library
- Do not import pytest, nose, or other testing frameworks without explicit approval
- Additional testing libraries require approval

### Test Execution
- All tests must be discoverable and runnable with: `python -m unittest discover`
- Tests are located in `backend/tests/` directory
- Test files must follow the pattern `test_*.py`
- Test classes must inherit from `unittest.TestCase`

### Test Coverage
- **New modules** must include corresponding unit tests
- **New functions and methods** should be covered by tests
- Tests should verify both success and error cases
- Use descriptive test method names (e.g., `test_import_gtfs_with_valid_feed`)

### Modifying Existing Tests
- **Critical**: Only modify unit tests when the expected output of the tested method changes
- When refactoring code without changing behavior:
  - **Do NOT modify the tests** – they verify the contract remains intact
  - **Only modify the implementation** being tested
  - Tests serve as regression safeguards during refactoring
- Modify tests only when:
  - The method's public API changes (parameters, return type)
  - The expected behavior or output changes
  - Fixing a bug that the test should have caught

### Test Structure Example
```python
import unittest
from echogtfs.module import function_to_test

class TestModuleName(unittest.TestCase):
    def setUp(self):
        # Setup test fixtures
        pass
    
    def tearDown(self):
        # Cleanup after tests
        pass
    
    def test_function_success_case(self):
        result = function_to_test(valid_input)
        self.assertEqual(result, expected_output)
    
    def test_function_error_case(self):
        with self.assertRaises(ExpectedException):
            function_to_test(invalid_input)
```

## Adapter Development

### Adapter Immutability Rule
- **Critical**: When modifying adapter code, preserve the behavior of existing adapter implementations
- Each adapter represents a specific "dialect" of an external data source format
- Changes to the base adapter must not break existing implementations
- When fixing bugs or refactoring adapters:
  - Test that all existing adapter implementations still work correctly
  - Preserve the expected input/output behavior of each dialect
  - Do not change parsing logic specific to one dialect when working on another

### Adapter Structure
- All adapters inherit from the base adapter class
- Each adapter implements:
  - `CONFIG_SCHEMA`: Configuration field definitions
  - `_validate_config()`: Validation logic
  - `fetch()`: Retrieve external data
  - `transform()`: Convert to ServiceAlert format
  - `import_alerts()`: Save to database

## Code Style

### Language Requirements
- **All code must be written in English**
  - Variable names, function names, class names in English
  - Comments and docstrings in English
  - Error messages and log messages in English
  - Exception messages in English
- German or other languages are **only allowed** for user-facing text in the frontend via the localization system
- No German comments, no German variable names, no mixed-language code

### Project Conventions
- Use async/await for database operations (SQLAlchemy async)
- Type hints are used throughout the codebase
- Follow PEP 8 style guidelines
- Use meaningful variable and function names
- Keep functions focused and single-purpose

### Imports
- Group imports: standard library, third-party, local imports
- Use absolute imports from `echogtfs` package
- Avoid wildcard imports (`from module import *`)

### Error Handling
- Use appropriate exception types
- Log errors using the configured logger
- Provide meaningful error messages
- Handle database errors gracefully

## Database Migrations

- **Explicit approval required** before creating new database migrations
- Migrations are numbered sequentially following the pattern: `001.sql`, `002.sql`, etc.
- Each migration file contains raw SQL
- Migrations are applied automatically on startup
- **Migrations must be idempotent**: Running them multiple times should not cause errors or data corruption
  - Use `IF NOT EXISTS` for CREATE statements
  - Use `IF EXISTS` for DROP statements
  - Check for existing data before INSERT operations
- When approved to create a migration:
  - Follow the existing numbering and naming pattern
  - Test the migration on a clean database
  - Test running the migration multiple times to ensure idempotency

## API Development

### FastAPI Routers
- Each router handles a specific domain (alerts, auth, sources, etc.)
- Use Pydantic models for request/response validation
- Apply appropriate authentication decorators

### Response Models
- Define clear Pydantic schemas for all endpoints
- Use proper HTTP status codes
- Return meaningful error messages
- Document endpoints with docstrings

## Security

- Never commit secrets or credentials
- Use environment variables for configuration
- Password hashing uses bcrypt
- JWT tokens for authentication
- Rate limiting is configured via SlowAPI

## Common Patterns

### Database Sessions
```python
from echogtfs.database import SessionLocal

async with SessionLocal() as session:
    result = await session.execute(select(Model))
    # ... work with session
    await session.commit()
```

### Logging
```python
import logging

logger = logging.getLogger("uvicorn")
logger.info("Information message")
logger.error("Error message", exc_info=True)
```

## Before Committing

- Run tests: `python -m unittest discover`
- Ensure compatibility with Python >= 3.10
- Verify no new dependencies were added without approval
- Check that adapters still behave correctly if modified
