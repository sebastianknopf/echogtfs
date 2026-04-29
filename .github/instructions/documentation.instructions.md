---
description: "Documentation authoring instructions. Use when: creating or updating technical developer documentation (docs/dev) or user-facing manual documentation (docs/manual)."
applyTo:
  - "docs/**/*.md"
---

# Documentation Instructions

## General Rules

- Write all documentation in English.
- Use plain descriptive text only. Do not use icons, emoji, or decorative characters.
- Keep sentences concise and direct. Prefer active voice.
- Do not document hypothetical or future features. Only document what the code currently does.
- Verify claims against the actual source code before writing. Do not infer behavior that is not evident from the code.
- Do not duplicate information across files. If a concept is already explained in another document, reference that document instead of repeating the explanation.
- Every new document must be added to the README index of its directory.

## Single Source of Truth

Any element of the system that can change over time during development must be documented in exactly one place. This applies in particular to enumerable, extensible, or configurable things such as: adapter types, user roles, supported languages, configuration keys, migration versions, API endpoints, and database tables.

- Identify the single authoritative document for each such element before writing.
- All other documents that mention the element must reference that authoritative document instead of repeating or paraphrasing its content.
- When the implementation changes (e.g., a new adapter is added), update only the authoritative document. Do not update any other document that merely references it.
- If no authoritative document exists yet for an element, create it or designate the most appropriate existing document as the authority, then update all references to point there.

## Developer Documentation (docs/dev)

Developer documentation is intended for engineers and AI agents that need to understand, modify, or extend the codebase. It must be written at a technical level sufficient to act on without needing to read the source code first.

### Scope

Each document in `docs/dev` covers a single technical concern. Before creating a new file, check whether the topic fits within an existing document. When a genuinely new technical concern arises (a new subsystem or a new cross-cutting pattern), create a new focused file rather than expanding an existing one. Read the `docs/dev/README.md` index to discover existing documents before writing.

### Content Requirements

- Always name the relevant source files at the top of the document under a "Relevant Files" section.
- Describe the execution flow or data flow in sequential steps where applicable.
- For configuration values, list them in a table with the variable name, default value, and meaning.
- For patterns that repeat across the codebase, explain the pattern once and give concrete examples from the actual source files.
- When documenting a component or system that has multiple layers, document each layer separately and explain how they interact.
- Do not add introductory or closing paragraphs that restate the document title.

### Accuracy Requirements

- Always read the relevant source files directly before writing or updating a document. Do not rely on other documentation files as a source of truth for technical facts.
- When documenting startup behavior, read the application entry point to verify the actual call sequence.
- When documenting scheduled jobs, read both the startup call site and the service function to determine where configuration is actually read from.
- When documenting roles and permissions, read the security module and every router that declares a permission dependency to verify correctness.
- When documenting the data model, read the ORM model definitions directly to ensure all tables and their columns are accurate and complete.

## User Documentation (docs/manual)

User documentation is intended for end users who operate the application through its web interface. It must not contain implementation details, source code references, or database internals.

### Scope

Each file in `docs/manual` covers a user-facing workflow or feature area. Before creating a new file, check whether the topic fits within an existing document by reading `docs/manual/README.md`. Create a new file only for a genuinely distinct workflow or feature area.

### Content Requirements

- Address the reader directly using second-person ("you").
- Describe UI interactions in terms of what the user sees and clicks, not what happens in the backend.
- Describe configuration fields by their UI label, not by their environment variable or database column name. Reference environment variables only where deployment configuration is explicitly the topic.
- Use numbered lists for step-by-step procedures.
- Use unordered lists for sets of options or feature descriptions where order does not matter.
- Include a brief introductory sentence at the top of each section that states what the section enables the user to do.

### Accuracy Requirements

- Verify field names and option labels against the actual frontend translation strings before writing. Use the English translations as the reference.
- Do not document backend-only concepts such as tokens, database tables, or class names.
- When a feature has role restrictions, state this in plain language without referencing technical role identifiers.
