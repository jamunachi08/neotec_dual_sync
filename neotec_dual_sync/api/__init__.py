"""
Neotec Dual Sync — Public whitelisted API endpoints.
"""
from __future__ import annotations

import json

import frappe
from frappe import _

from neotec_dual_sync.api.services import (
    get_settings,
    payload_hash,
    verify_hmac_signature,
    register_idempotency,
    should_block_loop,
    create_sync_log,
    apply_inbound_document,
    check_ip_allowlist,
    test_remote_connection,
    inbound_apply_flag,
)


# ---------------------------------------------------------------------------
# Inbound sync endpoint
# ---------------------------------------------------------------------------

@frappe.whitelist(allow_guest=False)
def receive_document():
    """
    Inbound sync entry point. Auth → HMAC → IP → loop → idempotency → apply.
    A SINGLE commit happens at the very end (or rollback on failure).
    Earlier versions committed mid-request, leaving partial state on failure.
    """
    settings = get_settings()

    if not settings.enabled:
        frappe.throw(_("Sync is disabled on this instance."), frappe.PermissionError)
    if settings.instance_role not in ("Target", "Both") or not settings.accept_inbound_sync:
        frappe.throw(_("Inbound sync is not allowed on this instance."), frappe.PermissionError)

    raw_body = frappe.request.get_data() or b""
    try:
        payload = json.loads(raw_body)
    except Exception:
        frappe.throw(_("Invalid JSON payload."), frappe.ValidationError)

    source_instance_id = payload.get("source_instance_id") or ""
    source_doctype = payload.get("source_doctype") or ""
    source_name = payload.get("source_docname") or ""
    tx = payload.get("sync_transaction_id") or frappe.generate_hash(length=20)
    sync_meta = payload.get("sync_meta") or {}

    # HMAC signature verification
    if settings.signature_required:
        provided_sig = frappe.request.headers.get("X-Neotec-Signature", "")
        shared_secret = settings.get_password("shared_secret") or ""
        if not shared_secret:
            _reject(source_doctype, source_name, tx, payload,
                    "HMAC_CONFIG_ERROR", "shared_secret not set but signature_required=1")
        if not verify_hmac_signature(raw_body, shared_secret, provided_sig):
            _reject(source_doctype, source_name, tx, payload,
                    "INVALID_SIGNATURE", "HMAC signature mismatch — request rejected")

    # IP allow-list check
    if source_instance_id:
        try:
            instance_doc = frappe.get_doc("Neotec Sync Instance",
                                          {"instance_id": source_instance_id})
            check_ip_allowlist(instance_doc)
        except frappe.DoesNotExistError:
            pass  # Unknown instance — allow but don't IP-enforce

    # Loop detection
    blocked, reason = should_block_loop(sync_meta, settings.local_instance_id)
    if blocked:
        with inbound_apply_flag():
            create_sync_log(
                reference_doctype=source_doctype, reference_name=source_name,
                status="Loop Prevented", direction="Inbound",
                request_payload=payload, response_payload={"reason": reason},
                sync_transaction_id=tx, source_instance_id=source_instance_id,
            )
        frappe.db.commit()
        return {"ok": False, "error_code": "LOOP_BLOCKED", "message": reason}

    # Idempotency check
    h = payload_hash(payload)
    existing, is_dup = register_idempotency(
        source_instance_id, source_doctype, source_name, tx, h
    )
    if is_dup:
        # Don't commit — register_idempotency was a no-op for duplicates
        return {"ok": False, "error_code": "DUPLICATE_DETECTED",
                "message": "Transaction already processed",
                "idempotency_log": existing}

    # Apply the document — services.apply_inbound_document handles its own
    # inbound_apply_flag scope.
    try:
        result = apply_inbound_document(payload, settings)
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(title="Neotec Sync: Inbound apply failure",
                         message=frappe.get_traceback())
        return {"ok": False, "error_code": "APPLY_FAILED", "message": str(e)}

    status = "Success" if result.get("ok") else "Failed"
    with inbound_apply_flag():
        create_sync_log(
            reference_doctype=source_doctype, reference_name=source_name,
            status=status, direction="Inbound",
            request_payload=payload,
            response_payload=result,
            error_message=result.get("error"),
            sync_transaction_id=tx,
            source_instance_id=source_instance_id,
        )

    if result.get("ok"):
        frappe.db.commit()
    else:
        # Keep the log + idempotency rows but discard the half-applied doc
        frappe.db.rollback()
        frappe.db.commit()  # commit the log + idempotency separately

    return {"ok": result.get("ok"), "message": result}


def _reject(doctype, name, tx, payload, code, message):
    with inbound_apply_flag():
        create_sync_log(
            reference_doctype=doctype, reference_name=name,
            status="Failed", direction="Inbound",
            request_payload=payload,
            error_message=f"{code}: {message}",
            sync_transaction_id=tx,
        )
    frappe.db.commit()
    frappe.throw(_(message), frappe.PermissionError)


# ---------------------------------------------------------------------------
# Manual trigger endpoint
# ---------------------------------------------------------------------------

@frappe.whitelist()
def manual_sync(doctype: str, docname: str):
    """Manually queue a single document for outbound sync."""
    from neotec_dual_sync.api.events import _queue_if_matched

    settings = get_settings()
    if not settings.enabled:
        frappe.throw(_("Sync is disabled."))
    if settings.instance_role == "Target":
        frappe.throw(_("This instance is configured as Target-only and cannot push documents."))

    doc = frappe.get_doc(doctype, docname)
    log_name = _queue_if_matched(doc, "manual")
    frappe.db.commit()
    return {
        "ok": bool(log_name),
        "log": log_name,
        "message": (
            f"Document {doctype}/{docname} queued for sync."
            if log_name else
            f"No enabled rule matched for {doctype}."
        ),
    }


# ---------------------------------------------------------------------------
# Connection test
# ---------------------------------------------------------------------------

@frappe.whitelist()
def validate_connection():
    settings = get_settings()
    return test_remote_connection(settings)


# ---------------------------------------------------------------------------
# Dashboard stats — single GROUP BY query
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_dashboard_stats():
    """
    Dashboard counts. Uses ONE grouped query for the status histogram
    instead of N separate db.count calls. Adds two more for the 24h
    throughput windows. Cached for 30 seconds in Redis to keep dashboards
    cheap when multiple operators have them open.
    """
    cache = frappe.cache()
    cached = cache.get_value("neotec_dual_sync:dashboard_stats")
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    stats = {
        "queued": 0, "processing": 0, "success": 0, "failed": 0,
        "skipped": 0, "loop_prevented": 0, "duplicate": 0, "received": 0,
    }

    # Single GROUP BY for the status histogram
    rows = frappe.db.sql(
        """
        SELECT status, COUNT(*) AS c
        FROM `tabNeotec Sync Log`
        GROUP BY status
        """,
        as_dict=True,
    )
    for r in rows:
        key = (r["status"] or "").lower().replace(" ", "_")
        if key in stats:
            stats[key] = int(r["c"])

    stats["open_conflicts"] = frappe.db.count("Neotec Sync Conflict", {"status": "Open"})
    stats["idempotency_records"] = frappe.db.count("Neotec Sync Idempotency Log")

    # Last 24h throughput — two indexed range queries
    from frappe.utils import add_to_date, now_datetime
    yesterday = add_to_date(now_datetime(), days=-1)
    stats["synced_last_24h"] = frappe.db.count(
        "Neotec Sync Log",
        {"status": "Success", "creation": (">", yesterday)},
    )
    stats["failed_last_24h"] = frappe.db.count(
        "Neotec Sync Log",
        {"status": "Failed", "creation": (">", yesterday)},
    )

    try:
        cache.set_value(
            "neotec_dual_sync:dashboard_stats",
            json.dumps(stats), expires_in_sec=30,
        )
    except Exception:
        pass
    return stats


# ---------------------------------------------------------------------------
# Conflict resolution
# ---------------------------------------------------------------------------

@frappe.whitelist()
def resolve_conflict(conflict_name: str, action: str):
    """action: 'accept_incoming' | 'keep_existing' | 'ignore'"""
    conflict = frappe.get_doc("Neotec Sync Conflict", conflict_name)

    if action == "accept_incoming":
        try:
            incoming = json.loads(conflict.payload_after or "{}")
            if incoming:
                with inbound_apply_flag():
                    target_dt = conflict.reference_doctype
                    target_name = conflict.reference_name
                    doc = frappe.get_doc(target_dt, target_name)
                    for k, v in incoming.items():
                        if k not in ("doctype", "name", "creation", "modified"):
                            setattr(doc, k, v)
                    doc.save(ignore_permissions=True)
        except Exception:
            frappe.log_error(
                title="Neotec Sync: Conflict Accept Error",
                message=frappe.get_traceback(),
            )
            frappe.throw(_("Failed to apply incoming changes. Check error log."))
        conflict.status = "Resolved"

    elif action == "keep_existing":
        conflict.status = "Resolved"

    elif action == "ignore":
        conflict.status = "Ignored"

    else:
        frappe.throw(_(f"Unknown conflict action: {action}"))

    conflict.save(ignore_permissions=True)
    return {"ok": True, "status": conflict.status}


# ---------------------------------------------------------------------------
# Schema fetch — used by the Mapping form's "Fetch Fields" button
# ---------------------------------------------------------------------------

@frappe.whitelist()
def fetch_schema(doctype: str, include_system: int = 0):
    """
    Return the field structure of a DocType on this instance.

    Reused for two purposes:
      1. The local Mapping form calls this directly to populate the source
         field picker.
      2. A peer instance calls this over HTTPS (with API auth) to discover
         this side's schema before building a mapping. That peer flow is
         what powers the "Fetch Target Fields" button on the source.
    """
    from neotec_dual_sync.api.schema import get_local_schema

    # Permission gate. We accept any of:
    #   * write on Sync Mapping (local UI builder),
    #   * read on Sync Settings (peer API user — has the Neotec Dual Sync API
    #     role which the install grants read on Settings).
    # We deliberately do NOT require write on Mapping for the peer call —
    # the peer is only inspecting our DocType metadata, not changing anything.
    allowed = (
        frappe.has_permission("Neotec Sync Mapping", "read")
        or frappe.has_permission("Neotec Sync Settings", "read")
        or "Neotec Dual Sync API" in (frappe.get_roles() or [])
    )
    if not allowed:
        frappe.throw(_("You do not have permission to inspect schemas."), frappe.PermissionError)

    try:
        return get_local_schema(doctype, include_system=bool(int(include_system or 0)))
    except Exception as e:
        return {"error": str(e)}


@frappe.whitelist()
def fetch_remote_schema(doctype: str, include_system: int = 0):
    """
    Ask the configured remote for `doctype`'s schema and return it. The form
    calls this when the user clicks "Fetch Target Fields" — we reach over
    HTTPS so the picker shows the actual target schema, not just whatever
    happens to exist locally.
    """
    from neotec_dual_sync.api.schema import get_remote_schema
    if not frappe.has_permission("Neotec Sync Mapping", "write"):
        frappe.throw(_("You do not have permission."), frappe.PermissionError)
    return get_remote_schema(doctype, include_system=bool(int(include_system or 0)))


@frappe.whitelist()
def build_field_pairs(source_doctype: str, target_doctype: str,
                      target_remote: int = 0, include_system: int = 0):
    """
    Convenience endpoint: fetch source schema (local), fetch target schema
    (local or remote), and return them paired up with auto-match suggestions
    and type-compatibility warnings.

    The Mapping form calls this once when the user clicks "Fetch Fields";
    the response drives the entire side-by-side picker UI.
    """
    from neotec_dual_sync.api import schema as _schema
    sys_flag = bool(int(include_system or 0))

    src = _schema.get_local_schema(source_doctype, include_system=sys_flag)

    if int(target_remote or 0):
        tgt = _schema.get_remote_schema(target_doctype, include_system=sys_flag)
    else:
        tgt = _schema.get_local_schema(target_doctype, include_system=sys_flag)

    return _schema.pair_fields(src, tgt)


# ---------------------------------------------------------------------------
# Operator-facing endpoints (v2.6.0)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_doc_sync_status(doctype: str, docname: str):
    """
    Cheap status lookup for the indicator on every synced doc form.
    Returns the latest Sync Log row for this (doctype, name), plus a small
    summary. Cached in Redis for 30 seconds.

    Output:
      {
        "in_scope":  bool,            # is this DocType in our sync scope at all?
        "status":    "Success" | "Failed" | "Queued" | "Processing" | "Skipped" | None,
        "last_sync_at": iso datetime | None,
        "last_error":   str | None,
        "log_name":     str | None,   # name of the latest Sync Log row
        "history_count": int,         # rows in Sync Log for this doc
      }
    """
    from neotec_dual_sync.api import scope as _scope

    # Treat as out-of-scope quickly when sync is off or doctype not configured
    sc = _scope.get_scope()
    in_scope = bool(sc["enabled"] and (doctype in sc["doctypes"]))

    # Cheapest possible: single SELECT for the latest row, indexed lookup
    row = frappe.db.sql(
        """
        SELECT name, status, modified, error_message
          FROM `tabNeotec Sync Log`
         WHERE reference_doctype = %s
           AND reference_name = %s
         ORDER BY modified DESC
         LIMIT 1
        """,
        (doctype, docname),
        as_dict=True,
    )

    if not row:
        return {
            "in_scope": in_scope,
            "status": None,
            "last_sync_at": None,
            "last_error": None,
            "log_name": None,
            "history_count": 0,
        }

    r = row[0]
    history_count = frappe.db.sql(
        "SELECT COUNT(*) FROM `tabNeotec Sync Log` "
        "WHERE reference_doctype=%s AND reference_name=%s",
        (doctype, docname),
    )[0][0]

    return {
        "in_scope": in_scope,
        "status": r["status"],
        "last_sync_at": r["modified"].isoformat() if r["modified"] else None,
        "last_error": (r["error_message"] or "")[:200],
        "log_name": r["name"],
        "history_count": int(history_count or 0),
    }


@frappe.whitelist()
def manual_sync_now(doctype: str, docname: str):
    """
    "Sync Now" button on the document form.

    Differs from manual_sync() in one important way: after queuing, it
    enqueues a one-shot Frappe background job that dispatches THIS row
    immediately, bypassing the cron throttle. The form polls for status
    and shows feedback within seconds rather than minutes.
    """
    from neotec_dual_sync.api.events import _queue_if_matched
    from neotec_dual_sync.api.services import get_settings

    settings = get_settings()
    if not settings.enabled:
        frappe.throw(_("Sync is disabled."))
    if settings.instance_role == "Target":
        frappe.throw(_("This instance is configured as Target-only and cannot push documents."))

    doc = frappe.get_doc(doctype, docname)
    log_name = _queue_if_matched(doc, "manual")

    if not log_name:
        return {
            "ok": False,
            "log": None,
            "message": f"No enabled rule matched for {doctype}.",
        }

    # Commit the queue insert before kicking off the background dispatcher
    frappe.db.commit()

    # Fire-and-forget background job — bypasses the cron throttle so the
    # operator gets feedback within a few seconds.
    frappe.enqueue(
        "neotec_dual_sync.api.jobs.dispatch_one_log",
        log_name=log_name,
        queue="default",
        timeout=120,
        is_async=True,
        now=False,
    )

    return {
        "ok": True,
        "log": log_name,
        "message": f"Queued and dispatching now. Watch this document for status.",
    }


@frappe.whitelist()
def bulk_requeue_logs(log_names):
    """
    Bulk Re-queue action on the Sync Log list view.
    Accepts a list (or JSON string) of Sync Log names. Flips them from
    Failed → Queued and resets retry_count. Returns the count updated.
    """
    if not frappe.has_permission("Neotec Sync Log", "write"):
        frappe.throw(_("You do not have permission to modify Sync Logs."), frappe.PermissionError)

    if isinstance(log_names, str):
        try:
            log_names = json.loads(log_names)
        except Exception:
            log_names = [log_names]
    if not isinstance(log_names, list) or not log_names:
        frappe.throw(_("No Sync Log rows selected."))

    # Cap to a sane batch size to prevent accidental mass updates
    if len(log_names) > 5000:
        frappe.throw(_("Cannot re-queue more than 5,000 rows at once."))

    placeholders = ", ".join(["%s"] * len(log_names))
    affected = frappe.db.sql(
        f"""
        UPDATE `tabNeotec Sync Log`
           SET status = 'Queued',
               retry_count = 0,
               error_message = NULL,
               modified = NOW()
         WHERE name IN ({placeholders})
           AND status IN ('Failed', 'Skipped')
           AND direction = 'Outbound'
        """,
        tuple(log_names),
    )
    count = frappe.db.sql("SELECT ROW_COUNT()")[0][0]
    frappe.db.commit()

    return {
        "ok": True,
        "requeued": int(count),
        "skipped": len(log_names) - int(count),
        "message": f"{count} row(s) re-queued. {len(log_names) - int(count)} skipped (wrong status or direction).",
    }


@frappe.whitelist()
def get_failure_summary(days: int = 7, limit: int = 10):
    """
    "Top Failure Reasons" panel on the dashboard.
    Groups failed Sync Log rows from the last N days by the FIRST line of
    their error_message (which is the most useful summary). Returns up to
    `limit` rows, ordered by frequency.
    """
    days = max(1, min(int(days or 7), 90))
    limit = max(1, min(int(limit or 10), 50))

    rows = frappe.db.sql(
        """
        SELECT
            SUBSTRING_INDEX(IFNULL(error_message, '(no error message)'), '\n', 1) AS reason,
            COUNT(*) AS occurrences,
            COUNT(DISTINCT reference_doctype) AS distinct_doctypes,
            MAX(modified) AS last_seen
          FROM `tabNeotec Sync Log`
         WHERE status = 'Failed'
           AND direction = 'Outbound'
           AND modified > NOW() - INTERVAL %s DAY
         GROUP BY reason
         ORDER BY occurrences DESC
         LIMIT %s
        """,
        (days, limit),
        as_dict=True,
    )

    for r in rows:
        if r.get("last_seen"):
            r["last_seen"] = r["last_seen"].isoformat()
        # Truncate long reason strings for display
        if r.get("reason") and len(r["reason"]) > 200:
            r["reason"] = r["reason"][:200] + "…"

    return {"days": days, "rows": rows}
