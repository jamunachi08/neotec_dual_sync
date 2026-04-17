import frappe

IGNORED_DOCTYPES = {"Neotec Sync Log", "Neotec Sync Batch", "Neotec Sync Settings", "Neotec Sync Rule", "Neotec Sync Field Map", "Neotec Sync Dashboard"}

def handle_on_submit(doc, method=None):
    if doc.doctype in IGNORED_DOCTYPES:
        return
    try:
        from neotec_dual_sync.api.services import enqueue_document_sync
        enqueue_document_sync(doc=doc, trigger="On Submit")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Neotec Dual Sync On Submit")

def handle_update_after_submit(doc, method=None):
    if doc.doctype in IGNORED_DOCTYPES:
        return
    try:
        from neotec_dual_sync.api.services import enqueue_document_sync
        enqueue_document_sync(doc=doc, trigger="Update After Submit")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Neotec Dual Sync Update After Submit")
