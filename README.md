# cosyflo-cli

Thin, tested command layer over the Cosyflo Laravel REST API. Slice 1 = the
rent-payments surface (list-pending, mark-paid, arrears list, chase-message
draft). Built per spec `t_2b70faf2`; command names are locked to the
nestflo-mcp name contract (`t_c44a2968` §5) so a future re-point needs no
renames: `payment list-pending` ↔ `payment_list_pending`, `payment mark-paid`
↔ `payment_mark_paid`, `arrears list` ↔ `arrears_list`.

No business logic, no direct DB: one command = one REST call = one rendered
result.

## Install

```sh
uv tool install .          # or: uv venv && uv pip install -e .
cosyflo --help
```

Requires Python 3.11+. Single dependency: `requests`.

## Commands (slice 1)

```
cosyflo payment list-pending --month 2026-10          # tenancies in arrears for a month
cosyflo payment mark-paid --tenancy-id T-1 --month 2026-10 --amount 825.00
cosyflo arrears list --tenancy-id T-1                 # per-tenancy payment schedule
cosyflo message draft --template chase-standard --tenant-name "A. Smith" \
    --tenancy-id T-1 --month 2026-10 --amount-short 125.00 [--output draft.txt]
```

`message draft` renders a local template and never sends anything (SR7).
Sending is deliberately out of scope.

Global flags: `--config <path>`, `--endpoint <url>`, `--token-source op|env`.

## Exit codes

0 success · 1 validation · 2 auth · 3 approval denied/blocked · 4 upstream
API error · 5 unexpected.

## Config

`~/.cosyflo-cli/config.json` (see `config.example.json`). Holds only the base
URL, the 1Password vault reference (not a secret), audit path, Feishu webhook.
No secrets ever live in config, env files, source, or logs.

Token resolution (SR1): `op read <op_ref>` at runtime (default, production) —
the service account's `api_token` never touches disk. `--token-source env`
reads `COSYFLO_API_TOKEN` instead — dev/staging convenience only, added so the
smoke demo can run where `op` cannot approve biometric unlock headlessly.

## Cross-cutting behaviour

- **Audit (D3/SR4)**: every mutation appends a hash-chained JSONL line
  (`~/.cosyflo-cli/audit.log` by default) with UTC ts, command, params,
  operator (resolved from the authenticated service account — D8), status, and
  a Feishu notify result. Reads append nothing. Failed mutations are logged
  with `status=error` + error code; credentials never reach the log.
- **Gate (D4/SR3)**: tenancy termination and rent-amount changes are
  gated — refused before any network call, a Feishu approval request is
  emitted, and the mutation only proceeds on an explicit approval. No channel
  configured → blocked (fail-closed). Slice 1 ships no command that performs a
  gated action; the machinery is unit-tested for slice 2.
- **Money (SR5)**: `cosyflo_cli/money.py` owns the single Decimal-based
  pounds↔pence conversion. The API stores pence; `create_payment` takes
  pounds and multiplies by 100 server-side. No float arithmetic anywhere.
- **Overwrite risk (R1)**: `create_payment` is `updateOrCreate` — re-marking
  a month silently overwrites. The CLI pre-reads the schedule and warns
  `overwriting existing value <old> with <new>` before writing.

## Tests

```sh
.venv/bin/python -m unittest discover -s tests
```

24 scenario tests — one per Gherkin scenario block in spec §7 (auth 3,
list-pending 3, mark-paid 6, arrears 3, message 3, gate 3, audit 3; the spec's
own count of 22 is off by two — see the task handoff). All mock-HTTP; no live
API in unit tests. The money round-trip contract (0, 0.01, 825.005→reject,
999999.99) is asserted inside the mark-paid records-a-payment test.