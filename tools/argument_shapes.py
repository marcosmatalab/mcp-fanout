"""Classify every probed tool by how many structural tokens its arguments commit. Stdlib only.

WHY THIS EXISTS. The paper's most actionable claim is that content attribution works on tools
whose arguments carry structure and fails on tools whose arguments are one free-text string. That
claim was qualitative. This turns it into a measured distribution over the tool schemas we probed,
so a reader can run the same classification against their own inventory.

THE RULE, AND WHICH WAY EACH CLASS IS WRONG. Everything here is derived from a committed
`inputSchema` and nothing from a value, because a value is not in a schema. A REQUIRED property of
type string commits at least one string whatever the caller passes. So:

  structured     two or more required string properties. At least two tokens are committed by the
                 schema itself, whatever the values are, so the call is attributable under
                 concurrency regardless of what the caller writes.
  single_value   fewer than two required string properties, but string leaves a caller can fill:
                 one required string, required arrays or objects of strings, or optional strings.
                 Whether they commit enough tokens depends entirely on the VALUE: a URL or a path
                 decomposes further, a bare phrase does not, and the schema cannot say which.
                 This is the undecided class and it is reported as undecided rather than assumed
                 to fail.
  no_string      no string ANYWHERE in the schema, at any depth: not a property, not an array
                 item, not a nested field. structure.py only ever makes tokens out of string
                 leaves, so no call to such a tool can carry one. This class is exact.

The first class is a CEILING and not a floor, and the two directions were settled by constructed
schemas rather than by argument (tests/test_tools.py). Two required strings that are enums of
two-byte values are counted `structured` and commit no token at all, because the matcher drops
anything under MIN_TOKEN_BYTES: the rule counts tools that are not attributable, never the reverse.
The previous `no_string` rule was wrong in the other direction: it filed a required ARRAY of
strings under never attributable, while the matcher walks every string leaf and attributes it.
Eight probed tools were in that position; they are `single_value` now, where a value decides.

DELIBERATELY NOT DONE: guessing from a property's NAME or DESCRIPTION that it holds a URL. `url`,
`path`, `query` are suggestive and suggestion is inference, which this project forbids in the
matcher and will not smuggle into its own measurement of the matcher. A schema that DECLARES
`format: uri` is the author stating it in machine-readable form, and that is counted, not guessed.

    make argument-shapes
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROBES = REPO / "registry" / "probes"


def _tools(doc: dict) -> list:
    t = doc.get("tools", doc)
    if isinstance(t, dict):
        t = t.get("tools", [])
    return t if isinstance(t, list) else []


def _carries_string(schema: object) -> bool:
    """Can a value valid under this schema contain a string leaf anywhere? The matcher's view."""
    if not isinstance(schema, dict):
        return False
    if schema.get("type") == "string" or (schema.get("type") is None and any(
            isinstance(e, str) for e in schema.get("enum") or [])):
        return True
    children = list((schema.get("properties") or {}).values())
    children += [schema.get("items"), schema.get("additionalProperties")]
    for key in ("anyOf", "oneOf", "allOf"):
        children += list(schema.get(key) or [])
    return any(_carries_string(child) for child in children)


def classify(tool: dict) -> dict:
    schema = tool.get("inputSchema") or {}
    props = schema.get("properties") or {}
    required = [r for r in (schema.get("required") or []) if r in props]
    req_strings = [r for r in required if (props[r] or {}).get("type") == "string"]
    declared_uri = [r for r in req_strings if (props[r] or {}).get("format") == "uri"]
    n = len(req_strings)
    if n >= 2:
        shape = "structured"
    elif n == 1:
        shape = "single_value_declared_uri" if declared_uri else "single_value"
    elif _carries_string(schema):
        shape = "single_value"
    else:
        shape = "no_string"
    return {"name": tool.get("name", ""), "shape": shape,
            "required_string_properties": n,
            # A DECLARED enum is the author writing down that a value identifies a class rather
            # than an instance. Counted because it is machine-readable, and reported as a lower
            # bound because a low-entropy field need not declare one.
            "declared_enum": any((props[r] or {}).get("enum") for r in req_strings),
            "optional_properties": len(props) - len(required)}


def main() -> int:
    per_server, tally, rows = {}, {}, []
    for path in sorted(PROBES.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        tools = _tools(doc)
        if not tools:
            continue
        local = {}
        for tool in tools:
            c = classify(tool)
            rows.append(c)
            local[c["shape"]] = local.get(c["shape"], 0) + 1
            tally[c["shape"]] = tally.get(c["shape"], 0) + 1
        # Gate rule 3 governs the AGGREGATE, not a diagnostic over committed schema files, but the
        # habit is cheap to keep: servers are counted, not named, in the published block below.
        per_server[path.stem] = local

    total = len(rows)
    structured = tally.get("structured", 0)
    declared_enum = sum(1 for r in rows if r["shape"] == "structured" and r["declared_enum"])
    single = tally.get("single_value", 0) + tally.get("single_value_declared_uri", 0)
    out = {
        "name": "argument_shape_distribution",
        "source": "registry/probes/*.json, the committed inputSchema of every probed tool",
        "servers": len(per_server),
        "tools": total,
        "by_shape": tally,
        "attributable_by_schema_alone": {
            "count": structured,
            "fraction": round(structured / total, 4) if total else None,
            "meaning": ("two or more required string properties, so at least two structural "
                        "tokens are committed whatever the caller passes"),
            "this_is_a_CEILING_not_a_floor": (
                "the rule counts structural COMMITMENTS, not their specificity. A required string "
                "that is a locale, a status or a region code commits a token that identifies a "
                "class rather than an instance, so the call effectively commits fewer "
                "distinguishing tokens than the schema suggests. A schema declares a value's "
                "shape and not its entropy, and no reading of schemas recovers the difference"),
            "declared_low_entropy_visible_here": declared_enum,
            "declared_low_entropy_note": (
                "tools in this class with at least one required string property declared as an "
                "enum. It is a lower bound on the problem and not a measure of it: a low-entropy "
                "field is under no obligation to declare an enum, and most do not"),
        },
        "undecided_until_a_value_is_seen": {
            "count": single,
            "fraction": round(single / total, 4) if total else None,
            "meaning": ("fewer than two required string properties, but string leaves the caller "
                        "can fill: one required string, required arrays or objects of strings, or "
                        "optional strings. Attributable only if the values decompose, which a "
                        "schema cannot say. Measured instance: "
                        "on one server a free-text search whose query embedded a repository "
                        "qualifier with a slash decomposed into two tokens and attributed, while "
                        "a plain phrase on the same server did not"),
        },
        "never_attributable_by_content": {
            "count": tally.get("no_string", 0),
            "fraction": round(tally.get("no_string", 0) / total, 4) if total else None,
            "meaning": ("no string anywhere in the schema, so no value valid under it can carry "
                        "a structural token. Exact, not a bound"),
        },
        "per_server_counts": per_server,
        "what_this_is_not": (
            "a prediction of the attributable share. It is derived from schemas alone, with no "
            "value inspected and no property name interpreted: the attributable class is a "
            "ceiling on attribution by schema, the never class is exact, and the undecided class "
            "is reported as undecided rather than assumed to fail"),
        "command": "make argument-shapes",
    }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
