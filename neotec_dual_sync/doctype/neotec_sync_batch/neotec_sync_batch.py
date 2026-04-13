import json
import frappe
from frappe.model.document import Document
from neotec_dual_sync.jobs import enqueue_rule

class NeotecSyncBatch(Document):
    @frappe.whitelist()
    def run_batch(self):
        self.status = "Running"
        self.last_run_on = frappe.utils.now_datetime()
        self.save(ignore_permissions=True)
        names = []
        if self.docnames_json:
            names = json.loads(self.docnames_json)
        rule = frappe.get_doc("Neotec Sync Rule", self.rule)
        queued = 0
        for name in names:
            enqueue_rule(frappe.get_doc(rule.source_doctype, name), rule.name, "batch")
            queued += 1
        self.status = "Completed"
        self.save(ignore_permissions=True)
        return {"queued": queued}
