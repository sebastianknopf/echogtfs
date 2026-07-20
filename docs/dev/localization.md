# Localization

## Overview

EchoGTFS implements a lightweight client-side i18n system with no external library dependencies. All user-visible strings are stored as translation keys in a central JavaScript file. The active language is determined at startup from user preference or backend configuration, and can be changed at runtime.

## Relevant Files

- `frontend/js/languages.js`: Defines `window.translations`, the global object containing all translation strings for all languages.
- `frontend/js/localization.js`: Defines the `i18n` module (IIFE, exposed as `window.i18n`). Implements `translate`, `setLanguage`, `getCurrentLanguage`, and `loadLanguageFromSettings`.
- `backend/src/echogtfs/routers/settings.py`: `GET /api/settings/app` endpoint that returns the backend-configured default language via the `app_language` key.

## Supported Languages

Two languages are supported:

- `de` (German): default language.
- `en` (English).

Language codes are the keys of the `window.translations` object. Adding a new language means adding a new top-level key to that object with all required translation strings.

## Module Load Order

`languages.js` must be loaded before `localization.js` in `index.html`, because `localization.js` reads `window.translations` at runtime. Both must be loaded before any other JavaScript module that calls `window.i18n()`.

## Translation Key Conventions

Keys are dot-separated namespaced strings. The first segment is the feature area. Examples:

| Key | Meaning |
|---|---|
| `login.title` | Title text on the login screen |
| `common.save` | Shared save button label |
| `nav.alerts` | Navigation item for the alerts section |
| `alerts.form.cause` | Label for the cause field in the alert form |
| `error.network` | User-facing network error message |

When adding a new key, place it in `languages.js` under the appropriate namespace comment block, and add translations for both `de` and `en`.

## How Translation Works

### Programmatic Use

```javascript
// Simple key lookup
const label = i18n.translate('common.save');

// With parameter interpolation
const msg = i18n.translate('alerts.count', { count: 5 });
// Template string in languages.js: 'alerts.count': '{count} Meldungen'
```

The `translate(key, params)` function:

1. Looks up `window.translations[currentLanguage][key]`.
2. If not found, logs a warning and returns the key itself (fail-visible).
3. Replaces `{paramName}` placeholders with values from `params`.

### Shorthand Alias

`core.js` exposes `window.i18n` as a shorthand for `i18n.translate`, so modules can call `window.i18n('key')` directly.

### HTML Declarative Use

HTML elements with a `data-i18n` attribute are automatically translated when the language is initialized or changed:

```html
<label data-i18n="login.username">Benutzername</label>
```

`initializeTranslations()` (called internally by `setLanguage`) queries all elements with `[data-i18n]` and sets their `textContent` to the resolved translation. Static fallback text inside the element is overwritten.

## Language Loading Priority

`loadLanguageFromSettings()` is called once during application initialization, before the login view is shown. It follows this priority order:

1. `localStorage` key `echogtfs_language`: user-explicit preference (survives page reload).
2. `GET /api/settings/app` response field `app_language`: backend-configured default.
3. Built-in default: `de`.

On a failed backend request the system silently falls back to the built-in default and still calls `initializeTranslations()`.

## Changing Language at Runtime

```javascript
// Change language without persisting
i18n.setLanguage('en');

// Change language and persist to localStorage
i18n.setLanguage('en', true);

// Clear persisted preference (revert to backend/default on next load)
i18n.clearUserLanguagePreference();
```

`setLanguage` validates that the target language key exists in `window.translations` before switching. An invalid code is silently ignored and a warning is logged.

## Backend Language Setting

The backend stores the configured application language in the `app_settings` table under the key `app_language`. The public endpoint `GET /api/settings/app` returns this and other non-sensitive settings. This value acts as the system default for users who have not set a personal preference.

## Adding a New Language

1. Open `frontend/js/languages.js`.
2. Add a new top-level key to `window.translations` (e.g., `fr: { ... }`).
3. Copy all existing keys from an existing language block and translate all values.
4. No other code changes are required; `setLanguage` and `loadLanguageFromSettings` are language-agnostic.

## Adding New Translation Keys

1. Identify the correct namespace for the new string.
2. Add the key-value pair to every language block in `languages.js`.
3. Use `i18n.translate('your.new.key')` in JavaScript or `data-i18n="your.new.key"` in HTML.
4. Never hardcode user-visible strings directly in HTML or JavaScript.
