# CURL CLI Builder

Meta-skill for turning curl samples into distributable skill packages (spec + Python CLI + SKILL.md).

**Design goal:** generated CLIs minimize Agent cognitive load—see [output-contract.md](output-contract.md).

## When to use

Provide:

1. One or more curl commands
2. What each curl does (plus response JSON samples when possible)
3. Skill/CLI naming preference
4. Optional: how tools should be combined (only then we write `orchestration.md`)

## Quick start

Tell the Agent:

> 使用 curl-cli-builder，根据以下 curl 封装成一个 skill …

Then follow `SKILL.md` workflow.

## Reference

- [output-contract.md](output-contract.md) — mandatory stdout JSON shape
- [templates/runtime/](templates/runtime/) — normalize/client/cli starting point
- `taishan-sql/` — completed example in this repo
- [reference.md](reference.md) — spec, `agent_output`, auth rules
- [examples.md](examples.md) — taishan-sql walkthrough
