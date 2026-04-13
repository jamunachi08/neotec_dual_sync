frappe.ui.form.on("Neotec Sync Settings", {
    refresh(frm) {
        frm.add_custom_button("Test Connection", () => {
            frappe.call("neotec_dual_sync.doctype.neotec_sync_settings.neotec_sync_settings.test_connection")
                .then(r => frappe.msgprint(r.message || "Connection test completed."));
        });
    }
});
