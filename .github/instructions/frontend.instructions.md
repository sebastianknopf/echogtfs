---
description: "Frontend development instructions for Vanilla JavaScript web interface. Use when: modifying HTML, CSS, JavaScript, frontend localization, or UI components."
applyTo:
  - "frontend/**/*.js"
  - "frontend/**/*.html"
  - "frontend/**/*.css"
  - "frontend/nginx.conf"
---

# Frontend Development Instructions

## Framework Restrictions

- **Vanilla JavaScript only** – no frameworks allowed
- Do not use React, Vue, Angular, Svelte, or any other JavaScript framework
- Do not suggest adding frameworks or build tools
- Keep code simple, functional, and framework-free
- Use modern JavaScript features (ES6+) that work in current browsers

## Code Philosophy

### Simplicity First
- Write lean, readable, and maintainable code
- Avoid over-engineering solutions
- Prefer simple solutions over complex abstractions
- Keep bundle size minimal (no external dependencies)

### Refactoring
- Refactoring is allowed when it improves the overall solution
- Consolidate duplicate code into reusable functions
- Improve code organization if it enhances clarity
- Maintain backward compatibility with existing features

### Code Reusability
- **Reuse existing code** whenever it makes sense
- When creating reusable functionality, extract it into a generic module
- Avoid duplicating logic across different modules
- Generic utility functions should be placed in appropriate shared modules
- Document reusable functions clearly for future use

## Technology Stack

### Allowed Technologies
- **HTML5**: Semantic markup, modern HTML features
- **CSS3**: Flexbox, Grid, custom properties, animations
- **JavaScript**: ES6+ (modules, arrow functions, async/await, classes, etc.)
- **Web APIs**: Fetch, LocalStorage, DOM manipulation, etc.

### Module System
- JavaScript files are organized as ES6 modules
- Each module uses the revealing module pattern or exports
- **All modules must be properly included in the HTML file** in correct dependency order
- Core modules (localization, core utilities) must load before domain-specific modules
- When creating new modules, ensure they are added to the HTML with proper sequencing
- Verify module dependencies are satisfied by load order

## Localization (i18n)

### Critical Requirement
- **All user-facing text must be localized**
- Never hardcode user-visible strings directly in HTML or JavaScript
- Always use localization keys from the translation system

### Using Localization

#### Check for Existing Keys
Before creating new localization keys:
1. Check the languages module for existing translations
2. Reuse existing keys when applicable
3. Only create new keys if no suitable key exists

#### Adding New Translations
When creating new user-facing text:

```javascript
// In your JavaScript module:
const message = i18n.translate('your.new.key');

// Add translations to the languages module:
translations: {
  de: {
    'your.new.key': 'Deutscher Text',
    // ... other German translations
  },
  en: {
    'your.new.key': 'English text',
    // ... other English translations
  }
}
```

#### HTML Templates
```javascript
// Set localized text in DOM elements
element.textContent = i18n.translate('alerts.title');
element.setAttribute('placeholder', i18n.translate('form.search'));
```

#### String Interpolation
```javascript
// Use parameters for dynamic values
const text = i18n.translate('messages.greeting', { name: userName });
// In translations: 'messages.greeting': 'Hello, {name}!'
```

### Translation Key Naming
- Use dot-separated namespaces: `section.component.label`
- Group related translations together
- Examples:
  - `alerts.title`, `alerts.create`, `alerts.delete`
  - `form.submit`, `form.cancel`, `form.required`
  - `errors.network`, `errors.validation`

## Code Organization

### Module Structure
```javascript
// frontend/js/module-name.js
const ModuleName = (() => {
  // Private variables and functions
  let _privateVar = null;
  
  function _privateFunction() {
    // Internal implementation
  }
  
  // Public API
  function publicFunction() {
    // Exposed functionality
  }
  
  function init() {
    // Module initialization
  }
  
  // Reveal public interface
  return {
    init: init,
    publicFunction: publicFunction
  };
})();
```

### File Organization
- Core module: API communication, shared utilities
- Localization module: i18n system
- Languages module: Translation strings
- Main module: Application initialization
- Domain-specific modules for different features (alerts, sources, accounts, etc.)

## API Integration

### Using the Core Module
```javascript
// GET request
const data = await Core.apiGet('/api/endpoint');

// POST request
const result = await Core.apiPost('/api/endpoint', {
  field: 'value'
});

// Error handling
try {
  const data = await Core.apiGet('/api/endpoint');
} catch (error) {
  Core.showError(i18n.translate('errors.network'));
}
```

### Authentication
- JWT tokens are managed by the core module
- Tokens stored in LocalStorage
- Automatic token refresh on API calls
- Login/logout handled by authentication module

### Authorization
- **Protected API calls require proper authorization**
- Non-public API endpoints must only be called when user is authenticated
- User roles are hard-coded as: **Admin**, **Poweruser**, **User**
- Verify user permissions before making protected API calls
- Handle authorization errors gracefully (401/403 responses)
- Do not expose admin-only functionality to regular users in the UI

## UI/UX Best Practices

### User Feedback
- Show loading indicators for async operations
- Display success messages for user actions
- Show clear error messages on failures
- Use localized messages throughout

### Forms
- Validate input on the client side
- Show validation errors clearly
- Disable submit buttons during processing
- Reset forms after successful submission

### Accessibility
- Use semantic HTML elements
- Provide appropriate ARIA labels when needed
- Ensure keyboard navigation works
- Maintain good color contrast

## CSS Guidelines

### Naming Conventions
- Use descriptive class names
- Keep specificity low
- Avoid deep nesting
- Use CSS custom properties for theming

### Organization
- Group related styles together
- Comment major sections
- Keep selectors simple
- Avoid !important unless absolutely necessary

### Responsive Design
- Mobile-first approach when applicable
- Use relative units (rem, em, %) over fixed pixels
- Test layouts at different viewport sizes
- CSS Grid and Flexbox for layouts

## Common Patterns

### Creating DOM Elements
```javascript
function createElement(tag, className, textContent) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (textContent) element.textContent = textContent;
  return element;
}
```

### Event Handling
```javascript
// Event delegation for dynamic content
container.addEventListener('click', (e) => {
  if (e.target.matches('.button-class')) {
    handleClick(e.target);
  }
});
```

### Async Data Loading
```javascript
async function loadData() {
  try {
    const data = await Core.apiGet('/api/data');
    renderData(data);
  } catch (error) {
    Core.showError(i18n.translate('errors.load_failed'));
  }
}
```

## Before Committing

- Verify all user-facing text uses localization
- Check that new localization keys exist in BOTH languages (de, en)
- Test functionality in the browser
- Ensure no framework dependencies were added
- Validate HTML and check console for JavaScript errors
- Verify responsive layout works at different screen sizes
