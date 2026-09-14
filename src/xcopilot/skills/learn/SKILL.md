---
name: learn
description: Understand new codebase or technology
triggers: [learn, study, understand, explore, onboard]
compatible_agents: [xcopilot, claude-code, codex, cursor, windsurf]
version: 1.0.0
---
# Learn Skill

## Overview
Systematic approach to understanding new codebases, technologies, or concepts.

## Prerequisites
- Access to the codebase or documentation
- Basic understanding of the domain
- Development environment set up

## Steps

### 1. Initial Exploration
- [ ] Read README and documentation
- [ ] Understand project structure and architecture
- [ ] Identify main entry points
- [ ] Review dependency list

### 2. Codebase Walkthrough
- [ ] Start from entry points (main, API routes, CLI)
- [ ] Follow key user flows through the code
- [ ] Understand data models and schemas
- [ ] Identify core modules and their responsibilities

### 3. Deep Dive
- [ ] Pick a specific feature to understand deeply
- [ ] Trace through the code with debugger
- [ ] Run tests to see expected behavior
- [ ] Modify code and observe effects

### 4. Technology Learning
- [ ] Read official documentation
- [ ] Build small prototype
- [ ] Experiment with key APIs
- [ ] Compare with alternatives

### 5. Knowledge Consolidation
- [ ] Create mental model diagram
- [ ] Write summary notes
- [ ] Create cheat sheet for key patterns
- [ ] Share knowledge with team

## Examples
```bash
# Explore codebase
tree -L 3 src/
grep -r "class.*Controller" src/

# Run tests to understand behavior
pytest tests/ -v --tb=short

# Debug specific flow
python -m pdb -c continue script.py
```

## Related Skills
- code-review
- debug
- refactor

## Configuration
- IDE bookmarks for key files
- Debug configurations for common scenarios
- Documentation links in project wiki