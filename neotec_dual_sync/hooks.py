app_name = "neotec_dual_sync"
app_title = "Neotec Dual Sync"
app_publisher = "Neotec"
app_description = "Production-oriented configurable dual instance synchronization for Frappe/ERPNext"
app_email = "support@neotec.example"
app_license = "MIT"
app_version = "2.6.0"

after_install = "neotec_dual_sync.install.after_install"
after_migrate = "neotec_dual_sync.install.after_migrate"

fixtures = [
    {"dt": "Role", "filters": [["name", "in", [
        "Neotec Dual Sync Manager",
        "Neotec Dual Sync User",
        "Neotec Dual Sync API",
    ]]]}
]

# ---------------------------------------------------------------------------
# Document events
#
# Performance notes:
#
# - We DO NOT register on_update on "*". on_update fires on every field-level
#   save and is the single biggest source of load. Use trigger_mode "On Update"
#   on a rule instead — the rule defines a narrow scope.
# - The first thing every handler does is consult an in-process scope cache
#   that answers "is this doctype in the active configuration?" in O(1) without
#   a DB hit. If not, the handler returns immediately.
# ---------------------------------------------------------------------------
doc_events = {
    "*": {
        "on_submit":              "neotec_dual_sync.api.events.handle_on_submit",
        "on_update_after_submit": "neotec_dual_sync.api.events.handle_update_after_submit",
        "after_insert":           "neotec_dual_sync.api.events.handle_after_insert",
        "on_update":              "neotec_dual_sync.api.events.handle_on_update",
    },
    # Cache invalidation — flush the scope cache when configuration changes
    "Neotec Sync Settings": {
        "on_update": "neotec_dual_sync.api.scope.invalidate_scope_cache",
    },
    "Neotec Sync Rule": {
        "on_update": "neotec_dual_sync.api.scope.invalidate_scope_cache",
    },
    "Neotec Sync Mapping": {
        "on_update": "neotec_dual_sync.api.scope.invalidate_scope_cache",
    },
}

doctype_js = {
    "Neotec Sync Settings": "public/js/neotec_sync_settings.js",
    "Neotec Sync Batch":    "public/js/neotec_sync_batch.js",
    "Neotec Sync Conflict": "public/js/neotec_sync_conflict.js",
    "Neotec Sync Log":      "public/js/neotec_sync_log.js",
}

# ---------------------------------------------------------------------------
# Universal form integration
#
# This script is included on EVERY desk form. It attaches a Sync Now button
# and a status indicator to documents whose DocType is in the active sync
# scope. Out-of-scope DocTypes pay one cached HTTP call and nothing else.
# ---------------------------------------------------------------------------
app_include_js = [
    "/assets/neotec_dual_sync/js/form_integration.js"
]

# ---------------------------------------------------------------------------
# Scheduler events
#
# All dispatcher jobs short-circuit when sync is disabled or the queue is
# empty, so a frequent cron costs essentially nothing on an idle install.
# ---------------------------------------------------------------------------
scheduler_events = {
    "cron": {
        # Dispatch — every 5 minutes, internally throttled
        "*/5 * * * *": [
            "neotec_dual_sync.api.jobs.process_batch_queue",
        ],
        # Retry — every 15 minutes, only runs if failed rows exist
        "*/15 * * * *": [
            "neotec_dual_sync.api.jobs.retry_failed_syncs",
        ],
        # Daily at 02:00 — batched cleanup
        "0 2 * * *": [
            "neotec_dual_sync.api.jobs.cleanup_old_logs",
        ],
    }
}
