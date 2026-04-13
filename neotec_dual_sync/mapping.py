import frappe

def get_matching_rules(doc):
    settings = frappe.get_single("Neotec Sync Settings")
    if not settings.enable_sync:
        return []
    return frappe.get_all(
        "Neotec Sync Rule",
        filters={"disabled": 0, "source_doctype": doc.doctype},
        fields=["name", "source_doctype", "target_doctype", "trigger_mode", "sync_condition", "only_after_submit"],
    )

def should_run_for_event(rule, event_name, doc):
    trigger_mode = rule.get("trigger_mode")
    if event_name == "on_submit" and trigger_mode not in ("On Submit", "Both"):
        return False
    if event_name == "batch" and trigger_mode not in ("Batch", "Both"):
        return False
    if rule.get("only_after_submit") and int(doc.docstatus or 0) != 1:
        return False
    condition = rule.get("sync_condition")
    if condition:
        try:
            return bool(frappe.safe_eval(condition, None, {"doc": doc.as_dict()}))
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Neotec Sync Condition Failed")
            return False
    return True

def build_payload(doc, rule_name):
    rule = frappe.get_doc("Neotec Sync Rule", rule_name)
    payload = {
        "source_doctype": doc.doctype,
        "source_name": doc.name,
        "target_doctype": rule.target_doctype,
        "data": {},
    }
    for row in rule.field_mappings:
        value = doc.get(row.source_field)
        if row.default_value and (value is None or value == ""):
            value = row.default_value
        if row.transform_expression:
            value = frappe.safe_eval(row.transform_expression, None, {"value": value, "doc": doc.as_dict()})
        payload["data"][row.target_field] = value
    return payload
