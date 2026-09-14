---
name: refactor
description: Code cleanup and improvement
triggers: [refactor, clean, improve, optimize, simplify]
compatible_agents: [xcopilot, claude-code, codex, cursor, windsurf]
version: 1.0.0
---
# Refactor Skill

## Overview
Systematic code improvement workflow for cleaning up, optimizing, and modernizing code without changing behavior.

## Prerequisites
- Comprehensive test suite (to verify behavior preservation)
- Version control (git)
- Understanding of the codebase

## Steps

### 1. Identify Refactoring Opportunities
- [ ] Run static analysis (ruff, mypy, sonar)
- [ ] Identify code smells (duplication, long methods, large classes)
- [ ] Check for deprecated patterns
- [ ] Review technical debt markers (TODO, FIXME, HACK)

### 2. Prioritize
- [ ] High impact, low risk first
- [ ] Focus on frequently changed code
- [ ] Address security/performance issues first
- [ ] Consider team familiarity with area

### 3. Prepare
- [ ] Ensure tests pass before starting
- [ ] Create baseline performance metrics
- [ ] Create git branch for refactoring
- [ ] Document current behavior

### 4. Refactor Incrementally
- [ ] **Extract Method** - Break large functions
- [ ] **Extract Class** - Separate responsibilities
- [ ] **Rename** - Improve naming clarity
- [ ] **Inline** - Remove unnecessary abstractions
- [ ] **Move Method/Field** - Better organization
- [ ] **Replace Conditional with Polymorphism** - Reduce complexity
- [ ] **Introduce Parameter Object** - Reduce parameter lists
- [ ] **Remove Dead Code** - Delete unused code
- [ ] **Replace Magic Numbers** - Use named constants

### 5. Verify Each Step
- [ ] Run tests after each small change
- [ ] Commit frequently with clear messages
- [ ] Run static analysis after each commit
- [ ] Check performance hasn't regressed

### 6. Final Verification
- [ ] Full test suite passes
- [ ] Static analysis clean
- [ ] Performance benchmarks met
- [ ] Code review completed
- [ ] Documentation updated

## Examples
```bash
# Run linters
ruff check src/ --fix
mypy src/

# Run tests
pytest tests/ -v

# Performance check
pytest tests/ --benchmark-only

# Git workflow
git checkout -b refactor/user-service
# ... make changes ...
git commit -m "refactor: extract user validation logic"
git push origin refactor/user-service
```

## Common Patterns

### Before (Long Method)
```python
def process_user(user):
    # 50 lines of validation, transformation, saving
```

### After (Extracted Methods)
```python
def process_user(user):
    validate_user(user)
    transformed = transform_user(user)
    save_user(transformed)
    notify_user(transformed)
```

## Related Skills
- code-review
- test
- debug

## Configuration
- Ruff rules in pyproject.toml
- Mypy strict mode in pyproject.toml
- Pre-commit hooks for automatic formatting