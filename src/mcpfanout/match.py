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

# ---------------------------------------------------------------------------------------------
# The evidence model: THREE SEPARATE CLAIMS.
#
# These replace the single EFECTIVO / DECLARADO / INDETERMINADO column, which conflated three
# different questions into one word and so could not answer any of them precisely. The three
# never appear together in one sentence, in a record or in a report, because a sentence that
# joins them is the conflation coming back:
#
#   OCCURRENCE   was the transfer observed at all
#   PROVENANCE   did the request carry recognisable material of ours (a file, an argument)
#   ATTRIBUTION  could it be tied to a specific tool call, and HOW STRONGLY
#
# What forced the split: the first real capture produced 90 DECLARADO flows, of which 87 were a
# package registry that cannot carry a tool call's arguments at all. Calling those DECLARADO
# asserts temporal correlation where the truth is ineligibility. They are UNATTRIBUTED, with the
# reason named.
# ---------------------------------------------------------------------------------------------

# OCCURRENCE. Did we see the transfer, and could we read it.
OCCURRENCE_OBSERVED = "observed"                  # TLS terminated, request read
OCCURRENCE_CONNECTION_ONLY = "connection_only"    # connection seen, contents unreadable

# PROVENANCE. What recognisable material of ours the request carried. Says nothing about which
# call caused it: that is attribution's job, and keeping them apart is the point.
PROVENANCE_NONE = "none"              # read it, found nothing of ours
PROVENANCE_CONTEXT = "context"        # material from a session context file
PROVENANCE_ARGUMENTS = "arguments"    # material from a driven call's arguments
PROVENANCE_BOTH = "both"
PROVENANCE_UNKNOWN = "unknown"        # could not read it, so nothing may be claimed either way

# ATTRIBUTION, a graded dimension, strongest first. A grade is a claim about EVIDENCE QUALITY,
# never about certainty of cause.
TRACE_PROPAGATED = "TRACE_PROPAGATED"
CONTENT_UNIQUE = "CONTENT_UNIQUE"
CONTENT_AMBIGUOUS = "CONTENT_AMBIGUOUS"
CONTENT_MATCH_UNCONTESTED = "CONTENT_MATCH_UNCONTESTED"
TEMPORAL_ONLY = "TEMPORAL_ONLY"
UNATTRIBUTED = "UNATTRIBUTED"

ATTRIBUTION_GRADES = (TRACE_PROPAGATED, CONTENT_UNIQUE, CONTENT_AMBIGUOUS,
                      CONTENT_MATCH_UNCONTESTED, TEMPORAL_ONLY, UNATTRIBUTED)

# Grades that may be called strong attribution. CONTENT_MATCH_UNCONTESTED is deliberately NOT
# among them: see grade_attribution.
STRONG_ATTRIBUTION = (TRACE_PROPAGATED, CONTENT_UNIQUE)

# Named reasons. An UNATTRIBUTED flow without a reason is a shrug recorded as data.
REASON_INELIGIBLE_PACKAGE_INFRASTRUCTURE = (
    "ineligible: package infrastructure traffic, carries no tool-call arguments")
REASON_NO_EVIDENCE = "no trace, no content match, and no temporal correlation available"
# A flow the LAUNCHER caused, before the server process existed. Not "we found no evidence": there
# was nothing that could have caused it. npx and uvx resolve and download a package before the
# server's first instruction runs, and that egress belongs to the package manager.
REASON_PRE_LAUNCH = ("pre-launch: seen while the launcher was resolving the package, before the "
                     "server process existed, so no tool call could have caused it")
REASON_UNREADABLE_NO_CORRELATION = "request unreadable and no temporal correlation available"
# A time window that covers several in-flight calls identifies a SET, not a call. Prefix only:
# the count is interpolated, and tests match on the prefix.
REASON_TEMPORAL_AMBIGUOUS_PREFIX = "time window covers "

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


def argument_kgrams_present(data: bytes, args_digests: frozenset[str],
                            redactor: Redactor) -> frozenset[str]:
    """WHICH of the call's argument k-grams appear in these bytes, not merely whether any does.

    The shipped matcher needs only the boolean, and used to compute it inline. It is exposed as the
    set because the rarity experiment (mcpfanout.rarity, F1.3) has to weigh exactly the k-grams that
    matched, and a second implementation of "which ones matched" would let the published
    false-positive figure describe a different matcher from the one that ships.
    """
    return args_digests & frozenset(redactor.kgram_digests(data))


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
    # direction: the flow grades TEMPORAL_ONLY rather than being falsely credited with a
    # content match it did not have.
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
    against args is an attribution claim, a match against a context file is a provenance claim.
    Those are two of the three separate claims in the evidence model, and conflating them is
    exactly what the single-column state was doing.

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


# ---------------------------------------------------------------------------------------------
# NUMBER 5'S MATCHER: structural containment over token digests.
#
# Separate from the k-gram path above, deliberately and permanently. Number 4 asks whether a
# request carried material from a context file, which is prose, and keeps the k-gram. Number 5
# asks whether a request was CAUSED by a specific call, whose arguments are JSON fields that
# reappear as path segments and query values, and that correspondence is structural. Two problems,
# two instruments (docs/METHOD.md, docs/PREREG-F2.md).
#
# Nothing here ever sees a token. The driver publishes the digest of each of a call's structural
# tokens; the addon digests the tokens it decomposes off the wire; these functions compare sets of
# digests. Set containment over digests is set containment over tokens up to a digest collision,
# which is bounded in shingle.py and at these set sizes is not expected to fire once.
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Candidates:
    """The outcome of asking which in-flight calls could have caused one request.

    Every field is published, because the difference between them is where threat 18 lives and a
    grade distribution alone cannot show it.
    """

    contained: tuple[int, ...]          # calls whose whole token set is present in the request
    discriminating: tuple[int, ...]     # of those, the ones that own a token no neighbour owns
    non_discriminating_active: int      # in-flight calls excluded for owning no such token
    token_count: int                    # tokens of the single surviving candidate, else 0


def discriminating_candidates(call_token_sets: list[frozenset[str]],
                              request_tokens: frozenset[str]) -> Candidates:
    """Which in-flight calls could have caused this request, after the discrimination rule.

    TWO STEPS, AND THE ORDER IS THE DESIGN.

    1. Containment. A call is contained when EVERY one of its structural tokens is present in the
       request. Not an intersection: intersecting fires whenever a call shares one token with a
       request, and for a host token that is every request to that host.

    2. Discrimination, and this is rule C from docs/PREREG-F2.md, adopted as a principle rather
       than as a threshold. A call that owns no token distinguishing it from the other calls in
       flight leaves the candidate set entirely. It is NOT that such a call makes the whole wave
       ambiguous: that was measured and costs two thirds of what containment gains.

    WHY THE RULE IS NOT OPTIONAL, measured rather than argued. In the concurrent run's fetch wave
    at N = 10, one call is `{"url": "https://example.net/", "max_length": 2000}`, whose only
    structural token is the host. Without step 2 it is contained in every flow of its own wave,
    including all ten `/robots.txt` requests, and each of those grades as a confident, unique,
    WRONG attribution to it: nine false strong attributions out of twenty flows. With step 2 it
    owns nothing its neighbours do not, it leaves the candidate set, and those flows correctly
    come out unattributed.

    WHAT THE RULE COSTS, and it is a limit of the method rather than of this implementation. A
    call whose tokens are a proper subset of a concurrent call's is also excluded, so it loses the
    attribution of its OWN flow. In the same wave, `/docs/deploy/runbook` is lost to
    `/docs/deploy/runbook?section=rollback-steps`, which is an agent re-reading its own document
    with more precision and is one of the commonest things an agent does. That flow goes
    unattributed and is never reassigned. docs/THREATS.md threat 18 carries the argument that no
    containment-based matcher can do better, and `non_discriminating_active` is published so the
    loss is visible in the output instead of looking like a matcher that failed to match.
    """
    contained = [i for i, toks in enumerate(call_token_sets)
                 if toks and toks <= request_tokens]
    non_discriminating = 0
    keep: list[int] = []
    for i, toks in enumerate(call_token_sets):
        others = [u for j, u in enumerate(call_token_sets) if j != i]
        shared: set[str] = set()
        for other in others:
            shared |= other
        if toks and not (toks - shared):
            non_discriminating += 1
        elif i in contained:
            keep.append(i)
    token_count = len(call_token_sets[keep[0]]) if len(keep) == 1 else 0
    return Candidates(contained=tuple(contained), discriminating=tuple(keep),
                      non_discriminating_active=non_discriminating, token_count=token_count)


def decide_occurrence(request_observed: bool) -> str:
    """Claim one: was the transfer observed, and could it be read."""
    return OCCURRENCE_OBSERVED if request_observed else OCCURRENCE_CONNECTION_ONLY


def decide_provenance(request_observed: bool, has_context_match: bool,
                      has_argument_match: bool) -> str:
    """Claim two: what recognisable material of ours the request carried.

    Unreadable means UNKNOWN, never NONE. "We looked and found nothing" and "we could not look"
    are different findings and collapsing them into one value is how a blind spot reads as a
    clean result.
    """
    if not request_observed:
        return PROVENANCE_UNKNOWN
    if has_context_match and has_argument_match:
        return PROVENANCE_BOTH
    if has_context_match:
        return PROVENANCE_CONTEXT
    if has_argument_match:
        return PROVENANCE_ARGUMENTS
    return PROVENANCE_NONE


def grade_attribution(*, traceparent_present: bool, argument_match: bool,
                      active_calls_in_window: int, matching_calls_in_window: int,
                      eligible: bool, has_time_and_pid: bool,
                      call_caused_possible: bool = True,
                      candidate_token_count: int = 0) -> tuple[str, str]:
    """Claim three: how strongly this flow can be tied to a tool call. Returns (grade, reason).

    ``call_caused_possible`` is False when the flow was seen in a lifecycle phase where no call of
    ours existed yet (record.PHASES_NOT_CALL_CAUSED). It is checked FIRST, before trace and content
    evidence, which is the opposite of how eligibility is treated and deliberately so: eligibility
    withholds a temporal guess about a flow that could have been caused by a call, while this says
    the flow predates every call there was. Nothing can outvote that, not even a content match,
    because a content match against a call that had not been made yet would be a collision.

    THE TAUTOLOGY THIS FUNCTION EXISTS TO AVOID. The corpus is driven sequentially, so in every
    window there is exactly ONE active call. Under that regime, "the fragment matched and there
    was no competing candidate" is true of every match by construction, and implementing
    CONTENT_UNIQUE that way would publish 100% strong attribution while having discriminated
    nothing. It would be a restatement of the experimental setup wearing a measurement's
    clothes. So:

      CONTENT_UNIQUE               requires active_calls_in_window > 1 AND the fragment present
                                   in exactly one of them. That is discrimination: candidates
                                   existed and the content told them apart.
      CONTENT_AMBIGUOUS            more than one active call and the fragment in several of
                                   them. Content matched and did NOT discriminate. A real
                                   outcome, and the one that bounds precision.
      CONTENT_MATCH_UNCONTESTED    a match with only one call active. Honest and weaker: there
                                   was nothing to tell apart. This is what sequential driving
                                   can yield, and it is NOT strong attribution.

    The same reasoning applies to the temporal grade, symmetrically. TEMPORAL_ONLY requires
    exactly one call in flight, because a window covering several identifies a set rather than a
    call. With more than one in flight and no content evidence the grade is UNATTRIBUTED, with
    the count in the reason. Anything else would let the weakest evidence claim what the
    strongest is not allowed to.

    So today, with sequential driving, this function emits no CONTENT_UNIQUE at all, and a test
    asserts that. The question the project exists to answer, whether content matching recovers
    attribution when time cannot, is answerable only in phase C with concurrent calls
    (docs/PHASES.md). The code says so instead of pretending otherwise.

    ELIGIBILITY ONLY DOWNGRADES THE WEAKEST GRADE. It is checked after trace and content
    evidence, never before. A package-registry flow that did carry our traceparent, or a literal
    fragment of a call's arguments, is attributed on that evidence and stays visible: the
    exclusion list withholds a temporal guess, it never suppresses direct evidence. Same
    principle as number 1 never filtering its raw count.
    """
    if not call_caused_possible:
        return UNATTRIBUTED, REASON_PRE_LAUNCH

    if traceparent_present:
        return TRACE_PROPAGATED, "our traceparent appeared in the outbound request"

    if argument_match:
        # THE ONE-TOKEN FLOOR. A single structural token is never strong evidence, whatever the
        # window says, and this is checked before the window because it is a property of the
        # evidence rather than of the competition. Measured against cases built to attack this
        # matcher: {"query": "logs"} is contained in /api/logs?level=warn, and a lone shared enum
        # value or a bare host is contained in anything that mentions it. The discrimination rule
        # in discriminating_candidates already removes the common case, a call whose only token is
        # shared with a neighbour; this catches the one it cannot, a call whose only token happens
        # to be unique in a small wave and is still a single generic word. It costs nothing on the
        # run this was pre-registered against, where every surviving candidate owns at least two
        # tokens, and it is a belt rather than a tuning constant. Zero means the caller did not
        # supply a token count (the k-gram path), and the floor does not apply.
        if candidate_token_count == 1:
            return CONTENT_AMBIGUOUS, (
                "a single structural token is not strong evidence on its own: one token "
                "identifies a class, not a call")
        if active_calls_in_window > 1 and matching_calls_in_window == 1:
            return CONTENT_UNIQUE, (
                f"fragment present in exactly 1 of {active_calls_in_window} concurrent calls")
        if active_calls_in_window > 1:
            return CONTENT_AMBIGUOUS, (
                f"fragment present in {matching_calls_in_window} of "
                f"{active_calls_in_window} concurrent calls; content did not discriminate")
        return CONTENT_MATCH_UNCONTESTED, (
            "fragment matched with only one call active: no competing candidate existed, so "
            "nothing was discriminated")

    if not eligible:
        return UNATTRIBUTED, REASON_INELIGIBLE_PACKAGE_INFRASTRUCTURE

    if has_time_and_pid and active_calls_in_window == 1:
        return TEMPORAL_ONLY, "time window and pid, with exactly one call in flight"

    if has_time_and_pid and active_calls_in_window > 1:
        # A window covering several in-flight calls identifies a SET, not a call, so it is not
        # attribution at all. Returning TEMPORAL_ONLY here would assert a correlation that
        # discriminates nothing, which is the same overstatement the old single-column model made
        # when it called package-registry traffic DECLARADO. Found while designing the phase A
        # bench: its fourth concurrency cell (N calls, none carrying arguments) has to land on
        # UNATTRIBUTED, and it would have landed on TEMPORAL_ONLY and looked like a pass.
        return UNATTRIBUTED, (
            f"{REASON_TEMPORAL_AMBIGUOUS_PREFIX}{active_calls_in_window} concurrent calls: "
            f"correlation identifies no single call")

    return UNATTRIBUTED, (REASON_NO_EVIDENCE if has_time_and_pid
                          else REASON_UNREADABLE_NO_CORRELATION)
