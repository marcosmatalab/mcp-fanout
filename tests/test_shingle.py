"""Tests for the rolling hash and winnowing, including the detection guarantee."""

from mcpfanout import shingle


def test_rolling_hash_is_deterministic():
    data = b"the quick brown fox jumps over the lazy dog"
    assert shingle.rolling_hashes(data, k=8) == shingle.rolling_hashes(data, k=8)


def test_short_input_has_no_kgram():
    assert shingle.rolling_hashes(b"short", k=16) == []
    # A string with no k-gram must winnow to the empty set: it can match nothing.
    assert shingle.fingerprints(b"short", k=16, w=8) == set()


def test_identical_data_same_fingerprints():
    a = b"AKIA_EXAMPLE_SECRET_TOKEN_0123456789 and some trailing context bytes"
    assert shingle.fingerprints(a) == shingle.fingerprints(bytes(a))


def test_winnow_detects_long_shared_substring():
    # Guarantee: a shared substring of length >= w + k - 1 yields a common fingerprint.
    k, w = shingle.DEFAULT_K, shingle.DEFAULT_W
    shared = b"X" * (w + k - 1) + b"_UNIQUE_MARKER_9f2a"  # comfortably over the threshold
    doc1 = b"left padding aaaa " + shared + b" bbbb right padding"
    doc2 = b"totally different prefix " + shared + b" and a different suffix zzzz"
    fp1 = shingle.fingerprints(doc1, k, w)
    fp2 = shingle.fingerprints(doc2, k, w)
    assert fp1 & fp2, "winnowing missed a shared substring longer than the guaranteed threshold"


def test_unrelated_data_do_not_collide_in_bulk():
    fp1 = shingle.fingerprints(b"one distinct sentence about apples and oranges here")
    fp2 = shingle.fingerprints(b"a completely unrelated line concerning tensors and gpus")
    # We do not require empty intersection in theory (hash collisions exist), but for these two
    # short unrelated strings the intersection must be empty in practice.
    assert not (fp1 & fp2)
