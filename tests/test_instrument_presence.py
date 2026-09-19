"""Gate rule 10 for the structural matcher: does it go red when the instrument is ABSENT.

The three instances in docs/THE-GATE.md rule 10 all passed their suites while doing nothing. The
structural path has the same shape and one extra trap: aggregate._attributing_match falls back to
the k-gram signal for flows with no structural fields, which is correct for a pre-F2 run and would
silently launder a post-F2 run whose driver stopped publishing token_digests.

So these tests do not check that the fields exist. All three historical failures had their fields.
They check that the fields hold what only a working instrument could have put there, through the
real driver entry point and the real addon loader.
"""

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

from mcpfanout.aggregate import Run, number_5, structural_instrument_state
from mcpfanout.driver import CallSpec, publish_active_calls, token_digests_for
from mcpfanout.record import Flow, RunManifest
from mcpfanout.redact import Redactor

REPO = Path(__file__).resolve().parent.parent
ADDON = REPO / "src" / "mcpfanout" / "capture_addon.py"

def _manifest():
    return RunManifest(run_id="t", created="", salt_fixed=True, k=22, w=8,
                       corpus_sha256="", pass_name="concurrent")


RUNBOOK = {"url": "https://example.net/docs/deploy/runbook"}
ROLLBACK = {"url": "https://example.net/docs/deploy/rollback"}


# --- The driver's half of the join.

def test_the_driver_publishes_non_empty_token_digests_for_a_call_with_arguments():
    """If this returns [], the whole structural path degrades to silence, not to an error."""
    digests = token_digests_for(CallSpec("fetch", RUNBOOK), Redactor())
    assert digests, "the driver published no structural tokens for a call that has some"
    assert len(digests) == 4, digests
    assert all(len(d) == 32 for d in digests)


def test_the_driver_publishes_nothing_for_a_call_with_no_arguments():
    assert token_digests_for(CallSpec("ping", {}), Redactor()) == []


# --- End to end: real driver publication, real addon loader, positive result.

class _Req:
    def __init__(self, host, path):
        self.raw_content = b""
        self.headers = {}
        self.pretty_host = host
        self.scheme = "https"
        self.method = "GET"
        self.path = path


class _Flow:
    def __init__(self, request):
        self.request = request
        self.server_conn = type("C", (), {"peername": ("93.184.216.34", 443)})()


def _load_addon(tmp_path, control):
    """Loaded the way mitmproxy loads it, by path under a synthetic package name."""
    fullname = "__mitmproxy_script__.instrument_presence"
    saved_path, saved_env = list(sys.path), dict(os.environ)
    sys.path.insert(0, str(ADDON.parent))
    os.environ.update({"MCPFANOUT_RUNDIR": str(tmp_path),
                       "MCPFANOUT_CONTROL": str(control),
                       "MCPFANOUT_RUNID": "t", "MCPFANOUT_SALT": "test-salt"})
    os.environ.pop("MCPFANOUT_CONTEXT", None)
    try:
        spec = importlib.util.spec_from_file_location(fullname, str(ADDON))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.addons[0]
    finally:
        sys.path[:] = saved_path
        os.environ.clear()
        os.environ.update(saved_env)
        sys.modules.pop(fullname, None)


def _drive(tmp_path, *arg_dicts, withhold_tokens=False, host="example.net",
           path="/docs/deploy/rollback"):
    """Publish a wave through the DRIVER's own function, then run the addon over one request."""
    control = tmp_path / "control"
    r = Redactor(salt=b"test-salt")
    entries = []
    for i, args in enumerate(arg_dicts):
        spec = CallSpec("fetch", args)
        entry = {"call_id": f"fetch-c{i:03d}", "traceparent": "", "args_present": True,
                 "args_digests": []}
        if not withhold_tokens:
            entry["token_digests"] = token_digests_for(spec, r)
        entries.append(entry)
    publish_active_calls(control, "t", "fetch", entries, phase="driving")
    rec = _load_addon(tmp_path, control)
    rec.request(_Flow(_Req(host, path)))
    rec.done()
    return [json.loads(l) for l in (tmp_path / "flows.jsonl").open()][-1]


def test_the_instrument_produces_the_value_only_a_working_one_could(tmp_path):
    """Not "the field is present": all three rule 10 failures had their fields present."""
    row = _drive(tmp_path, RUNBOOK, ROLLBACK)
    assert row["structural_match"] is True
    assert row["structural_contained"] == 1
    assert row["structural_candidates"] == 1
    assert row["candidate_token_count"] == 4
    assert row["call_id"] == "fetch-c001"


def test_withholding_the_drivers_token_digests_is_detected_and_not_absorbed(tmp_path):
    """The trap. The addon must not fake a match, and the run must not read as a clean zero."""
    row = _drive(tmp_path, RUNBOOK, ROLLBACK, withhold_tokens=True)
    assert row["structural_match"] is False
    assert row["structural_contained"] == 0

    run = Run(_manifest(), [], [Flow(**row)])
    state = structural_instrument_state(run)
    assert state["state"] == "absent", state
    assert "did not run" in state["warning"]


def test_a_working_run_reports_the_instrument_as_present(tmp_path):
    row = _drive(tmp_path, RUNBOOK, ROLLBACK)
    run = Run(_manifest(), [], [Flow(**row)])
    assert structural_instrument_state(run)["state"] == "present"


def test_number_5_carries_the_instrument_state_so_a_zero_cannot_be_read_as_a_finding(tmp_path):
    row = _drive(tmp_path, RUNBOOK, ROLLBACK, withhold_tokens=True)
    run = Run(_manifest(), [], [Flow(**row)])
    out = number_5(run)
    assert out["structural_instrument"]["state"] == "absent"
    assert "warning" in out["structural_instrument"]


@pytest.mark.parametrize("path,expected", [
    ("/docs/deploy/rollback", True),
    ("/robots.txt", False),
    ("/unrelated", False),
])
def test_the_addon_discriminates_rather_than_matching_everything(tmp_path, path, expected):
    """An instrument that matches everything is as absent as one that matches nothing."""
    row = _drive(tmp_path, RUNBOOK, ROLLBACK, path=path)
    assert row["structural_match"] is expected, path
