---
name: deploy
description: Build and deploy applications
triggers: [deploy, ship, release, publish]
compatible_agents: [xcopilot, claude-code, codex, cursor, windsurf]
version: 1.0.0
---
# Deploy Skill

## Overview
Complete deployment workflow for building, testing, and releasing applications.

## Prerequisites
- CI/CD pipeline configured
- Access to deployment targets
- Version tagging strategy defined

## Steps

### 1. Pre-deployment Checks
- [ ] All tests pass (unit, integration, e2e)
- [ ] Code coverage meets threshold
- [ ] Linting and type checking pass
- [ ] Security audit passes
- [ ] Dependencies audited for vulnerabilities

### 2. Version Management
- [ ] Update version number (semantic versioning)
- [ ] Update CHANGELOG.md
- [ ] Create git tag (e.g., `v1.2.3`)
- [ ] Push tag to remote

### 3. Build
- [ ] Clean build artifacts
- [ ] Install dependencies
- [ ] Run build process
- [ ] Verify build artifacts
- [ ] Run smoke tests on build

### 4. Staging Deployment
- [ ] Deploy to staging environment
- [ ] Run staging smoke tests
- [ ] Verify critical user flows
- [ ] Performance baseline check
- [ ] Stakeholder approval (if required)

### 5. Production Deployment
- [ ] Schedule deployment window
- [ ] Notify stakeholders
- [ ] Deploy to production
- [ ] Run production smoke tests
- [ ] Monitor error rates and latency
- [ ] Verify rollback plan works

### 6. Post-deployment
- [ ] Monitor for 30 minutes
- [ ] Check error rates and metrics
- [ ] Update deployment status
- [ ] Notify team of completion
- [ ] Document any issues

## Examples
```bash
# Build and test
python -m build
pytest tests/ -v

# Deploy to staging
./scripts/deploy.sh staging

# Deploy to production
./scripts/deploy.sh production

# Rollback if needed
./scripts/rollback.sh
```

## Related Skills
- test
- code-review
- debug

## Configuration
- Deployment targets in config
- Environment variables for secrets
- Notification webhooks