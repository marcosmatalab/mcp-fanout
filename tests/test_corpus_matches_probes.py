"""Every corpus argument must validate against the server's REAL tool schema.

This is the test the corpus never had, and its absence was threat 1 in practice rather than in
theory: registry/servers.yaml carried guessed tool names, and of the four guessed for
`everything`, three did not exist. A call to a tool that does not exist returns an error, records
zero egress, and drags numbers 1, 2 and 5 down without anything in the output saying so. A
measurement that fails quietly is worse than one that fails loudly.

The schemas are read from registry/probes/*.json, which are committed outputs of
harness/probe.py. So the check is against what the servers actually answered, not against a
second copy of our own beliefs.

Why a hand-written validator rather than `jsonschema`: the repository's runtime is stdlib-only by
design (see pyproject.toml), and the encargo's requirement is narrow -- required fields present
and types correct. That is about sixty auditable lines. A full JSON Schema implementation would
check far more than we assert and would be a dependency in the one place that must stay
trivially reproducible. Trade-off: this validator does not understand $ref, oneOf, format, or
numeric bounds, so it can pass an argument a real server still rejects. It cannot pass a
non-existent tool, a missing required field, or a wrong type, which are the failures that
actually happened.
"""

import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
CANARY = "CANARY_QRY_ab12cd34ef56"

# Keys in a corpus entry that are documentation, not protocol. drive_all.load_corpus reads only
# "tool" and "arguments", so "why" rides along ignored; the test requires it, because a corpus
# entry without a stated reason is the kind of plausible guess this whole file exists to stop.
META_KEYS = {"tool", "arguments", "why"}

JSON_TYPES = {
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "array": list,
    "object": dict,
    "null": type(None),
}


def _registry() -> dict:
    return yaml.safe_load((ROOT / "registry" / "servers.yaml").read_text())


def _servers() -> list[dict]:
    return _registry()["servers"]


def _ids() -> list[str]:
    return [s["id"] for s in _servers()]


def _type_ok(value, spec) -> bool:
    """True if ``value`` matches a JSON Schema ``type``, which may be a string or a list."""
    if spec is None:
        return True
    names = spec if isinstance(spec, list) else [spec]
    for name in names:
        py = JSON_TYPES.get(name)
        if py is None:
            return True  # a type we do not model: do not claim a violation we cannot prove
        # bool is a subclass of int in Python; JSON Schema does not consider true a number.
        if name in ("number", "integer") and isinstance(value, bool):
            continue
        if isinstance(value, py):
            return True
    return False


def _validate(value, schema, where: str, errors: list[str]) -> None:
    """Check required fields and types, recursing into object properties and array items."""
    if not isinstance(schema, dict):
        return

    if "anyOf" in schema:
        # Accept if any branch accepts. Collect nothing from the losing branches.
        for branch in schema["anyOf"]:
            trial: list[str] = []
            _validate(value, branch, where, trial)
            if not trial:
                return
        errors.append(f"{where}: matches no branch of anyOf")
        return

    if not _type_ok(value, schema.get("type")):
        errors.append(f"{where}: expected type {schema.get('type')!r}, got "
                      f"{type(value).__name__} ({value!r})")
        return

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{where}: {value!r} not in enum {schema['enum']}")

    if isinstance(value, dict):
        props = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value:
                errors.append(f"{where}: missing required field {name!r}")
        for name, sub in value.items():
            if name in props:
                _validate(sub, props[name], f"{where}.{name}", errors)
            elif props and schema.get("additionalProperties") is not True:
                # An argument the schema does not declare is exactly the "plausible but wrong"
                # failure this test exists for, so it is an error even when the schema is silent
                # about additionalProperties.
                errors.append(f"{where}: unknown field {name!r}; declared: {sorted(props)}")

    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for i, item in enumerate(value):
            _validate(item, schema["items"], f"{where}[{i}]", errors)


def _strings(value):
    """Every string anywhere in an argument tree, so a canary cannot hide in a nested field."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


def _load(server: dict) -> tuple[list[dict], dict[str, dict]]:
    corpus = json.loads((ROOT / server["corpus_ref"]).read_text())
    probe = json.loads((ROOT / server["probe_ref"]).read_text())
    return corpus, {t["name"]: t for t in probe["tools"]}


@pytest.mark.parametrize("server", _servers(), ids=_ids())
def test_referenced_files_exist(server):
    assert (ROOT / server["corpus_ref"]).is_file(), server["corpus_ref"]
    assert (ROOT / server["probe_ref"]).is_file(), server["probe_ref"]


@pytest.mark.parametrize("server", _servers(), ids=_ids())
def test_every_corpus_tool_exists_on_the_server(server):
    corpus, tools = _load(server)
    assert corpus, f"{server['id']}: empty corpus drives nothing"
    unknown = sorted({c["tool"] for c in corpus} - set(tools))
    assert not unknown, (f"{server['id']}: tools not offered by the server: {unknown}. "
                         f"Offered: {sorted(tools)}")


@pytest.mark.parametrize("server", _servers(), ids=_ids())
def test_every_corpus_argument_validates(server):
    corpus, tools = _load(server)
    errors: list[str] = []
    for i, call in enumerate(corpus):
        tool = tools.get(call["tool"])
        if tool is None:
            continue  # reported by the test above; do not double-report
        _validate(call.get("arguments", {}), tool["inputSchema"],
                  f"{server['id']}[{i}] {call['tool']}", errors)
    assert not errors, "\n".join(errors)


@pytest.mark.parametrize("server", _servers(), ids=_ids())
def test_every_corpus_entry_states_why(server):
    corpus, _ = _load(server)
    for i, call in enumerate(corpus):
        assert call.get("why", "").strip(), f"{server['id']}[{i}] {call['tool']}: no 'why'"
        extra = set(call) - META_KEYS
        assert not extra, f"{server['id']}[{i}]: unrecognised corpus keys {sorted(extra)}"


@pytest.mark.parametrize("server", [s for s in _servers() if s["expects_egress"]],
                         ids=[s["id"] for s in _servers() if s["expects_egress"]])
def test_egress_servers_carry_the_canary(server):
    """Number 5 is only measurable if something recognisable of ours is in the arguments.

    Only enforced where egress is expected: for a local control the canary is useful but not
    required, since there is no downstream for it to travel to.
    """
    corpus, _ = _load(server)
    assert any(CANARY in s for c in corpus for s in _strings(c.get("arguments", {}))), (
        f"{server['id']}: expects_egress but no argument carries the canary")


@pytest.mark.parametrize("server", _servers(), ids=_ids())
def test_tool_count_matches_the_probe(server):
    probe = json.loads((ROOT / server["probe_ref"]).read_text())
    assert server["tool_count"] == probe["tool_count"], (
        f"{server['id']}: registry says {server['tool_count']}, probe found {probe['tool_count']}")
    assert server["protocol_version_answered"] == probe["server_protocol_version"]


@pytest.mark.parametrize("server", _servers(), ids=_ids())
def test_launch_command_is_pinned_to_an_exact_version(server):
    """An unpinned launch makes a run unreproducible and lets a later release change a number."""
    pkg = [a for a in server["launch"] if not a.startswith("-")][1:]
    assert pkg, f"{server['id']}: no package in launch command"
    assert "@" in pkg[0].lstrip("@"), f"{server['id']}: {pkg[0]} is not pinned to a version"


def test_probe_files_are_machine_independent():
    """A committed probe must not name the operator's home directory.

    The first filesystem probe embedded an absolute path under /home, which is not reproducible
    registry data and leaks the operator's layout into a published file.
    """
    offenders = [p.name for p in (ROOT / "registry" / "probes").glob("*.json")
                 if "/home/" in p.read_text() or "/Users/" in p.read_text()]
    assert not offenders, f"absolute home paths in committed probes: {offenders}"


def test_argument_less_calls_are_possible_on_some_servers_and_not_others():
    """Pins the with/without-arguments split, which is a publishable result on its own.

    Three of the ten servers offer a tool whose schema requires nothing; the other seven require
    an argument on every tool they expose, so no argument-less call is possible there at all.
    This asserts the shape rather than a count: if a future pin changes it, the split is a
    finding to re-read, not a test to silence.
    """
    without = set()
    for server in _servers():
        corpus, tools = _load(server)
        if any(not c.get("arguments") for c in corpus):
            without.add(server["id"])
        # If the server offers an argument-less tool, the corpus must actually drive one.
        offers = any(not t["inputSchema"].get("required") for t in tools.values())
        assert offers == (server["id"] in without), (
            f"{server['id']}: offers an argument-less tool = {offers}, corpus drives one = "
            f"{server['id'] in without}")
    assert without == {"everything", "filesystem", "memory"}


# --- Figures quoted in prose. Gate rule 2: no figure without a command behind it. docs/THREATS.md
# --- threat 8 quotes a tool count per server, and prose drifts from data silently.

def test_threats_doc_tool_counts_match_the_probes():
    import re
    text = (ROOT / "docs" / "THREATS.md").read_text()
    for server in _servers():
        probe = json.loads((ROOT / server["probe_ref"]).read_text())
        # Only where the prose actually quotes a count: "<id> (13 tools)" or "<id> (13)".
        for quoted in re.findall(rf"\b{re.escape(server['id'])}\s*\((\d+)\b", text):
            assert int(quoted) == probe["tool_count"], (
                f"docs/THREATS.md says {server['id']} has {quoted} tools; "
                f"the probe found {probe['tool_count']}")


def test_threats_doc_total_matches_the_sum_of_the_probes():
    import re
    text = (ROOT / "docs" / "THREATS.md").read_text()
    total = sum(json.loads((ROOT / s["probe_ref"]).read_text())["tool_count"] for s in _servers())
    assert re.search(rf"\b{total} tools in all\b", text), (
        f"docs/THREATS.md does not state the measured total of {total} tools")
