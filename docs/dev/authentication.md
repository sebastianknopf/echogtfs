# Authentication and Authorization

## Overview

EchoGTFS uses JWT Bearer tokens for all authenticated API endpoints. Tokens are issued via an OAuth2 password-flow endpoint. A sliding session mechanism automatically extends token lifetime with each successful authenticated request.

## Relevant Files

- `backend/src/echogtfs/security.py`: Password hashing, JWT creation, and FastAPI dependency functions.
- `backend/src/echogtfs/routers/auth.py`: Login endpoint.
- `backend/src/echogtfs/main.py`: `SlidingTokenMiddleware` registration.
- `backend/src/echogtfs/config.py`: JWT configuration values.
- `frontend/js/core.js`: API client; token storage and injection, sliding token update, 401 handling.

## Configuration

All JWT parameters are set via environment variables:

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | (required, no default) | HMAC signing key for JWTs. Must be set explicitly; startup fails otherwise. |
| `ALGORITHM` | `HS256` | JWT signing algorithm. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Initial token expiry in minutes. |
| `LOGIN_RATE_LIMIT` | `10/minute` | Rate limit applied to the login endpoint. |

## Token Lifecycle

### Issuance

`POST /api/auth/token` accepts an `application/x-www-form-urlencoded` body with `username` and `password` fields (standard OAuth2 password flow). On success it returns:

```json
{ "access_token": "<jwt>", "token_type": "bearer" }
```

The endpoint is rate-limited by `slowapi` using the `LOGIN_RATE_LIMIT` setting.

### Signing and Claims

Tokens are created by `create_access_token(subject)` in `security.py`. The JWT payload contains:

- `sub`: the username string.
- `exp`: expiry timestamp (UTC).

Tokens are signed with HMAC-SHA256 (or the configured algorithm) using `SECRET_KEY`.

### Validation

`get_current_user` is a FastAPI dependency that:

1. Extracts the Bearer token from the `Authorization` header via `OAuth2PasswordBearer`.
2. Decodes and verifies the token with `jwt.decode`.
3. Reads the `sub` claim and loads the corresponding `User` row from the database.
4. Stores the user object in `request.state.user` for use by `SlidingTokenMiddleware`.
5. Raises `HTTP 401` if the token is missing, malformed, expired, or refers to a non-existent user.

### Sliding Session

`SlidingTokenMiddleware` is a Starlette `BaseHTTPMiddleware` registered in `main.py`. After every successful (2xx) authenticated response it:

1. Reads `request.state.user` (set by `get_current_user`).
2. Calls `create_access_token(user.username)` to create a fresh token with a new expiry.
3. Attaches the new token as the `X-New-Token` response header.

The frontend API client in `core.js` reads this header on every response and overwrites `localStorage['auth-token']` with the new value. This means a session stays alive as long as the user is active; it expires only after `ACCESS_TOKEN_EXPIRE_MINUTES` minutes of complete inactivity.

### Token Storage on the Frontend

The JWT is stored in `localStorage` under the key `auth-token`. The current user object (username, roles) is cached separately under `current-user`. On a 401 response the API client removes both keys and calls `window.location.reload()` to force the login view.

## Password Hashing

Passwords are hashed with bcrypt via the `hash_password(password)` function. Verification is done with `verify_password(plain, hashed)`. Both functions are in `security.py`.

## Role Model

The `User` model has three boolean flag columns that control access:

| Flag | Column | Description |
|---|---|---|
| Active | `is_active` | Account must be active to authenticate. Inactive accounts receive `HTTP 400`. |
| Superuser | `is_superuser` | Full administrative access. Can manage users, all settings, and all resources. |
| Technical contact | `is_technical_contact` | Intermediate role. Can manage data sources and settings alongside superusers. |

## FastAPI Dependency Aliases

`security.py` exports three type aliases that route handlers use as annotated dependencies:

| Alias | Resolved by | Minimum required role |
|---|---|---|
| `CurrentUser` | `get_current_active_user` | Any active authenticated user |
| `CurrentSuperuser` | `get_current_superuser` | `is_superuser = True` |
| `CurrentPoweruser` | `get_current_poweruser_or_admin` | `is_technical_contact = True` or `is_superuser = True` |

Example usage in a router:

```python
from echogtfs.security import CurrentSuperuser

@router.delete("/{user_id}")
async def delete_user(user_id: int, current_user: CurrentSuperuser, db: _DB):
    ...
```

## GTFS-RT Endpoint Authentication

The GTFS-RT output endpoint (`/api/realtime/feed`) uses a separate optional Basic Auth mechanism, not the JWT system. If both `gtfs_rt_username` and `gtfs_rt_password` are present in the `app_settings` table, the endpoint requires an `Authorization: Basic` header. This allows consumer applications (e.g., journey planners) to access the feed without needing a user account.

## First Superuser Bootstrap

If the `users` table is empty at startup, `main.py` creates one user from the environment variables `FIRST_SUPERUSER`, `FIRST_SUPERUSER_EMAIL`, and `FIRST_SUPERUSER_PASSWORD`. This user is created with `is_superuser=True` and `is_active=True`. The password is bcrypt-hashed before storage.
