"""
Neotec Dual Sync — Scope cache.

This module is the *fast path* for document event handlers. The Frappe `*`
doc_events fire on every save of every document in the entire system. If we
were to hit the database from each one, the server would melt under any real
ERP load. So we maintain an in-process snapshot of the active sync scope:

    {
        "enabled":         bool,
        "role":            "Source" | "Target" | "Both",
        "outbound":        bool,
        "doctypes":        frozenset[str],   # doctypes that have a rule
        "modules":         frozenset[str],   # modules in the global allow-list
        "include_drafts":  bool,
        "min_dispatch":    int,              # min seconds between dispatch runs
    }

The cache is rebuilt lazily on the first call after invalidation. Invalidation
is driven by Frappe doc_events on Settings / Rule / Mapping (see hooks.py).

Excluded internal doctypes are checked first and answered in O(1) without
even touching the cache.
"""
from __future__ import annotations

import time
import frappe

# DocTypes that must NEVER trigger sync — these are our own framework + Frappe
# internals that would either loop or generate noise. Hard-coded so we can
# answer in O(1) without ever loading settings.
_EXCLUDED_DOCTYPES = frozenset({
    "Neotec Sync Log",
    "Neotec Sync Batch",
    "Neotec Sync Settings",
    "Neotec Sync Idempotency Log",
    "Neotec Sync Conflict",
    "Neotec Sync Rule",
    "Neotec Sync Mapping",
    "Neotec Sync Field Map",
    "Neotec Sync Mapping Row",
    "Neotec Sync Instance",
    "Neotec Sync Route Policy",
    "Neotec Sync API Key",
    "Neotec Sync Dashboard",
    "Neotec Sync Module Filter",
    # Frappe internals — never sync these
    "Error Log",
    "Activity Log",
    "Access Log",
    "Version",
    "Scheduled Job Log",
    "Email Queue",
    "Communication",
    "DocShare",
    "Document Follow",
    "View Log",
    "Route History",
    "Webhook Request Log",
    "Notification Log",
    "Energy Point Log",
    "Console Log",
    "Custom Field",
    "Property Setter",
    "DocType",
    "DocField",
    "DocPerm",
})


# Module-level cache. Per-process; in a multi-worker setup each worker has
# its own. The cache is small (a handful of frozensets and primitives), so
# duplication is cheap.
_SCOPE_CACHE: dict | None = None
_SCOPE_TTL_SECONDS = 300  # hard upper bound; force a rebuild every 5 minutes
_SCOPE_LOADED_AT: float = 0.0


def excluded(doctype: str) -> bool:
    """O(1) check for system / framework doctypes we never sync."""
    return doctype in _EXCLUDED_DOCTYPES


def get_scope() -> dict:
    """
    Return the cached scope snapshot, building it if missing or expired.
    Safe to call on every doc save — typical cost is one dict lookup.
    """
    global _SCOPE_CACHE, _SCOPE_LOADED_AT

    now = time.monotonic()
    if _SCOPE_CACHE is not None and (now - _SCOPE_LOADED_AT) < _SCOPE_TTL_SECONDS:
        return _SCOPE_CACHE

    _SCOPE_CACHE = _build_scope()
    _SCOPE_LOADED_AT = now
    return _SCOPE_CACHE


def invalidate_scope_cache(doc=None, method=None):
    """Drop the cached scope. Called from doc_events when config changes."""
    global _SCOPE_CACHE, _SCOPE_LOADED_AT
    _SCOPE_CACHE = None
    _SCOPE_LOADED_AT = 0.0
    # Best-effort cluster-wide invalidation via Frappe's redis cache so other
    # workers also rebuild on their next request.
    try:
        frappe.cache().delete_value("neotec_dual_sync:scope_version")
        frappe.cache().set_value(
            "neotec_dual_sync:scope_version", str(time.time()), expires_in_sec=86400
        )
    except Exception:
        pass


def is_in_scope(doctype: str, module: str | None = None) -> bool:
    """
    Fast-path used by event handlers BEFORE doing any work.
    Returns False when:
      * the doctype is on the framework exclusion list
      * sync is globally disabled
      * the instance is Target-only (does not push)
      * outbound sync is turned off
      * the doctype is not covered by any enabled rule
      * a module allow-list is configured and the doctype's module is not in it
    """
    if excluded(doctype):
        return False

    scope = get_scope()
    if not scope["enabled"]:
        return False
    if scope["role"] == "Target":
        return False
    if not scope["outbound"]:
        return False
    if doctype not in scope["doctypes"]:
        return False

    # Optional module-level allow-list. If empty -> no module filter applied.
    if scope["modules"]:
        if module is None:
            try:
                module = frappe.db.get_value("DocType", doctype, "module")
            except Exception:
                module = None
        if module not in scope["modules"]:
            return False

    return True


def _build_scope() -> dict:
    """
    Build the cached snapshot. Runs at most once per TTL window per worker.
    Uses cheap SELECTs — never loads the full Settings document.
    """
    default = {
        "enabled":        False,
        "role":           "Source",
        "outbound":       False,
        "doctypes":       frozenset(),
        "modules":        frozenset(),
        "include_drafts": False,
        "min_dispatch":   60,
    }

    try:
        # Single targeted SELECT — much cheaper than frappe.get_single
        row = frappe.db.get_value(
            "Neotec Sync Settings",
            "Neotec Sync Settings",
            ["enabled", "instance_role", "allow_outbound_sync",
             "min_dispatch_interval_seconds", "include_drafts_in_scope"],
            as_dict=True,
        )
    except Exception:
        return default

    if not row:
        return default

    if not row.get("enabled"):
        # Stop here — no need to enumerate rules if globally disabled
        default["role"] = row.get("instance_role") or "Source"
        return default

    # Pull only the columns we need from rule rows; avoids loading a full
    # child table object graph.
    try:
        rules = frappe.db.sql(
            """
            SELECT source_doctype
            FROM `tabNeotec Sync Rule`
            WHERE parent = %s
              AND parenttype = %s
              AND IFNULL(enabled, 0) = 1
              AND source_doctype IS NOT NULL
              AND source_doctype != ''
            """,
            ("Neotec Sync Settings", "Neotec Sync Settings"),
            as_dict=True,
        )
    except Exception:
        rules = []

    doctypes = frozenset(r["source_doctype"] for r in rules if r.get("source_doctype"))

    # Optional module filter — read from the dedicated child table
    try:
        modules = frappe.db.sql(
            """
            SELECT module_name
            FROM `tabNeotec Sync Module Filter`
            WHERE parent = %s
              AND parenttype = %s
              AND IFNULL(enabled, 0) = 1
            """,
            ("Neotec Sync Settings", "Neotec Sync Settings"),
            as_dict=True,
        )
        module_set = frozenset(
            m["module_name"] for m in modules if m.get("module_name")
        )
    except Exception:
        # Child doctype may not exist on first migration — fail open
        module_set = frozenset()

    return {
        "enabled":        bool(row.get("enabled")),
        "role":           row.get("instance_role") or "Source",
        "outbound":       bool(row.get("allow_outbound_sync")),
        "doctypes":       doctypes,
        "modules":        module_set,
        "include_drafts": bool(row.get("include_drafts_in_scope")),
        "min_dispatch":   int(row.get("min_dispatch_interval_seconds") or 60),
    }
