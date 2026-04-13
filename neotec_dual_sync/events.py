from neotec_dual_sync.mapping import get_matching_rules, should_run_for_event
from neotec_dual_sync.jobs import enqueue_rule

def handle_on_submit(doc, method=None):
    for rule in get_matching_rules(doc):
        if should_run_for_event(rule, "on_submit", doc):
            enqueue_rule(doc, rule["name"], "on_submit")

def handle_update_after_submit(doc, method=None):
    return
