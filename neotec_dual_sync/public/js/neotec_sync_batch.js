frappe.ui.form.on('Neotec Sync Batch', {
  refresh(frm) {
    if (!frm.is_new()) {
      frm.add_custom_button(__('Run Batch'), function() {
        frappe.call({
          method: 'neotec_dual_sync.api.services.run_batch',
          args: { batch_name: frm.doc.name },
          callback: function(r) {
            if (r.message) {
              frappe.msgprint(__('Batch processed: {0}', [r.message.processed || 0]));
              frm.reload_doc();
            }
          }
        });
      });
    }
  }
});
