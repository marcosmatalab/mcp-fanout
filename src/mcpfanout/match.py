"""Content matching: numbers 4 and 5, and the causal-union key.

This is the load-bearing novelty of the project. Number 5 (the fraction of outbound
connections that can be tied to their causing call by a literal content match) is the number
nobody has measured, and it is the key of union that Half A lacks: if a fragment of the call
arguments appears literally in the outbound payload, that is causal evidence, not a temporal
correlation. See docs/METHOD.md, "Half B is the join key of Half A".

Everything here is deterministic. There are no statistical variables: a substring either is or
is not present. The only probabilistic quantity in the whole matching stack is the hash
collision bound, and that lives in shingle.py where the hash is defined.

Matching is done at the exact k-gram level (not winnowed), so the numbers are exact byte
coverage. Winnowing is only for what gets persisted (see redact.winnowed_digests); it never
enters a number.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .redact import Redactor

# The three resolution states, as strings so they serialize verbatim into records.
EFECTIVO = "EFECTIVO"
DECLARADO = "DECLARADO"
INDETERMINADO = "INDETERMINADO"


@dataclass
class MatchResult:
    total_bytes: int              # size of the outbound body examined
    matched_bytes: int            # bytes of the body covered by any context reference (exact)
    matched_refs: list[str]       # which references contributed at least one k-gram
    causal: bool                  # a fragment of the CALL ARGUMENTS appears literally in body
    coverage: float = field(init=False)

    def __post_init__(self) -> None:
        # Coverage is matched over total. A zero-length body has zero coverage by definition,
        # not a division error: an empty body can match nothing.
        self.coverage = (self.matched_bytes / self.total_bytes) if self.total_bytes else 0.0


def _covered_bytes(positional_digests: list[str], member_set: frozenset[str], k: int) -> int:
    """Exact count of body bytes covered by any k-gram present in ``member_set``.

    ``positional_digests[i]`` is the salted digest of the body's k-gram starting at offset i.
    A hit at i covers the half-open interval [i, i+k). We union those fixed-length intervals in
    a single left-to-right pass (they arrive sorted by start), so the cost is O(len(body)) and
    overlaps are never double counted.
    """
    matched = 0
    cur_end = -1  # exclusive end of the covered run built so far
    for i, dg in enumerate(positional_digests):
        if dg in member_set:
            start, end = i, i + k
            if start > cur_end:
                matched += k
                cur_end = end
            elif end > cur_end:
                matched += end - cur_end
                cur_end = end
    return matched


def build_reference_index(references: dict[str, bytes], redactor: Redactor) -> dict[str, frozenset[str]]:
    """Index each reference (a context file, or a call's arguments) to its k-gram digest set.

    Built once per run. The raw reference bytes are consumed here and not retained: only the
    salted digest sets survive, which is the digest-only guarantee applied to the context side.
    """
    return {ref_id: redactor.kgram_digest_set(data) for ref_id, data in references.items()}


def match_body(
    body: bytes,
    context_index: dict[str, frozenset[str]],
    args_digests: frozenset[str],
    redactor: Redactor,
) -> MatchResult:
    """Match one outbound body against the context files and against the call's arguments.

    ``context_index`` maps reference id -> digest set for the session context files (number 4).
    ``args_digests`` is the digest set of the causing call's arguments (number 5, the causal
    key). Passing args separately, rather than as one more reference, is deliberate: a match
    against args is a causal claim (EFECTIVO), a match against a context file is a leak claim.
    They answer different questions and must not be conflated.
    """
    positional = redactor.kgram_digests(body)
    body_set = frozenset(positional)

    # Number 4: which context references appear, and how many body bytes they cover (exact).
    matched_refs = [ref_id for ref_id, digs in context_index.items() if digs & body_set]
    if matched_refs:
        context_union: frozenset[str] = frozenset().union(*(context_index[r] for r in matched_refs))
        matched_bytes = _covered_bytes(positional, context_union, redactor.k)
    else:
        matched_bytes = 0

    # Number 5: causal union. Non-empty intersection with the call's own arguments.
    # A match shorter than k bytes is not detected; that is a false negative and the safe
    # direction (we say DECLARADO instead of falsely EFECTIVO).
    causal = bool(args_digests & body_set)

    return MatchResult(
        total_bytes=len(body),
        matched_bytes=matched_bytes,
        matched_refs=matched_refs,
        causal=causal,
    )


def decide_state(causal: bool, body_observed: bool, has_time_and_pid: bool) -> str:
    """Map available evidence to a resolution state (docs/DOCTRINE.md, the three states).

    Order matters: content evidence beats correlation. If a fragment of the arguments is in the
    payload, the connection is EFECTIVO regardless of how many other calls were concurrent. If
    we only have a time window and a pid, we say DECLARADO and call it correlation. If the body
    was never observed (TLS we did not terminate, an argument-less call, an async pool with no
    body), we say INDETERMINADO with the cause named by the caller.
    """
    if causal:
        return EFECTIVO
    if body_observed and has_time_and_pid:
        return DECLARADO
    return INDETERMINADO
