"""Structural decomposition: one vocabulary, applied identically to both sides of a match.

WHY THIS EXISTS, AND WHY IT IS NOT A BETTER MATCHER. Numbers 4 and 5 turned out to be two
different problems wearing one instrument. Number 4 asks whether a request carried material from
a context file, and context files are prose: long, unstructured, and a literal k-gram is the right
tool, with a measured false-positive rate of 0.0000 (docs/CALIBRATION.md, F1.2). Number 5 asks
whether a request was caused by a specific tool call, and a tool call's arguments are not prose.
They are JSON fields whose values reappear on the wire as path segments and query parameters. The
correspondence is STRUCTURAL, and a k-gram cannot see it: `/docs/deploy/runbook` is 20 bytes and
invisible at k = 22, while `/docs/deploy/checklist` is 22 and visible, which is a matcher whose
sensitivity depends on how a documentation site happened to name a page.

So number 4 keeps the k-gram and number 5 moves here. Two problems, two instruments, written down
in docs/METHOD.md and pre-registered in docs/PREREG-F2.md.

THE RULE, AND ITS BOUNDARY. This module decomposes structure. It does not interpret meaning, and
docs/DOCTRINE.md draws the line: splitting a URL per RFC 3986, percent-decoding, plus-decoding and
walking JSON to its scalar leaves are allowed, because each recovers a structure the sender put
there with a published algorithm. Case folding, stemming, edit distance, synonym expansion and
embeddings are forbidden, because each guesses what the sender meant. The test of a proposed step
is not whether it improves recall: it is whether two independent implementations of the written
rule must agree on every input. Percent-decoding must. Stemming need not.

ONE RULE, ONE PLACE, BOTH SIDES. The same decomposition is applied to a call's arguments and to
the request on the wire. That is the whole reason this is a module and not two helpers: two
implementations of "what is a token" that drift apart produce a matcher whose false negatives are
invisible, because nothing fails, the sets simply stop intersecting. tests/test_structure.py
asserts the two entry points agree on the same string.

WHAT IS DELIBERATELY NOT A TOKEN.

- Non-string JSON scalars. A number, a boolean, a null. `{"max_length": 2000}` contributes
  nothing: 2000 has no textual identity, it is a knob, and treating it as evidence would attribute
  a flow to whichever call happened to share a page size.
- Anything shorter than MIN_TOKEN_BYTES after decoding. See the constant.

THE HOST IS A TOKEN HERE, AND IS NOT ONE IN match.py. That asymmetry is deliberate and was
measured. `match.match_request` excludes the host from the k-gram target on purpose, and putting
it back raises the k-gram false-positive rate from 0.0000 to 0.2500 while moving self-match not at
all: inside a byte run, a host manufactures literal overlap between calls that share nothing. As a
structural TOKEN the host is compared by equality against a token of the arguments, so it can only
match a call that actually named that host. It still carries almost no discriminating power, which
is not this module's problem to solve: it is handled where candidates are chosen, by the
discrimination rule in match.py, and the site-root call that owns nothing but a host is exactly
the case that rule exists for.
"""

from __future__ import annotations

import json
import urllib.parse

# The shortest decoded token that may be evidence. It is a DETECTION parameter and, since F2, a
# PRIVACY parameter too, and the second reading is the binding one.
#
# Detection: below three bytes a value identifies nothing. `id`, `os`, `to` appear in unrelated
# requests constantly, and admitting them would make containment fire on coincidence.
#
# Privacy: redact.py PENDING gap 2 says a keyed hash does not protect a value with low entropy and
# a known format, and names enums and short codes as the class. Structural tokens ARE that class,
# so the 22-byte window that used to act as an accidental privacy floor is gone. Three does not
# restore it and is not pretending to: docs/DOCTRINE.md states that for short tokens a keyed
# digest is obfuscation and not access control, and both redact.py PENDING gaps are preconditions
# of deploying this outside a measurement. This constant bounds the detection nuisance; it does
# not bound the privacy exposure, and no value of it would.
#
# Held at 3 because that is the value every figure in docs/PREREG-F2.md was predicted at. Moving
# it invalidates the pre-registered predictions and is a re-registration, not a tweak.
MIN_TOKEN_BYTES = 3


def _keep(values: list[str]) -> list[str]:
    """Percent-decode, then apply the length floor. In that order, deliberately.

    Applying the floor first would admit `%20` (three bytes) and reject the space it decodes to,
    which is a rule about our own encoding rather than about the sender's value.
    """
    out = []
    for v in values:
        d = urllib.parse.unquote(v)
        if len(d) >= MIN_TOKEN_BYTES:
            out.append(d)
    return out


def split_string(value: str) -> list[str]:
    """Decompose ONE string into structural tokens. The single rule both sides are built on.

    A URL yields its host, its path segments and its query VALUES. Query keys are excluded: a key
    is the API's vocabulary, not the caller's data, and `q`, `id` or `sha` would match every
    request to the same endpoint. A bare path yields its segments. Anything else is one token.
    """
    out: list[str] = []
    rest = value
    if "://" in rest:
        u = urllib.parse.urlsplit(rest)
        if u.netloc:
            out.append(u.netloc)
        rest = u.path
        for values in urllib.parse.parse_qs(u.query, keep_blank_values=True).values():
            out.extend(values)
    if "/" in rest:
        out.extend(seg for seg in rest.split("/") if seg)
    elif rest:
        out.append(rest)
    return _keep(out)


def _string_leaves(obj: object, out: list[str]) -> list[str]:
    """Every string scalar of a JSON document, in document order. Non-strings are skipped."""
    if isinstance(obj, dict):
        for v in obj.values():
            _string_leaves(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _string_leaves(v, out)
    elif isinstance(obj, str):
        out.append(obj)
    return out


def tokens_of_arguments(arguments: dict) -> frozenset[str]:
    """The structural vocabulary of one tool call's arguments. The CAUSE side."""
    out: list[str] = []
    for leaf in _string_leaves(arguments, []):
        out.extend(split_string(leaf))
    return frozenset(out)


def tokens_of_request(host: str, target: str, body: bytes | str = b"") -> frozenset[str]:
    """The structural vocabulary of one outbound request. The EFFECT side.

    Decomposed twice, and the second pass is not redundant. The first pass splits the wire into
    host, path segments and query values. A query value may itself be a URL or a path (an agent
    asking a fetch proxy for `?url=https://host/a/b`), so each token is split again by the same
    rule. Without it, a call whose argument is `a/b` would not match a request that carries
    `a/b` inside a parameter, which is the redirector case and is common.
    """
    first: list[str] = []
    u = urllib.parse.urlsplit("//" + host + target)
    if u.netloc:
        first.append(u.netloc)
    first.extend(seg for seg in u.path.split("/") if seg)
    for values in urllib.parse.parse_qs(u.query, keep_blank_values=True).values():
        first.extend(values)

    text = body.decode("utf-8", "replace") if isinstance(body, bytes) else body
    if text:
        try:
            first.extend(_string_leaves(json.loads(text), []))
        except (ValueError, TypeError):
            # Not JSON: try form encoding, which is the other body shape a tool call produces.
            # A body that is neither contributes nothing rather than being split on guesswork.
            for values in urllib.parse.parse_qs(text, keep_blank_values=True).values():
                first.extend(values)

    tokens = set(_keep(first))
    for token in list(tokens):
        tokens.update(split_string(token))
    return frozenset(tokens)


def contains(call_tokens: frozenset[str], request_tokens: frozenset[str]) -> bool:
    """Containment: every structural token of the call is present in the request.

    Not an intersection test. An intersection fires when a call shares any one token with a
    request, which for `example.net` is every request to that host. Containment asks for all of
    them, which is what makes the criterion usable without a score or a threshold, and it is why
    there is no tunable constant in this function. A call with no tokens at all is never
    contained: it claims nothing, so it cannot be evidence.
    """
    return bool(call_tokens) and call_tokens <= request_tokens


def distinguishing(call_tokens: frozenset[str],
                   other_calls: list[frozenset[str]]) -> frozenset[str]:
    """The tokens this call owns that no other concurrent call owns.

    Empty means the call cannot be told apart from its neighbours by content, whatever a matcher
    does with it. See match.discriminating_candidates and docs/THREATS.md threat 18.
    """
    shared: set[str] = set()
    for other in other_calls:
        shared |= other
    return call_tokens - shared
