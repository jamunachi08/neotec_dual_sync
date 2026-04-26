"""
Neotec Dual Sync — Scheduled Jobs.

Design notes:

  * Each job's first action is a cheap probe (EXISTS / cached flag) that
    answers "is there anything to do?" in microseconds. If not, return.
  * Throttling — successive dispatch runs within `min_dispatch_interval_seconds`
    (configurable, default 60) are skipped. A frequent cron is fine when the
    body is gated.
  * We use direct SQL UPDATE for status transitions instead of
    `get_doc().save()`, which would run validations and version tracking we
    don't need on our own internal queue table.
  * Cleanup deletes are LIMIT-batched to avoid long table locks on big sites.
"""
from __future__ import annotations

import time
import traceback

import frappe
from frappe.utils import now_datetime, add_to_date

from neotec_dual_sync.api import scope as _scope


_THROTTLE_CACHE_KEY = "neotec_dual_sync:last_dispatch_at"


# ---------------------------------------------------------------------------
# Dispatch — outbound queue processor
# ---------------------------------------------------------------------------

def process_batch_queue():
    """
    Pick up Queued outbound rows and dispatch them. Short-circuits when:
      * sync is globally disabled
      * the instance is Target-only
      * outbound is disabled
      * no rows are queued
      * we ran too recently (throttle)
    """
    sc = _scope.get_scope()
    if not sc["enabled"] or sc["role"] == "Target" or not sc["outbound"]:
        return

    # Throttle — skip if we ran more recently than min_dispatch_interval_seconds
    if not _acquire_throttle(sc["min_dispatch"]):
        return

    # Cheap EXISTS probe — avoids any further work on an empty queue
    has_rows = frappe.db.sql(
        """
        SELECT 1 FROM `tabNeotec Sync Log`
        WHERE status = 'Queued' AND direction = 'Outbound'
        LIMIT 1
        """
    )
    if not has_rows:
        return

    # Load settings ONCE for this run — reused for every row
    settings = frappe.get_cached_doc("Neotec Sync Settings", "Neotec Sync Settings")
    batch_size = max(1, min(int(settings.batch_size or 50), 500))

    queued = frappe.db.sql(
        """
        SELECT name, reference_doctype, reference_name,
               sync_transaction_id, rule_name, retry_count
        FROM `tabNeotec Sync Log`
        WHERE status = 'Queued' AND direction = 'Outbound'
        ORDER BY creation ASC
        LIMIT %s
        """,
        (batch_size,),
        as_dict=True,
    )

    if not queued:
        return

    # Build a rule lookup ONCE so each row doesn't re-iterate the rules table
    rule_index = _build_rule_index(settings)

    success = 0
    failed = 0
    for row in queued:
        try:
            _dispatch_one(row, settings, rule_index)
            success += 1
        except Exception:
            failed += 1
            # Log only the row name — full traceback goes to Error Log only
            # if log_level is DEBUG, to avoid flooding Error Log on incidents.
            if (settings.log_level or "INFO") == "DEBUG":
                frappe.log_error(
                    title=f"Neotec Sync: Dispatch error for {row['name']}",
                    message=traceback.format_exc(),
                )
            _set_log_status(
                row["name"],
                status="Failed",
                error_message=traceback.format_exc()[-500:],
            )

    # Single commit at end of run — much cheaper than per-row
    frappe.db.commit()


def _acquire_throttle(min_seconds: int) -> bool:
    """
    Return True if at least `min_seconds` have elapsed since the last
    successful dispatch. Updates the cache atomically-enough for our needs.
    """
    if min_seconds <= 0:
        return True
    try:
        last = frappe.cache().get_value(_THROTTLE_CACHE_KEY)
        now = time.time()
        if last and (now - float(last)) < min_seconds:
            return False
        frappe.cache().set_value(
            _THROTTLE_CACHE_KEY, str(now), expires_in_sec=86400
        )
    except Exception:
        # If cache is unavailable, fall through and run anyway
        pass
    return True


def _build_rule_index(settings) -> dict:
    """
    Map rule name + source_doctype to a lightweight rule descriptor.
    Built once per dispatch run, reused across all rows.
    """
    by_name: dict[str, dict] = {}
    by_doctype: dict[str, dict] = {}
    for r in (settings.rules or []):
        if not getattr(r, "enabled", 1):
            continue
        descriptor = {
            "name":             getattr(r, "name", None),
            "source_doctype":   r.source_doctype,
            "target_doctype":   r.target_doctype,
            "trigger_mode":     getattr(r, "trigger_mode", "On Submit"),
            "mapping_profile":  getattr(r, "mapping_profile", None),
            "duplicate_policy": getattr(r, "duplicate_policy", "Skip If Unchanged"),
        }
        if descriptor["name"]:
            by_name[descriptor["name"]] = descriptor
        # First rule per doctype wins for fallback
        by_doctype.setdefault(r.source_doctype, descriptor)
    return {"by_name": by_name, "by_doctype": by_doctype}


def _dispatch_one(row: dict, settings, rule_index: dict):
    """Dispatch a single queued log row. Lazy-imports services to keep
    handler-import cost low for sites that never run dispatch."""
    from neotec_dual_sync.api.services import push_document_to_remote

    name = row["name"]
    doctype = row["reference_doctype"]
    docname = row["reference_name"]
    tx_id = row["sync_transaction_id"]

    if not doctype or not docname:
        _set_log_status(
            name, status="Skipped",
            error_message="Missing reference_doctype or reference_name",
        )
        return

    # Mark Processing — single column UPDATE
    _set_log_status(name, status="Processing")

    try:
        doc = frappe.get_doc(doctype, docname)
    except frappe.DoesNotExistError:
        _set_log_status(
            name, status="Skipped",
            error_message=f"Document {doctype}/{docname} no longer exists",
        )
        return

    # Find the rule — by name first, then by doctype fallback
    rule = (
        rule_index["by_name"].get(row.get("rule_name"))
        or rule_index["by_doctype"].get(doctype)
    )
    if not rule:
        _set_log_status(
            name, status="Skipped",
            error_message=f"No matching enabled rule for {doctype}",
        )
        return

    sync_meta = {"route_trace": [], "hop_count": 0}
    result = push_document_to_remote(doc, rule, settings, tx_id, sync_meta)

    if result.get("dry_run"):
        _set_log_status(
            name, status="Success",
            response_payload=result.get("payload"),
            error_message="[Dry Run — not actually sent]",
        )
        return

    if result.get("ok"):
        _set_log_status(
            name, status="Success",
            response_payload=result.get("response"),
            error_message=None,
        )
        return

    # Failure — increment retry counter; max_retries decides Failed vs Queued
    new_retry = int(row.get("retry_count") or 0) + 1
    max_retries = int(settings.max_retries or 3)
    final_status = "Failed" if new_retry > max_retries else "Failed"
    # NOTE: we always write Failed here. Re-queue happens in retry_failed_syncs
    # after the back-off window. This avoids hot-looping a failing endpoint.
    _set_log_status(
        name,
        status=final_status,
        error_message=(result.get("error") or "Unknown error")[:500],
        response_payload=result.get("response"),
        retry_count=new_retry,
    )


def _set_log_status(log_name: str, **fields):
    """
    Direct SQL UPDATE on `tabNeotec Sync Log`. Avoids `frappe.get_doc`,
    `save()`, version tracking, and per-call commits.
    """
    if not log_name:
        return
    if not fields:
        return

    import json
    sets = []
    values = []
    for k, v in fields.items():
        if isinstance(v, (dict, list)):
            v = json.dumps(v, default=str)[:65000]  # MariaDB TEXT-safe
        sets.append(f"`{k}` = %s")
        values.append(v)
    sets.append("`modified` = NOW()")
    values.append(log_name)
    frappe.db.sql(
        f"UPDATE `tabNeotec Sync Log` SET {', '.join(sets)} WHERE name = %s",
        tuple(values),
    )


# ---------------------------------------------------------------------------
# Retry — re-queue Failed rows whose back-off window has elapsed
# ---------------------------------------------------------------------------

def retry_failed_syncs():
    """
    Re-queue Failed rows that have:
      * retry_count < max_retries
      * been Failed for at least `interval * 2^retry_count` minutes
    """
    sc = _scope.get_scope()
    if not sc["enabled"] or sc["role"] == "Target":
        return

    settings = frappe.get_cached_doc("Neotec Sync Settings", "Neotec Sync Settings")
    max_retries = int(settings.max_retries or 3)
    interval_mins = int(settings.retry_interval_minutes or 10)

    # Cheap probe — bail if no failed rows are eligible
    has_rows = frappe.db.sql(
        """
        SELECT 1 FROM `tabNeotec Sync Log`
        WHERE status = 'Failed' AND direction = 'Outbound'
          AND IFNULL(retry_count, 0) < %s
        LIMIT 1
        """,
        (max_retries,),
    )
    if not has_rows:
        return

    failed = frappe.db.sql(
        """
        SELECT name, retry_count, modified
        FROM `tabNeotec Sync Log`
        WHERE status = 'Failed' AND direction = 'Outbound'
          AND IFNULL(retry_count, 0) < %s
        ORDER BY modified ASC
        LIMIT 200
        """,
        (max_retries,),
        as_dict=True,
    )

    now = now_datetime()
    requeued = 0
    for row in failed:
        rc = int(row["retry_count"] or 0)
        wait_minutes = interval_mins * (2 ** rc)
        retry_after = add_to_date(row["modified"], minutes=wait_minutes)
        if now >= retry_after:
            frappe.db.sql(
                """
                UPDATE `tabNeotec Sync Log`
                SET status = 'Queued', modified = NOW()
                WHERE name = %s
                """,
                (row["name"],),
            )
            requeued += 1

    if requeued:
        frappe.db.commit()


# ---------------------------------------------------------------------------
# Cleanup — daily housekeeping, batched
# ---------------------------------------------------------------------------

def cleanup_old_logs():
    """
    Daily housekeeping. Deletes are LIMIT-batched and committed per batch
    to avoid long table locks on sites with large log volumes.
    """
    settings = frappe.get_cached_doc("Neotec Sync Settings", "Neotec Sync Settings")
    log_retention_days = int(getattr(settings, "log_retention_days", 30) or 30)
    idem_retention_days = int(getattr(settings, "idempotency_retention_days", 60) or 60)

    cutoff_logs = add_to_date(now_datetime(), days=-log_retention_days)
    cutoff_idem = add_to_date(now_datetime(), days=-idem_retention_days)

    # Delete in 5,000-row batches
    _batched_delete(
        """
        DELETE FROM `tabNeotec Sync Log`
        WHERE status IN ('Success', 'Skipped', 'Duplicate', 'Loop Prevented')
          AND creation < %s
        LIMIT 5000
        """,
        (cutoff_logs,),
    )

    _batched_delete(
        """
        DELETE FROM `tabNeotec Sync Idempotency Log`
        WHERE creation < %s
        LIMIT 5000
        """,
        (cutoff_idem,),
    )


def _batched_delete(sql: str, params: tuple, max_iterations: int = 100):
    """Repeat a LIMIT-bounded DELETE until no rows are affected, committing
    after each batch. Bounded by `max_iterations` as a safety stop."""
    for _ in range(max_iterations):
        frappe.db.sql(sql, params)
        affected = frappe.db.sql("SELECT ROW_COUNT()")[0][0]
        frappe.db.commit()
        if not affected:
            return


# ---------------------------------------------------------------------------
# Immediate single-row dispatch — used by the "Sync Now" button on documents
# ---------------------------------------------------------------------------

def dispatch_one_log(log_name: str):
    """
    Dispatch ONE Sync Log row right now, bypassing the cron throttle.
    Called from frappe.enqueue() by manual_sync_now(). The user is watching
    their screen — they need feedback in seconds, not at the next */5 cron.

    This does NOT update the throttle key, so a normal cron run that fires
    seconds later still proceeds normally for any other queued rows.
    """
    sc = _scope.get_scope()
    if not sc["enabled"] or sc["role"] == "Target" or not sc["outbound"]:
        _set_log_status(log_name, status="Skipped",
                        error_message="Sync disabled or instance is Target-only")
        frappe.db.commit()
        return

    settings = frappe.get_cached_doc("Neotec Sync Settings", "Neotec Sync Settings")
    rule_index = _build_rule_index(settings)

    row = frappe.db.sql(
        """
        SELECT name, reference_doctype, reference_name,
               sync_transaction_id, rule_name, retry_count
          FROM `tabNeotec Sync Log`
         WHERE name = %s
        """,
        (log_name,),
        as_dict=True,
    )
    if not row:
        return  # row gone — nothing to do
    row = row[0]

    try:
        _dispatch_one(row, settings, rule_index)
    except Exception:
        if (settings.log_level or "WARN") == "DEBUG":
            frappe.log_error(
                title=f"Neotec Sync: Immediate dispatch error for {log_name}",
                message=traceback.format_exc(),
            )
        _set_log_status(
            log_name,
            status="Failed",
            error_message=traceback.format_exc()[-500:],
        )

    frappe.db.commit()
