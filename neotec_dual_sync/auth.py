import hmac
import frappe

def validate_shared_secret():
    settings = frappe.get_single("Neotec Sync Settings")
    supplied = frappe.get_request_header("X-Neotec-Shared-Secret")
    if not settings.shared_secret or not supplied or not hmac.compare_digest(supplied, settings.shared_secret):
        frappe.throw("Unauthorized sync request.", frappe.PermissionError)

def build_headers():
    settings = frappe.get_single("Neotec Sync Settings")
    headers = {
        "Content-Type": "application/json",
        "X-Neotec-Shared-Secret": settings.shared_secret or "",
    }
    if settings.api_key and settings.api_secret:
        headers["Authorization"] = f"token {settings.api_key}:{settings.api_secret}"
    return headers
