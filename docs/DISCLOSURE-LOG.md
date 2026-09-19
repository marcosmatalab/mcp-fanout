# Disclosure log

Gate rule 7 (`docs/THE-GATE.md`) says that a destination a server's documentation does not declare
is a stop: nothing that locates that server is published until the finding has been raised with
whoever can act on it. This file is the record of those raisings, with dates, so "we told them" is
a fact with a timestamp rather than a recollection.

**It is also the authorisation trail.** Naming an instance in a committed artifact is refused by
`mcpfanout.control.publishable` without an authorisation string, and the string points here. So a
file under `docs/figures/control/` that names a server can always be traced back to an entry
below, and an entry below can always be traced back to what was actually sent.

**What this log is not.** It is not a vulnerability disclosure process and none of the entries
below is a vulnerability. This project measures where tool calls cause traffic to go. Where the
answer is surprising, the surprise is usually a documentation gap, and that is what gets raised,
in those words, with no severity, no identifier and no deadline. A finding that did turn out to be
a vulnerability would leave this file and follow a coordinated process instead.

---

## 2026-09-19, browser-embedded background egress

**Observed.** In the sequential phase B pass (run `20260919T115452Z-sequential`), the
`@modelcontextprotocol/server-puppeteer` server reached two destinations during a single
`puppeteer_navigate` call that its documentation does not mention:
`clients2.google.com` (GET) and `accounts.google.com` (POST). A third,
`www.gstatic.com`, appeared in an earlier capture of the same server and not in this one.

**Measured, not reasoned.** A control run launched the same browser binary with the same flags
through the same proxy, with no MCP server in the process tree, navigating to the same URL. See
the entry's command and verdict in `docs/figures/control/`, and threat 15 in `docs/THREATS.md`.

**Content.** Neither flow carried any of the corpus's k-grams, at the k the matcher is calibrated
to. The POST body was 1 byte. This is background traffic, not the phenomenon the six numbers
measure.

**Raised.** An issue was opened with the maintainers of the reference server set, phrased as a
documentation gap and not as a security report: the tool's description says it navigates to the
URL it is given, and does not mention the background traffic an embedded browser carries with it,
which is material for anyone deploying it in a regulated environment. No severity, no identifier,
no deadline. Draft text kept at `docs/disclosure/2026-09-19-puppeteer-docs-gap.md`.

**Authorisation to name the instance.** Marcos Mata, 2026-09-19. The finding is published as class
AND instance together with the cause in the same sentence, per threat 15: naming only the class is
unverifiable, and naming only the package accuses a maintainer of something the maintainer did not
write.

**Status.** Raised 2026-09-19. No response yet.
