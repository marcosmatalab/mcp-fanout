"""Digest-only redaction: the privacy boundary of the whole harness.

Doctrine (docs/DOCTRINE.md): the collector may see payloads that carry personal data, so it
stores digests and references with a salt, never content. The only sentence it can emit is:
"the fragment with hash X, from reference Y, appeared in the output toward domain Z."

Everything that leaves memory passes through a Redactor. Raw bytes exist only transiently,
during the hashing pass, which is unavoidable: to know whether a fragment was sent you must
see it. The doctrine constrains STORAGE, not the in-memory match.

Design decisions
----------------
- Salted digest with BLAKE2b keyed by the salt. Reason for a keyed hash over plain SHA-256:
  without a secret key, an adversary who guesses a candidate secret can confirm its presence
  by recomputing the digest (a dictionary attack on the stored fingerprints). Keying with a
  per-deployment salt removes that. Trade-off: digests are only comparable within one salt,
  so cross-run comparison is not possible. We do not need it; a run is self-contained.

- Digest truncated to 128 bits (16 bytes). Collision probability at 128 bits over the
  fingerprint counts we handle (< 1e7) is < 1e-25 by the birthday bound, negligible, and it
  halves storage versus a full 256-bit digest. This is a genuine probabilistic quantity, so
  it is stated rather than hidden.

- Fixed default salt for reproducibility. `make verify` and any published measurement must be
  reproducible byte for byte (docs/PROTOCOL.md rule 1). A fixed salt makes stored digests
  identical across runs. The NUMBERS are invariant to the salt regardless (they are counts and
  ratios over set intersections), so a secret salt in a real deployment changes what is stored
  but never what is reported.

PENDING, and deliberately not built here
----------------------------------------
Two gaps in the privacy boundary, written down because the argument above reads as finished and
is not. Neither is a to-do a later refactor absorbs; both are limits on what this code may
honestly be used for today.

1. PER-INSTALLATION KEY MANAGEMENT, WITH ROTATION. There is one constant, DEFAULT_SALT, published
   in this file. Correct for a reproducible measurement, wrong for a deployment: a published salt
   is not a key, so the dictionary attack the keyed hash exists to prevent is wide open against
   any run using the default. What is missing is a key generated per installation at install
   time, never committed, plus rotation. Rotation is not a config change: digests are only
   comparable within one key, so rotating invalidates every stored fingerprint, which makes it a
   data-lifecycle decision. Until it exists, treat every digest made with DEFAULT_SALT as public.

2. AN EXPLICIT MINIMUM-FRAGMENT-LENGTH POLICY. k = 16 bytes is a DETECTION parameter, chosen so a
   shared run is not coincidental. It is currently doing double duty as a privacy parameter and it
   is not adequate for that. A salted hash does not protect a value with low entropy and a known
   format, which is precisely the class this harness hunts: a four-digit PIN, a date of birth, a
   short account number, an enum. An adversary holding the salt only has to enumerate the format.
   No value of k fixes this. What is needed is a stated policy on which fragment classes may be
   fingerprinted at all, written before a real deployment rather than after one.
"""

from __future__ import annotations

import hashlib

from . import shingle

# Fixed salt for reproducible measurement runs. A real deployment overrides it with a secret.
# Documented as fixed on purpose: see the module docstring, last bullet.
DEFAULT_SALT = b"mcp-fanout/fixed-salt/v1"

_DIGEST_BYTES = 16  # 128-bit truncation. See module docstring.


class Redactor:
    """Turns byte strings into salted, content-free fingerprint digests."""

    def __init__(self, salt: bytes = DEFAULT_SALT, k: int = shingle.DEFAULT_K,
                 w: int = shingle.DEFAULT_W) -> None:
        if not salt:
            # An empty salt would make the keyed hash behave like a plain hash and reopen the
            # dictionary attack above. Refuse it loudly rather than degrade silently.
            raise ValueError("salt must be non-empty")
        self.salt = salt
        self.k = k
        self.w = w

    def _digest_int(self, value: int) -> str:
        """Salted 128-bit hex digest of one rolling-hash value."""
        h = hashlib.blake2b(
            value.to_bytes(8, "big", signed=False),
            key=self.salt,
            digest_size=_DIGEST_BYTES,
        )
        return h.hexdigest()

    def kgram_digests(self, data: bytes) -> list[str]:
        """Positional list of salted digests, one per k-gram, left to right.

        Positional (a list, not a set) because exact byte-coverage in match.py needs to know
        which offsets are covered. The caller discards positions when it only needs membership.
        """
        return [self._digest_int(v) for v in shingle.rolling_hashes(data, self.k)]

    def kgram_digest_set(self, data: bytes) -> frozenset[str]:
        """Membership set of salted k-gram digests. Used to index a reference (a file, args)."""
        return frozenset(self._digest_int(v) for v in shingle.rolling_hashes(data, self.k))

    def winnowed_digests(self, data: bytes) -> frozenset[str]:
        """Compact, persisted fingerprint set (winnowed). A subset of kgram_digest_set.

        This is what may be written to disk for later audit. It is smaller (fewer fingerprints)
        and it carries the winnowing detection guarantee from shingle.winnow.
        """
        return frozenset(self._digest_int(v) for v in shingle.fingerprints(data, self.k, self.w))


    def token_digest(self, token: str) -> str:
        """Salted digest of ONE structural token. Never the token itself leaves this process.

        DOMAIN SEPARATION, and it is not decoration. A k-gram digest is the hash of a rolling-hash
        VALUE; a token digest is the hash of the token's bytes. Without a separator the two live in
        one namespace, and a k-gram whose rolling hash happened to equal a token's byte pattern
        would be indistinguishable from that token. The two sets are compared against different
        things and must never be interchangeable, so the prefix makes a cross-domain equality
        impossible rather than improbable.

        WHAT THIS DOES NOT PROTECT, stated where the code is rather than only in the doctrine.
        Structural tokens are short, low-entropy and drawn from a known vocabulary: `docs`,
        `deploy`, `warn`, a ref name, an enum. Against a holder of the salt they are recoverable by
        enumeration in seconds. This is PENDING gap 2 above arriving on the main path, not a new
        problem, and no digest function fixes it. For short tokens a keyed digest is obfuscation,
        not access control (docs/DOCTRINE.md). Both PENDING gaps are preconditions of deploying
        the structural matcher outside a measurement.
        """
        h = hashlib.blake2b(b"tok\x00" + token.encode("utf-8", "surrogateescape"),
                            key=self.salt, digest_size=_DIGEST_BYTES)
        return h.hexdigest()

    def token_digest_set(self, tokens) -> frozenset[str]:
        """Membership set of salted token digests. The only form tokens are compared in."""
        return frozenset(self.token_digest(t) for t in tokens)


def format_finding(digest: str, reference: str, domain: str) -> str:
    """The one sentence the collector is allowed to store or print about a match."""
    return f"fragment {digest} from reference {reference} appeared in output toward {domain}"
