"""Content matching: numbers 4 and 5, and the causal-union key.

This is the load-bearing novelty of the project. Number 5 (the fraction of outbound
connections that can be tied to their causing call by a literal content match) is the number
nobody has measured, and it is the key of union that Half A lacks: if a fragment of the call
arguments appears literally in the outbound request, that is causal evidence, not a temporal
correlation. See docs/METHOD.md, "Half B is the join key of Half A".

Two channels are matched, separately: the REQUEST TARGET (path + query) and the BODY. Both are
bytes leaving the machine toward a third party. They are counted apart and never summed into one
headline, so that number 5 cannot be inflated with URLs -- see MatchResult.

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

# Which channel of the request carried the causal fragment. Reported alongside the state, never
# folded into it: a match in the query string and a match in the body are both causal evidence,
# but a reviewer must be able to see which one produced the number rather than take it on trust.
CHANNEL_NONE = "none"
CHANNEL_TARGET = "target"
CHANNEL_BODY = "body"
CHANNEL_BOTH = "both"


@dataclass
class MatchResult:
    """Per-channel match evidence for one outbound request.

    Two channels, counted separately and never summed into a single headline. The request target
    (path + query) and the body are both bytes on the wire toward a third party, so excluding the
    target blinds the harness to the entire GET channel -- which is the channel most third-party
    APIs use and the one the incidents this project cites travel on. But a target match and a body
    match are not interchangeable evidence, and reporting one figure would let number 5 be
    inflated by URLs. Hence four byte counts, not two.
    """
    target_bytes: int             # size of the request target examined (path + query)
    target_matched_bytes: int     # bytes of the target covered by any context reference (exact)
    body_bytes: int               # size of the outbound body examined
    body_matched_bytes: int       # bytes of the body covered by any context reference (exact)
    matched_refs: list[str]       # references contributing at least one k-gram, either channel
    causal_channel: str           # CHANNEL_NONE / _TARGET / _BODY / _BOTH
    causal: bool = field(init=False)
    target_coverage: float = field(init=False)
    body_coverage: float = field(init=False)

    def __post_init__(self) -> None:
        self.causal = self.causal_channel != CHANNEL_NONE
        # Coverage per channel, matched over that channel's own total. Deliberately NOT a
        # combined ratio: pooling a 40-byte target with a 40kB body produces a figure that
        # describes neither, and there is no question either channel's coverage cannot answer.
        # A zero-length channel has zero coverage by definition, not a division error.
        self.target_coverage = (self.target_matched_bytes / self.target_bytes) if self.target_bytes else 0.0
        self.body_coverage = (self.body_matched_bytes / self.body_bytes) if self.body_bytes else 0.0


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


def _match_channel(
    data: bytes,
    context_index: dict[str, frozenset[str]],
    args_digests: frozenset[str],
    redactor: Redactor,
) -> tuple[int, list[str], bool]:
    """Match one channel's bytes. Returns (matched context bytes, matching refs, args hit)."""
    positional = redactor.kgram_digests(data)
    present = frozenset(positional)

    # Number 4: which context references appear, and how many bytes they cover (exact).
    refs = [ref_id for ref_id, digs in context_index.items() if digs & present]
    if refs:
        union: frozenset[str] = frozenset().union(*(context_index[r] for r in refs))
        matched = _covered_bytes(positional, union, redactor.k)
    else:
        matched = 0

    # Number 5: causal union. Non-empty intersection with the call's own arguments.
    # A match shorter than k bytes is not detected; that is a false negative and the safe
    # direction (we say DECLARADO instead of falsely EFECTIVO).
    return matched, refs, bool(args_digests & present)


def match_request(
    target: bytes,
    body: bytes,
    context_index: dict[str, frozenset[str]],
    args_digests: frozenset[str],
    redactor: Redactor,
) -> MatchResult:
    """Match one outbound request against the context files and against the call's arguments.

    Renamed from ``match_body``, which had come to lie about what it does: it only ever saw the
    body, so an argument travelling in a query string was invisible and numbers 4 and 5 were
    structurally zero for every GET-based server. A secret in a query string has already left
    the machine -- it is bytes on the wire toward a third party -- so excluding it was not the
    digest-only policy, it was a blind spot covering the channel most third-party APIs use.

    ``target`` is the REQUEST TARGET: path plus query, exactly as it goes on the wire. Not the
    absolute URL. The host and scheme are not content drawn from our context, and including them
    would manufacture self-matches (a context file mentioning a hostname would "match" every
    request to it) while telling us nothing about what leaked.

    ``context_index`` maps reference id -> digest set for the session context files (number 4).
    ``args_digests`` is the digest set of the causing call's arguments (number 5, the causal
    key). Passing args separately, rather than as one more reference, is deliberate: a match
    against args is a causal claim (EFECTIVO), a match against a context file is a leak claim.
    They answer different questions and must not be conflated.

    Caveat, and it is a real one: matching is byte-literal, so a value the client
    percent-encodes, base64s, or splits across parameters is not detected in the target. That is
    a false negative in the safe direction and it is the same limit the body channel always had.
    """
    t_matched, t_refs, t_causal = _match_channel(target, context_index, args_digests, redactor)
    b_matched, b_refs, b_causal = _match_channel(body, context_index, args_digests, redactor)

    if t_causal and b_causal:
        channel = CHANNEL_BOTH
    elif t_causal:
        channel = CHANNEL_TARGET
    elif b_causal:
        channel = CHANNEL_BODY
    else:
        channel = CHANNEL_NONE

    return MatchResult(
        target_bytes=len(target),
        target_matched_bytes=t_matched,
        body_bytes=len(body),
        body_matched_bytes=b_matched,
        # Union across channels, sorted so two runs over the same input produce the same bytes
        # (gate rule 1); a set's iteration order would break byte-identical artifacts.
        matched_refs=sorted(set(t_refs) | set(b_refs)),
        causal_channel=channel,
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
