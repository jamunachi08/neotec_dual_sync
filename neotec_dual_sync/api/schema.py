"""
Neotec Dual Sync — Schema Inspection.

Returns the field structure of a DocType: parent fields, child tables, and
the fields of those child tables. Used by the Mapping form's "Fetch Fields"
button to populate the field selection dialog.

Two modes:
  * Local — read frappe.get_meta() on this instance.
  * Remote — call the remote's whitelisted endpoint over authenticated HTTPS
    so the source can present the *target's* schema (which may differ from
    the source's own, especially when the two sides have different custom
    fields).

Returned shape is intentionally compact and JSON-friendly:

    {
        "doctype": "Sales Order",
        "module":  "Selling",
        "is_submittable": 1,
        "fields": [
            {
                "fieldname": "customer",
                "label":     "Customer",
                "fieldtype": "Link",
                "options":   "Customer",
                "reqd":      1,
                "read_only": 0,
                "is_child":  False,
            },
            ...
        ],
        "child_tables": [
            {
                "fieldname":     "items",
                "label":         "Items",
                "child_doctype": "Sales Order Item",
                "fields": [ {fieldname, label, fieldtype, options, reqd, ...}, ... ]
            },
            ...
        ]
    }
"""
from __future__ import annotations

import json

import frappe
import requests
from frappe import _


# Field types that aren't user data — we hide them from the field picker by
# default (the user can still see them via "Show System Fields").
_SYSTEM_FIELDTYPES = frozenset({
    "Section Break", "Column Break", "Tab Break", "HTML", "Heading",
    "Button", "Image", "Fold", "Table Break",
})

# DocType columns Frappe creates automatically — never useful to map by hand.
_FRAPPE_INTERNAL_FIELDS = frozenset({
    "name", "owner", "creation", "modified", "modified_by",
    "docstatus", "idx", "_user_tags", "_comments", "_assign",
    "_liked_by", "_seen", "lft", "rgt", "old_parent",
    "parent", "parentfield", "parenttype",
})


def get_local_schema(doctype: str, include_system: bool = False) -> dict:
    """
    Inspect a DocType on THIS instance and return its parent + child schema.
    """
    if not doctype:
        frappe.throw(_("DocType is required"))

    try:
        meta = frappe.get_meta(doctype)
    except frappe.DoesNotExistError:
        frappe.throw(_("DocType '{0}' does not exist on this instance.").format(doctype))

    parent_fields = []
    child_tables = []

    for df in meta.fields:
        if not include_system and df.fieldtype in _SYSTEM_FIELDTYPES:
            continue
        if df.fieldname in _FRAPPE_INTERNAL_FIELDS:
            continue

        if df.fieldtype in ("Table", "Table MultiSelect"):
            child_doctype = df.options
            if not child_doctype:
                continue
            child_tables.append({
                "fieldname": df.fieldname,
                "label": df.label or df.fieldname,
                "child_doctype": child_doctype,
                "reqd": int(df.reqd or 0),
                "fields": _child_table_fields(child_doctype, include_system),
            })
        else:
            parent_fields.append(_field_summary(df))

    return {
        "doctype": doctype,
        "module": meta.module,
        "is_submittable": int(meta.is_submittable or 0),
        "is_table": int(meta.istable or 0),
        "fields": parent_fields,
        "child_tables": child_tables,
    }


def _child_table_fields(child_doctype: str, include_system: bool) -> list[dict]:
    """Return the user-facing fields of a child DocType."""
    try:
        meta = frappe.get_meta(child_doctype)
    except frappe.DoesNotExistError:
        return []

    out = []
    for df in meta.fields:
        if not include_system and df.fieldtype in _SYSTEM_FIELDTYPES:
            continue
        if df.fieldname in _FRAPPE_INTERNAL_FIELDS:
            continue
        if df.fieldtype in ("Table", "Table MultiSelect"):
            # Nested child tables are rare; flag but don't recurse for now
            continue
        out.append(_field_summary(df))
    return out


def _field_summary(df) -> dict:
    """Pull the subset of DocField metadata the UI needs."""
    return {
        "fieldname": df.fieldname,
        "label": df.label or df.fieldname,
        "fieldtype": df.fieldtype,
        "options": (df.options or "").split("\n")[0] if df.options else "",
        "reqd": int(df.reqd or 0),
        "read_only": int(df.read_only or 0),
        "hidden": int(df.hidden or 0),
        "default": df.default or "",
        "description": (df.description or "")[:200],
    }


# ---------------------------------------------------------------------------
# Remote schema fetch
# ---------------------------------------------------------------------------

def get_remote_schema(doctype: str, include_system: bool = False) -> dict:
    """
    Ask the configured remote for its schema of `doctype`. Uses the same
    API credentials and HTTPS settings as ordinary sync. Returns the same
    shape as get_local_schema().
    """
    from neotec_dual_sync.api.services import get_settings

    settings = get_settings()
    if not settings.remote_base_url:
        frappe.throw(_("Remote Base URL is not configured in Sync Settings."))
    if not settings.api_key:
        frappe.throw(_("Remote API credentials are not configured."))

    url = (
        settings.remote_base_url.rstrip("/")
        + "/api/method/neotec_dual_sync.api.fetch_schema"
    )
    headers = {
        "Content-Type": "application/json",
        "Authorization": "token {}:{}".format(
            settings.api_key or "",
            settings.get_password("api_secret") or "",
        ),
    }
    params = {
        "doctype": doctype,
        "include_system": 1 if include_system else 0,
    }

    try:
        resp = requests.get(
            url, headers=headers, params=params,
            verify=bool(settings.verify_ssl),
            timeout=int(settings.timeout_seconds or 30),
        )
    except requests.exceptions.SSLError as e:
        frappe.throw(_("SSL error talking to remote: {0}").format(e))
    except requests.exceptions.ConnectionError as e:
        frappe.throw(_("Could not connect to remote: {0}").format(e))
    except requests.exceptions.Timeout:
        frappe.throw(_("Timed out fetching remote schema."))

    if resp.status_code == 401:
        frappe.throw(_("Remote rejected credentials (401). Check API Key/Secret."))
    if resp.status_code == 403:
        frappe.throw(_("Remote rejected the request (403). Check user role."))
    if resp.status_code != 200:
        frappe.throw(_("Remote returned HTTP {0}: {1}").format(resp.status_code, resp.text[:300]))

    try:
        data = resp.json()
    except Exception:
        frappe.throw(_("Remote response was not valid JSON."))

    schema = data.get("message") if isinstance(data, dict) else None
    if not schema or not isinstance(schema, dict):
        frappe.throw(_("Remote response did not include schema."))
    if "error" in schema:
        frappe.throw(_("Remote error: {0}").format(schema["error"]))

    return schema


# ---------------------------------------------------------------------------
# Pairing — match source fields to target fields
# ---------------------------------------------------------------------------

def pair_fields(source_schema: dict, target_schema: dict) -> dict:
    """
    Build a default pairing of source fields to target fields based on
    fieldname match, then label match. Returns a dict ready for the UI.

    {
      "parent_pairs": [
        {
          "source": {fieldname,label,fieldtype,reqd,...},
          "target": {fieldname,label,fieldtype,reqd,...} | None,
          "included": 1,                  # default ON if both sides have it
          "auto_match": "name"|"label"|None,
          "warning": "" | "type mismatch: Data -> Int"
        },
        ...
      ],
      "child_pairs": [
        {
          "source": {fieldname,label,child_doctype},
          "target": {fieldname,label,child_doctype} | None,
          "included": 1,
          "field_pairs": [ ... same shape as parent_pairs ... ]
        },
        ...
      ],
      "unmatched_target_fields": [ ... target-only fields, for visibility ... ],
      "unmatched_target_tables": [ ... target-only child tables ... ],
    }
    """
    result = {
        "source_doctype": source_schema.get("doctype"),
        "target_doctype": target_schema.get("doctype"),
        "parent_pairs": [],
        "child_pairs": [],
        "unmatched_target_fields": [],
        "unmatched_target_tables": [],
    }

    # ---- parent fields ----
    target_by_name = {f["fieldname"]: f for f in target_schema.get("fields", [])}
    target_by_label = {(f["label"] or "").lower(): f
                       for f in target_schema.get("fields", []) if f.get("label")}
    used_target_names: set[str] = set()

    for sf in source_schema.get("fields", []):
        match, how = _best_match_for(sf, target_by_name, target_by_label, used_target_names)
        warning = _type_warning(sf, match) if match else ""
        result["parent_pairs"].append({
            "source": sf,
            "target": match,
            "included": 1 if match else 0,
            "auto_match": how,
            "warning": warning,
        })
        if match:
            used_target_names.add(match["fieldname"])

    # Target-only fields (the source doesn't have these — show as unmatched)
    for tf in target_schema.get("fields", []):
        if tf["fieldname"] not in used_target_names:
            result["unmatched_target_fields"].append(tf)

    # ---- child tables ----
    target_child_by_name = {c["fieldname"]: c
                            for c in target_schema.get("child_tables", [])}
    used_target_tables: set[str] = set()

    for sc in source_schema.get("child_tables", []):
        tc = target_child_by_name.get(sc["fieldname"])
        if tc:
            used_target_tables.add(tc["fieldname"])

        # Pair the rows inside the child table
        if tc:
            tc_by_name = {f["fieldname"]: f for f in tc.get("fields", [])}
            tc_by_label = {(f["label"] or "").lower(): f
                           for f in tc.get("fields", []) if f.get("label")}
            used_inner: set[str] = set()
            field_pairs = []
            for sf in sc.get("fields", []):
                m, how = _best_match_for(sf, tc_by_name, tc_by_label, used_inner)
                field_pairs.append({
                    "source": sf,
                    "target": m,
                    "included": 1 if m else 0,
                    "auto_match": how,
                    "warning": _type_warning(sf, m) if m else "",
                })
                if m:
                    used_inner.add(m["fieldname"])
            unmatched_inner_target = [
                f for f in tc.get("fields", [])
                if f["fieldname"] not in used_inner
            ]
        else:
            field_pairs = [
                {"source": sf, "target": None, "included": 0,
                 "auto_match": None, "warning": ""}
                for sf in sc.get("fields", [])
            ]
            unmatched_inner_target = []

        result["child_pairs"].append({
            "source": {
                "fieldname": sc["fieldname"],
                "label": sc["label"],
                "child_doctype": sc["child_doctype"],
            },
            "target": {
                "fieldname": tc["fieldname"],
                "label": tc["label"],
                "child_doctype": tc["child_doctype"],
            } if tc else None,
            "included": 1 if tc else 0,
            "field_pairs": field_pairs,
            "unmatched_target_fields": unmatched_inner_target,
        })

    for tc in target_schema.get("child_tables", []):
        if tc["fieldname"] not in used_target_tables:
            result["unmatched_target_tables"].append({
                "fieldname": tc["fieldname"],
                "label": tc["label"],
                "child_doctype": tc["child_doctype"],
            })

    return result


def _best_match_for(sf: dict, by_name: dict, by_label: dict, used: set):
    """Try to find a target field for `sf`. Prefer fieldname, then label."""
    m = by_name.get(sf["fieldname"])
    if m and m["fieldname"] not in used:
        return m, "name"
    if sf.get("label"):
        m = by_label.get(sf["label"].lower())
        if m and m["fieldname"] not in used:
            return m, "label"
    return None, None


# Type-compatibility groups — within a group, types are interchangeable
_TYPE_GROUPS = [
    {"Data", "Small Text", "Text", "Long Text", "Text Editor", "Code"},
    {"Int", "Float", "Currency", "Percent"},
    {"Date", "Datetime"},
    {"Check"},
    {"Link", "Dynamic Link"},
    {"Select"},
    {"Attach", "Attach Image", "Image"},
    {"JSON"},
]


def _type_warning(sf: dict, tf: dict) -> str:
    """Return a non-empty string when source/target types are not compatible."""
    if not tf:
        return ""
    s_t = sf.get("fieldtype") or ""
    t_t = tf.get("fieldtype") or ""
    if s_t == t_t:
        return ""
    for grp in _TYPE_GROUPS:
        if s_t in grp and t_t in grp:
            return ""
    return f"Type differs: {s_t} → {t_t}"
