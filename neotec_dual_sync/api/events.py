"""
Neotec Dual Sync — Document Event Handlers.

These handlers run on every save of every document in the system, so they
must be cheap. The first thing each handler does is consult the in-process
scope cache (see `scope.py`); if the doctype isn't in scope, we return in
microseconds without touching the database.
"""
from __future__ import annotations

import frappe

from neotec_dual_sync.api import scope as _scope

# Map trigger_mode (config) -> set of event names that should fire it.
# Manual is a special case handled separately.
_TRIGGER_MAP = {
    "On Submit":  {"on_submit", "on_update_after_submit"},
    "On Insert":  {"after_insert"},
    "On Update":  {"on_update", "on_update_after_submit"},
    "Batch":      {"after_insert", "on_update", "on_submit"},
    "Both":       {"on_submit", "on_update_after_submit",
                   "after_insert", "on_update"},
    "Manual":     set(),  # Manual rules are only fired via the API endpoint
}


def _queue_if_matched(doc, event_name: str):
    """
    Decide whether this document save should be queued, and if so, create
    the Sync Log row. Returns the log doc on enqueue, else None.
    """
    doctype = doc.doctype

    # 1. Hard exclusion list — answered without any DB or cache lookup
    if _scope.excluded(doctype):
        return None

    # 2. Loopback guard. If a save is happening because we just received a
    #    document from the remote, the inbound applier sets a flag in
    #    `frappe.flags` for the duration of the request. Don't echo it back.
    if getattr(frappe.flags, "neotec_inbound_apply", False):
        return None

    # 3. Per-document loopback flag (only meaningful for doctypes where the
    #    operator chose to install the custom field — checked via getattr so
    #    it's a no-op when the field doesn't exist).
    if getattr(doc, "nxd_received_from_remote", 0):
        return None

    # 4. Fast-path scope filter. This is an O(1) check against an in-process
    #    frozenset; no DB query unless the cache is cold.
    if not _scope.is_in_scope(doctype, getattr(doc, "module", None)):
        return None

    # Manual is dispatched via API only; ignore real document events.
    if event_name == "manual":
        return _enqueue_manual(doc)

    # Now we know we have at least one rule for this doctype. Look up the
    # actual matching rules. We deliberately do this on the slow path —
    # it only runs when we already know the doctype is in scope.
    rules = _matching_rules_for(doctype, event_name)
    if not rules:
        return None

    queued = None
    for rule in rules:
        # Optional condition script — fail closed
        cond = rule.get("condition_script")
        if cond and not _eval_condition(cond, doc):
            continue

        queued = _create_log_row(doc, event_name, rule)

    return queued


def _enqueue_manual(doc):
    """Manual trigger — find any enabled rule for this doctype and enqueue."""
    rules = _matching_rules_for(doc.doctype, event_name=None, include_manual=True)
    if not rules:
        frappe.throw(f"No enabled sync rule for DocType '{doc.doctype}'.")
    rule = rules[0]
    return _create_log_row(doc, "manual", rule)


def _matching_rules_for(doctype: str, event_name: str | None,
                        include_manual: bool = False) -> list[dict]:
    """
    Return the list of rule rows (as plain dicts) for this doctype that
    should fire on `event_name`. Uses a single targeted SELECT and is cached
    per request to avoid repeated lookups during cascade updates.
    """
    cache_key = f"neotec_rules:{doctype}"
    cached = frappe.local.cache.get(cache_key) if hasattr(frappe.local, "cache") else None
    if cached is None:
        cached = frappe.db.sql(
            """
            SELECT name, source_doctype, target_doctype, trigger_mode,
                   mapping_profile, duplicate_policy, condition_script,
                   only_when_submitted
            FROM `tabNeotec Sync Rule`
            WHERE parent = %s
              AND parenttype = %s
              AND source_doctype = %s
              AND IFNULL(enabled, 0) = 1
            """,
            ("Neotec Sync Settings", "Neotec Sync Settings", doctype),
            as_dict=True,
        )
        if hasattr(frappe.local, "cache"):
            frappe.local.cache[cache_key] = cached

    if not cached:
        return []

    if event_name is None:
        # Manual — return all rules; caller picks one
        return [r for r in cached if include_manual or r.get("trigger_mode") != "Manual"]

    out = []
    for rule in cached:
        trigger = rule.get("trigger_mode") or "On Submit"
        events = _TRIGGER_MAP.get(trigger, set())
        if event_name in events:
            out.append(rule)
    return out


def _eval_condition(script: str, doc) -> bool:
    """Evaluate a Python condition script using safe_exec. Fail closed."""
    if not script or not script.strip():
        return True
    try:
        # Frappe v15 location: frappe.utils.safe_exec.safe_exec
        from frappe.utils.safe_exec import safe_exec
        local_vars = {"doc": doc, "result": True}
        safe_exec(script, _locals=local_vars)
        return bool(local_vars.get("result", True))
    except Exception:
        frappe.log_error(
            title="Neotec Sync: Condition Script Error",
            message=frappe.get_traceback(),
        )
        return False  # Fail closed — don't sync if condition errors


def _create_log_row(doc, event_name: str, rule: dict):
    """
    Insert a Queued sync log row using direct SQL — bypasses the heavy
    `frappe.get_doc(...).insert()` validation cycle. We don't need version
    tracking, hooks, or permissions on our own internal queue table.
    """
    name = frappe.generate_hash(length=20)
    tx_id = frappe.generate_hash(length=20)

    frappe.db.sql(
        """
        INSERT INTO `tabNeotec Sync Log`
            (name, creation, modified, modified_by, owner,
             reference_doctype, reference_name, event_name, direction,
             status, sync_transaction_id, rule_name, retry_count, idx)
        VALUES (%s, NOW(), NOW(), %s, %s,
                %s, %s, %s, 'Outbound',
                'Queued', %s, %s, 0, 0)
        """,
        (name, frappe.session.user or "Administrator",
         frappe.session.user or "Administrator",
         doc.doctype, doc.name, event_name, tx_id, rule.get("name")),
    )
    # No commit() here — Frappe will commit at the end of the request once,
    # together with the user's own document save. That's the whole point.
    return name


# ---------------------------------------------------------------------------
# Frappe doc_event entry points
# ---------------------------------------------------------------------------

def handle_on_submit(doc, method=None):
    _queue_if_matched(doc, "on_submit")


def handle_update_after_submit(doc, method=None):
    _queue_if_matched(doc, "on_update_after_submit")


def handle_after_insert(doc, method=None):
    _queue_if_matched(doc, "after_insert")


def handle_on_update(doc, method=None):
    """
    on_update fires on EVERY field-level save. The scope cache short-circuits
    out-of-scope doctypes in O(1), so this is cheap to leave registered.
    """
    _queue_if_matched(doc, "on_update")
