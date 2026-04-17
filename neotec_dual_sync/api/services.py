import json
import frappe

SYNC_DOCTYPES = {"Neotec Sync Log", "Neotec Sync Batch", "Neotec Sync Settings", "Neotec Sync Rule", "Neotec Sync Field Map", "Neotec Sync Dashboard"}

def cint_or_default(value, default):
    try:
        return int(value)
    except Exception:
        return default

def get_settings():
    if frappe.db.exists("DocType", "Neotec Sync Settings"):
        return frappe.get_single("Neotec Sync Settings")
    return None

def get_applicable_rules(doc, trigger=None):
    if doc.doctype in SYNC_DOCTYPES or not frappe.db.exists("DocType", "Neotec Sync Rule"):
        return []
    rules = frappe.get_all(
        "Neotec Sync Rule",
        filters={"enabled": 1, "source_doctype": doc.doctype},
        fields=["name", "trigger_mode", "source_doctype", "target_doctype", "only_when_submitted", "batch_group"],
        order_by="idx asc"
    )
    out = []
    for rule in rules:
        mode = (rule.trigger_mode or "").strip()
        if trigger == "On Submit" and mode not in ("On Submit", "Both"):
            continue
        if trigger == "Batch" and mode not in ("Batch", "Both"):
            continue
        if getattr(doc, "docstatus", 0) != 1 and rule.only_when_submitted:
            continue
        out.append(rule)
    return out

def safe_payload_from_doc(doc):
    data = doc.as_dict(no_nulls=False)
    for key in ("__last_sync_on", "_user_tags", "_comments", "_liked_by", "_assign", "doctype", "name", "owner", "creation", "modified", "modified_by", "docstatus", "idx"):
        data.pop(key, None)
    return data

def create_sync_log(doc, rule, trigger):
    payload = safe_payload_from_doc(doc)
    log = frappe.get_doc({
        "doctype": "Neotec Sync Log",
        "reference_doctype": doc.doctype,
        "reference_name": doc.name,
        "rule": rule.get("name"),
        "trigger_source": trigger,
        "status": "Queued",
        "payload_json": json.dumps(payload, ensure_ascii=False),
    })
    log.insert(ignore_permissions=True)
    return log

def enqueue_document_sync(doc, trigger="On Submit"):
    settings = get_settings()
    if not settings or not settings.enabled or settings.instance_role not in ("Source", "Both"):
        return
    for rule in get_applicable_rules(doc, trigger=trigger):
        create_sync_log(doc, rule, trigger)

def process_pending_logs(limit=None):
    limit = cint_or_default(limit, 20)
    logs = frappe.get_all(
        "Neotec Sync Log",
        filters={"status": ["in", ["Queued", "Retry"]]},
        fields=["name"],
        order_by="creation asc",
        limit=limit,
    )
    for row in logs:
        process_log(row["name"])

def process_log(name):
    log = frappe.get_doc("Neotec Sync Log", name)
    settings = get_settings()
    if not settings:
        log.status = "Failed"
        log.error_message = "Settings not configured"
        log.save(ignore_permissions=True)
        return
    log.status = "Processing"
    log.save(ignore_permissions=True)
    log.status = "Success"
    log.response_json = json.dumps({"message": "Processed by enhanced framework placeholder"}, ensure_ascii=False)
    log.save(ignore_permissions=True)

def retry_failed_logs(limit=None):
    settings = get_settings()
    if not settings:
        return
    max_retries = cint_or_default(getattr(settings, "max_retries", 3), 3)
    logs = frappe.get_all(
        "Neotec Sync Log",
        filters={"status": "Failed", "retry_count": ["<", max_retries]},
        fields=["name"],
        order_by="modified asc",
        limit=cint_or_default(limit, 10),
    )
    for row in logs:
        doc = frappe.get_doc("Neotec Sync Log", row.name)
        doc.status = "Retry"
        doc.retry_count = (doc.retry_count or 0) + 1
        doc.save(ignore_permissions=True)

@frappe.whitelist()
def run_batch(batch_name=None):
    if not batch_name:
        frappe.throw("batch_name is required")
    batch = frappe.get_doc("Neotec Sync Batch", batch_name)
    batch.status = "Running"
    batch.save(ignore_permissions=True)

    filters = {}
    if batch.filters_json:
        filters = json.loads(batch.filters_json)

    targets = frappe.get_all(
        batch.source_doctype,
        filters=filters,
        fields=["name"],
        limit=batch.batch_limit or 100
    )
    count = 0
    for row in targets:
        doc = frappe.get_doc(batch.source_doctype, row.name)
        for rule in get_applicable_rules(doc, trigger="Batch"):
            if batch.rule and batch.rule != rule.get("name"):
                continue
            create_sync_log(doc, rule, "Batch")
            count += 1

    batch.status = "Completed"
    batch.processed_count = count
    batch.save(ignore_permissions=True)
    return {"status": "ok", "processed": count}

@frappe.whitelist(allow_guest=False)
def receive_document():
    payload = frappe.request.get_json() or {}
    return {"status": "ok", "received": True, "payload_keys": sorted(list(payload.keys()))}
