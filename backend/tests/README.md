# echogtfs Test Suite

Comprehensive unit tests for the echogtfs project using Python's standard library `unittest` framework.

## Overview

The test suite covers the following components:

- **Adapter Tests** (`tests/adapters/`):
  - `test_base.py` - BaseAdapter abstract class
  - `test_gtfsrt.py` - GTFS-Realtime Adapter
  - `test_sirilite.py` - SIRI-Lite Adapter (Swiss Dialect)
  - `test_sirisx.py` - SIRI-SX Adapter

- **Security Tests** (`tests/test_security.py`):
  - Password Hashing (bcrypt)
  - Password Verification
  - JWT Token Creation and Validation

- **Test Helpers** (`tests/helpers.py`):
  - Mock objects for Database Sessions
  - Mock HTTP Responses
  - Fixture generators for test data

## Installation and Setup

### 1. Activate Project-Level Virtual Environment

**Important:** All tests must be run within the project-level virtual environment to avoid global package installations.

```powershell
# Activate the virtual environment (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# Or for cmd
.\venv\Scripts\activate.bat
```

### 2. Install Dependencies

```powershell
# Install backend dependencies in editable mode
pip install -e backend

# All required test dependencies are already included in pyproject.toml
```

### 3. Test Configuration

The tests automatically use test configuration values defined in `tests/test_config.py`. These are set before importing echogtfs modules, so no `.env` file or manual environment variables are required.

**Important:** The test configuration contains a test `SECRET_KEY` that should **ONLY** be used for testing, never in production!

## Running Tests

**Prerequisites:** Ensure the project-level virtual environment is activated before running tests.

### Run All Tests

```powershell
# Navigate to backend directory (with venv activated)
cd backend

# Test Discovery - automatically finds all tests
python -m unittest discover
```

### Verbose Output

```powershell
# Detailed output for all tests
python -m unittest discover -v
```

## Test Coverage

To measure test coverage, use `coverage.py`:

```powershell
# Install coverage in project venv
pip install coverage

# Run tests with coverage
cd backend
coverage run -m unittest discover

# Display coverage report
coverage report

# Generate HTML coverage report
coverage html
# Open htmlcov/index.html in browser
```