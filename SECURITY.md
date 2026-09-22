# Security policy

## This repository is a measurement harness, not a service

It runs third-party MCP servers inside a container, observes what leaves the machine, and stores
salted digests. It exposes no network service, accepts no untrusted input from outside the machine
it runs on, and holds no credential: the one lab token used in the measurement lives outside the
repository and outside the image, and `tests/test_credentials_never_persisted.py` fails if a
credential reaches any artifact this repository produces, proving its own scanner against a planted
canary before it reports anything clean.

The synthetic secrets under `corpus/context/` are bait. They are unique `CANARY_` strings, they
exist to be detected leaving the machine, and none of them is a real credential. That is stated in
the files themselves as well as here.

## Reporting something about this repository

Open an issue, or write to the address in [`CITATION.cff`](CITATION.cff). There is no private
channel and no bug bounty. If what you found is sensitive enough that a public issue is the wrong
first step, say so in one line without the detail and the detail can move elsewhere.

## Reporting something this repository found about YOUR project

This is the case that actually arises, and the process it follows is written down before it is
needed, in [`docs/PROTOCOL.md`](docs/PROTOCOL.md) rule 7 and
[`docs/DISCLOSURE-LOG.md`](docs/DISCLOSURE-LOG.md):

- A destination a server's documentation does not declare **stops the run**. Nothing that locates
  that server is published until the finding has been reported.
- Findings are reported as what they are. The two that exist were sent as **documentation gaps, not
  vulnerabilities**: no severity, no identifier, no deadline. A behaviour that is deliberate and
  documented in a project's own code is not a vulnerability because an agent now calls it.
- What was sent is kept verbatim in [`docs/disclosure/`](docs/disclosure/), so a maintainer can
  check what was said about them rather than reconstruct it.
- The log records **whether anyone answered**, including when nobody did. A log that recorded only
  answers would quietly overstate how often these reports are read.

If you maintain a project named in the disclosure log and something there is wrong, that is the
most useful issue this repository can receive, and it will be corrected in the log with the
correction visible rather than silently.
