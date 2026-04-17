# Neotec Dual Sync v1.4.0

Enhanced Frappe Cloud-safe synchronization framework for dual-instance ERPNext/Frappe deployments.

## Included
- Three-level Frappe app structure
- Fixtures for roles and workspace export placeholder
- Enhanced Neotec Sync Settings UI
- DocType link selectors in Rules grid for Source DocType and Target DocType
- Batch and On Submit processing modes
- Queue/retry controls, dry-run mode, log level, audit snapshot, secret masking
- Generic sync rules and field mapping tables

## Post-install
Run these commands after updating the app:

```bash
bench --site yoursite reload-doc neotec_dual_sync doctype neotec_sync_rule
bench --site yoursite reload-doc neotec_dual_sync doctype neotec_sync_settings
bench --site yoursite migrate
bench --site yoursite clear-cache
bench build --app neotec_dual_sync
```
