# Agent-Oriented CLI Output Contract

Generated CLIs exist primarily for **Agent tool invocation** (shell → parse stdout → decide next step). Optimize every layer for the smallest reliable parse rule set.

## Design goals

1. **One branch**: read `ok` → success path or failure path. No third “HTTP OK but business failed inside data” state.
2. **Minimal envelope**: omit fields that do not change Agent decisions (`elapsed_ms`, empty `warnings`).
3. **Task-shaped `data`**: expose only fields the Agent needs for the next command or the final answer—not full upstream JSON.
4. **Actionable failures**: every failure includes `next_step` telling the Agent what to do next.
5. **Per-command docs**: generated `SKILL.md` documents the exact `data` shape for each subcommand.

## stdout / exit code

| Layer | Rule |
|-------|------|
| stdout | Always one JSON object (pretty-printed, trailing newline) |
| stderr | Human/debug logs only; never required for parsing |
| exit code | `0` when `ok: true`, `1` when `ok: false` |
| crash | Best-effort JSON failure before exit; see `failure()` in runtime template |

Agent parsing rule (document verbatim in every generated SKILL):

> Parse stdout as JSON. If `ok` is `false`, stop and follow `next_step`. Otherwise read `data` using the field guide for that command.

## Success envelope

```json
{
  "ok": true,
  "tool": "sources",
  "data": {}
}
```

| Field | Required | Purpose |
|-------|----------|---------|
| `ok` | yes | always `true` |
| `tool` | yes | subcommand name; correlates output when chaining or running in parallel |
| `data` | yes | command-specific payload; may be `{}` when nothing useful remains after trimming |

Do **not** include by default: `warnings`, `elapsed_ms`, `raw`, nested `result`.

Optional flags (only when user asks):

- `--include-raw` → add `data._raw` with upstream body (debug)
- `--verbose` → add top-level `elapsed_ms`

## Failure envelope

```json
{
  "ok": false,
  "tool": "query",
  "error_code": "AUTH_UNAVAILABLE",
  "message": "未从浏览器读取到有效 Cookie",
  "recoverable": true,
  "next_step": "Run `{cli} doctor`. If still failing, ask the user to log in to the platform in Edge or Chrome, then retry."
}
```

| Field | Required | Purpose |
|-------|----------|---------|
| `ok` | yes | always `false` |
| `tool` | yes | subcommand that failed |
| `error_code` | yes | stable machine enum (see table below) |
| `message` | yes | short human-readable reason |
| `recoverable` | yes | `true` if retry/adjustment may help without code changes |
| `next_step` | yes | **action instruction for the Agent** (may include `{cli}` placeholder) |

Optional context keys (only when they help the next step): `candidates`, `status`, `resolution`.

## Standard `error_code` values

| Code | recoverable | Default `next_step` intent |
|------|-------------|----------------------------|
| `AUTH_UNAVAILABLE` | true | run `doctor`, ask user to log in |
| `AUTH_EXPIRED` | true | same as auth unavailable |
| `INVALID_ARGUMENT` | false | fix CLI flags from `--help` |
| `HTTP_ERROR` | true | retry once; check env / platform status |
| `NETWORK_ERROR` | true | retry once |
| `TIMEOUT` | true | retry with smaller request or split work |
| `INVALID_JSON` | false | report platform/API anomaly |
| `API_ERROR` | varies | read `message`; often user-facing platform error |
| `AMBIGUOUS_TARGET` | true | present `candidates` to user, pick one, retry |
| `INTERNAL_ERROR` | false | report unexpected CLI failure; do not retry blindly |

Implement `next_step` defaults in `normalize.py` (`ERROR_GUIDANCE` map). Override in handler only when a command-specific action is clearer.

## Shaping `data` (spec `agent_output`)

Upstream APIs are noisy. The builder must configure trimming in each YAML spec:

```yaml
response:
  ok_path: code
  ok_value: 1
  data_path: data.list
  error_path: message
  agent_output:
    type: list          # list | object | rows
    item_fields: [id, name, appName]
    rename:
      appName: app_name
    omit_raw: true
```

| `type` | Agent gets | Use when |
|--------|------------|----------|
| `list` | `{ "items": [...] }` | discovery / navigation |
| `object` | flat key/value map | single record or scalar bundle |
| `rows` | `{ "rows": [...], "row_count": N }` | tabular query results |

Rules:

- Map upstream success into **`ok: true` at CLI layer**. Never leave business failure as `ok: true`.
- Rename keys to **stable snake_case** in `data`.
- Drop null/empty fields when trimming items.
- For long lists, support `--limit N` (default cap e.g. 50) and set `data.truncated: true` when capped.

## Generated SKILL.md requirements

For **each** subcommand, document:

1. One-line purpose
2. Example invocation
3. **`data` field guide** (bullet list of keys the Agent should read)
4. Which field feeds the **next** command in a chain (if any)

Example fragment:

```markdown
### `sources`

Returns authorized root nodes.

```bash
{cli} sources --env prod
```

**Parse on success**

- `data.items[]` — each item has `id`, `name`
- Next step: pass `id` to `children --id`
```

## Builder checklist additions

When generating a skill package:

- [ ] Every spec has `response.agent_output` configured
- [ ] `normalize.py` implements contract (no empty `warnings`, no default `elapsed_ms`)
- [ ] `client.py` sets `tool` on every response
- [ ] `cli.py` prints JSON + `SystemExit(1)` on `ok: false`
- [ ] Generated SKILL.md has per-command **Parse on success** sections
- [ ] Failure samples documented (at least `AUTH_UNAVAILABLE`, `API_ERROR`)
