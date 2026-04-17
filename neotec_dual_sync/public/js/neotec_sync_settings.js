frappe.ui.form.on("Neotec Sync Settings", {
  onload(frm) {
    bind_rule_queries(frm);
  },

  refresh(frm) {
    bind_rule_queries(frm);

    frm.add_custom_button(__("Validate Configuration"), function () {
      frappe.msgprint(__("Configuration validation placeholder completed."));
    });
  },

  default_trigger_mode(frm) {
    apply_defaults_to_blank_rows(frm);
  }
});

function bind_rule_queries(frm) {
  if (!frm.fields_dict.rules || !frm.fields_dict.rules.grid) return;

  const grid = frm.fields_dict.rules.grid;
  const doctype_query = () => ({
    filters: {
      istable: 0,
      issingle: 0,
      is_virtual: 0,
    },
  });

  ["source_doctype", "target_doctype"].forEach((fieldname) => {
    const field = grid.get_field(fieldname);
    if (field) {
      field.get_query = doctype_query;
    }
  });

  grid.wrapper.on("click", ".grid-add-row", () => {
    setTimeout(() => {
      const rows = frm.doc.rules || [];
      const row = rows[rows.length - 1];
      if (row && !row.trigger_mode && frm.doc.default_trigger_mode) {
        frappe.model.set_value(row.doctype, row.name, "trigger_mode", frm.doc.default_trigger_mode);
      }
    }, 100);
  });

  frm.fields_dict.rules.grid.on_grid_fields_dict = function (doc) {
    return {
      source_doctype: { get_query: doctype_query },
      target_doctype: { get_query: doctype_query },
    };
  };

  frm.refresh_field("rules");
}

function apply_defaults_to_blank_rows(frm) {
  (frm.doc.rules || []).forEach((row) => {
    if (!row.trigger_mode && frm.doc.default_trigger_mode) {
      frappe.model.set_value(row.doctype, row.name, "trigger_mode", frm.doc.default_trigger_mode);
    }
  });
}

frappe.ui.form.on("Neotec Sync Rule", {
  source_doctype(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    if (!row.target_doctype && row.source_doctype) {
      frappe.model.set_value(cdt, cdn, "target_doctype", row.source_doctype);
    }
    if (!row.trigger_mode && frm.doc.default_trigger_mode) {
      frappe.model.set_value(cdt, cdn, "trigger_mode", frm.doc.default_trigger_mode);
    }
  }
});
