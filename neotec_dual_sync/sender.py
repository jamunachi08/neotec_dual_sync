import requests
import frappe
from neotec_dual_sync.auth import build_headers

def send_payload(payload):
    settings = frappe.get_single("Neotec Sync Settings")
    if not settings.remote_base_url:
        frappe.throw("Remote Base URL is required.")
    url = settings.remote_base_url.rstrip("/") + "/api/method/neotec_dual_sync.api.receive_document"
    response = requests.post(
        url,
        json=payload,
        headers=build_headers(),
        timeout=settings.request_timeout or 30,
        verify=bool(settings.verify_ssl),
    )
    response.raise_for_status()
    return response.json()
