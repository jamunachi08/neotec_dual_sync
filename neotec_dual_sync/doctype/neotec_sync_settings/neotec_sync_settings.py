import frappe
from frappe.model.document import Document
import requests

class NeotecSyncSettings(Document):
    pass

@frappe.whitelist()
def test_connection():
    settings = frappe.get_single("Neotec Sync Settings")
    if not settings.remote_base_url:
        return "Remote Base URL is not set."
    url = settings.remote_base_url.rstrip("/") + "/api/method/ping"
    try:
        response = requests.get(url, timeout=settings.request_timeout or 10, verify=bool(settings.verify_ssl))
        return f"Connection OK: HTTP {response.status_code}"
    except Exception as exc:
        return f"Connection failed: {exc}"
