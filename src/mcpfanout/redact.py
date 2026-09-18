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
  reproducible byte for byte (docs/THE-GATE.md rule 1). A fixed salt makes stored digests
  identical across runs. The NUMBERS are invariant to the salt regardless (they are counts and
  ratios over set intersections), so a secret salt in a real deployment changes what is stored
  but never what is reported.
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


def format_finding(digest: str, reference: str, domain: str) -> str:
    """The one sentence the collector is allowed to store or print about a match."""
    return f"fragment {digest} from reference {reference} appeared in output toward {domain}"
