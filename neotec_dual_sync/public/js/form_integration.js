// Neotec Dual Sync — Universal form integration
//
// Attaches to EVERY Frappe form. On load, asks the server "is this DocType
// in our sync scope?" — if yes, renders:
//   1. A coloured status dot in the form's title area showing the latest
//      sync status for THIS document.
//   2. A "Sync Now" toolbar action that bypasses the cron throttle and
//      polls for status feedback within seconds.
//
// Out-of-scope DocTypes pay one tiny cached HTTP call on form load and
// nothing else — the script returns immediately.

(function () {
    'use strict';

    // Skip the integration entirely on our own DocTypes — they have their
    // own form scripts and don't sync themselves.
    const SELF_DOCTYPES = new Set([
        'Neotec Sync Settings', 'Neotec Sync Log', 'Neotec Sync Mapping',
        'Neotec Sync Rule', 'Neotec Sync Conflict', 'Neotec Sync Batch',
        'Neotec Sync Idempotency Log', 'Neotec Sync Instance',
        'Neotec Sync Field Map', 'Neotec Sync Mapping Row',
        'Neotec Sync Module Filter', 'Neotec Sync Route Policy',
        'Neotec Sync API Key', 'Neotec Sync Dashboard'
    ]);

    // Per-tab cache of "is this DocType in scope?" so we don't re-ask
    // on every form refresh. Cleared on page reload.
    const SCOPE_CACHE = new Map();

    // Hook into Frappe's form refresh — fires for every doctype.
    if (!window.frappe || !frappe.ui || !frappe.ui.form) return;

    frappe.ui.form.on('*', {
        refresh(frm) {
            if (!frm || !frm.doc || !frm.doctype) return;
            if (SELF_DOCTYPES.has(frm.doctype)) return;
            if (frm.is_new()) return;  // never indicate on unsaved docs

            handleForm(frm);
        }
    });

    function handleForm(frm) {
        const cached = SCOPE_CACHE.get(frm.doctype);
        if (cached === false) return;     // confirmed out-of-scope
        if (cached === true) {
            renderUI(frm);
            return;
        }

        // First time we see this doctype this session — ask once.
        frappe.call({
            method: 'neotec_dual_sync.api.get_doc_sync_status',
            args: { doctype: frm.doctype, docname: frm.doc.name },
            callback(r) {
                if (!r.message) {
                    SCOPE_CACHE.set(frm.doctype, false);
                    return;
                }
                if (!r.message.in_scope) {
                    SCOPE_CACHE.set(frm.doctype, false);
                    return;
                }
                SCOPE_CACHE.set(frm.doctype, true);
                renderUI(frm, r.message);
            },
            error() {
                // Server error or no permissions — don't decorate, fail silently
                SCOPE_CACHE.set(frm.doctype, false);
            }
        });
    }

    function renderUI(frm, status_data) {
        // 1. Add the Sync Now button (always, for any in-scope doctype)
        addSyncNowButton(frm);

        // 2. Render the status indicator
        if (status_data) {
            renderIndicator(frm, status_data);
        } else {
            // Cache hit but no data — fetch fresh
            refreshIndicator(frm);
        }
    }

    function addSyncNowButton(frm) {
        // Avoid duplicate buttons on repeat refresh
        if (frm.custom_buttons && frm.custom_buttons[__('Sync Now')]) return;

        frm.add_custom_button(__('Sync Now'), function () {
            triggerSyncNow(frm);
        }, __('Neotec Sync'));

        frm.add_custom_button(__('Sync History'), function () {
            frappe.set_route('List', 'Neotec Sync Log', {
                reference_doctype: frm.doctype,
                reference_name: frm.doc.name
            });
        }, __('Neotec Sync'));
    }

    function triggerSyncNow(frm) {
        frappe.show_alert({ message: __('Queueing sync…'), indicator: 'blue' }, 3);

        frappe.call({
            method: 'neotec_dual_sync.api.manual_sync_now',
            args: { doctype: frm.doctype, docname: frm.doc.name },
            callback(r) {
                const m = r.message || {};
                if (!m.ok) {
                    frappe.show_alert({
                        message: __('Could not queue: ') + (m.message || 'unknown'),
                        indicator: 'orange'
                    }, 6);
                    return;
                }
                frappe.show_alert({
                    message: __('Queued. Dispatching…'),
                    indicator: 'blue'
                }, 4);
                pollForCompletion(frm, m.log, 0);
            }
        });
    }

    // Poll the sync log row up to 12 times (every 1.5s = 18s) to give the
    // user feedback. The background dispatcher should finish in <5s normally.
    function pollForCompletion(frm, log_name, attempt) {
        if (attempt > 12) {
            frappe.show_alert({
                message: __('Still in progress — check Sync History'),
                indicator: 'blue'
            }, 6);
            refreshIndicator(frm);
            return;
        }

        setTimeout(() => {
            frappe.db.get_value('Neotec Sync Log', log_name, ['status', 'error_message'])
                .then(r => {
                    const v = (r && r.message) || {};
                    if (v.status === 'Success') {
                        frappe.show_alert({
                            message: __('✓ Synced successfully'),
                            indicator: 'green'
                        }, 5);
                        refreshIndicator(frm);
                    } else if (v.status === 'Failed') {
                        frappe.show_alert({
                            message: __('✗ Sync failed: ') + (v.error_message || 'unknown'),
                            indicator: 'red'
                        }, 8);
                        refreshIndicator(frm);
                    } else if (v.status === 'Skipped') {
                        frappe.show_alert({
                            message: __('Skipped: ') + (v.error_message || ''),
                            indicator: 'gray'
                        }, 6);
                        refreshIndicator(frm);
                    } else {
                        // Still Queued or Processing — keep polling
                        pollForCompletion(frm, log_name, attempt + 1);
                    }
                });
        }, 1500);
    }

    function refreshIndicator(frm) {
        frappe.call({
            method: 'neotec_dual_sync.api.get_doc_sync_status',
            args: { doctype: frm.doctype, docname: frm.doc.name },
            callback(r) {
                if (r.message) renderIndicator(frm, r.message);
            }
        });
    }

    function renderIndicator(frm, data) {
        if (!data || !data.status) {
            // Document is in scope but has never been synced — show a neutral hint
            frm.dashboard.set_headline_alert(`
                <div class="nx-sync-pill nx-sync-neutral">
                    <span class="nx-sync-dot"></span>
                    <span>Not yet synced</span>
                    <span class="nx-sync-hint">— click <em>Neotec Sync → Sync Now</em></span>
                </div>
                ${pillStyles()}
            `);
            return;
        }

        const palette = {
            'Success':        { cls: 'nx-sync-green',  label: 'Synced' },
            'Failed':         { cls: 'nx-sync-red',    label: 'Sync failed' },
            'Queued':         { cls: 'nx-sync-amber',  label: 'Queued for sync' },
            'Processing':     { cls: 'nx-sync-amber',  label: 'Syncing…' },
            'Skipped':        { cls: 'nx-sync-gray',   label: 'Sync skipped' },
            'Duplicate':      { cls: 'nx-sync-gray',   label: 'Duplicate (already synced)' },
            'Loop Prevented': { cls: 'nx-sync-gray',   label: 'Loop prevented' },
            'Received':       { cls: 'nx-sync-blue',   label: 'Received via sync' },
        }[data.status] || { cls: 'nx-sync-neutral', label: data.status };

        const ago = data.last_sync_at ? frappe.datetime.comment_when(data.last_sync_at) : '';
        const errMsg = data.last_error
            ? `<div class="nx-sync-err">${frappe.utils.escape_html(data.last_error)}</div>`
            : '';

        const html = `
            <div class="nx-sync-pill ${palette.cls}" title="${frappe.utils.escape_html(palette.label)}">
                <span class="nx-sync-dot"></span>
                <span><strong>${palette.label}</strong></span>
                ${ago ? `<span class="nx-sync-when">${frappe.utils.escape_html(ago)}</span>` : ''}
                ${data.history_count > 1 ? `<span class="nx-sync-hint">— ${data.history_count} sync events</span>` : ''}
            </div>
            ${errMsg}
            ${pillStyles()}
        `;
        frm.dashboard.set_headline_alert(html);
    }

    function pillStyles() {
        // Inline so we don't need a separate CSS file. Idempotent — Frappe
        // dedupes identical inline styles so re-renders don't multiply them.
        return `
            <style>
                .nx-sync-pill {
                    display: inline-flex; align-items: center; gap: 8px;
                    font-size: 12px; padding: 4px 10px; border-radius: 12px;
                    margin: 4px 0; line-height: 1.4;
                }
                .nx-sync-pill .nx-sync-dot {
                    width: 8px; height: 8px; border-radius: 50%;
                    display: inline-block;
                }
                .nx-sync-pill .nx-sync-when { opacity: 0.75; font-size: 11px; }
                .nx-sync-pill .nx-sync-hint { opacity: 0.6; font-size: 11px; }
                .nx-sync-pill em { font-style: italic; }
                .nx-sync-green  { background: #D1FAE5; color: #065F46; }
                .nx-sync-green  .nx-sync-dot { background: #10B981; }
                .nx-sync-red    { background: #FEE2E2; color: #991B1B; }
                .nx-sync-red    .nx-sync-dot { background: #EF4444; }
                .nx-sync-amber  { background: #FEF3C7; color: #92400E; }
                .nx-sync-amber  .nx-sync-dot { background: #F59E0B; }
                .nx-sync-blue   { background: #DBEAFE; color: #1E40AF; }
                .nx-sync-blue   .nx-sync-dot { background: #3B82F6; }
                .nx-sync-gray, .nx-sync-neutral { background: #F3F4F6; color: #4B5563; }
                .nx-sync-gray   .nx-sync-dot, .nx-sync-neutral .nx-sync-dot { background: #9CA3AF; }
                .nx-sync-err {
                    font-size: 11px; color: #991B1B; background: #FEF2F2;
                    padding: 4px 8px; border-radius: 4px; margin: 2px 0 6px;
                    font-family: Consolas, Menlo, monospace;
                }
            </style>
        `;
    }
})();
