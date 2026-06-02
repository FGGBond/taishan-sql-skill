---
name: curl-cli-builder
description: Builds distributable Agent Skills from one or more curl samples by generating YAML API specs, browser-cookie authenticated Python CLIs, and SKILL.md usage guides. Use when the user provides curl commands, wants to wrap internal platform APIs as CLI tools, create skill packages with scripts/cli, or asks to encapsulate HTTP requests for AI coding tools.
---

# CURL to CLI Skill Builder

Turn user-provided curl samples into a **distributable skill package** with bundled CLI tools. Follow the `taishan-sql/` layout in this repository as the reference implementation.

**Primary design goal:** minimize Agent cognitive load when invoking generated CLIs. Read [output-contract.md](output-contract.md) before building.

## Inputs required from user

Collect before building:

1. One or more **curl commands** (preferably with a sample response JSON for each).
2. **Function description** for each curl (what it does, key params, success/error shape).
3. **Skill name** (lowercase-hyphen, e.g. `my-platform-api`).
4. **CLI command name** (e.g. `my-platform-cli`).
5. Optional: **environment variants** (prod/test base URLs).
6. Optional: **orchestration intent** — see below.

If response samples are missing, ask once. Proceed with best-effort spec fields and mark uncertain paths in generated specs.

## Orchestration rule (critical)

**Do not invent multi-tool workflows unless the user explicitly asks for combination guidance.**

- User **did not** describe how tools should be chained → generate `SKILL.md` with command list + general workflow only. Let the Agent pick tools at runtime.
- User **did** describe combinations (e.g. "先 listRoot，再 listChildren，最后 queryData") → also generate `orchestration.md` with their suggested sequences verbatim or lightly structured. Label it **suggested**, not mandatory.

If unclear, ask:

> 是否需要我写入固定的多工具组合编排建议？若不需要，我只生成各 CLI 命令说明，由 Agent 按任务智能选用。

## Output package structure

Generate a new directory at repo root (or user-specified path):

```text
{skill-name}/
├── SKILL.md
├── README.md
├── orchestration.md          # only if user provided combination intent
├── scripts/
│   ├── install.sh
│   └── cli/
│       ├── pyproject.toml
│       ├── README.md
│       ├── specs/            # one YAML per API
│       └── src/{package}/
│           ├── cli.py
│           ├── client.py
│           ├── auth.py
│           ├── config.py
│           ├── specs.py
│           ├── normalize.py
│           └── spec_data/    # copy of specs for pip install fallback
```

Use templates in [templates/](templates/) and details in [reference.md](reference.md).

## Build workflow

Copy this checklist and track progress:

```text
- [ ] Parse each curl → draft YAML spec
- [ ] Classify params: business / auth / constant / noise
- [ ] Configure response paths + agent_output trimming per spec
- [ ] Copy runtime from templates/runtime/ (client, normalize, cli skeleton)
- [ ] Register one CLI subcommand per API spec
- [ ] Add doctor command (auth check)
- [ ] Write generated SKILL.md with per-command "Parse on success" sections
- [ ] Write README.md
- [ ] Write orchestration.md only if user requested
- [ ] Verify: compile, install.sh, --help, success + failure JSON shape
```

### Step 1: Parse curl → spec

For each curl extract: method, base URL, path, query, headers, body. **Strip** cookie/token/ticket values from specs; set `auth.provider: browser_cookie`. Drop browser noise headers (`sec-ch-ua`, `sec-fetch-*`, `priority`). See [reference.md](reference.md).

For each response sample, configure **`response.agent_output`** so stdout `data` contains only fields the Agent needs—not the full upstream JSON.

### Step 2: Implement CLI runtime

Start from [templates/runtime/](templates/runtime/):

- **normalize.py**: Agent-oriented envelope; map API failure → `ok: false`; shape `data` via `agent_output`.
- **client.py**: load spec → build request → inject cookies → attach `tool` on every response.
- **cli.py**: one subcommand per spec; shared `--env`; global `--verbose` / `--include-raw` only.

#### Output contract (mandatory)

Follow [output-contract.md](output-contract.md). Summary:

**Success**

```json
{ "ok": true, "tool": "sources", "data": { "items": [] } }
```

**Failure**

```json
{
  "ok": false,
  "tool": "sources",
  "error_code": "AUTH_UNAVAILABLE",
  "message": "...",
  "recoverable": true,
  "next_step": "Run `{cli} doctor` ..."
}
```

Agent parsing rule to embed in every generated SKILL:

> Parse stdout as JSON. If `ok` is `false`, stop and follow `next_step`. Otherwise read `data` using that command's field guide below.

Do **not** emit by default: empty `warnings`, `elapsed_ms`, or upstream `raw` blobs.

### Step 3: Write generated SKILL.md

Include:

1. Setup (`bash scripts/install.sh`) → `doctor`
2. Agent parsing rule (above)
3. **Per-command sections** with example invocation + **Parse on success** field list
4. Failure handling (`error_code` table or pointer to `next_step`)
5. Notes (no secrets in repo)
6. Link to `orchestration.md` only if it exists

See [templates/SKILL.md.template](templates/SKILL.md.template).

### Step 4: install.sh

```bash
python -m pip install -e "${SCRIPT_DIR}/cli"
```

### Step 5: Verify

```bash
python -m compileall -q {skill}/scripts/cli/src
bash {skill}/scripts/install.sh
{cli-name} doctor
{cli-name} --help
```

Confirm stdout is always valid JSON and exit code matches `ok`.

## Reference implementation

Study `taishan-sql/` in this repo: three specs, browser auth, `--env prod|test`, resolver pattern for multi-step discovery. When updating an existing skill, migrate its output to [output-contract.md](output-contract.md).

## Additional resources

- Agent output contract: [output-contract.md](output-contract.md)
- Spec format and curl classification: [reference.md](reference.md)
- End-to-end example: [examples.md](examples.md)
- Runtime templates: [templates/runtime/](templates/runtime/)
- File templates: [templates/](templates/)
