"""Test the MCP stdio driver against the mock server."""

import sys
from pathlib import Path

from mcpfanout.driver import CallSpec, drive, new_traceparent


def test_traceparent_shape():
    tp = new_traceparent()
    parts = tp.split("-")
    assert parts[0] == "00" and len(parts[1]) == 32 and len(parts[2]) == 16 and parts[3] == "01"


def test_drive_mock_server():
    mock = str(Path(__file__).parent / "mock_server.py")
    corpus = [
        CallSpec("search", {"query": "hello"}),
        CallSpec("search", {}),  # argument-less call: args_present must be False
    ]
    results = drive([sys.executable, mock], corpus, run_id="t", server_id="mock")
    assert len(results) == 2
    assert all(r.ok for r in results), [r.error for r in results]
    assert results[0].args_present is True
    assert results[1].args_present is False
    # Each call carries a distinct traceparent (the attribution key).
    assert results[0].traceparent != results[1].traceparent
