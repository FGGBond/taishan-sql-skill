# CURL → CLI Reference

## Agent-first output

All generated CLIs must follow [output-contract.md](output-contract.md). The builder's job is not only HTTP wrapping—it is **response shaping for Agent tool calls**.

When analyzing a curl response sample, ask:

1. Which fields does the Agent need for the **answer** or the **next command**?
2. Can list items be trimmed to 3–6 stable snake_case keys?
3. What should the Agent do on failure (`next_step`)?

## Curl field classification

| Category | Examples | Action |
|----------|----------|--------|
| **auth** | `Cookie`, `Authorization`, `iam_token`, `x-csrf-token` | Runtime via `browser_cookie` or auth provider; never in spec/git |
| **business** | query/body fields the caller must supply | Expose as CLI flags → spec `param` |
| **constant** | `systemType=origin`, `isDesensitization=1` | spec `default` or fixed `value` |
| **noise** | `sec-ch-ua*`, `sec-fetch-*`, `priority`, `accept-language` | Omit from spec |
| **environment** | prod vs test host | spec `environments.prod/test.base_url` |

## YAML spec template

```yaml
name: execute_sql
description: 执行线上数据库只读 SQL
method: POST
base_url: https://api.example.com
environments:
  prod:
    base_url: https://api.example.com
  test:
    base_url: http://testapi.example.com
path: /dbquery/queryData
headers:
  accept: application/json, text/plain, */*
  content-type: application/json;charset=UTF-8
  origin: https://portal.example.com
  referer: https://portal.example.com/
auth:
  provider: browser_cookie
query:
  _t:
    auto: timestamp_ms
request:
  body:
    sql:
      param: sql
      type: string
      required: true
response:
  ok_path: code
  ok_value: 1
  data_path: data.dataList
  execute_time_path: data.executeTime.executeTime
  error_path: message
  data_encoding: json_string   # when API returns JSON string in data field
  agent_output:
    type: rows
    item_fields: []              # empty = keep all keys after decode
    rename: {}
    omit_raw: true
safety:
  timeout_seconds: 30
```

### `response.agent_output`

| Field | Purpose |
|-------|---------|
| `type: list` | `data.items[]` for discovery/navigation |
| `type: rows` | `data.rows[]` + `data.row_count` for tabular results |
| `type: object` | flat map for single records |
| `item_fields` | whitelist per list/row element; omit to keep all keys |
| `rename` | upstream key → snake_case Agent key |
| `omit_raw` | when true (default), never embed upstream JSON in `data` |

Add command-specific shaping in `normalize.py` only when YAML cannot express it (e.g. multi-key row flattening).

## CLI subcommand naming

Map spec `name` snake_case to CLI kebab-case:

| spec name | CLI command |
|-----------|-------------|
| `list_root_sources` | `sources` or `list-root` |
| `query_data` | `query` |

Prefer short verbs users already know. Always include `doctor`.

## Browser authentication

Default stack (from `taishan-sql`):

1. Load cookies from Edge, then Chrome (`browser-cookie3`).
2. When calling host `api.example.com`, send only cookies valid for that host (avoid sibling-domain cookie bloat → HTTP 400).
3. Load jar with domain hint `jd.com` (or parent domain) but filter by target host on send.
4. macOS may prompt Keychain once; run install/doctor outside sandbox if needed.

Env vars:

- `TAISHAN_SQL_BROWSER` → reuse pattern as `{PKG}_BROWSER`
- `{PKG}_COOKIE_DOMAINS` — optional override
- `{PKG}_SPECS_DIR` — optional spec path override

## Generated SKILL.md sections

1. YAML frontmatter (`name`, `description` with WHAT + WHEN, third person)
2. Setup → `bash scripts/install.sh` → `doctor`
3. **Agent parsing rule** (from output-contract.md)
4. **Per-command blocks**: invocation example + **Parse on success** bullets
5. Failure handling: trust `next_step`; mention common `error_code` values
6. General workflow (resolve ambiguity before chaining)
7. Notes (secrets, limits)
8. Link to `orchestration.md` **only if user supplied combination intent**

### Per-command doc pattern

```markdown
### `{command}`

{one-line purpose}

\`\`\`bash
{cli} {command} ...
\`\`\`

**Parse on success**

- `data.items[]` — fields: `id`, `name`
- Next: `{other-command} --id data.items[n].id`
```

## orchestration.md (optional)

Create **only** when user explicitly describes tool chains. Structure:

```markdown
# Suggested orchestrations

These are user-provided suggestions. The Agent may adapt steps as needed.

## Scenario: {name}

1. `{cli} {cmd-a} ...`
2. Parse `{field}` from step 1
3. `{cli} {cmd-b} --id "{field}" ...`
```

Do not add scenarios the user did not mention.

## Verification checklist

- [ ] No secrets in specs, SKILL.md, or git
- [ ] All subcommands in `--help`
- [ ] Each spec has `response.agent_output`
- [ ] Success stdout matches contract (`ok`, `tool`, `data` only by default)
- [ ] Failure stdout includes `next_step`; exit code `1`
- [ ] Generated SKILL.md documents `data` fields per command
- [ ] `doctor` reports auth ok when browser logged in
- [ ] Generated skill root has `SKILL.md` (not nested `skill/SKILL.md`)
