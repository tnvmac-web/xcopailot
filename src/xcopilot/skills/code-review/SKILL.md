---
name: code-review
description: Review code for bugs, security, best practices
triggers: [review, code-review, PR review]
compatible_agents: [xcopilot, claude-code, codex, cursor, windsurf]
version: 1.0.0
---
# Code Review Skill

## Overview
Comprehensive code review checklist for security, quality, and maintainability.

## Prerequisites
- Access to the codebase
- Understanding of the project's coding standards
- Permission to view and comment on changes

## Steps

### 1. Security Review
- [ ] No hardcoded credentials, API keys, or secrets
- [ ] Input validation on all user-facing endpoints
- [ ] No SQL injection vulnerabilities (parameterized queries)
- [ ] No XSS vulnerabilities (proper output encoding)
- [ ] Authentication and authorization checks on protected routes
- [ ] Secure password handling (bcrypt/argon2, not plaintext)
- [ ] No sensitive data in logs
- [ ] Dependencies checked for known vulnerabilities (npm audit, pip-audit)

### 2. Code Quality
- [ ] Clear, descriptive variable and function names
- [ ] No code duplication (DRY principle)
- [ ] Functions are small and focused (single responsibility)
- [ ] Proper error handling with meaningful messages
- [ ] Type hints present on all public functions
- [ ] Docstrings for public APIs
- [ ] Consistent code style (follow project conventions)

### 3. Testing
- [ ] Unit tests cover new functionality
- [ ] Edge cases considered and tested
- [ ] Integration tests for API endpoints
- [ ] Test coverage meets project threshold (>80%)
- [ ] Tests are deterministic and fast

### 4. Performance
- [ ] No N+1 query problems
- [ ] Appropriate caching strategies
- [ ] Database indexes on frequently queried columns
- [ ] No memory leaks or resource leaks

### 5. Architecture
- [ ] Changes align with project architecture
- [ ] Proper separation of concerns
- [ ] No circular dependencies
- [ ] Configuration externalized (environment variables)

## Examples
```bash
# Run security audit
pip-audit
npm audit

# Run tests with coverage
pytest tests/ --cov=src --cov-fail-under=80

# Run linters
ruff check src/
mypy src/
```

## Related Skills
- debug
- test
- refactor

## Configuration
- Configure severity thresholds in `.github/workflows/ci-cd.yml`
- Customize rules in `ruff.toml` or `pyproject.toml`