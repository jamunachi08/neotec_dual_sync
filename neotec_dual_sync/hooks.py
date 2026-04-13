app_name = "neotec_dual_sync"
app_title = "Neotec Dual Sync"
app_publisher = "Neotec"
app_description = "Settings-driven dual instance synchronization for Frappe"
app_email = "support@neotec.example"
app_license = "MIT"

after_install = "neotec_dual_sync.install.after_install"
after_migrate = "neotec_dual_sync.install.after_migrate"

fixtures = [
    {"dt": "Role", "filters": [["name", "in", ["Neotec Dual Sync Manager", "Neotec Dual Sync User"]]]},
    {"dt": "Custom Field", "filters": [["module", "=", "Neotec Dual Sync"]]},
    {"dt": "Property Setter", "filters": [["module", "=", "Neotec Dual Sync"]]},
    {"dt": "Client Script", "filters": [["module", "=", "Neotec Dual Sync"]]},
]

doc_events = {
    "*": {
        "on_submit": "neotec_dual_sync.events.handle_on_submit",
        "on_update_after_submit": "neotec_dual_sync.events.handle_update_after_submit",
    }
}

scheduler_events = {
    "cron": {
        "*/10 * * * *": [
            "neotec_dual_sync.jobs.process_batch_queue",
            "neotec_dual_sync.jobs.retry_failed_logs",
        ]
    }
}

doctype_js = {
    "Neotec Sync Settings": "public/js/neotec_sync_settings.js",
    "Neotec Sync Batch": "public/js/neotec_sync_batch.js",
}
