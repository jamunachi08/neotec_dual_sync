import frappe
from neotec_dual_sync.mapping import build_payload
from neotec_dual_sync.sender import send_payload

def enqueue_rule(doc, rule_name, trigger_event="on_submit"):
    log = frappe.get_doc({
        "doctype": "Neotec Sync Log",
        "reference_doctype": doc.doctype,
        "reference_name": doc.name,
        "rule": rule_name,
        "trigger_event": trigger_event,
        "status": "Queued",
    })
    log.insert(ignore_permissions=True)
    frappe.enqueue("neotec_dual_sync.jobs.process_log", queue="long", log_name=log.name)

def process_log(log_name):
    log = frappe.get_doc("Neotec Sync Log", log_name)
    log.status = "Processing"
    log.save(ignore_permissions=True)
    doc = frappe.get_doc(log.reference_doctype, log.reference_name)
    payload = build_payload(doc, log.rule)
    log.payload_json = frappe.as_json(payload)
    try:
        response = send_payload(payload)
        log.response_json = frappe.as_json(response)
        log.status = "Success"
    except Exception:
        log.status = "Failed"
        log.error_message = frappe.get_traceback()
        log.retries = (log.retries or 0) + 1
    log.save(ignore_permissions=True)
    frappe.db.commit()

def process_batch_queue():
    settings = frappe.get_single("Neotec Sync Settings")
    if not settings.enable_sync:
        return
    for row in frappe.get_all("Neotec Sync Batch", filters={"status": ["in", ["Draft", "Queued"]]}, fields=["name"], limit=settings.batch_size or 20):
        frappe.get_doc("Neotec Sync Batch", row.name).run_batch()

def retry_failed_logs():
    settings = frappe.get_single("Neotec Sync Settings")
    for row in frappe.get_all("Neotec Sync Log", filters={"status": "Failed", "retries": ["<", settings.max_retries or 3]}, fields=["name"], limit_page_length=settings.batch_size or 20):
        process_log(row.name)
