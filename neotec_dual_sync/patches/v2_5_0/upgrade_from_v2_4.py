"""
Patch: upgrade from v2.4.x / v2.5.0 to v2.5.1.

Changes since v2.5.0:
  * `included` checkbox on Neotec Sync Field Map and Sync Mapping Row.
    Existing rows must default to 1 (true) so the engine continues to
    sync them after upgrade.
  * Same defensive Settings cleanup as v2.5.0.

Indexes are added by `after_migrate` -> `_add_indexes`, not here.
"""
import frappe


def execute():
    # ── Settings safety (carry-over from v2.5.0) ─────────────────────────
    name = "Neotec Sync Settings"
    if frappe.db.exists("Neotec Sync Settings", name):
        row = frappe.db.get_value(
            "Neotec Sync Settings", name,
            ["min_dispatch_interval_seconds", "log_retention_days",
             "idempotency_retention_days", "include_drafts_in_scope",
             "remote_base_url", "log_level"],
            as_dict=True,
        ) or {}

        updates = {}
        if row.get("min_dispatch_interval_seconds") in (None, 0):
            updates["min_dispatch_interval_seconds"] = 60
        if not row.get("log_retention_days"):
            updates["log_retention_days"] = 30
        if not row.get("idempotency_retention_days"):
            updates["idempotency_retention_days"] = 60
        if row.get("include_drafts_in_scope") is None:
            updates["include_drafts_in_scope"] = 0
        if row.get("log_level") == "INFO":
            updates["log_level"] = "WARN"
        if not row.get("remote_base_url"):
            updates["enabled"] = 0

        if updates:
            frappe.db.set_value("Neotec Sync Settings", name, updates)
        frappe.clear_document_cache("Neotec Sync Settings", name)

    # ── New: default `included` = 1 on legacy field-map rows ─────────────
    # MariaDB will have created the column as nullable when the JSON was
    # migrated. Anything still NULL or 0 from before the new field existed
    # should be treated as "yes, sync this".
    try:
        frappe.db.sql("""
            UPDATE `tabNeotec Sync Field Map`
               SET `included` = 1
             WHERE `included` IS NULL
        """)
    except Exception:
        pass  # Column may not exist on a brand-new install — ignore
    try:
        frappe.db.sql("""
            UPDATE `tabNeotec Sync Mapping Row`
               SET `included` = 1
             WHERE `included` IS NULL
        """)
    except Exception:
        pass

    frappe.db.commit()
