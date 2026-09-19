"""Measure the F2 predictions. Rule 6: every figure in docs/PREREG-F2.md has a command.

    make f2              P3, P4, P5 and P6 on calibration material. Run this while working.
    make f2-reserved     P5 on the RESERVED half. Measured ONCE, at the end.

Why the two are separate commands and not a flag with a default: the reserved half is measured
once and its figure is what gets published. A single command that could be pointed at either half
is a command somebody points at the wrong one, which is how the previous reserve was lost.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from mcpfanout import match as _match           # noqa: E402
from mcpfanout import structure as S            # noqa: E402
from mcpfanout.driver import args_bytes         # noqa: E402
from mcpfanout.redact import Redactor           # noqa: E402

R = Redactor()


# --- P3: does a call match itself, and do the old families stay clean.

def _load(half: str) -> dict:
    name = {"calibration": "calibration.json", "held-out": "held-out.json",
            "reserved": "reserved.json"}[half]
    return json.loads((REPO / "corpus" / "negative" / name).read_text(encoding="utf-8"))


HOST = "docs.example.net"   # the negative corpus states one host throughout


def _call_tokens(call: dict) -> frozenset[str]:
    return S.tokens_of_arguments(call["arguments"])


def _request_tokens(call: dict) -> frozenset[str]:
    return S.tokens_of_request(HOST, call["request"]["target"], call["request"]["body"])


def self_match(half: str) -> dict:
    data = _load(half)
    per_family, hits, total = {}, 0, 0
    for fam in data["families"]:
        h = sum(1 for c in fam["calls"] if S.contains(_call_tokens(c), _request_tokens(c)))
        per_family[fam["family"]] = f"{h}/{len(fam['calls'])}"
        hits += h
        total += len(fam["calls"])
    return {"per_family": per_family, "rate": round(hits / total, 4), "n": total}


def false_positives(half: str, families: list[str] | None, use_rule_c: bool) -> dict:
    """Ordered pairs within a family: does B's argument material appear in A's request.

    With rule C the pair is treated as two concurrent calls, which is what the pair rule means:
    B is refused as a candidate when it owns no token A does not also own.
    """
    data = _load(half)
    per_family, fp, pairs = {}, 0, 0
    for fam in data["families"]:
        if families and fam["family"] not in families:
            continue
        f, p = 0, 0
        for a in fam["calls"]:
            for b in fam["calls"]:
                if a["id"] == b["id"]:
                    continue
                p += 1
                ta, tb = _call_tokens(a), _call_tokens(b)
                wire = _request_tokens(a)
                if not S.contains(tb, wire):
                    continue
                if use_rule_c and not S.distinguishing(tb, [ta]):
                    continue
                if use_rule_c and len(tb) < 2:
                    continue
                f += 1
        per_family[fam["family"]] = f"{f}/{p}"
        fp += f
        pairs += p
    return {"per_family": per_family, "rate": round(fp / pairs, 4) if pairs else None,
            "false_positives": fp, "pairs": pairs}


# --- P4: re-grade the concurrent run's waves, derived from the corpus.

def _wire_of(url: str) -> tuple[str, str]:
    s = urllib.parse.urlsplit(url)
    return s.netloc, (s.path or "/") + (("?" + s.query) if s.query else "")


def regrade() -> dict:
    """The corpus-derived re-grade, and the honest statement of what it is.

    NOT a re-grade of the stored flows. flows.jsonl from run 20260919T130847Z-concurrent was
    written before the structural fields existed, so the run cannot be re-graded from what was
    persisted: that is threat 16's question arriving from a new direction. What IS re-derivable is
    the wire each call produces, because every driven call is a fetch of a URL the corpus names,
    and the flow COMPOSITION is cross-checked against the real run below. A figure derived this
    way is honest only while that cross-check holds, so it is printed rather than assumed.
    """
    plan = [("fetch", [2, 5, 10], True), ("puppeteer", [2], False)]
    grades, false_strong, robots_strong, excluded = {}, 0, 0, []
    for name, levels, robots in plan:
        corpus = json.loads((REPO / "corpus" / "concurrent" / f"{name}.json")
                            .read_text(encoding="utf-8"))
        for n in levels:
            wave = corpus[:n]
            toks = [R.token_digest_set(S.tokens_of_arguments(c["arguments"])) for c in wave]
            cand0 = _match.discriminating_candidates(toks, frozenset())
            excluded.append({"server": name, "wave": n,
                             "non_discriminating": cand0.non_discriminating_active})
            for i, c in enumerate(wave):
                if "url" not in c["arguments"]:
                    continue
                host, tgt = _wire_of(c["arguments"]["url"])
                for target in ([tgt, "/robots.txt"] if robots else [tgt]):
                    wire = R.token_digest_set(S.tokens_of_request(host, target))
                    cand = _match.discriminating_candidates(toks, wire)
                    grade, _ = _match.grade_attribution(
                        traceparent_present=False,
                        argument_match=bool(cand.discriminating),
                        active_calls_in_window=n,
                        matching_calls_in_window=len(cand.discriminating),
                        eligible=True, has_time_and_pid=True,
                        candidate_token_count=cand.token_count)
                    grades[grade] = grades.get(grade, 0) + 1
                    if grade == "CONTENT_UNIQUE":
                        if cand.discriminating[0] != i:
                            false_strong += 1
                        if target == "/robots.txt":
                            robots_strong += 1
    strong = grades.get("CONTENT_UNIQUE", 0)
    return {"grades": grades, "strong": strong, "false_strong": false_strong,
            "robots_strong": robots_strong,
            "simulated_flows": sum(grades.values()),
            "fraction_over_38_attributable": round(strong / 38, 4),
            "fraction_over_19_content": round(strong / 19, 4),
            "non_discriminating_calls": excluded}


def crosscheck(run_dir: Path) -> dict:
    """The composition of the real run, so the derivation above is checkable and not trusted."""
    if not (run_dir / "flows.jsonl").is_file():
        return {"checked": False, "why": f"{run_dir} has no flows.jsonl"}
    rows = [json.loads(l) for l in (run_dir / "flows.jsonl").open()]
    call_caused = [r for r in rows
                   if r["phase"] not in ("launcher", "handshake")
                   and r["dest_host"] != "registry.npmjs.org"]
    robots = [r for r in call_caused if r["target_bytes"] == 11]
    const = [r for r in call_caused if r["dest_host"] == "clients2.google.com"]
    return {"checked": True, "run": run_dir.name, "flows_total": len(rows),
            "call_caused_eligible": len(call_caused),
            "constant_client_paths": len(robots) + len(const),
            "content_denominator": len(call_caused) - len(robots) - len(const)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reserved", action="store_true",
                    help="measure P5 on the RESERVED half. Once, at the end.")
    ap.add_argument("--run", default="runs/20260919T130847Z-concurrent")
    args = ap.parse_args()

    if args.reserved:
        out = {"what": "P5 on the reserved half, measured once",
               "half": "reserved",
               "self_match": self_match("reserved"),
               "containment_subset_without_rule_c":
                   false_positives("reserved", ["containment_subset"], False),
               "containment_subset_with_rule_c":
                   false_positives("reserved", ["containment_subset"], True),
               "all_families_with_rule_c": false_positives("reserved", None, True),
               "command": "make f2-reserved"}
        print(json.dumps(out, indent=2, sort_keys=True))
        return 0

    old = ["search_query", "rest_path", "doc_url", "json_post"]
    out = {
        "P3_self_match": {h: self_match(h) for h in ("calibration", "held-out")},
        "P3_false_positives_original_families":
            {h: false_positives(h, old, True) for h in ("calibration", "held-out")},
        "P4_regrade": regrade(),
        "P4_crosscheck_against_the_real_run": crosscheck(REPO / args.run),
        "P5_containment_subset_calibration": {
            "without_rule_c": false_positives("calibration", ["containment_subset"], False),
            "with_rule_c": false_positives("calibration", ["containment_subset"], True),
        },
        "command": "make f2",
        "note": ("held-out.json is CALIBRATION material: it was measured through a bare json.load "
                 "on 2026-09-19. The reserve is corpus/negative/reserved.json and it has its own "
                 "command, `make f2-reserved`."),
    }
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
