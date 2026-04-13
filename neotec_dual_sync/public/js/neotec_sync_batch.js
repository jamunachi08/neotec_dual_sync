frappe.ui.form.on("Neotec Sync Batch", {
    refresh(frm) {
        if (!frm.is_new()) {
            frm.add_custom_button("Run Batch", () => {
                frappe.call({method: "run_batch", doc: frm.doc}).then(() => frm.reload_doc());
            });
        }
    }
});
