"""Build the containment-adversarial family and the NEW reserved half of the negative corpus.

Why this is a generator and not hand-written JSON. The reserved half has to satisfy invariants
that are easy to violate by hand and expensive to violate quietly: no information string may
appear anywhere in the other halves, every declared shared literal must really be shared, and
every call's arguments must serialise the way the driver serialises them. Generating them makes
the invariants checkable in one place and the corpus re-derivable, which is rule 6 applied to a
corpus instead of a figure.

WHY A NEW RESERVED HALF EXISTS AT ALL. `corpus/negative/held-out.json` was loaded with a bare
json.load by an external review's scripts, bypassing `calibrate.load_negative`, and measured. Its
false-positive figure is therefore a CALIBRATION figure and may not be published as a held-out
one. The material is not wasted: it is still a valid negative control, it is simply no longer
unseen. This file builds the replacement.

    python tools/build_negative_extras.py            # write the files
    python tools/build_negative_extras.py --check    # verify they match what this script builds
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
NEG = REPO / "corpus" / "negative"


def q(s: str) -> str:
    return urllib.parse.quote_plus(s)


# --- The containment-adversarial family ------------------------------------------------------
#
# Built against STRUCTURAL CONTAINMENT, not against the k-gram matcher. Every other family in this
# corpus shares long literal runs, which is what defeats a k-gram. Containment does not care about
# runs at all: it asks whether every structural token of one call is present in another call's
# request. The cases that defeat THAT are different, and four of them are built here:
#
#   subset        one call's tokens are a proper subset of another call's request. The attack that
#                 containment cannot see at all without a discrimination rule.
#   generic       a call whose only token is a common word that appears in several requests.
#   enum          two calls sharing a low-cardinality value (a ref name, a status) and nothing else.
#   shared_org    same organisation, different repository: the case a human reads as obviously
#                 distinct and a set-containment rule can get wrong.
#
# A call with an EMPTY information list is deliberate and is the finding, not an omission: a call
# that carries nothing of its own cannot be attributed by content, and a matcher that claims it
# anyway has invented the claim. The pair rule is unchanged: (A, B) asks whether B's arguments
# appear in A's request, and any yes is a false positive because B did not cause A's request.

def containment_family(org_a: str, org_b: str, repo_a: str, repo_b: str,
                       leaf: str, s1: str, s2: str, s3: str, ref: str, prefix: str) -> dict:
    def call(n: int, args: dict, target: str, info: list[str], case: str,
             why: str, free: str = "") -> dict:
        c = {"id": f"{prefix}-contain-{n:02d}", "arguments": args,
             "request": {"target": target, "body": ""},
             "information": info, "case": case, "why": why}
        if free:
            c["information_free"] = free
        return c

    def contents(o: str, r: str, p: str) -> str:
        return f"/repos/{o}/{r}/contents/{p}"

    SUBSET_FREE = (
        "Carries no value of its own. That is the attack and not an omission: containment asks "
        "whether every token of a call is present in a request, so a call that owns nothing "
        "unique is contained in any request that mentions its organisation and repository. A "
        "call with a distinguishing value could not be a subset of another call's request, so "
        "this case cannot be built any other way.")
    ENUM_FREE = (
        "Its only non-shared token is a low-cardinality ref name shared with its sibling call. An "
        "enum value is not information: it identifies a class, not an instance, and a match "
        "driven by it is driven by nothing.")

    return {
        "family": "containment_subset",
        "api": ("a repository contents API: JSON {owner, repo, path?, ref?} in, "
                "GET /repos/<owner>/<repo>/... out"),
        "shared_structure_note": (
            "the JSON envelope, the /repos/ prefix, two organisations and two repository names "
            "shared across the family, and a path vocabulary drawn from one repository layout"),
        "shared_literals": ['{"owner": "', '"repo": "', "/repos/"],
        "why": (
            "The other four families in this corpus were authored against a k-gram matcher and "
            "share long literal runs. Structural containment does not read runs at all, so those "
            "families cannot falsify it and a rate of zero over them means only that they were "
            "built for a different instrument. This family is built against containment itself: "
            "a call whose tokens are a proper subset of another call's request, two calls sharing "
            "an enum value and nothing else, and one repository reached through two organisations. "
            "Five of its eight calls carry no information of their own and say so in an explicit "
            "information_free field, because a call that owns no distinguishing value is precisely "
            "the call containment gets wrong, and it cannot be built with one."),
        "calls": [
            call(1, {"owner": org_a, "repo": repo_a, "path": f"{leaf}/{s1}"},
                 contents(org_a, repo_a, f"{leaf}/{s1}"),
                 [f"{leaf}/{s1}", s1], "anchor",
                 "The full call, and the request every subset case below is measured against."),
            call(2, {"owner": org_a, "repo": repo_a},
                 f"/repos/{org_a}/{repo_a}",
                 [], "subset",
                 "Its two tokens are a proper subset of call 01's request tokens, so containment "
                 "claims it caused call 01's request. It did not. The family's headline case.",
                 SUBSET_FREE),
            call(3, {"owner": org_a, "repo": repo_a, "path": leaf},
                 contents(org_a, repo_a, leaf),
                 [], "subset",
                 "A second subset one token longer, so the attack is visibly a property of "
                 "containment and not of any particular minimum token count.",
                 SUBSET_FREE),
            call(4, {"owner": org_a, "repo": repo_b, "path": f"{leaf}/{s2}"},
                 contents(org_a, repo_b, f"{leaf}/{s2}"),
                 [s2], "shared_org",
                 "Same organisation and same path prefix as call 01, different repository. A "
                 "human reads these as plainly distinct; the test is whether the matcher does."),
            call(5, {"owner": org_a, "repo": repo_a, "ref": ref},
                 f"/repos/{org_a}/{repo_a}/commits?sha={q(ref)}",
                 [], "enum",
                 "A ref name shared with call 06 and nothing else of its own.", ENUM_FREE),
            call(6, {"owner": org_a, "repo": repo_b, "ref": ref},
                 f"/repos/{org_a}/{repo_b}/commits?sha={q(ref)}",
                 [], "enum",
                 "The same ref name in the other repository of the same organisation.", ENUM_FREE),
            call(7, {"owner": org_b, "repo": repo_a, "path": f"{leaf}/{s3}"},
                 contents(org_b, repo_a, f"{leaf}/{s3}"),
                 [s3], "shared_org",
                 "The mirror of call 04: the same repository name reached through the other "
                 "organisation, so the distinguishing token moves from the second path segment "
                 "to the first."),
            call(8, {"owner": org_b, "repo": repo_a},
                 f"/repos/{org_b}/{repo_a}",
                 [], "subset",
                 "The subset case again, under the second organisation, so the family does not "
                 "rest the whole attack on one anchor.",
                 SUBSET_FREE),
        ],
    }


# --- The new reserved half --------------------------------------------------------------------
# Fresh vocabulary throughout: no string here appears in either existing half. The four classic
# families mirror the SHAPES of the originals, because a reserve that tests different shapes is
# not a reserve for the same measurement.

RES_SEARCH = [
    "purge a stale dns record", "throttle a webhook retry loop", "expire a cached bearer token",
    "mirror a bucket across regions", "quarantine a flapping health check",
    "backfill a partitioned index", "drain a saturated worker pool", "pin a transitive dependency",
]
RES_REPOS = [
    ("slate-harbor", "ticket-relay", "docs/quotas.md"),
    ("amber-works", "quota-daemon", "docs/failover.md"),
    ("basalt-yard", "tally-courier", "docs/retention.md"),
    ("cobalt-mill", "notify-bridge", "docs/backpressure.md"),
    ("dune-signal", "asset-pruner", "docs/sharding.md"),
    ("ember-ridge", "trace-fanout", "docs/sampling.md"),
    ("fjord-works", "batch-warden", "docs/idempotency.md"),
    ("gantry-lane", "schema-vault", "docs/migrations.md"),
]
RES_GUIDES = [
    "storage/lifecycle-rules", "identity/delegation-chains", "network/peering-limits",
    "runtime/warm-pools", "billing/commitment-tiers", "observability/cardinality-caps",
    "delivery/canary-gates", "security/key-custody",
]
RES_TEXTS = [
    "the migration window should exclude the quarterly close",
    "the runbook should name a rollback owner for every step",
    "the alert should page only after two consecutive failures",
    "the retention policy should keep audit events for seven years",
    "the deploy should halt when error budget is exhausted",
    "the schema change should ship behind a read flag first",
    "the backup should be restored into a scratch project monthly",
    "the incident review should record what was ruled out",
]


def reserved_families() -> list[dict]:
    search = {
        "family": "search_query",
        "api": "a search endpoint: JSON {query} in, GET /api/search?q=<plus-encoded> out",
        "shared_structure_note": "the JSON envelope, the path prefix, the opening phrase, and "
                                 "plus-encoding of every space",
        "shared_literals": ['{"query": "', "/api/search?q=", "how to "],
        "why": ("Free-text search is the most common shape an agent sends and the one where shared "
                "English carries the most bytes. Every call begins with the same four words, which "
                "is not a trick: an agent asking a documentation search engine phrases its "
                "questions the same way every time."),
        "calls": [
            {"id": f"res-search-{i:02d}", "arguments": {"query": f"how to {t}"},
             "request": {"target": f"/api/search?q={q('how to ' + t)}", "body": ""},
             "information": [t, q(t)]}
            for i, t in enumerate(RES_SEARCH, 1)
        ],
    }
    rest = {
        "family": "rest_path",
        "api": "a repository contents API: JSON {owner, repo, path} in, GET /repos/.../contents/... out",
        "shared_structure_note": "the JSON envelope, the path prefix, the docs/ directory and the "
                                 ".md extension",
        "shared_literals": ['{"owner": "', '"path": "docs/', "/repos/", "/contents/docs/", ".md"],
        "why": ("A REST path built by interpolating caller-supplied fields into a fixed template. "
                "The template is most of the bytes, and every call in this family shares it, so a "
                "matcher that keys on the template rather than on the interpolated values will "
                "claim every pair here."),
        "calls": [
            {"id": f"res-rest-{i:02d}",
             "arguments": {"owner": o, "repo": r, "path": p},
             "request": {"target": f"/repos/{o}/{r}/contents/{p}", "body": ""},
             "information": [o, r, p]}
            for i, (o, r, p) in enumerate(RES_REPOS, 1)
        ],
    }
    doc = {
        "family": "doc_url",
        "api": "a fetch tool: JSON {url} in, GET <path> out",
        "shared_structure_note": "the scheme, the host, and the /guides/ prefix, with only the "
                                 "final two segments varying",
        "shared_literals": ["https://docs.example.net/guides/", "/guides/"],
        "why": ("The case where the argument and the request are nearly the same string, so a "
                "matcher has the easiest possible job and any false positive here is a matcher "
                "keying on the shared site structure rather than on the document asked for. This "
                "is also the family whose leaves straddle the shipped k, which is what makes it "
                "the family that moves when k moves."),
        "calls": [
            {"id": f"res-doc-{i:02d}",
             "arguments": {"url": f"https://docs.example.net/guides/{g}"},
             "request": {"target": f"/guides/{g}", "body": ""},
             "information": [g.split("/")[-1]]}
            for i, g in enumerate(RES_GUIDES, 1)
        ],
    }
    post = {
        "family": "json_post",
        "api": "a rewrite endpoint: JSON {locale, text} in, JSON {locale, requestId, text} out",
        "shared_structure_note": "the JSON envelope on both sides, a constant locale, and an "
                                 "opening article shared by every sentence",
        "shared_literals": ['"locale": "en-US"', '"text": "', "the "],
        "why": ("The body channel, where the request is a re-serialisation of the arguments with a "
                "field added. The envelope and the locale are shared by construction and the only "
                "thing that differs is the sentence, so this family measures whether a match is "
                "being carried by the envelope."),
        "calls": [
            {"id": f"res-post-{i:02d}",
             "arguments": {"locale": "en-US", "text": t},
             "request": {"target": "/v1/rewrite",
                         "body": json.dumps({"locale": "en-US", "requestId": f"req-{i:04d}",
                                             "text": t}, sort_keys=True)},
             "information": [t]}
            for i, t in enumerate(RES_TEXTS, 1)
        ],
    }
    contain = containment_family("glasswing", "tidewater", "parcel-api", "parcel-web",
                                 "handbook", "handover", "custody", "quiesce", "mainline", "res")
    return [search, rest, doc, post, contain]


CAL_CONTAIN = ("northwind", "eastwind", "billing-core", "billing-edge",
               "playbook", "oncall", "escalation", "rotation", "stable", "cal")

RESERVED_DOC = {
    "_what_this_is": (
        "Negative control, RESERVED half: concurrent call pairs that share LANGUAGE STRUCTURE and "
        "NO INFORMATION. Every match the matcher claims between two calls of one family is a false "
        "positive, because neither call's arguments caused the other's request. This half is "
        "measured ONCE, at the end, and is what a published false-positive figure comes from."),
    "_why_this_file_exists": (
        "It replaces corpus/negative/held-out.json as the reserve. That file was loaded with a bare "
        "json.load by an external review's scripts, bypassing calibrate.load_negative, and "
        "measured. Its figure is therefore a calibration figure. The material is still a valid "
        "negative control; it is simply no longer unseen, and docs/CALIBRATION.md and "
        "docs/PREREG-F2.md say so rather than quietly continuing to call it held out."),
    "_the_guard_is_a_courtesy": (
        "calibrate.load_negative refuses this half to a calibration purpose. That refusal is a "
        "COURTESY, not a lock: any json.load of this path bypasses it, which is exactly what "
        "happened. It is written here so nobody mistakes the refusal for a guarantee. See "
        "docs/PREREG-F2.md section 1 for what a lock would cost."),
    "half": "reserved",
    "pair_rule": (
        "ordered pairs WITHIN a family only: (A, B) asks whether B's arguments appear in A's "
        "request. Cross-family pairs share no structure, so counting them would deflate the rate "
        "with cases nobody finds hard."),
}


def build_reserved() -> dict:
    return {**RESERVED_DOC, "families": reserved_families()}


def build_calibration() -> dict:
    data = json.loads((NEG / "calibration.json").read_text(encoding="utf-8"))
    fams = [f for f in data["families"] if f["family"] != "containment_subset"]
    fams.append(containment_family(*CAL_CONTAIN))
    data["families"] = fams
    return data


def dump(obj: dict) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    targets = {NEG / "reserved.json": build_reserved(),
               NEG / "calibration.json": build_calibration()}
    bad = 0
    for path, obj in targets.items():
        text = dump(obj)
        if args.check:
            current = path.read_text(encoding="utf-8") if path.exists() else ""
            if current != text:
                print(f"STALE: {path.relative_to(REPO)}")
                bad += 1
        else:
            path.write_text(text, encoding="utf-8")
            print(f"wrote {path.relative_to(REPO)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
