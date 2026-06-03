# big-data-sql CLI

AI-callable CLI for executing SQL on the JD big-data platform.

## Install

From the skill root (`big-data-sql/`):

```bash
bash scripts/install.sh
bash scripts/big-data-sql doctor
```

## Commands

- `doctor` — check browser auth and configuration
- `init` — resolve your ERP local git project (`getErpLocalProject`), then `addScript` and save `profile.json` (run once, or `init --force` to recreate)
- `run --sql "<sql>"` — submit and wait for results (default, engine `presto`)
- `run --sql "<sql>" --engine spark` — use Spark (`engineType`; also `doris`)
- `run --sql "<sql>" --no-wait` — submit only, then use `poll`
- `poll --artifact-dir <dir>` — continue polling a running job

Profile path: `~/.config/big-data-sql/profile.json` (override with `BDP_SQL_PROFILE_PATH`).

All commands print a JSON envelope to stdout. Full logs and results are saved under the artifact directory.
