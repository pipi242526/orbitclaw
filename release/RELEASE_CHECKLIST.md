# Release Checklist (Fork)

## Quality Gate

- [ ] `uv run pytest -q` passes
- [ ] Changed Python files pass incremental lint gate
- [ ] No unresolved P0 bugs in release scope

## Iron Laws Validation

- [ ] Resource budgets documented and unchanged or justified
- [ ] Output policy path verified (language/no tool leakage/failure guidance)
- [ ] Unified message contract unchanged or migration documented
- [ ] Config changes are reversible
- [ ] New extension points are non-invasive to core loop

## Upstream Governance

- [ ] Monthly upstream patch audit report added (`release/upstream-audits/YYYY-MM.md`)
- [ ] Accepted upstream patches cherry-picked and tested
- [ ] Rejected patches have explicit reasons

## Packaging & Docs

- [ ] Release notes include breaking/non-breaking sections
- [ ] README/Quick Start reflects current defaults
- [ ] Attribution to upstream project remains explicit
- [ ] Product release is published on the new repository `main` branch (not upstream fork branches)
- [ ] Release tag (`vX.Y.Z`) is created and pushed on the product repository

## Runtime Validation

- [ ] Docker compose cold start test on server
- [ ] WebUI `/healthz` and token-path health check pass
- [ ] Gateway can process one real channel message roundtrip
