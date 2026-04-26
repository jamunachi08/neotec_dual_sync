# Changelog v2.6.0 — Operator-friendly UX

This release is a focused operator-experience pass. Every feature lives next
to where the operator already is, not on a separate screen they have to
remember exists.

## What's new

### 1. Sync Now button on every synced document

Open any document of a synced DocType. A new "Neotec Sync" menu appears in
the toolbar with two actions:

- **Sync Now** — queues the document and dispatches it immediately (bypasses
  the cron throttle). The button polls and shows ✓ Synced / ✗ Failed
  feedback within a few seconds, not minutes.
- **Sync History** — jumps to the Sync Log filtered to this document.

Implementation: `app_include_js` registers a single global script
(`form_integration.js`) that runs on every form. First load, it asks
"is this DocType in scope?". If no — silent return. If yes — adds the
buttons. The scope check is cached per browser tab.

### 2. Sync status indicator on every document

In-scope documents show a coloured pill near the top of the form:

- 🟢 Synced (with relative time)
- 🟡 Queued / Processing
- 🔴 Sync failed (with the first 200 chars of the error)
- 🔵 Received via sync
- ⚪ Skipped / Duplicate / Loop Prevented

Out-of-scope documents and our own DocTypes show nothing.

### 3. Bulk Re-queue on Sync Log list view

The Sync Log list now has:

- **Action menu → Bulk Re-queue Selected** — flips Failed/Skipped rows back
  to Queued, resets retry_count. Hard-capped at 5,000 rows per click.
- **Quick Filter buttons** — "Failed this week", "Failed this month",
  "Currently queued". One click triages.

### 4. Top Failure Reasons panel on the Settings dashboard

Below the existing counters, a new "Sync Health" section groups the last
7 days of failures by error message (using the first line of error_message
as the grouping key). Shows count, distinct doctypes, last seen, and a
"See logs →" jump button per row.

If there are no failures, shows a green "Sync looks healthy" panel instead.

### 5. "How Sync Works" page

A new Frappe Page at `/app/neotec-sync-help`, also pinned as the FIRST
shortcut on the Neotec Dual Sync workspace. Contains:

- Plain-English intro
- The flow diagram (the one we sketched in the design discussions)
- A 5-step quickstart with numbered cards
- Troubleshooting categorised by question type (A/B/C)
- Sync Log status reference
- Quick links to all the main views

The Settings page also has an Explore → How Sync Works button for operators
already on Settings.

### 6. Immediate dispatch path

Sync Now uses `frappe.enqueue` to fire a one-shot background job that
dispatches the single queued row. The job (`dispatch_one_log` in jobs.py)
loads settings once, dispatches the row, commits. Operator sees feedback
in ~1-3 seconds. The cron throttle is unaffected — normal scheduled runs
continue normally for any other queued rows.

## New endpoints

| Endpoint | Purpose |
|---|---|
| `get_doc_sync_status(doctype, docname)` | Status indicator data — single indexed SELECT |
| `manual_sync_now(doctype, docname)` | "Sync Now" button — queues + immediate dispatch |
| `bulk_requeue_logs(log_names)` | Bulk Re-queue list action |
| `get_failure_summary(days, limit)` | Top Failure Reasons panel data |

## What didn't make this release (deliberately)

- **Bulk Sync dialog with date filters** — too dangerous as a UI button
  during incidents. Documented as a bench command in the manual instead.
- **Custom failure report** — the Sync Log list with quick filters is
  enough; a parallel report would just confuse operators.
- **Per-user notification of failed syncs** — turns into spam fast. Better
  served by an opt-in weekly digest, which can be added later as a
  Server Script.

## Performance impact

Out-of-scope documents pay one HTTP call (cached after first load) to
`get_doc_sync_status` on first form load. Subsequent forms of the same
DocType skip the call entirely (per-tab cache).

In-scope documents pay one indexed SELECT on form load to fetch status.
The query uses the existing `(reference_doctype, reference_name)` index
added in v2.5.0.

The dashboard's failure summary is a single GROUP BY query, not cached
(but very fast — bounded by the 7-day window and indexed status column).

## Files changed

| Path | Change |
|---|---|
| `hooks.py` | Added `app_include_js` |
| `api/__init__.py` | +4 endpoints (status, sync_now, bulk_requeue, failure_summary) |
| `api/jobs.py` | +`dispatch_one_log` immediate-dispatch helper |
| `public/js/form_integration.js` | NEW — universal form integration |
| `public/js/neotec_sync_settings.js` | +failure panel rendering, +Help button |
| `doctype/neotec_sync_log/neotec_sync_log_list.js` | NEW — list-view JS |
| `page/neotec_sync_help/*` | NEW — How Sync Works page |
| `workspace/neotec_dual_sync/...json` | Help page added as first shortcut |
| `__init__.py`, `setup.py`, `pyproject.toml`, `hooks.py` | Bump to 2.6.0 |

## Migration

No schema changes. No patch needed. Just `bench update --apps neotec_dual_sync`
and `bench --site SITE migrate` (which is a no-op for this release) followed
by `bench restart` so the new `app_include_js` registers.
