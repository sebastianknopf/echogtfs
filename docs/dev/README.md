# EchoGTFS Developer Documentation

This directory contains technical documentation for the EchoGTFS system, intended for developers and AI agents that need to understand, extend, or maintain the codebase.

## Contents

- [architecture.md](architecture.md): Overall system architecture, component responsibilities, data flow, and technology stack.
- [authentication.md](authentication.md): Authentication and authorization model, JWT lifecycle, sliding sessions, and role system.
- [localization.md](localization.md): Frontend i18n system, translation key conventions, language loading, and adding new languages.
- [material-design.md](material-design.md): Custom Material Design 3 implementation in CSS and JavaScript, design tokens, component patterns, and UI conventions.

## Context for AI Agents

EchoGTFS is a self-hosted, containerized web application. The backend is a Python/FastAPI service; the frontend is a Vanilla JavaScript single-page application served by NGINX. There are no frontend build steps. All backend logic lives under `backend/src/echogtfs/`. All frontend logic lives under `frontend/`.

When making changes, consult the instruction files at `.github/instructions/backend.instructions.md` and `.github/instructions/frontend.instructions.md` first.
