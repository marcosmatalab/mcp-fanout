# Disclosure log

Gate rule 7 (`docs/PROTOCOL.md`) says that a destination a server's documentation does not declare
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

**Raised: 2026-09-19, https://github.com/modelcontextprotocol/servers/issues/4829.** Phrased as a
documentation gap and not as a security report: the tool's description says it navigates to the
URL it is given, and does not mention the background traffic an embedded browser carries with it,
which is material for anyone deploying it in a regulated environment. No severity, no identifier,
no deadline. Text as sent: `docs/disclosure/2026-09-19-puppeteer-docs-gap.md`.

**Where it was filed, and why not where the code is.** `src/puppeteer` is no longer in
`modelcontextprotocol/servers`; it is in `modelcontextprotocol/servers-archived`, which is
archived, and GitHub does not accept new issues on an archived repository. So the issue went to
the active repository, raising the point as a convention for any server that embeds a browser
engine and naming the archived package as the concrete case rather than as the addressee. The
alternative, filing nothing, would have left this entry without the date gate rule 7 exists to be
able to show.

**Authorisation to name the instance.** Marcos Mata, 2026-09-19. The finding is published as class
AND instance together with the cause in the same sentence, per threat 15: naming only the class is
unverifiable, and naming only the package accuses a maintainer of something the maintainer did not
write.

**Status.** Raised 2026-09-19 as issue 4829. No response yet.

---

## 2026-09-19, a tool call that installs and executes third-party code while it runs

**Observed.** Driving `mcp-server-fetch@2026.8.18` under capture, the server opened 82
connections to `registry.npmjs.org` while serving tool calls that named a single reserved domain,
against 4 to the host the calls actually asked for. Package caches are warmed before the proxy
starts, so these are not the harness's. Runs `20260919T115452Z-sequential` and
`20260919T130847Z-concurrent`.

**Measured, not reasoned.** The chain was read out of the installed package, not inferred from a
hostname: `mcp-server-fetch` depends on `readabilipy`, whose `simple_json.py` calls `have_node()`
during HTML conversion, which calls `run_npm_install()` in `utils.py`, which runs
`subprocess.run(["npm", "install"], check=True)` against a shipped `package.json` with no lockfile
and three unpinned ranges. Full chain and the command to reproduce it: `docs/THREATS.md`
threat 17.

**Why it was raised.** Gate rule 7: `registry.npmjs.org` is a destination the tool's own
documentation does not declare. Beyond that, the code executed is resolved at call time, so the
same pinned server runs different JavaScript on different days. The measured drift is the
evidence: 87 connections on 2026-09-18, 82 on each of two runs on 2026-09-19.

**Raised 2026-09-19**, as two issues rather than one, because there are two different asks and a
single text would let each maintainer read it as the other's problem:

| addressee | ask | issue |
|---|---|---|
| `alan-turing-institute/ReadabiliPy` | ship a lockfile and use `npm ci`, capture the subprocess output so npm does not write to the parent's stdout, offer an opt-out | https://github.com/alan-turing-institute/ReadabiliPy/issues/122 |
| `modelcontextprotocol/servers` | document that HTML conversion may install npm packages on first use, and what that means for an egress allowlist | https://github.com/modelcontextprotocol/servers/issues/4830 |

Not a vulnerability report. No severity, no identifier, no security framing. The behaviour is
deliberate on ReadabiliPy's part and documented as a fallback in its own code; what the report
adds is that the caller is now often an autonomous agent, where the same behaviour has different
consequences. Text as sent:
`docs/disclosure/2026-09-19-readabilipy-npm-install-at-call-time.md`.

**This entry carries a publication window and previous entries do not.** About 30 days, around
2026-10-19, stated in both texts as a note about our own timing and explicitly not as a deadline
for anyone to fix anything. The reason for the departure: the write-up names the mechanism in
full, and giving maintainers a date in advance is better than letting them find out from the
paper. It does not make this a vulnerability process and nothing is embargoed.

**Not yet answered, as of 2026-09-19.** Responses are recorded in the draft file as they
arrive. If the publication date arrives with no reply, that is recorded here as
`no response as of the publication date` and publication proceeds: the window was a courtesy
notice of our own timing and never a condition either maintainer accepted or owed us. The absence
of a reply is also data, and a log that only records answers would quietly overstate how often
these reports are read.

## Status of the three issues, checked rather than assumed

Each check is a read of the issue's own state through GitHub's API, recorded with its date. The
plural matters: a log that records only answers would quietly overstate how often these reports are
read, so "open, no reply" is written down the same way a reply would be.

| checked | issue | state | maintainer response |
| --- | --- | --- | --- |
| 2026-09-22 | `alan-turing-institute/ReadabiliPy#122` | open | none |
| 2026-09-22 | `modelcontextprotocol/servers#4829` | open | none |
| 2026-09-22 | `modelcontextprotocol/servers#4830` | open | none |

The next check is due on **2026-10-19**, when the publication window closes. Whatever it finds,
including nothing, is recorded here before `v1.0.0` is tagged.
