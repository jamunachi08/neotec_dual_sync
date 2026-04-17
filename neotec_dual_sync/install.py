import frappe

ROLES = ["Neotec Dual Sync Manager", "Neotec Dual Sync User"]


def _ensure_roles():
    for role_name in ROLES:
        if not frappe.db.exists("Role", role_name):
            doc = frappe.get_doc({"doctype": "Role", "role_name": role_name})
            doc.insert(ignore_permissions=True)


def _ensure_settings_doc():
    if not frappe.db.exists("Neotec Sync Settings", "Neotec Sync Settings"):
        doc = frappe.get_doc({
            "doctype": "Neotec Sync Settings",
            "enabled": 1,
            "instance_role": "Source",
            "verify_ssl": 1,
            "timeout_seconds": 30,
            "default_trigger_mode": "On Submit",
            "batch_size": 100,
            "max_retries": 3,
            "retry_interval_minutes": 10,
            "enable_audit_snapshot": 1,
            "mask_secrets_in_logs": 1,
        })
        doc.insert(ignore_permissions=True)


def after_install():
    _ensure_roles()
    _ensure_settings_doc()
    frappe.db.commit()


def after_migrate():
    _ensure_roles()
    frappe.db.commit()
