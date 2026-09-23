# The example runs

`runs/` is not tracked. These three directories are, and they are not captured runs.

`example-sequential` and `example-concurrent` are **redacted** copies of the two runs this
repository publishes, produced by [`tools/redact_run.py`](../tools/redact_run.py) from
`20260919T115452Z-sequential` and `20260919T194649Z-concurrent`. They exist for one reason: without
them `make n1` fails in a clean clone with `error: no runs/ directory yet`, and five of the ten
Quickstart commands do not run. A repository whose argument is reproducibility cannot ask a reader
to take the six numbers on trust.

`example-blind-proxy` is the third, redacted from `20260919T193121Z-concurrent`, the concurrent
capture taken while the proxy was still blind to Node's global `fetch`. None of the six numbers is
read from it. It is committed because finding 1 in the README (threat 19) is read from it: without
it the figures of the headline finding, 16 of 17 calls completed with no flow while they ran and 10
connections the proxy never saw, could not be re-run by anyone, and `make backstop` on the other
concurrent run printed a different run whose one count of 10 matched by coincidence.
`make backstop RUN=example-blind-proxy` prints both halves.

## What was replaced, and what was kept

| Replaced | By |
| --- | --- |
| server ids | `server-0` .. `server-9`, in the order the run's own manifest recorded |
| tool names | `tool-0` .. `tool-N` within each server, assigned in sorted order |
| call ids | `<server label>-c<NNN>`, keeping the numbering so the join to the flows survives |
| destination hosts | one label per class: `package-registry-a`, `third-party-a` .., `loopback-proxy` |
| destination addresses | `192.0.2.0/24`, the RFC 5737 documentation range, one address per label |
| error messages | the exception class and the JSON-RPC code. Two of the three named a vendor |
| version pins | dropped: three of the ten packages are identifiable from their exact version alone |

Kept, byte for byte: every salted digest, every byte count, every timestamp, every protocol
revision, every lifecycle phase, and every field the six numbers are computed from. That is why the
numbers are identical rather than similar.

## What this costs, stated rather than buried

Three of the six numbers are computed by applying a list in `registry/` to a hostname: whether the
destination is package infrastructure (numbers 1 and 5) and whether it is self-hostable (number 6).
A redacted run has no hostname, so those answers cannot be re-derived from it. They were computed
before the hostnames were destroyed and are carried in the record, with the digest of the list they
were computed against recorded in `manifest.json` under `redaction`.

**The cost is that a newer registry cannot re-answer an old published run**, which is exactly the
property the attribution grade is kept OUT of the record to preserve. The mitigation is not a
promise: `make n1` prints the carried digest next to the current file's digest and says whether they
still match, so a list that has moved shows up in the output instead of being assumed away.

The same applies to gate rule 7. The declaration in `registry/declared-destinations.json` is keyed
by real server ids, so it is relabelled through the same map and carried with the run. The check
still runs, over labels, and because the relabelling is injective its answer is the answer it gives
on the capture. What it cannot do is read a maintainer's documentation about a destination nobody
declared, and `make disclosure` says so in its own output.

## Verify it yourself

```bash
# 1. No host, no server name, no tool name survived
grep -riE "github|npmjs|google|brave|puppeteer|modelcontextprotocol" runs/example-*/ ; echo "exit=$? (1 = clean)"

# 2. Gate rule 7 is clear: nobody's destination is undeclared
make disclosure RUN=example-concurrent ; echo "exit=$? (0 = clear)"

# 3. The headline number is the published one, from the committed run
make n5 RUN=example-concurrent | grep content_attributable_fraction
#   "content_attributable_fraction": 0.6579

# 4. And the whole figure matches, field by field
python3 -m pytest tests/test_example_runs.py -q
```

Check 4 is the one that matters: `tests/test_example_runs.py` recomputes every one of the six
numbers from these directories and compares them against the committed aggregates under
`docs/figures/`, which were produced from the captures. It fails on any difference other than the
three fields a redacted run adds to say that its classification was carried. A published run that
stopped reproducing its own published figure is the defect `make figures-check` exists for,
arriving from the other side.

## Regenerating them

Only possible where the captures still are, which is the machine that ran them:

```bash
python3 tools/redact_run.py --run runs/20260919T115452Z-sequential --out runs/example-sequential
python3 tools/redact_run.py --run runs/20260919T194649Z-concurrent --out runs/example-concurrent
python3 tools/redact_run.py --run runs/20260919T193121Z-concurrent --out runs/example-blind-proxy
```

The output is deterministic: the same capture produces the same redacted run byte for byte.
