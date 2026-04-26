"""
Neotec Dual Sync — Install / Migrate hooks.

Sets up:
  * Roles
  * Singleton Settings (with safe defaults — sync OFF until configured)
  * Indexes on the hot tables (Sync Log, Idempotency Log)

We deliberately do NOT create `nxd_received_from_remote` / `nxd_source_name`
custom fields on every doctype — that would be invasive on a real ERP. The
operator opts in per-doctype via `add_loopback_fields_for_doctype` (called
from the Settings UI). Doctypes without the fields still work fine; the
inbound applier uses `frappe.flags.neotec_inbound_apply` for in-process
loopback prevention, which is the case that matters most.
"""
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field


# ---------------------------------------------------------------------------
# Public hooks
# ---------------------------------------------------------------------------

def after_install():
    _setup_roles()
    _setup_settings()
    _add_indexes()


def after_migrate():
    _setup_roles()
    _setup_settings()
    _add_indexes()


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------

def _setup_roles():
    for role in ("Neotec Dual Sync Manager",
                 "Neotec Dual Sync User",
                 "Neotec Dual Sync API"):
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role}).insert(ignore_permissions=True)


# ---------------------------------------------------------------------------
# Settings — safe defaults
# ---------------------------------------------------------------------------

def _setup_settings():
    if frappe.db.exists("Neotec Sync Settings", "Neotec Sync Settings"):
        return

    doc = frappe.get_doc({
        "doctype": "Neotec Sync Settings",
        # SAFE DEFAULTS — sync is OFF by default.
        # The operator must explicitly enable after configuration.
        "enabled": 0,
        "instance_role": "Source",
        "local_instance_id": frappe.generate_hash(length=12),
        "accept_inbound_sync": 1,
        "allow_outbound_sync": 1,
        "prevent_loopback": 1,
        "max_hop_count": 5,
        "verify_ssl": 1,
        "timeout_seconds": 30,
        "default_trigger_mode": "On Submit",
        "signature_required": 1,
        "batch_size": 50,
        "max_retries": 3,
        "retry_interval_minutes": 10,
        "min_dispatch_interval_seconds": 60,
        "log_retention_days": 30,
        "idempotency_retention_days": 60,
        "enable_audit_snapshot": 0,    # OFF — turn on only when needed
        "mask_secrets_in_logs": 1,
        "allow_delete_sync": 0,
        "dry_run_mode": 0,
        "log_level": "WARN",
        "include_drafts_in_scope": 0,
    })
    doc.insert(ignore_permissions=True)


# ---------------------------------------------------------------------------
# Indexes — critical for queue performance
# ---------------------------------------------------------------------------

# (table, index_name, columns)
_INDEXES = [
    ("tabNeotec Sync Log",
     "idx_neotec_log_status_dir_creation",
     "(`status`, `direction`, `creation`)"),
    ("tabNeotec Sync Log",
     "idx_neotec_log_status_dir_retry_modified",
     "(`status`, `direction`, `retry_count`, `modified`)"),
    ("tabNeotec Sync Log",
     "idx_neotec_log_reference",
     "(`reference_doctype`, `reference_name`)"),
    ("tabNeotec Sync Log",
     "idx_neotec_log_tx",
     "(`sync_transaction_id`)"),
    ("tabNeotec Sync Idempotency Log",
     "idx_neotec_idem_tx",
     "(`sync_transaction_id`)"),
    ("tabNeotec Sync Idempotency Log",
     "idx_neotec_idem_source",
     "(`source_instance_id`, `source_doctype`, `source_docname`)"),
    ("tabNeotec Sync Idempotency Log",
     "idx_neotec_idem_creation",
     "(`creation`)"),
    ("tabNeotec Sync Conflict",
     "idx_neotec_conflict_status",
     "(`status`, `creation`)"),
]


def _add_indexes():
    """Idempotently create our hot-path indexes. Skips silently if a table
    or index already exists."""
    for table, index_name, columns in _INDEXES:
        try:
            # Check if table exists
            tables = frappe.db.sql(
                "SHOW TABLES LIKE %s", (table,)
            )
            if not tables:
                continue
            # Check if index already exists
            existing = frappe.db.sql(
                "SHOW INDEX FROM `%s` WHERE Key_name = %%s" % table,
                (index_name,),
            )
            if existing:
                continue
            frappe.db.sql(
                f"ALTER TABLE `{table}` ADD INDEX `{index_name}` {columns}"
            )
        except Exception:
            # Don't fail the migration on an index hiccup — just log
            frappe.log_error(
                title=f"Neotec Sync: Could not create index {index_name}",
                message=frappe.get_traceback(),
            )


# ---------------------------------------------------------------------------
# Optional: per-doctype loopback custom fields
# ---------------------------------------------------------------------------

def add_loopback_fields_for_doctype(doctype: str):
    """
    Add `nxd_received_from_remote` and `nxd_source_name` custom fields to
    a single doctype. Call this from the Settings UI when the operator
    opts a doctype in to file-level loopback tracking.
    """
    fields = [
        {
            "fieldname": "nxd_received_from_remote",
            "label": "Received From Remote (Neotec Sync)",
            "fieldtype": "Check",
            "default": "0",
            "hidden": 1,
            "no_copy": 1,
            "read_only": 1,
            "print_hide": 1,
        },
        {
            "fieldname": "nxd_source_name",
            "label": "Source Name (Neotec Sync)",
            "fieldtype": "Data",
            "hidden": 1,
            "no_copy": 1,
            "read_only": 1,
            "print_hide": 1,
        },
    ]
    for f in fields:
        if not frappe.db.exists("Custom Field", f"{doctype}-{f['fieldname']}"):
            create_custom_field(doctype, f)
    frappe.clear_cache(doctype=doctype)


@frappe.whitelist()
def install_loopback_fields(doctype: str):
    """Whitelisted wrapper so the Settings UI can install fields per doctype."""
    if not frappe.has_permission("Neotec Sync Settings", "write"):
        frappe.throw("Insufficient permissions.")
    add_loopback_fields_for_doctype(doctype)
    return {"ok": True, "doctype": doctype}
