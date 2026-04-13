import frappe
from frappe import _
from neotec_dual_sync.auth import validate_shared_secret

@frappe.whitelist(methods=["POST"])
def receive_document():
    validate_shared_secret()
    payload = frappe.request.get_json() or {}
    target_doctype = payload.get("target_doctype")
    source_name = payload.get("source_name")
    data = payload.get("data") or {}
    if not target_doctype or not source_name:
        frappe.throw(_("Missing target_doctype or source_name"))
    doc = frappe.get_doc({"doctype": target_doctype, **data})
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"status": "success", "name": doc.name}
