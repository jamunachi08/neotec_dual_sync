// Neotec Sync Settings — Form JS
frappe.ui.form.on('Neotec Sync Settings', {

    onload(frm) {
        bind_rule_queries(frm);
    },

    refresh(frm) {
        bind_rule_queries(frm);

        // ── Test Connection button ──────────────────────────────────────────
        frm.add_custom_button(__('Test Connection'), function () {
            frappe.show_alert({ message: __('Testing connection…'), indicator: 'blue' });
            frappe.call({
                method: 'neotec_dual_sync.api.validate_connection',
                callback(r) {
                    if (r.message && r.message.ok) {
                        frappe.show_alert({ message: __('✔ ') + r.message.message, indicator: 'green' });
                    } else {
                        const msg = (r.message && r.message.message) || __('Connection failed');
                        frappe.show_alert({ message: __('✘ ') + msg, indicator: 'red' });
                    }
                }
            });
        }, __('Actions'));

        // ── Generate Local Instance ID ──────────────────────────────────────
        if (!frm.doc.local_instance_id) {
            frm.add_custom_button(__('Generate Instance ID'), function () {
                frm.set_value('local_instance_id', frappe.utils.get_random(16));
                frm.save();
            }, __('Actions'));
        }

        // ── View Sync Logs ──────────────────────────────────────────────────
        frm.add_custom_button(__('View Sync Logs'), function () {
            frappe.set_route('List', 'Neotec Sync Log', {});
        }, __('Explore'));

        frm.add_custom_button(__('Open Conflicts'), function () {
            frappe.set_route('List', 'Neotec Sync Conflict', { status: 'Open' });
        }, __('Explore'));

        frm.add_custom_button(__('Idempotency Log'), function () {
            frappe.set_route('List', 'Neotec Sync Idempotency Log', {});
        }, __('Explore'));

        frm.add_custom_button(__('How Sync Works'), function () {
            frappe.set_route('neotec-sync-help');
        }, __('Explore'));

        // ── Install Loopback Fields on a DocType ────────────────────────────
        // Adds nxd_received_from_remote + nxd_source_name custom fields to a
        // user-chosen DocType. Optional but stronger than in-process loopback
        // detection (it survives cross-request scenarios).
        frm.add_custom_button(__('Install Loopback Fields'), function () {
            const d = new frappe.ui.Dialog({
                title: __('Install Loopback Fields'),
                fields: [
                    {
                        label: __('DocType'),
                        fieldname: 'doctype',
                        fieldtype: 'Link',
                        options: 'DocType',
                        reqd: 1,
                        get_query: () => ({ filters: { istable: 0, custom: 0 } })
                    },
                    {
                        fieldtype: 'HTML',
                        options: '<p style="font-size:12px;color:#6b7280">Adds two hidden custom fields (<code>nxd_received_from_remote</code>, <code>nxd_source_name</code>) used for cross-request loopback prevention and source-tracking. Safe and reversible — uninstall via Customize Form.</p>'
                    }
                ],
                primary_action_label: __('Install'),
                primary_action(values) {
                    frappe.call({
                        method: 'neotec_dual_sync.install.install_loopback_fields',
                        args: { doctype: values.doctype },
                        callback(r) {
                            if (r.message && r.message.ok) {
                                frappe.show_alert({
                                    message: __('Installed on ') + r.message.doctype,
                                    indicator: 'green'
                                });
                                d.hide();
                            }
                        }
                    });
                }
            });
            d.show();
        }, __('Actions'));

        // ── Refresh Scope Cache ─────────────────────────────────────────────
        // Forces all workers to re-read the scope filter immediately. Useful
        // after a config change if the cache TTL hasn't elapsed yet.
        frm.add_custom_button(__('Refresh Scope Cache'), function () {
            frappe.call({
                method: 'frappe.client.set_value',
                args: {
                    doctype: 'Neotec Sync Settings',
                    name: 'Neotec Sync Settings',
                    fieldname: 'modified',
                    value: frappe.datetime.now_datetime()
                },
                callback() {
                    frappe.show_alert({
                        message: __('Scope cache will refresh on next save.'),
                        indicator: 'blue'
                    });
                }
            });
        }, __('Actions'));

        // ── Live dashboard stats ────────────────────────────────────────────
        frappe.call({
            method: 'neotec_dual_sync.api.get_dashboard_stats',
            callback(r) {
                if (!r.message) return;
                const s = r.message;
                const html = `
                  <div style="display:flex;gap:18px;flex-wrap:wrap;padding:10px 0">
                    ${stat_badge('Queued',    s.queued,          '#f59e0b')}
                    ${stat_badge('Success',   s.success,         '#10b981')}
                    ${stat_badge('Failed',    s.failed,          '#ef4444')}
                    ${stat_badge('Received',  s.received,        '#3b82f6')}
                    ${stat_badge('Conflicts', s.open_conflicts,  '#8b5cf6')}
                    ${stat_badge('24h Sent',  s.synced_last_24h, '#10b981')}
                    ${stat_badge('24h Failed',s.failed_last_24h, '#ef4444')}
                  </div>`;
                frm.set_intro(html, false);
            }
        });

        // ── Top Failure Reasons (last 7 days) ──────────────────────────────
        // Built lazily so it doesn't slow the form load on healthy systems.
        render_failure_panel(frm);
    },

    instance_role(frm) {
        // Show/hide outbound fields based on role
        const is_source_or_both = ['Source', 'Both'].includes(frm.doc.instance_role);
        frm.toggle_display('remote_base_url',   is_source_or_both);
        frm.toggle_display('api_key',           is_source_or_both);
        frm.toggle_display('api_secret',        is_source_or_both);
        frm.toggle_display('shared_secret',     is_source_or_both);
        frm.toggle_display('signature_required',is_source_or_both);
        frm.toggle_display('allow_outbound_sync', is_source_or_both);
    }
});

frappe.ui.form.on('Neotec Sync Rule', {
    source_doctype(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (row.source_doctype && !row.target_doctype) {
            frappe.model.set_value(cdt, cdn, 'target_doctype', row.source_doctype);
        }
        if (!row.trigger_mode && frm.doc.default_trigger_mode) {
            frappe.model.set_value(cdt, cdn, 'trigger_mode', frm.doc.default_trigger_mode);
        }
    }
});

function bind_rule_queries(frm) {
    if (!frm.fields_dict.rules || !frm.fields_dict.rules.grid) return;
    const grid = frm.fields_dict.rules.grid;
    const dt_query = () => ({ filters: { istable: 0 } });
    ['source_doctype', 'target_doctype'].forEach(f => {
        if (grid.get_field(f)) grid.get_field(f).get_query = dt_query;
    });
    frm.refresh_field('rules');
}

function stat_badge(label, value, color) {
    return `<div style="background:#f3f4f6;border-radius:8px;padding:8px 14px;text-align:center;min-width:90px">
      <div style="font-size:22px;font-weight:700;color:${color}">${value ?? 0}</div>
      <div style="font-size:11px;color:#6b7280">${label}</div>
    </div>`;
}


function render_failure_panel(frm) {
    frappe.call({
        method: 'neotec_dual_sync.api.get_failure_summary',
        args: { days: 7, limit: 5 },
        callback(r) {
            const data = r.message || {};
            const rows = data.rows || [];

            // If no failures, show a positive note instead of an empty panel
            if (!rows.length) {
                frm.dashboard.add_section(
                    `<div style="padding:14px 18px; background:#F0FDF4; border:1px solid #BBF7D0;
                                 border-radius:8px; color:#065F46; font-size:13px;">
                       <strong>No failures in the last ${data.days || 7} days.</strong>
                       Sync looks healthy.
                     </div>`,
                    __('Sync Health')
                );
                return;
            }

            const total = rows.reduce((acc, r) => acc + (r.occurrences || 0), 0);

            const tbody = rows.map((row, i) => {
                const reason = (row.reason || '(no error message)').replace(/</g, '&lt;');
                const seen   = row.last_seen ? frappe.datetime.comment_when(row.last_seen) : '';
                return `
                    <tr style="border-top: 1px solid #FECACA;">
                        <td style="padding:8px 10px; font-family: Consolas, Menlo, monospace;
                                   font-size: 12px; color: #991B1B; word-break: break-word;">
                            ${reason}
                        </td>
                        <td style="padding:8px 10px; text-align:right;
                                   font-weight:600; color:#7F1D1D; white-space:nowrap;">
                            ${row.occurrences} ×
                        </td>
                        <td style="padding:8px 10px; color:#6B7280; font-size:11px; white-space:nowrap;">
                            ${row.distinct_doctypes} doctype(s)<br>${seen}
                        </td>
                        <td style="padding:8px 10px;">
                            <button class="btn btn-xs btn-default nx-jump-failures"
                                    data-reason="${encodeURIComponent(row.reason || '')}"
                                    style="font-size: 11px;">
                                See logs →
                            </button>
                        </td>
                    </tr>
                `;
            }).join('');

            const html = `
                <div style="background:#FFF; border:1px solid #FCA5A5; border-radius:8px; overflow:hidden;">
                    <div style="padding:12px 16px; background:#FEF2F2; border-bottom:1px solid #FCA5A5;
                                display:flex; justify-content:space-between; align-items:center;">
                        <div>
                            <strong style="color:#991B1B;">Top Failure Reasons</strong>
                            <span style="color:#6B7280; font-size:12px; margin-left:6px;">
                                — last ${data.days} days, ${total} total failure(s)
                            </span>
                        </div>
                        <button class="btn btn-xs btn-default" id="nx-view-all-failures">
                            View all failures
                        </button>
                    </div>
                    <table style="width:100%; border-collapse:collapse; font-size:13px;">
                        <thead>
                            <tr style="background:#FEF2F2; color:#7F1D1D;">
                                <th style="text-align:left; padding:8px 10px; font-weight:500;">Reason</th>
                                <th style="text-align:right; padding:8px 10px; font-weight:500;">Count</th>
                                <th style="text-align:left; padding:8px 10px; font-weight:500;">Scope / Last seen</th>
                                <th style="padding:8px 10px;"></th>
                            </tr>
                        </thead>
                        <tbody>${tbody}</tbody>
                    </table>
                </div>
            `;

            frm.dashboard.add_section(html, __('Sync Health'));

            // Wire jump-to-logs buttons after the section is in the DOM
            setTimeout(() => {
                document.querySelectorAll('.nx-jump-failures').forEach(btn => {
                    btn.addEventListener('click', () => {
                        const reason = decodeURIComponent(btn.dataset.reason || '');
                        // Use a "like" filter on error_message to find these
                        frappe.set_route('List', 'Neotec Sync Log', {
                            status: 'Failed',
                            error_message: ['like', '%' + reason.substring(0, 60) + '%']
                        });
                    });
                });
                const viewAll = document.getElementById('nx-view-all-failures');
                if (viewAll) {
                    viewAll.addEventListener('click', () => {
                        frappe.set_route('List', 'Neotec Sync Log', { status: 'Failed' });
                    });
                }
            }, 50);
        }
    });
}
