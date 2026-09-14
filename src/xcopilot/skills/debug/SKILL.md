---
name: debug
description: Debugging workflow for errors and issues
triggers: [bug, error, fix, debug]
compatible_agents: [xcopilot, claude-code, codex, cursor, windsurf]
version: 1.0.0
---
# Debug Skill

## Overview
Systematic debugging workflow for identifying and fixing errors.

## Prerequisites
- Access to error logs and stack traces
- Ability to reproduce the issue
- Development environment set up

## Steps

### 1. Understand the Problem
- [ ] Read the error message completely
- [ ] Identify the exact error type (syntax, runtime, logic)
- [ ] Note the file, line number, and context
- [ ] Check if the error is reproducible

### 2. Gather Information
- [ ] Read the full stack trace
- [ ] Check recent changes in the affected area
- [ ] Review related tests
- [ ] Check environment (dependencies, versions)

### 3. Isolate the Issue
- [ ] Create a minimal reproduction case
- [ ] Use binary search (git bisect) if regression
- [ ] Add logging/print statements at key points
- [ ] Use debugger breakpoints

### 4. Analyze Root Cause
- [ ] Identify the exact line causing the issue
- [ ] Understand why the code behaves incorrectly
- [ ] Check for similar patterns elsewhere
- [ ] Verify assumptions about data flow

### 5. Implement Fix
- [ ] Make minimal, targeted change
- [ ] Follow existing code patterns
- [ ] Add defensive checks if appropriate
- [ ] Update comments if behavior changes

### 6. Verify Fix
- [ ] Run existing tests to ensure no regression
- [ ] Test the specific error case
- [ ] Test edge cases
- [ ] Run full test suite

### 7. Document
- [ ] Add comment explaining the fix
- [ ] Update documentation if needed
- [ ] Consider adding a test case for the bug

## Examples
```bash
# Run specific test
pytest tests/ -k "test_name" -v

# Debug with pdb
python -m pdb script.py

# Check logs
tail -f logs/error.log
```

## Related Skills
- test
- code-review
- refactor

## Configuration
- Debug logging level in config
- Breakpoint persistence in IDE