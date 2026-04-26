# Changelog

## v2.5.0 — Performance, scoping, correctness

This release rewrites the hot path of the app to eliminate the symptoms
reported in production: continuous server load, one job running constantly,
and inability to scope sync to specific modules / DocTypes.

### Resource consumption — fixed

- **In-process scope cache.** Every doc save consults a tiny in-process
  frozenset before doing any work. If the saved DocType is not part of the
  active sync configuration, the handler returns in microseconds without
  hitting the database. Previously every save did a full
  `frappe.get_single("Neotec Sync Settings")` plus a child-table iteration.
- **`on_update` now fast-pathed.** `on_update` fires on every field change
  of every document in the system; the original app would still load
  Settings on every one of those fires. The new scope cache makes
  out-of-scope saves essentially free.
- **Scheduler is gated.** `process_batch_queue` and `retry_failed_syncs`
  start with a cheap `EXISTS`-style probe — if the queue is empty (the
  normal state on an idle install), they return without further work.
- **Dispatch throttling.** `min_dispatch_interval_seconds` (default 60)
  prevents successive dispatch runs from piling up. Cron can fire as often
  as every 5 minutes safely.
- **One commit per dispatch run** instead of one commit per row.
- **Direct SQL UPDATE for status transitions** instead of
  `frappe.get_doc(...).save()`, which would otherwise run validations,
  versioning, and hooks on every status change.
- **Database indexes added on Sync Log and Idempotency Log** by the migration:
  - `(status, direction, creation)`
  - `(status, direction, retry_count, modified)`
  - `(reference_doctype, reference_name)`
  - `(sync_transaction_id)`
- **`track_changes: 0`** on Settings, Rule, Mapping, Field Map, Mapping Row,
  Idempotency Log, Batch, API Key, Route Policy, Dashboard. (Conflict and
  Instance retain `track_changes: 1` because their audit trail matters.)
- **Audit Snapshot defaulted OFF.** When on it doubles log table growth.
- **Log retention defaulted to 30 days, idempotency to 60 days,** with a
  batched (5,000-row LIMIT) cleanup that commits between batches to avoid
  long table locks.
- **Dashboard collapses 10 separate `db.count()` calls into one
  `GROUP BY`,** with a 30-second Redis cache to absorb multiple operators
  refreshing the same form.
- **Default log level is now WARN** instead of INFO. DEBUG mode no longer
  writes per-batch info entries to Error Log.

### Sync scope — by Module and by DocType (your request)

- New **Module Filter** child table on Settings (`Neotec Sync Module Filter`).
  Empty = no module restriction. Non-empty = only DocTypes from those
  modules are eligible. Ideal when you want "sync everything in
  Manufacturing and Stock, ignore the rest of ERPNext".
- DocType-level scoping is unchanged in shape (still driven by the Rules
  table) but is now **the primary filter** consulted at event time.
  Previously the rule loop was inside a settings load; now it runs only
  after the scope cache says "yes, this doctype is in scope".
- New `include_drafts_in_scope` toggle: when off, draft documents are
  ignored even when their DocType is in scope. Default off.

### Correctness — bugs fixed

- **Loopback prevention now actually works.** The old code referenced
  `nxd_received_from_remote` and `nxd_source_name` custom fields that were
  never installed on any doctype. The new version uses a request-scoped
  `frappe.flags.neotec_inbound_apply` flag, which works on every doctype
  with no schema changes. The custom fields are still supported as an
  optional belt-and-braces layer — install them per-doctype via the
  Settings UI button **Install Loopback Fields**.
- **Manual trigger logic fixed.** The old elif chain in `_queue_if_matched`
  could double-queue or skip valid rules when called manually.
- **`safe_exec` import corrected** for Frappe v15
  (`frappe.utils.safe_exec.safe_exec`). Previously every Condition Script
  and Transform Script silently failed.
- **Inbound endpoint commits once at end** instead of 3-4 times mid-request.
  Failures cleanly roll back the doc apply while preserving the audit log.
- **`_doc_content_hash` no longer reloads the target doc** on the inbound
  update path — uses the doc already in memory.
- **New `On Insert` and `On Update` trigger modes** on rules, properly
  mapped to event names (the old code conflated all of these).

### Schema additions on Settings

| Field | Default | Purpose |
|---|---|---|
| `module_filters` (Table) | empty | Module allow-list |
| `include_drafts_in_scope` | 0 | Sync drafts? |
| `min_dispatch_interval_seconds` | 60 | Dispatch throttle |
| `log_retention_days` | 30 | Log cleanup window |
| `idempotency_retention_days` | 60 | Idempotency cleanup |

### Migration safety

- The included v2.5.0 patch:
  - Force-disables sync if `remote_base_url` is empty (defensive).
  - Defaults all new fields to safe values on existing rows.
  - Switches `log_level` from INFO to WARN.
  - Clears the document cache so the new schema takes effect immediately.
- After-migrate adds the indexes idempotently — safe to re-run.

### Files changed

| File | Change |
|---|---|
| `hooks.py` | New cache-invalidation hooks; cleaner cron schedule |
| `api/scope.py` | NEW — in-process scope cache |
| `api/events.py` | Rewrite — fast-path filter, direct SQL insert |
| `api/jobs.py` | Rewrite — throttled, EXISTS-probed, batched cleanup |
| `api/services.py` | Rewrite — direct SQL updates, single commit, `inbound_apply_flag` |
| `api/__init__.py` | Rewrite — single GROUP BY dashboard, single-commit inbound |
| `install.py` | Indexes added; loopback fields are opt-in per doctype |
| `patches/v2_5_0/upgrade_from_v2_4.py` | NEW — schema migration |
| `doctype/neotec_sync_module_filter/` | NEW child doctype |
| `doctype/neotec_sync_settings/*.json` | New fields, `track_changes` off |
| `doctype/neotec_sync_rule/*.json` | More trigger modes, `track_changes` off |
| `doctype/neotec_sync_mapping/*.json` | `track_changes` off |
| (others) | `track_changes` off on hot-path tables |
| `pyproject.toml`, `setup.py`, `__init__.py` | Versions reconciled to 2.5.0 |
