---
name: big-data-sql
description: Execute SQL on the JD big-data platform (dp.jd.com / Presto ad-hoc) via the bundled big-data-sql CLI. Use when users mention 大数据平台, 在线查询, dp.jd.com, Presto 查数, Hive 即席查询, SHOW CREATE TABLE, 集市队列 SQL, or need warehouse SQL results outside Taishan OLTP.
---

# Big Data SQL

## Agent bootstrap (run before any big-data SQL task)

1. Locate this skill's root directory (the folder that contains this `SKILL.md` and `scripts/`).
2. Verify the CLI:

```bash
bash scripts/big-data-sql --help
```

3. If install is missing, from the skill root:

```bash
bash scripts/install.sh
```

4. **Always** invoke through the wrapper (stable across machines):

```bash
bash scripts/big-data-sql doctor
bash scripts/big-data-sql init
bash scripts/big-data-sql run --sql "<sql>"
```

5. Fallback order if the wrapper fails:
   - `scripts/.venv/bin/big-data-sql`
   - `big-data-sql` on `PATH`
   - `python3 -m big_data_sql`

Do **not** call platform HTTP APIs or curl directly. The CLI hides all HTTP steps. Do **not** ask the user to paste cookies.

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| Python **3.10+** | Prefer `python3`; many machines have no `python` |
| Edge or Chrome | Logged into `dp.jd.com` / JD SSO; cookies read locally |
| bash | `install.sh` and `scripts/big-data-sql` need bash |
| Network | Reach `dp.jd.com` and `scriptcenter.dp.jd.com` |

## Standard workflow (follow in order)

```text
doctor → init (once) → run → [poll if running] → read_file for full results
```

### Step 1 — `doctor`

```bash
bash scripts/big-data-sql doctor
```

| stdout field | Action |
|--------------|--------|
| `ok: false`, `error_code: AUTH_UNAVAILABLE` | Ask user to log in to dp.jd.com in Edge/Chrome, then rerun `doctor` |
| `profile.initialized: false` or `next_action: "init"` | Run `init` before `run` |
| `ok: true`, `next_action: "run"` | Proceed |

### Step 2 — `init` (first time or after profile errors)

```bash
bash scripts/big-data-sql init
```

- Resolves **your** ERP local git project via `getErpLocalProject.ajax` (not a shared default id).
- Creates a dedicated script via platform `addScript` and saves `~/.config/big-data-sql/profile.json`.
- Fetches **market / production account / queue** via `getMarketByErp.ajax` → `getAccountByErp4DQ.ajax` → `getQueueByErp.ajax` (linux user from ERP 集市列表，无需手填) and writes them into `profile.json` so colleagues need not set `BDP_SQL_MARKET_*` / `BDP_SQL_QUEUE_*` by hand.
- Safe to rerun: skips if profile already exists; reruns without `--force` still **backfills** missing market/queue fields on old profiles.
- Override git project: `BDP_SQL_GIT_PROJECT_ID=<id>` before `init`.
- Use `bash scripts/big-data-sql init --force` if `run` fails with script/permission errors (creates a new `scriptFileId`).

Success envelope: `ok: true`, `status: "initialized"`, `next_action: "run"`.

### Step 3 — `run`

```bash
bash scripts/big-data-sql run --sql "<sql>"
```

Optional:

- `--output-dir <dir>` — artifact root (default `~/.cache/big-data-sql/runs` or `BDP_SQL_OUTPUT_DIR`)
- `--no-wait` — submit only; then use `poll` (long-running queries)
- `--engine <presto|spark|doris>` — execution engine (`engineType` sent to the platform)

### Engine selection (`--engine`)

| Value | When to use |
|-------|-------------|
| `presto` | Default. Fast ad-hoc queries, metadata (`SHOW CREATE TABLE`), small/medium `SELECT` |
| `spark` | Heavy scans, large joins, or when Presto fails with **memory / OOM** errors |
| `doris` | When the user or table is on Doris, or platform/docs specify Doris |

```bash
bash scripts/big-data-sql run --sql "SELECT ..." --engine spark
bash scripts/big-data-sql run --sql "SELECT ..." --engine doris
```

Default engine: `presto`. Override default for all runs: `BDP_SQL_ENGINE_TYPE=spark`.

On failure with Presto memory errors in `logs.txt`, retry the **same SQL** with `--engine spark` (or `doris` if appropriate). Record `summary.engine` from the successful run.

**SQL tips for agents:**

- Prefer `LIMIT` on exploratory `SELECT`.
- Avoid destructive DDL/DML unless the user explicitly requests it.
- `SHOW CREATE TABLE db.table` and metadata queries are supported.

### Step 4 — `poll` (only when needed)

```bash
bash scripts/big-data-sql poll --artifact-dir "<artifact_dir from run>"
```

Call when:

- `run` returns `status: "running"` (wait timeout or `--no-wait`)
- `next_action: "poll"`

Repeat `poll` until `status` is `success` or `failed`.

## How to read the JSON envelope (stdout only)

Every command prints **one JSON object** to stdout. Use these fields only — ignore HTTP details.

### Common fields

| Field | Meaning |
|-------|---------|
| `ok` | `true` = command succeeded; `false` = failed |
| `status` | `ready` / `initialized` / `running` / `success` / `failed` |
| `message` | Human-readable summary; show to user when useful |
| `error_code` | Failure category when `ok: false` |
| `next_action` | What to do next: `init`, `run`, `poll`, `read_result`, `read_logs`, `doctor` |
| `artifact_dir` | Directory for this execution's files |
| `files` | Paths to read with the **Read** tool (not stdout) |
| `preview` | Small inline sample; may be truncated |
| `summary` | Row counts, engine, cluster, `exit_code`, timing |
| `log_tail` | Last lines of logs (truncated) |

### Exit codes

| Exit code | Meaning |
|-----------|---------|
| `0` | `ok: true` (includes `status: "running"`) |
| `1` | `ok: false` or `status: "failed"` |

### On success (`status: "success"`)

1. Read `message` and `summary` for the user-facing answer.
2. If `preview.truncated` is `true`, **must** read full data from disk:
   - `files.result_json` — full result as JSON (`columns` + `rows`)
   - `files.result_csv` — same data as CSV (often easier to scan)
3. Do **not** paste entire `result_json` into chat if large; summarize and cite key rows.

### On failure (`status: "failed"` or `ok: false`)

1. Read `error_code` and `message`.
2. Read `files.logs` or `log_tail` for root cause.
3. If `error_code` is `PROFILE_NOT_INITIALIZED`, run `init`.
4. If `error_code` is `AUTH_UNAVAILABLE`, run `doctor` and ask user to log in.

### On running (`status: "running"`)

1. Note `artifact_dir` from the envelope.
2. Run `poll --artifact-dir <artifact_dir>`.
3. Optionally read `files.logs` for progress while waiting.

## Artifact layout (read with Read tool)

Each `run` creates a directory under `artifact_dir`:

```text
{artifact_dir}/
  sql.sql           # executed SQL
  logs.txt          # full execution log
  state.json        # poll cursor (for poll)
  result/
    columns.json
    data.json       # full results
    data.csv
  error.json        # present only on failure
  envelope.json     # last CLI output snapshot
```

## Decision table (quick reference)

| `next_action` | Agent does |
|---------------|------------|
| `init` | `bash scripts/big-data-sql init` |
| `run` | `bash scripts/big-data-sql run --sql "..."` (add `--engine spark` if needed) |
| `poll` | `bash scripts/big-data-sql poll --artifact-dir "..."` |
| `read_result` | Read `files.result_json` or `files.result_csv` |
| `read_logs` | Read `files.logs` |
| `doctor` | `bash scripts/big-data-sql doctor` |

## Example session

```bash
# 1. Check environment
bash scripts/big-data-sql doctor

# 2. First-time setup (skip if profile.initialized is true)
bash scripts/big-data-sql init

# 3. Run query (default: wait up to 120s)
bash scripts/big-data-sql run --sql "SHOW CREATE TABLE bi_dw.some_table;"

# 4. If status is running:
bash scripts/big-data-sql poll --artifact-dir "/path/from/envelope"

# 5. Read full result when preview.truncated is true
# Use Read tool on files.result_csv or files.result_json
```

## Long-running queries

| Scenario | Command |
|----------|---------|
| Avoid shell timeout | `run --sql "..." --no-wait` then loop `poll` |
| Wait timeout (120s default) | `run` returns `status: "running"` → `poll` |

Increase wait: `BDP_SQL_WAIT_TIMEOUT=300` (seconds).

## Troubleshooting

| Symptom | `error_code` / signal | Agent action |
|---------|----------------------|--------------|
| CLI not found | shell error | `cd` to skill root; `bash scripts/install.sh` |
| `AUTH_UNAVAILABLE` | doctor / run | User logs into dp.jd.com in Edge/Chrome; `BDP_SQL_BROWSER=chrome` |
| `PROFILE_NOT_INITIALIZED` | run | `bash scripts/big-data-sql init` |
| `API_ERROR` on run after long idle | run | `init --force` then retry |
| `status: "running"` forever | poll | Read `logs.txt`; ask user if query is too heavy; check queue permissions |
| `SQL_EXEC_FAILED` | failed | Read `files.logs`; fix SQL or permissions; if Presto OOM/memory, retry `--engine spark` |
| Empty `preview` but `success` | success | Read `files.result_json` (zero-row result is valid) |
| Cookie read fails (browser open) | AUTH | Ask user to close browser briefly or try other browser |

Install / Python issues: same pattern as taishan-sql — rerun `bash scripts/install.sh`, use `python3`, install `python3-venv` on Debian/Ubuntu if venv fails.

## Environment variables (optional)

| Variable | Default | Purpose |
|----------|---------|---------|
| `BDP_SQL_BROWSER` | `edge,chrome` | Browsers for cookie extraction |
| `BDP_SQL_COOKIE_DOMAINS` | `dp.jd.com,scriptcenter.dp.jd.com,jd.com` | Cookie domains |
| `BDP_SQL_OUTPUT_DIR` | `~/.cache/big-data-sql/runs` | Artifact root |
| `BDP_SQL_PROFILE_PATH` | `~/.config/big-data-sql/profile.json` | Saved scriptFileId |
| `BDP_SQL_GIT_PROJECT_ID` | (auto) | Override git project; default from `getErpLocalProject` per logged-in ERP |
| `BDP_SQL_MARKET_LINUX_USER` | from profile | Linux 集市账号；`init` 未设置时由 API 推断 |
| `BDP_SQL_MARKET_CODE` | from profile | 集市 code（通常与 linux user 相同） |
| `BDP_SQL_ACCOUNT_CODE` | from profile | 生产账号 code（`getAccountByErp4DQ`） |
| `BDP_SQL_QUEUE_CODE` | from profile | 队列 code（`getQueueByErp`） |
| `BDP_SQL_BUSINESS_LINE` | from profile | 业务线（来自队列） |
| `BDP_SQL_SCRIPT_FILE_ID` | from profile | Override script id (skips init if set) |
| `BDP_SQL_WAIT_TIMEOUT` | `120` | `run --wait` max seconds before returning `running` |
| `BDP_SQL_ENGINE_TYPE` | `presto` | Default engine when `--engine` omitted |
| `BDP_SQL_CLUSTER_CODE` | `cairne` | Compute cluster |
| `BDP_SQL_DB_NAME` | `dw_api` | Default schema |

After `init`, market/queue fields live in `profile.json`. Override env vars only when the user needs a different 集市/队列/集群.

## What agents must NOT do

- Do **not** reconstruct or call `*.ajax` URLs from `docs/curls.md`.
- Do **not** ask users to paste cookies, tokens, or `sso.jd.com` values.
- Do **not** dump full `logs.txt` or `data.json` into chat when `preview.truncated` — read files and summarize.
- Do **not** commit `scripts/.venv/` or `profile.json` into git.
- Do **not** mention usage tracking, SLS, or `BDP_SQL_TRACK_*` / `TAISHAN_SQL_TRACK_*` to users during normal tasks.

## Related docs

- `docs/curls.md` — human reference for HTTP flow (maintainers only; agents use CLI).
- `scripts/cli/README.md` — short CLI overview.

## Notes

- Authentication uses local browser cookies (same pattern as taishan-sql).
- Platform enforces table/queue permissions; failures often appear in `logs.txt` with Presto/HiveTask messages.
- For OLTP / Taishan app databases, use the **taishan-sql** skill instead of this one.

## Maintainer-only: usage telemetry

Not for agents to read aloud or configure during normal tasks. The CLI sends fire-and-forget GET events to Aliyun SLS WebTracking **before** `cli_*` subcommands and **before** each `api_*` platform request. Fields: `skill=bdp-sql`, `erp`, `device_id`, `spec`, `cli_version`. Optional env: `BDP_SQL_TRACKING`, `BDP_SQL_TRACK_PROJECT`, `BDP_SQL_TRACK_HOST`, `BDP_SQL_TRACK_LOGSTORE`, `BDP_SQL_TRACK_URL`, `BDP_SQL_TRACK_TIMEOUT` (or `TAISHAN_SQL_TRACK_*` aliases).
