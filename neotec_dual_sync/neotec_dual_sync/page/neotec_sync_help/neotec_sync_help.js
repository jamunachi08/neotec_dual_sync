// Neotec Sync — "How Sync Works" page
//
// A welcoming first-touch page for new users. Renders:
//   1. A 3-line plain-English intro
//   2. The flow diagram (same SVG used in the design discussions)
//   3. A 5-step quickstart
//   4. "What if a document didn't sync?" troubleshooting section
//   5. Links into Settings, Sync Log, Conflicts

frappe.pages['neotec-sync-help'].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __('How Sync Works'),
        single_column: true
    });

    page.set_secondary_action(__('Open Settings'), () => {
        frappe.set_route('Form', 'Neotec Sync Settings', 'Neotec Sync Settings');
    });

    page.set_primary_action(__('Open Sync Log'), () => {
        frappe.set_route('List', 'Neotec Sync Log');
    }, 'list');

    const $body = $(wrapper).find('.layout-main-section');
    $body.html(renderHelpHTML());

    // Wire the inline buttons
    $body.on('click', '[data-nx-help-action]', function () {
        const action = $(this).data('nx-help-action');
        if (action === 'settings') frappe.set_route('Form', 'Neotec Sync Settings', 'Neotec Sync Settings');
        if (action === 'logs') frappe.set_route('List', 'Neotec Sync Log');
        if (action === 'failures') frappe.set_route('List', 'Neotec Sync Log', { status: 'Failed' });
        if (action === 'conflicts') frappe.set_route('List', 'Neotec Sync Conflict', { status: 'Open' });
        if (action === 'mappings') frappe.set_route('List', 'Neotec Sync Mapping');
    });
};


function renderHelpHTML() {
    return `
        <style>
            .nx-help { max-width: 920px; margin: 0 auto; padding: 24px; font-size: 14px;
                       line-height: 1.6; color: #1F2937; }
            .nx-help h1 { font-size: 28px; font-weight: 600; margin: 0 0 6px;
                          color: #1F2937; }
            .nx-help .nx-help-tagline { font-size: 16px; color: #6B7280;
                                        margin: 0 0 28px; }
            .nx-help h2 { font-size: 18px; font-weight: 600; margin: 32px 0 12px;
                          color: #1E40AF; padding-bottom: 6px;
                          border-bottom: 2px solid #E5E7EB; }
            .nx-help h3 { font-size: 15px; font-weight: 600; margin: 20px 0 8px;
                          color: #1F2937; }
            .nx-help p { margin: 0 0 12px; }
            .nx-help code { font-family: Consolas, Menlo, monospace; font-size: 13px;
                            background: #F3F4F6; padding: 2px 6px; border-radius: 3px; }
            .nx-help .nx-callout { background: #EFF6FF; border-left: 4px solid #3B82F6;
                                   padding: 12px 16px; border-radius: 4px;
                                   margin: 16px 0; color: #1E40AF; }
            .nx-help .nx-warn { background: #FEF3C7; border-left-color: #F59E0B;
                                color: #92400E; }
            .nx-help .nx-good { background: #D1FAE5; border-left-color: #10B981;
                                color: #065F46; }
            .nx-help .nx-step { background: #FFF; border: 1px solid #E5E7EB;
                                border-radius: 8px; padding: 14px 18px; margin: 10px 0;
                                display: flex; align-items: flex-start; gap: 14px; }
            .nx-help .nx-step-num { background: #1E40AF; color: white; width: 28px;
                                    height: 28px; border-radius: 50%;
                                    display: flex; align-items: center; justify-content: center;
                                    font-weight: 600; flex-shrink: 0; }
            .nx-help .nx-step-body { flex: 1; }
            .nx-help .nx-step-body strong { display: block; margin-bottom: 4px; font-size: 14px; }
            .nx-help .nx-step-body p { margin: 0; color: #4B5563; font-size: 13px; }
            .nx-help .nx-button-row { display: flex; gap: 8px; flex-wrap: wrap; margin: 8px 0; }
            .nx-help button.nx-action {
                padding: 6px 14px; font-size: 13px; background: #FFF;
                border: 1px solid #D1D5DB; border-radius: 6px; cursor: pointer;
                color: #1F2937;
            }
            .nx-help button.nx-action:hover { background: #F9FAFB; border-color: #1E40AF; }
            .nx-help button.nx-action.nx-primary {
                background: #1E40AF; color: white; border-color: #1E40AF;
            }
            .nx-help button.nx-action.nx-primary:hover { background: #1E3A8A; }
            .nx-help .nx-diagram-wrap {
                background: #FAFBFC; border: 1px solid #E5E7EB; border-radius: 12px;
                padding: 20px; margin: 16px 0; overflow-x: auto;
            }
            .nx-help .nx-diagram-wrap svg { max-width: 100%; height: auto; display: block; margin: 0 auto; }
            .nx-help table { width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 13px; }
            .nx-help th { background: #F3F4F6; text-align: left; padding: 8px 10px;
                          font-weight: 600; color: #374151; }
            .nx-help td { padding: 8px 10px; border-top: 1px solid #E5E7EB;
                          vertical-align: top; }
            .nx-help .nx-status-row td:first-child { white-space: nowrap; }
            .nx-help .nx-status-pill {
                display: inline-block; padding: 2px 10px; border-radius: 12px;
                font-size: 12px; font-weight: 500;
            }
            .nx-help .nx-status-green  { background: #D1FAE5; color: #065F46; }
            .nx-help .nx-status-red    { background: #FEE2E2; color: #991B1B; }
            .nx-help .nx-status-amber  { background: #FEF3C7; color: #92400E; }
            .nx-help .nx-status-blue   { background: #DBEAFE; color: #1E40AF; }
            .nx-help .nx-status-gray   { background: #F3F4F6; color: #4B5563; }
        </style>

        <div class="nx-help">
            <h1>${__('How Sync Works')}</h1>
            <p class="nx-help-tagline">${__(
                'A 3-minute primer on what this app does, how to set it up, and what to do when something doesn\'t sync.'
            )}</p>

            ${renderIntroSection()}
            ${renderDiagramSection()}
            ${renderQuickstartSection()}
            ${renderTroubleshootSection()}
            ${renderStatusKeySection()}
            ${renderQuickLinksSection()}
        </div>
    `;
}


function renderIntroSection() {
    return `
        <h2>${__('What this app does')}</h2>
        <p>${__(
            'Neotec Dual Sync keeps two Frappe / ERPNext instances in agreement on the documents you choose to share — Sales Orders, Customers, Items, or any DocType you configure.'
        )}</p>
        <p>${__(
            'You keep working in ERPNext as usual. Saved documents that match your sync rules are sent to the other instance automatically. Failed syncs are retried; conflicts are flagged for human review.'
        )}</p>
        <div class="nx-callout nx-good">
            <strong>${__('Designed to stay out of your way.')}</strong> ${__(
                'Documents not in your sync rules cost zero CPU on save. The dispatcher runs in the background and stays idle when there\'s nothing to do.'
            )}
        </div>
    `;
}


function renderDiagramSection() {
    return `
        <h2>${__('What happens when you save a document')}</h2>
        <p>${__(
            'Every save passes through three fast O(1) gates before any database work happens. Most saves never reach the queue at all — they\'re filtered out in microseconds.'
        )}</p>
        <div class="nx-diagram-wrap">
            ${renderFlowSVG()}
        </div>
        <p style="font-size:13px; color:#6B7280; text-align:center; margin-top: 8px;">
            ${__('Teal gates are O(1) checks. Purple steps are the only writes. Amber steps run in the background, separate from your save.')}
        </p>
    `;
}


function renderFlowSVG() {
    return `
<svg viewBox="0 0 680 760" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Sync flow diagram">
  <defs>
    <marker id="nxhArrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M2 1 L8 5 L2 9" fill="none" stroke="#5F5E5A" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </marker>
  </defs>

  <text x="340" y="32" text-anchor="middle" font-family="sans-serif" font-size="15" font-weight="600" fill="#1F2937">User saves a document</text>
  <text x="340" y="52" text-anchor="middle" font-family="sans-serif" font-size="12" fill="#6B7280">Any DocType, anywhere in ERPNext</text>

  <rect x="220" y="68" width="240" height="44" rx="8" fill="#F1EFE8" stroke="#5F5E5A" stroke-width="0.5"/>
  <text x="340" y="86" text-anchor="middle" font-family="sans-serif" font-size="14" font-weight="500" fill="#2C2C2A">Frappe fires doc_event</text>
  <text x="340" y="103" text-anchor="middle" font-family="sans-serif" font-size="12" fill="#5F5E5A">on_update / on_submit / after_insert</text>
  <line x1="340" y1="112" x2="340" y2="138" stroke="#5F5E5A" stroke-width="1.5" marker-end="url(#nxhArrow)"/>

  <rect x="180" y="138" width="320" height="56" rx="8" fill="#E1F5EE" stroke="#0F6E56" stroke-width="0.5"/>
  <text x="340" y="158" text-anchor="middle" font-family="sans-serif" font-size="14" font-weight="500" fill="#04342C">Gate 1: framework exclusion</text>
  <text x="340" y="178" text-anchor="middle" font-family="sans-serif" font-size="12" fill="#0F6E56">Email Queue, Version, View Log etc — instant skip</text>
  <line x1="340" y1="194" x2="340" y2="220" stroke="#5F5E5A" stroke-width="1.5" marker-end="url(#nxhArrow)"/>

  <rect x="180" y="220" width="320" height="56" rx="8" fill="#E1F5EE" stroke="#0F6E56" stroke-width="0.5"/>
  <text x="340" y="240" text-anchor="middle" font-family="sans-serif" font-size="14" font-weight="500" fill="#04342C">Gate 2: in-process scope cache</text>
  <text x="340" y="260" text-anchor="middle" font-family="sans-serif" font-size="12" fill="#0F6E56">Is this DocType in your Rules? Module allowed?</text>
  <line x1="340" y1="276" x2="340" y2="302" stroke="#5F5E5A" stroke-width="1.5" marker-end="url(#nxhArrow)"/>

  <rect x="180" y="302" width="320" height="56" rx="8" fill="#E1F5EE" stroke="#0F6E56" stroke-width="0.5"/>
  <text x="340" y="322" text-anchor="middle" font-family="sans-serif" font-size="14" font-weight="500" fill="#04342C">Gate 3: loopback flag</text>
  <text x="340" y="342" text-anchor="middle" font-family="sans-serif" font-size="12" fill="#0F6E56">Did this save come from inbound sync?</text>
  <line x1="340" y1="358" x2="340" y2="386" stroke="#5F5E5A" stroke-width="1.5" marker-end="url(#nxhArrow)"/>

  <rect x="180" y="386" width="320" height="56" rx="8" fill="#EEEDFE" stroke="#534AB7" stroke-width="0.5"/>
  <text x="340" y="406" text-anchor="middle" font-family="sans-serif" font-size="14" font-weight="500" fill="#26215C">INSERT one row into Sync Log</text>
  <text x="340" y="426" text-anchor="middle" font-family="sans-serif" font-size="12" fill="#534AB7">Status = Queued. User's request ends here.</text>

  <line x1="220" y1="160" x2="84" y2="160" stroke="#5F5E5A" stroke-width="1.5" marker-end="url(#nxhArrow)"/>
  <line x1="220" y1="242" x2="84" y2="242" stroke="#5F5E5A" stroke-width="1.5" marker-end="url(#nxhArrow)"/>
  <line x1="220" y1="324" x2="84" y2="324" stroke="#5F5E5A" stroke-width="1.5" marker-end="url(#nxhArrow)"/>

  <rect x="20" y="142" width="60" height="36" rx="6" fill="#F1EFE8" stroke="#888780" stroke-width="0.5"/>
  <text x="50" y="158" text-anchor="middle" font-family="sans-serif" font-size="11" fill="#444441">Skip</text>
  <text x="50" y="170" text-anchor="middle" font-family="sans-serif" font-size="10" fill="#888780">~1µs</text>

  <rect x="20" y="224" width="60" height="36" rx="6" fill="#F1EFE8" stroke="#888780" stroke-width="0.5"/>
  <text x="50" y="240" text-anchor="middle" font-family="sans-serif" font-size="11" fill="#444441">Skip</text>
  <text x="50" y="252" text-anchor="middle" font-family="sans-serif" font-size="10" fill="#888780">~1µs</text>

  <rect x="20" y="306" width="60" height="36" rx="6" fill="#F1EFE8" stroke="#888780" stroke-width="0.5"/>
  <text x="50" y="322" text-anchor="middle" font-family="sans-serif" font-size="11" fill="#444441">Skip</text>
  <text x="50" y="334" text-anchor="middle" font-family="sans-serif" font-size="10" fill="#888780">~1µs</text>

  <line x1="340" y1="468" x2="340" y2="496" stroke="#888780" stroke-width="0.5" stroke-dasharray="4 4"/>
  <text x="354" y="486" text-anchor="start" font-family="sans-serif" font-size="11" fill="#888780">Background, separate from user request</text>

  <rect x="180" y="500" width="320" height="56" rx="8" fill="#FAEEDA" stroke="#854F0B" stroke-width="0.5"/>
  <text x="340" y="520" text-anchor="middle" font-family="sans-serif" font-size="14" font-weight="500" fill="#412402">Cron every 5 min: dispatcher wakes</text>
  <text x="340" y="540" text-anchor="middle" font-family="sans-serif" font-size="12" fill="#854F0B">Throttle + EXISTS probe — empty queue → return</text>
  <line x1="340" y1="556" x2="340" y2="582" stroke="#5F5E5A" stroke-width="1.5" marker-end="url(#nxhArrow)"/>

  <rect x="180" y="582" width="320" height="56" rx="8" fill="#FAEEDA" stroke="#854F0B" stroke-width="0.5"/>
  <text x="340" y="602" text-anchor="middle" font-family="sans-serif" font-size="14" font-weight="500" fill="#412402">Send batch over HTTPS</text>
  <text x="340" y="622" text-anchor="middle" font-family="sans-serif" font-size="12" fill="#854F0B">Receiver: idempotency + route trace + hop check</text>
  <line x1="340" y1="638" x2="340" y2="664" stroke="#5F5E5A" stroke-width="1.5" marker-end="url(#nxhArrow)"/>

  <rect x="180" y="664" width="320" height="56" rx="8" fill="#EEEDFE" stroke="#534AB7" stroke-width="0.5"/>
  <text x="340" y="684" text-anchor="middle" font-family="sans-serif" font-size="14" font-weight="500" fill="#26215C">Update Sync Log row to Success</text>
  <text x="340" y="704" text-anchor="middle" font-family="sans-serif" font-size="12" fill="#534AB7">No write back to your business document</text>
</svg>
    `;
}


function renderQuickstartSection() {
    return `
        <h2>${__('Your first 5 minutes')}</h2>
        <div class="nx-step">
            <div class="nx-step-num">1</div>
            <div class="nx-step-body">
                <strong>${__('Enter remote credentials in Settings.')}</strong>
                <p>${__(
                    'Open Sync Settings and fill in Remote Base URL, API Key, API Secret, and Shared Secret of the other instance.'
                )}</p>
            </div>
        </div>
        <div class="nx-step">
            <div class="nx-step-num">2</div>
            <div class="nx-step-body">
                <strong>${__('Test the connection.')}</strong>
                <p>${__(
                    'Click Actions → Test Connection. You should see a green ✓. Resolve any HTTPS or credential errors before proceeding.'
                )}</p>
            </div>
        </div>
        <div class="nx-step">
            <div class="nx-step-num">3</div>
            <div class="nx-step-body">
                <strong>${__('Add at least one Rule.')}</strong>
                <p>${__(
                    'In the Rules table at the bottom of Settings, add a row: pick a DocType to sync, a Trigger Mode, and a Duplicate Policy.'
                )}</p>
            </div>
        </div>
        <div class="nx-step">
            <div class="nx-step-num">4</div>
            <div class="nx-step-body">
                <strong>${__('Optionally narrow with Module Filters.')}</strong>
                <p>${__(
                    'In the Sync Scope section, list the modules you actually want to sync (e.g. Selling, Stock). Empty = all modules. Narrower = lower load.'
                )}</p>
            </div>
        </div>
        <div class="nx-step">
            <div class="nx-step-num">5</div>
            <div class="nx-step-body">
                <strong>${__('Tick Enabled and save.')}</strong>
                <p>${__(
                    'From this point, saves of documents matching your rules will sync automatically. Save a test document and watch the Sync Log.'
                )}</p>
            </div>
        </div>
        <div class="nx-button-row" style="margin-top: 20px;">
            <button class="nx-action nx-primary" data-nx-help-action="settings">${__('Open Settings')}</button>
            <button class="nx-action" data-nx-help-action="logs">${__('Open Sync Log')}</button>
        </div>
    `;
}


function renderTroubleshootSection() {
    return `
        <h2>${__('What if a document didn\'t sync?')}</h2>
        <p>${__('Sync issues fall into three categories. Each has a specific place to look:')}</p>

        <h3>${__('A. "I want to know if THIS document synced"')}</h3>
        <p>${__(
            'Open the document. If its DocType is in your sync scope, you\'ll see a coloured indicator near the top showing the latest sync status. The Neotec Sync menu has Sync Now and Sync History buttons.'
        )}</p>

        <h3>${__('B. "Show me everything that didn\'t sync"')}</h3>
        <p>${__(
            'Open Sync Log. Use the quick filters at the top — "Failed this week", "Failed this month", "Currently queued" — to triage. Tick rows and choose Actions → Bulk Re-queue to retry many at once.'
        )}</p>
        <div class="nx-button-row">
            <button class="nx-action" data-nx-help-action="failures">${__('See all Failed logs')}</button>
            <button class="nx-action" data-nx-help-action="logs">${__('Open Sync Log')}</button>
        </div>

        <h3>${__('C. "Re-send this one document right now"')}</h3>
        <p>${__(
            'Open the document. Click Neotec Sync → Sync Now. The button bypasses the cron schedule and dispatches immediately — you\'ll see Synced ✓ or Failed ✗ within a few seconds.'
        )}</p>

        <div class="nx-callout nx-warn">
            <strong>${__('Common reasons a sync fails:')}</strong>
            <ul style="margin: 8px 0 0 20px; padding: 0;">
                <li>${__('Required field is empty after mapping → fix your Mapping or set a Default Value')}</li>
                <li>${__('Remote rejected the credentials → re-check API Key/Secret on the remote')}</li>
                <li>${__('Network timeout → check the remote is up; the retry job will catch up automatically')}</li>
                <li>${__('Loop blocked → topology error, check Hop Count and route trace')}</li>
            </ul>
        </div>
    `;
}


function renderStatusKeySection() {
    return `
        <h2>${__('Sync Log status key')}</h2>
        <table>
            <thead>
                <tr>
                    <th>${__('Status')}</th>
                    <th>${__('Meaning')}</th>
                </tr>
            </thead>
            <tbody>
                <tr class="nx-status-row">
                    <td><span class="nx-status-pill nx-status-amber">Queued</span></td>
                    <td>${__('Created and waiting for the dispatcher.')}</td>
                </tr>
                <tr class="nx-status-row">
                    <td><span class="nx-status-pill nx-status-amber">Processing</span></td>
                    <td>${__('Currently being sent.')}</td>
                </tr>
                <tr class="nx-status-row">
                    <td><span class="nx-status-pill nx-status-green">Success</span></td>
                    <td>${__('Sent and acknowledged by the remote.')}</td>
                </tr>
                <tr class="nx-status-row">
                    <td><span class="nx-status-pill nx-status-red">Failed</span></td>
                    <td>${__('Last attempt failed. Will retry automatically up to Max Retries.')}</td>
                </tr>
                <tr class="nx-status-row">
                    <td><span class="nx-status-pill nx-status-gray">Skipped</span></td>
                    <td>${__('No action needed (document gone, no rule, or unchanged content).')}</td>
                </tr>
                <tr class="nx-status-row">
                    <td><span class="nx-status-pill nx-status-gray">Duplicate</span></td>
                    <td>${__('Receiver already saw this transaction — idempotency rejected.')}</td>
                </tr>
                <tr class="nx-status-row">
                    <td><span class="nx-status-pill nx-status-gray">Loop Prevented</span></td>
                    <td>${__('Document was looping between instances — dropped to protect both sides.')}</td>
                </tr>
                <tr class="nx-status-row">
                    <td><span class="nx-status-pill nx-status-blue">Received</span></td>
                    <td>${__('Inbound — successfully applied from a remote.')}</td>
                </tr>
            </tbody>
        </table>
    `;
}


function renderQuickLinksSection() {
    return `
        <h2>${__('Quick links')}</h2>
        <div class="nx-button-row">
            <button class="nx-action" data-nx-help-action="settings">${__('Sync Settings')}</button>
            <button class="nx-action" data-nx-help-action="logs">${__('Sync Log')}</button>
            <button class="nx-action" data-nx-help-action="failures">${__('Failed Logs')}</button>
            <button class="nx-action" data-nx-help-action="conflicts">${__('Open Conflicts')}</button>
            <button class="nx-action" data-nx-help-action="mappings">${__('Mappings')}</button>
        </div>
    `;
}
