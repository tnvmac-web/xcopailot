---
name: test
description: Run tests and verify functionality
triggers: [test, verify, check, pytest]
compatible_agents: [xcopilot, claude-code, codex, cursor, windsurf]
version: 1.0.0
---
# Test Skill

## Overview
Comprehensive testing workflow for verifying code functionality and quality.

## Prerequisites
- Test framework installed (pytest, jest, etc.)
- Test environment configured
- Test data available

## Steps

### 1. Test Planning
- [ ] Identify what needs testing (new features, bug fixes, regressions)
- [ ] Determine test types needed (unit, integration, e2e)
- [ ] Define test data requirements
- [ ] Set coverage targets

### 2. Unit Tests
- [ ] Test individual functions in isolation
- [ ] Mock external dependencies
- [ ] Test edge cases and boundary conditions
- [ ] Test error handling paths
- [ ] Achieve target coverage (>80%)

### 3. Integration Tests
- [ ] Test component interactions
- [ ] Test API endpoints
- [ ] Test database operations
- [ ] Test external service integrations

### 4. End-to-End Tests
- [ ] Test critical user flows
- [ ] Test across browsers (if web)
- [ ] Test on different environments
- [ ] Test performance benchmarks

### 5. Test Execution
- [ ] Run tests in CI/CD pipeline
- [ ] Run tests locally before commit
- [ ] Run tests in parallel for speed
- [ ] Generate coverage reports

### 6. Test Maintenance
- [ ] Remove flaky tests
- [ ] Update tests when behavior changes
- [ ] Keep test data current
- [ ] Refactor test code for maintainability

## Examples
```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html

# Run specific test
pytest tests/ -k "test_user_login" -v

# Run in parallel
pytest tests/ -n auto

# Watch mode
pytest-watch tests/
```

## Related Skills
- code-review
- debug
- deploy

## Configuration
- pytest.ini or pyproject.toml for pytest config
- Coverage thresholds in CI/CD
- Test fixtures in conftest.py