import frappe

def process_batch_queue():
    try:
        from neotec_dual_sync.api.services import process_pending_logs
        process_pending_logs()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Neotec Dual Sync Batch Processor")

def retry_failed_syncs():
    try:
        from neotec_dual_sync.api.services import retry_failed_logs
        retry_failed_logs()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Neotec Dual Sync Retry Processor")
