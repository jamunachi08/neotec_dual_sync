import frappe

def after_install():
    ensure_roles()

def after_migrate():
    ensure_roles()

def ensure_roles():
    for role_name in ("Neotec Dual Sync Manager", "Neotec Dual Sync User"):
        if not frappe.db.exists("Role", role_name):
            frappe.get_doc({
                "doctype": "Role",
                "role_name": role_name,
                "desk_access": 1,
                "is_custom": 1,
            }).insert(ignore_permissions=True)
