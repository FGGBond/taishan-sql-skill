# Example: taishan-sql

The `taishan-sql/` directory in this repo is the reference output of this builder pattern.

## Input (3 curls)

| # | Purpose | Endpoint |
|---|---------|----------|
| 1 | List authorized DB sources | `GET /workflow/wfdbquery/listRoot` |
| 2 | List child nodes by id | `GET /dbquery/listChildren?id=...` |
| 3 | Execute SQL | `POST /dbquery/queryData` |

User also provided response JSON for each and noted the chain: listRoot → listChildren → listChildren → queryData.

## Generated artifacts

- **Specs**: `scripts/cli/specs/*.yaml` with `environments.prod/test` and `response.agent_output`
- **CLI**: `taishan-sql sources | children | resolve-db | query | doctor`
- **Auth**: browser cookies for `dbsv5api.jd.com` / `testapi.dbsv5.jd.com`
- **SKILL.md**: setup, per-command parse guides, workflow
- **orchestration**: embedded in SKILL workflow (`resolve-db` automates the tree walk)

## Example generated commands

```bash
bash scripts/install.sh
taishan-sql doctor
taishan-sql sources --env test
taishan-sql resolve-db --keyword "settle-bk"
taishan-sql query --keyword "settle-bk" --sql "select 1 limit 1"
```

## Agent-oriented output (target contract)

**Discovery (`sources`)**

```json
{
  "ok": true,
  "tool": "sources",
  "data": {
    "items": [{ "id": "...", "name": "..." }]
  }
}
```

**Query (`query`)**

```json
{
  "ok": true,
  "tool": "query",
  "data": {
    "rows": [{ "col_a": "..." }],
    "row_count": 1,
    "execute_time_ms": 12
  }
}
```

**Auth failure**

```json
{
  "ok": false,
  "tool": "doctor",
  "error_code": "AUTH_UNAVAILABLE",
  "message": "...",
  "recoverable": true,
  "next_step": "Run `taishan-sql doctor`. Ask the user to log in ..."
}
```

See [output-contract.md](output-contract.md) for the full rules.

## Builder takeaway

When the user gives multiple related curls:

- Shared runtime (`templates/runtime/`) serves all specs.
- Configure **`agent_output`** per spec so Agents never parse raw platform JSON.
- Add **resolver** subcommands only when steps are predictable (like `resolve-db`).
- Put fixed user-described chains in `orchestration.md`; keep SKILL.md general for ad-hoc Agent use.
- Document **Parse on success** for every subcommand in generated SKILL.md.
