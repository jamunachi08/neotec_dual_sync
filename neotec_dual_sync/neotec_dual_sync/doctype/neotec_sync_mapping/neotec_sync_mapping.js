// Neotec Sync Mapping — Form JS
//
// Provides the "Fetch Fields" workflow:
//   1. User picks Source DocType + Target DocType (and target side: local/remote).
//   2. Click "Fetch Fields" — server returns paired schemas.
//   3. A dialog renders three sections:
//        a. Parent fields, side-by-side checkbox table
//        b. Child tables, each as its own collapsible section
//        c. Target-only fields the source doesn't have (informational)
//   4. User toggles ✓ / ✗ for each row, optionally re-pairs target fields.
//   5. Click "Apply" — populates the Field Mappings + Child Table Mappings tables.
//
// Design notes:
//   * All UI styling is inline so the file is self-contained and survives
//     Frappe's bundling without separate CSS.
//   * "included" maps to the new Sync checkbox column on the child rows.
//   * Re-running Fetch Fields prompts before overwriting existing rows.
//   * Type-mismatch warnings are surfaced inline, not blocking.

frappe.ui.form.on('Neotec Sync Mapping', {

    refresh(frm) {
        frm.add_custom_button(__('Fetch Fields'), () => open_fetch_fields_dialog(frm), __('Tools'));

        frm.add_custom_button(__('Toggle All Sync'), () => {
            const rows = frm.doc.field_mappings || [];
            const target = !rows.every(r => r.included);
            rows.forEach(r => frappe.model.set_value(r.doctype, r.name, 'included', target ? 1 : 0));
            (frm.doc.child_table_mappings || []).forEach(r =>
                frappe.model.set_value(r.doctype, r.name, 'included', target ? 1 : 0));
            frappe.show_alert({ message: __(target ? 'All ticked' : 'All unticked'), indicator: 'blue' });
        }, __('Tools'));

        frm.add_custom_button(__('Show Inclusion Summary'), () => show_inclusion_summary(frm), __('Tools'));
    },

    source_doctype(frm) {
        if (frm.doc.source_doctype && !frm.doc.target_doctype) {
            frm.set_value('target_doctype', frm.doc.source_doctype);
        }
    }
});


// ──────────────────────────────────────────────────────────────────────────
// Fetch Fields dialog
// ──────────────────────────────────────────────────────────────────────────

function open_fetch_fields_dialog(frm) {
    if (!frm.doc.source_doctype || !frm.doc.target_doctype) {
        frappe.msgprint({
            title: __('Set DocTypes first'),
            message: __('Please set both Source DocType and Target DocType before fetching fields.'),
            indicator: 'orange'
        });
        return;
    }

    const opts_dialog = new frappe.ui.Dialog({
        title: __('Fetch Fields — {0} → {1}', [frm.doc.source_doctype, frm.doc.target_doctype]),
        size: 'small',
        fields: [
            {
                fieldtype: 'Select',
                fieldname: 'target_side',
                label: __('Target Schema Source'),
                options: [
                    { label: __('This instance (local)'),     value: 'local' },
                    { label: __('Remote instance (configured Remote URL)'), value: 'remote' }
                ],
                default: 'local',
                reqd: 1,
                description: __(
                    'Local: read the target DocType from this site. ' +
                    'Remote: ask the configured remote so you see ITS schema (preferred when sides differ).'
                )
            },
            {
                fieldtype: 'Check',
                fieldname: 'include_system',
                label: __('Include system / hidden fields'),
                default: 0,
                description: __('Section breaks, HTML, buttons, hidden flags, etc. Off by default.')
            }
        ],
        primary_action_label: __('Fetch'),
        primary_action(values) {
            opts_dialog.hide();
            run_fetch(frm, values.target_side, values.include_system);
        }
    });
    opts_dialog.show();
}


function run_fetch(frm, target_side, include_system) {
    frappe.dom.freeze(__('Fetching fields…'));
    frappe.call({
        method: 'neotec_dual_sync.api.build_field_pairs',
        args: {
            source_doctype: frm.doc.source_doctype,
            target_doctype: frm.doc.target_doctype,
            target_remote: target_side === 'remote' ? 1 : 0,
            include_system: include_system ? 1 : 0
        },
        callback(r) {
            frappe.dom.unfreeze();
            if (!r.message) {
                frappe.msgprint({ title: __('No data'), message: __('Empty response from server.'), indicator: 'red' });
                return;
            }
            if (r.message.error) {
                frappe.msgprint({ title: __('Fetch failed'), message: r.message.error, indicator: 'red' });
                return;
            }
            open_picker_dialog(frm, r.message);
        },
        error(err) {
            frappe.dom.unfreeze();
            frappe.msgprint({
                title: __('Fetch failed'),
                message: (err && err.message) || __('Unknown error.'),
                indicator: 'red'
            });
        }
    });
}


// ──────────────────────────────────────────────────────────────────────────
// Picker dialog — side-by-side, with checkboxes
// ──────────────────────────────────────────────────────────────────────────

function open_picker_dialog(frm, pairs) {
    // We render our own HTML inside an HTML field for full control.
    const dialog = new frappe.ui.Dialog({
        title: __('Select fields to sync — {0} → {1}', [pairs.source_doctype, pairs.target_doctype]),
        size: 'extra-large',
        fields: [{ fieldtype: 'HTML', fieldname: 'picker_area' }],
        primary_action_label: __('Apply Selection'),
        primary_action() {
            apply_picker_selection(frm, dialog, pairs);
        }
    });

    dialog.show();
    const $area = dialog.get_field('picker_area').$wrapper;
    $area.empty();
    $area.append(render_picker_html(pairs));
    wire_picker_handlers($area, pairs);
}


function render_picker_html(pairs) {
    const html = [];
    html.push(`
        <style>
            .nx-picker { font-size: 13px; }
            .nx-picker .nx-section-title {
                font-weight: 600; font-size: 14px; margin: 16px 0 8px;
                color: #1F2937; border-bottom: 2px solid #E5E7EB; padding-bottom: 4px;
            }
            .nx-picker .nx-counter { color: #6B7280; font-weight: normal; font-size: 12px; }
            .nx-picker .nx-toolbar { margin: 8px 0; display: flex; gap: 8px; flex-wrap: wrap; }
            .nx-picker .nx-toolbar button {
                font-size: 12px; padding: 4px 10px; border: 1px solid #D1D5DB;
                background: #F9FAFB; border-radius: 4px; cursor: pointer;
            }
            .nx-picker .nx-toolbar button:hover { background: #F3F4F6; }
            .nx-picker table { width: 100%; border-collapse: collapse; font-size: 13px; }
            .nx-picker th { background: #F3F4F6; text-align: left; padding: 6px 8px; font-weight: 600; color: #374151; }
            .nx-picker td { padding: 6px 8px; border-top: 1px solid #F3F4F6; vertical-align: middle; }
            .nx-picker tr:hover td { background: #FAFAFA; }
            .nx-picker .nx-fieldname { font-family: Consolas, Menlo, monospace; font-size: 12px; color: #1F2937; }
            .nx-picker .nx-label { color: #6B7280; }
            .nx-picker .nx-fieldtype { font-size: 11px; color: #6B7280; padding: 1px 6px;
                background: #F3F4F6; border-radius: 3px; }
            .nx-picker .nx-reqd { color: #DC2626; font-weight: 700; margin-left: 3px; }
            .nx-picker .nx-warning { font-size: 11px; color: #92400E; background: #FEF3C7;
                padding: 1px 6px; border-radius: 3px; margin-left: 6px; }
            .nx-picker .nx-target-cell select { width: 100%; padding: 3px; font-size: 12px;
                border: 1px solid #D1D5DB; border-radius: 3px; }
            .nx-picker .nx-target-missing { color: #9CA3AF; font-style: italic; font-size: 12px; }
            .nx-picker .nx-child-block { border: 1px solid #E5E7EB; border-radius: 6px;
                margin: 12px 0; padding: 0; background: #FFFFFF; }
            .nx-picker .nx-child-header { padding: 8px 12px; background: #F9FAFB;
                border-bottom: 1px solid #E5E7EB; display: flex; align-items: center; gap: 10px;
                cursor: pointer; }
            .nx-picker .nx-child-body { padding: 8px 12px; }
            .nx-picker .nx-collapsed .nx-child-body { display: none; }
            .nx-picker .nx-chevron { font-size: 12px; color: #6B7280; }
            .nx-picker .nx-info-block { background: #EFF6FF; border-left: 3px solid #3B82F6;
                padding: 8px 12px; margin: 12px 0; font-size: 12px; color: #1E40AF; }
            .nx-picker .nx-pill { display: inline-block; padding: 1px 8px; border-radius: 10px;
                font-size: 11px; background: #DBEAFE; color: #1E40AF; margin-left: 6px; }
            .nx-picker .nx-pill-warn { background: #FEF3C7; color: #92400E; }
            .nx-picker input[type="checkbox"] { transform: scale(1.1); cursor: pointer; }
        </style>
        <div class="nx-picker">
    `);

    // ── Toolbar
    html.push(`
        <div class="nx-toolbar">
            <button data-nx-action="select-all-parent">✓ Select all parent</button>
            <button data-nx-action="clear-all-parent">✗ Clear all parent</button>
            <button data-nx-action="select-required">✓ Required only</button>
            <button data-nx-action="select-all-children">✓ Select all child tables</button>
            <button data-nx-action="clear-all-children">✗ Clear all child tables</button>
        </div>
    `);

    // ── Parent fields
    const parent_count = pairs.parent_pairs.length;
    const parent_picked = pairs.parent_pairs.filter(p => p.included).length;
    html.push(`
        <div class="nx-section-title">
            Parent Fields
            <span class="nx-counter">— ${parent_picked} of ${parent_count} selected by default</span>
        </div>
    `);
    html.push(render_field_table(pairs.parent_pairs, pairs, 'parent', null));

    // ── Child tables
    if (pairs.child_pairs && pairs.child_pairs.length) {
        html.push(`
            <div class="nx-section-title">
                Child Tables
                <span class="nx-counter">— ${pairs.child_pairs.length} found</span>
            </div>
        `);
        pairs.child_pairs.forEach((cp, idx) => {
            html.push(render_child_block(cp, pairs, idx));
        });
    }

    // ── Unmatched target-only fields
    if (pairs.unmatched_target_fields && pairs.unmatched_target_fields.length) {
        html.push(`
            <div class="nx-section-title">
                Target-only fields
                <span class="nx-counter">— exist on target but not on source. Informational; nothing to map.</span>
            </div>
            <div class="nx-info-block">
                ${pairs.unmatched_target_fields.map(f =>
                    `<code class="nx-fieldname">${escapeHtml(f.fieldname)}</code>
                     <span class="nx-fieldtype">${escapeHtml(f.fieldtype)}</span>`
                ).join(' &nbsp; ')}
            </div>
        `);
    }

    if (pairs.unmatched_target_tables && pairs.unmatched_target_tables.length) {
        html.push(`
            <div class="nx-info-block">
                <strong>Target-only child tables:</strong> ${pairs.unmatched_target_tables.map(t =>
                    `<code class="nx-fieldname">${escapeHtml(t.fieldname)}</code>`).join(', ')}
            </div>
        `);
    }

    html.push('</div>');
    return html.join('');
}


function render_field_table(field_pairs, all_pairs, scope, child_index) {
    const target_options = (scope === 'parent')
        ? buildTargetOptions(all_pairs)            // all parent target fields
        : buildChildTargetOptions(all_pairs.child_pairs[child_index]); // this child's target fields

    const rows = field_pairs.map((p, i) => {
        const checked = p.included ? 'checked' : '';
        const reqd = (p.target && p.target.reqd) ? '<span class="nx-reqd" title="Required on target">*</span>' : '';
        const warning = p.warning ? `<span class="nx-warning">${escapeHtml(p.warning)}</span>` : '';
        const auto = p.auto_match
            ? `<span class="nx-pill">auto: ${p.auto_match}</span>`
            : (p.target ? '' : '<span class="nx-pill nx-pill-warn">no match</span>');

        const target_select = render_target_select(target_options, p.target ? p.target.fieldname : '');

        return `
            <tr data-nx-scope="${scope}" data-nx-child="${child_index === null ? '' : child_index}" data-nx-row="${i}">
                <td style="width:40px; text-align:center;">
                    <input type="checkbox" data-nx-include ${checked}>
                </td>
                <td style="width:40%;">
                    <code class="nx-fieldname">${escapeHtml(p.source.fieldname)}</code>
                    <div class="nx-label">${escapeHtml(p.source.label || '')}
                        <span class="nx-fieldtype">${escapeHtml(p.source.fieldtype || '')}</span>
                        ${p.source.reqd ? '<span class="nx-reqd" title="Required on source">*</span>' : ''}
                    </div>
                </td>
                <td style="width:5%; text-align:center; color:#9CA3AF;">→</td>
                <td class="nx-target-cell" style="width:45%;">
                    ${target_select}
                    ${reqd} ${warning} ${auto}
                </td>
            </tr>
        `;
    }).join('');

    return `
        <table>
            <thead>
                <tr>
                    <th style="width:40px;">Sync</th>
                    <th>Source Field</th>
                    <th></th>
                    <th>Target Field</th>
                </tr>
            </thead>
            <tbody>${rows}</tbody>
        </table>
    `;
}


function render_child_block(cp, pairs, idx) {
    const tgt_label = cp.target
        ? `→ <code class="nx-fieldname">${escapeHtml(cp.target.fieldname)}</code>
           <span class="nx-fieldtype">${escapeHtml(cp.target.child_doctype)}</span>`
        : '<span class="nx-pill nx-pill-warn">no matching target table</span>';

    const inner_table = cp.field_pairs && cp.field_pairs.length
        ? render_field_table(cp.field_pairs, pairs, 'child', idx)
        : '<div class="nx-info-block">This child table has no user fields to map.</div>';

    return `
        <div class="nx-child-block" data-nx-child-block="${idx}">
            <div class="nx-child-header" data-nx-toggle>
                <input type="checkbox" data-nx-child-include ${cp.included ? 'checked' : ''}
                       title="Include this child table in sync">
                <span class="nx-chevron">▼</span>
                <strong>${escapeHtml(cp.source.label)}</strong>
                <code class="nx-fieldname">${escapeHtml(cp.source.fieldname)}</code>
                <span class="nx-fieldtype">${escapeHtml(cp.source.child_doctype)}</span>
                ${tgt_label}
            </div>
            <div class="nx-child-body">${inner_table}</div>
        </div>
    `;
}


function render_target_select(options, current_value) {
    const opts = ['<option value="">(none)</option>']
        .concat(options.map(o =>
            `<option value="${escapeHtml(o.fieldname)}" ${o.fieldname === current_value ? 'selected' : ''}>
                ${escapeHtml(o.label)} — ${escapeHtml(o.fieldtype)}
            </option>`
        ));
    return `<select data-nx-target>${opts.join('')}</select>`;
}


function buildTargetOptions(pairs) {
    // All target parent fields, including those that are currently unmatched
    const seen = new Set();
    const out = [];
    pairs.parent_pairs.forEach(p => {
        if (p.target && !seen.has(p.target.fieldname)) {
            seen.add(p.target.fieldname);
            out.push(p.target);
        }
    });
    pairs.unmatched_target_fields.forEach(t => {
        if (!seen.has(t.fieldname)) { seen.add(t.fieldname); out.push(t); }
    });
    out.sort((a, b) => a.fieldname.localeCompare(b.fieldname));
    return out;
}


function buildChildTargetOptions(child_pair) {
    const seen = new Set();
    const out = [];
    (child_pair.field_pairs || []).forEach(p => {
        if (p.target && !seen.has(p.target.fieldname)) {
            seen.add(p.target.fieldname);
            out.push(p.target);
        }
    });
    (child_pair.unmatched_target_fields || []).forEach(t => {
        if (!seen.has(t.fieldname)) { seen.add(t.fieldname); out.push(t); }
    });
    out.sort((a, b) => a.fieldname.localeCompare(b.fieldname));
    return out;
}


// ──────────────────────────────────────────────────────────────────────────
// Picker event handlers
// ──────────────────────────────────────────────────────────────────────────

function wire_picker_handlers($area, pairs) {
    // Toolbar buttons
    $area.on('click', '[data-nx-action]', function () {
        const action = $(this).data('nx-action');
        const $rows = $area.find('tbody tr');

        if (action === 'select-all-parent') {
            $rows.filter('[data-nx-scope="parent"]').find('[data-nx-include]').prop('checked', true);
        } else if (action === 'clear-all-parent') {
            $rows.filter('[data-nx-scope="parent"]').find('[data-nx-include]').prop('checked', false);
        } else if (action === 'select-required') {
            $rows.find('[data-nx-include]').prop('checked', false);
            $rows.filter('[data-nx-scope="parent"]').each(function () {
                const idx = $(this).data('nx-row');
                if (pairs.parent_pairs[idx].target && pairs.parent_pairs[idx].target.reqd) {
                    $(this).find('[data-nx-include]').prop('checked', true);
                }
            });
        } else if (action === 'select-all-children') {
            $area.find('[data-nx-child-include]').prop('checked', true);
        } else if (action === 'clear-all-children') {
            $area.find('[data-nx-child-include]').prop('checked', false);
        }
    });

    // Collapse / expand child blocks (clicking the header except the checkbox)
    $area.on('click', '[data-nx-toggle]', function (ev) {
        if ($(ev.target).is('input[type="checkbox"]')) return;
        $(this).closest('.nx-child-block').toggleClass('nx-collapsed');
        const $chev = $(this).find('.nx-chevron');
        $chev.text($(this).closest('.nx-child-block').hasClass('nx-collapsed') ? '▶' : '▼');
    });

    // When user changes target dropdown, sync it back into the pairs structure
    // (we rebuild on Apply, so we just need to keep the DOM authoritative here)
}


// ──────────────────────────────────────────────────────────────────────────
// Apply selection — write rows back to the form's child tables
// ──────────────────────────────────────────────────────────────────────────

function apply_picker_selection(frm, dialog, pairs) {
    const existing_rows = (frm.doc.field_mappings || []).length
                        + (frm.doc.child_table_mappings || []).length;

    const proceed = () => {
        // Clear existing rows then add fresh
        frm.clear_table('field_mappings');
        frm.clear_table('child_table_mappings');

        const $rows = dialog.get_field('picker_area').$wrapper.find('tbody tr');
        let parent_added = 0;
        let child_added = 0;

        // 1. Parent fields
        $rows.filter('[data-nx-scope="parent"]').each(function () {
            const $tr = $(this);
            const included = $tr.find('[data-nx-include]').is(':checked');
            const idx = $tr.data('nx-row');
            const pair = pairs.parent_pairs[idx];
            const target_field = $tr.find('[data-nx-target]').val();
            if (!included || !pair.source.fieldname || !target_field) return;

            const row = frm.add_child('field_mappings');
            row.included = 1;
            row.source_field = pair.source.fieldname;
            row.target_field = target_field;
            row.mapping_type = 'Direct';
            row.required_in_target = (pair.target && pair.target.reqd) ? 1 : 0;
            row.target_data_type = inferDataType(pair.target ? pair.target.fieldtype : '');
            parent_added++;
        });

        // 2. Child tables (one row per *included* table; nested field selection
        //    is encoded into `description` for now — a future enhancement is
        //    to auto-create per-child Mapping documents.)
        const $blocks = dialog.get_field('picker_area').$wrapper.find('.nx-child-block');
        $blocks.each(function () {
            const $b = $(this);
            const cidx = $b.data('nx-child-block');
            const cp = pairs.child_pairs[cidx];
            if (!cp || !cp.target) return;

            const child_included = $b.find('[data-nx-child-include]').is(':checked');
            if (!child_included) return;

            const row = frm.add_child('child_table_mappings');
            row.included = 1;
            row.source_table_field = cp.source.fieldname;
            row.target_table_field = cp.target.fieldname;
            row.source_child_doctype = cp.source.child_doctype;
            row.target_child_doctype = cp.target.child_doctype;
            child_added++;

            // Note: Frappe doesn't support nested grid editing inside a Mapping
            // Row directly. We don't create per-table Mapping documents
            // automatically because that would clutter the database; the user
            // can create them later if they need scripted transforms inside a
            // child table. For straightforward direct copy of all child
            // fields, the engine falls back to dict(item).
        });

        frm.refresh_field('field_mappings');
        frm.refresh_field('child_table_mappings');
        dialog.hide();

        frappe.show_alert({
            message: __('Added {0} field mappings and {1} child tables.', [parent_added, child_added]),
            indicator: 'green'
        }, 6);
    };

    if (existing_rows > 0) {
        frappe.confirm(
            __('This will replace your existing {0} mapping row(s). Continue?', [existing_rows]),
            proceed
        );
    } else {
        proceed();
    }
}


// ──────────────────────────────────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────────────────────────────────

function inferDataType(fieldtype) {
    const map = {
        'Int': 'Int', 'Float': 'Float', 'Currency': 'Currency', 'Percent': 'Float',
        'Date': 'Date', 'Datetime': 'Datetime', 'Check': 'Check',
        'Link': 'Link', 'Dynamic Link': 'Link', 'JSON': 'JSON',
        'Text': 'Text', 'Long Text': 'Text', 'Small Text': 'Text',
        'Code': 'Text', 'Text Editor': 'Text'
    };
    return map[fieldtype] || 'Data';
}


function escapeHtml(s) {
    return String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}


function show_inclusion_summary(frm) {
    const fm = frm.doc.field_mappings || [];
    const ctm = frm.doc.child_table_mappings || [];
    const fm_on = fm.filter(r => r.included).length;
    const ctm_on = ctm.filter(r => r.included).length;
    frappe.msgprint({
        title: __('Inclusion Summary'),
        message: `
            <table style="width:100%; font-size:13px;">
              <tr><td><strong>Parent fields:</strong></td>
                  <td style="text-align:right;">${fm_on} of ${fm.length} included</td></tr>
              <tr><td><strong>Child tables:</strong></td>
                  <td style="text-align:right;">${ctm_on} of ${ctm.length} included</td></tr>
            </table>
            <hr/>
            <p style="font-size:12px; color:#6B7280;">
                Untick the <em>Sync</em> column on any row to exclude that field
                without removing it. Untick a child table row to skip the entire table.
            </p>
        `,
        indicator: 'blue'
    });
}
