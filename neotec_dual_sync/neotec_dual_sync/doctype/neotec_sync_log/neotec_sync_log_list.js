// Neotec Sync Log — List View JS
//
// Adds:
//   1. Bulk Re-queue action (when one or more rows are selected)
//   2. Quick-filter shortcuts: "Failed this week", "Failed this month", "Queued"
//   3. Status indicator coloring on the list

frappe.listview_settings['Neotec Sync Log'] = {

    add_fields: ['status', 'direction', 'retry_count', 'modified'],

    get_indicator(doc) {
        const map = {
            'Success':        ['Synced',         'green',  'status,=,Success'],
            'Failed':         ['Failed',         'red',    'status,=,Failed'],
            'Queued':         ['Queued',         'yellow', 'status,=,Queued'],
            'Processing':     ['Processing',     'blue',   'status,=,Processing'],
            'Skipped':        ['Skipped',        'gray',   'status,=,Skipped'],
            'Duplicate':      ['Duplicate',      'gray',   'status,=,Duplicate'],
            'Loop Prevented': ['Loop blocked',   'orange', 'status,=,Loop Prevented'],
            'Received':       ['Received',       'blue',   'status,=,Received'],
        };
        return map[doc.status] || [doc.status, 'gray', `status,=,${doc.status}`];
    },

    onload(listview) {
        // ── Bulk Re-queue action ──────────────────────────────────────────
        listview.page.add_actions_menu_item(__('Bulk Re-queue Selected'), () => {
            const selected = listview.get_checked_items() || [];
            if (!selected.length) {
                frappe.msgprint({
                    title: __('Nothing selected'),
                    message: __('Tick the rows you want to re-queue first.'),
                    indicator: 'orange'
                });
                return;
            }

            const eligible = selected.filter(d =>
                ['Failed', 'Skipped'].includes(d.status) && d.direction === 'Outbound'
            );

            if (!eligible.length) {
                frappe.msgprint({
                    title: __('Nothing eligible'),
                    message: __('Only Failed or Skipped Outbound rows can be re-queued. ' +
                                'Selected rows are in a different state.'),
                    indicator: 'orange'
                });
                return;
            }

            const skipped_msg = (eligible.length < selected.length)
                ? `<br><span style="color:#92400E;">${selected.length - eligible.length} of ${selected.length}
                   selected row(s) will be skipped (wrong status or direction).</span>`
                : '';

            frappe.confirm(
                __('Re-queue {0} log row(s)? Their status will change to Queued and retry_count reset to 0.{1}',
                   [eligible.length, skipped_msg]),
                () => {
                    frappe.call({
                        method: 'neotec_dual_sync.api.bulk_requeue_logs',
                        args: { log_names: eligible.map(d => d.name) },
                        freeze: true,
                        freeze_message: __('Re-queueing…'),
                        callback(r) {
                            const m = r.message || {};
                            frappe.show_alert({
                                message: m.message || __('Done'),
                                indicator: m.requeued > 0 ? 'green' : 'orange'
                            }, 6);
                            listview.refresh();
                        }
                    });
                }
            );
        });

        // ── Quick filter shortcuts ────────────────────────────────────────
        // Add three buttons that jump to common views without typing filters.
        const shortcuts = [
            {
                label: __('Failed this week'),
                indicator: 'red',
                filters: [
                    ['Neotec Sync Log', 'status', '=', 'Failed'],
                    ['Neotec Sync Log', 'modified', '>', frappe.datetime.add_days(frappe.datetime.now_datetime(), -7)]
                ]
            },
            {
                label: __('Failed this month'),
                indicator: 'red',
                filters: [
                    ['Neotec Sync Log', 'status', '=', 'Failed'],
                    ['Neotec Sync Log', 'modified', '>', frappe.datetime.add_days(frappe.datetime.now_datetime(), -30)]
                ]
            },
            {
                label: __('Currently queued'),
                indicator: 'yellow',
                filters: [
                    ['Neotec Sync Log', 'status', 'in', ['Queued', 'Processing']]
                ]
            },
        ];

        shortcuts.forEach(sc => {
            listview.page.add_inner_button(sc.label, () => {
                listview.filter_area.clear();
                sc.filters.forEach(f => listview.filter_area.add(f[0], f[1], f[2], f[3]));
                listview.refresh();
            }, __('Quick Filters'));
        });
    }
};
