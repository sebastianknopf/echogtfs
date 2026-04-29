# Material Design Implementation

## Overview

EchoGTFS uses a custom, handcrafted implementation of Material Design 3 (MD3) principles. There is no Material Web Components library or any other external UI dependency. All styling is contained in `frontend/css/app.css`. Behavior such as ripple effects is implemented in plain JavaScript within `frontend/js/core.js`.

## Relevant Files

- `frontend/css/app.css`: All styles, design tokens as CSS custom properties, and every component class.
- `frontend/js/core.js`: JavaScript behavior for ripple effects, view transitions, and dynamic theme helpers.
- `frontend/index.html`: Markup structure that uses the CSS component classes.

## Design Tokens

All visual constants are defined as CSS custom properties on `:root`. They are grouped by category:

### Color

| Token | Value | Usage |
|---|---|---|
| `--md-primary` | `#008c99` (teal) | Top app bar, focus rings, active field borders, links |
| `--md-primary-dark` | `#006870` | Primary hover state |
| `--md-primary-light` | `#4dbecb` | Lighter primary accents |
| `--md-on-primary` | `#ffffff` | Text and icons on primary surfaces |
| `--md-primary-container` | `#cef5f8` | Primary-tinted containers |
| `--md-secondary` | `#99cc04` (lime) | Action buttons (filled, tonal, outlined, text) |
| `--md-secondary-dark` | `#7aaa00` | Secondary hover state |
| `--md-on-secondary` | `#1d2700` | Text on secondary buttons |
| `--md-secondary-container` | `#d4ee7f` | Tonal button and hover backgrounds |
| `--md-background` | `#f2f8f8` | Page background |
| `--md-surface` | `#ffffff` | Card and dialog backgrounds |
| `--md-surface-variant` | `#dce8ea` | Dividers, spinner track |
| `--md-error` | `#b3261e` | Error states, danger buttons |
| `--md-on-error` | `#ffffff` | Text on error surfaces |
| `--md-on-surface` | `rgba(0,0,0,.87)` | Primary body text |
| `--md-on-surface-medium` | `rgba(0,0,0,.60)` | Secondary text, placeholder labels |
| `--md-on-surface-disabled` | `rgba(0,0,0,.38)` | Disabled text |
| `--md-outline` | `rgba(0,0,0,.38)` | Default input border |
| `--md-outline-variant` | `rgba(0,0,0,.12)` | Subtle dividers |

### Elevation (Box Shadows)

| Token | Usage |
|---|---|
| `--md-elev-1` | Resting card and filled button shadow |
| `--md-elev-2` | Hovered card, top app bar |
| `--md-elev-3` | Dialogs |
| `--md-elev-4` | Floating action surfaces |

### Shape (Border Radius)

| Token | Value |
|---|---|
| `--md-shape-xs` | `4px` |
| `--md-shape-s` | `8px` |
| `--md-shape-m` | `12px` |
| `--md-shape-l` | `16px` |
| `--md-shape-xl` | `28px` |

Buttons use a pill shape (`border-radius: 20px`) per MD3 conventions. Cards use `--md-shape-m`.

### Motion

| Token | Value |
|---|---|
| `--md-easing` | `cubic-bezier(.4, 0, .2, 1)` (standard MD3 easing) |
| `--md-transition` | `.2s cubic-bezier(.4, 0, .2, 1)` |

## Component Classes

### Buttons

All buttons use the `.md-btn` base class combined with a modifier:

| Class | Style | Usage |
|---|---|---|
| `.md-btn--filled` | Lime secondary background | Primary actions |
| `.md-btn--tonal` | Secondary container background | Secondary actions |
| `.md-btn--outlined` | Transparent with secondary border | Tertiary actions |
| `.md-btn--text` | Transparent, secondary text color | Low-emphasis actions |
| `.md-btn--danger` | Error red background | Destructive actions |
| `.md-btn--full` | `width: 100%` modifier | Full-width buttons (e.g., login form) |

Disabled state is handled purely by CSS: `.md-btn:disabled` overrides color and shadow.

### Ripple Effect

Any element with the `data-ripple` attribute receives a programmatic ripple on click. The JavaScript in `core.js` listens for `pointerdown` events on `[data-ripple]` elements, creates an absolutely positioned `.ripple` span at the click coordinates, and removes it after the animation completes. The `.ripple` class is defined in CSS with a scale-and-fade `@keyframes ripple-out` animation.

### Text Fields (Outlined)

Text fields follow the MD3 outlined field pattern with a floating label:

```html
<div class="md-field" id="field-username">
  <input class="md-field__input" type="text" placeholder=" " />
  <label class="md-field__label" for="username">Label</label>
</div>
```

The label floats above the input border when the field is focused or has a value (using `:focus` and `:not(:placeholder-shown)` CSS selectors). A `placeholder=" "` (single space) is required to trigger `:not(:placeholder-shown)` correctly.

For `<select>` elements, which do not support `:placeholder-shown`, the JavaScript must add the class `md-field--has-value` to the wrapper `.md-field` when a value is selected.

Modifier `.md-field--inline` produces a compact field for use in panel headers and filter bars.

Error state is toggled by adding `.is-error` to the wrapper `.md-field`. This changes the border and label to `--md-error`.

### Cards

`.md-card` provides a white surface with `--md-shape-m` border radius and `--md-elev-1` shadow. Use it for self-contained content sections.

### Top App Bar

`.top-app-bar` is a sticky 64-pixel tall bar with primary color background. It contains `.top-app-bar__title` (flex-grow title text) and `.top-app-bar__section` (right-aligned action groups). Icon buttons within the bar use `.md-icon-btn`.

### Icon Buttons

`.md-icon-btn` is a 40x40 circular button with transparent background and `--md-on-primary` text color for use on the primary-colored top app bar. It supports the ripple effect.

### Views and Transitions

Each functional section of the SPA is a `div.view[data-view="name"]`. Views default to `display: none`. The active view receives the `.is-active` class, which sets `display: flex; flex-direction: column; min-height: 100vh` and plays a `fade-up` entrance animation (opacity + translateY, 220 ms).

View switching is managed in JavaScript; only one view has `.is-active` at a time.

### Loading Screen

`.loading-screen` is a fixed full-viewport overlay with `z-index: 9999`. It hides when `.is-hidden` is added, which applies an opacity fade-out transition. The spinner inside uses the CSS `spin` keyframe animation.

### Toast (Snackbar)

`.toast` is the snackbar element positioned at the bottom of the screen. JavaScript adds `.is-visible` to show it and removes it after a timeout. Variants `.toast--error` and `.toast--success` apply error and success colors.

### Dialogs

`.md-dialog` is an absolutely centered container with `--md-elev-3` shadow and `--md-shape-l` border radius. A `.md-dialog__overlay` backdrop sits behind it. JavaScript toggles `.is-open` on both elements to show or hide.

## Typography

The font stack is `Roboto, 'Segoe UI', system-ui, -apple-system, sans-serif`. No web font is loaded; the system font is used as fallback. Font sizes and weights follow MD3 type scale guidelines but are specified inline per component rather than via a separate type-scale token system.

## Accessibility Conventions

- All icon-only buttons include `aria-label` attributes.
- Form inputs use explicit `<label for>` associations.
- Dynamic content regions use `aria-live` and `role="status"` or `role="alert"` as appropriate.
- Focus-visible styles use `outline: 2px solid` for keyboard navigability without affecting mouse users.
- The loading screen uses `aria-live="polite"` and `aria-label`.
