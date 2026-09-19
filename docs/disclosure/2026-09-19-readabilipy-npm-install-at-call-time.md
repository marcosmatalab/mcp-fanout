# Draft: `npm install` runs inside a tool call, from unpinned ranges with no lockfile

Written for two sets of maintainers, kept here so the text that was sent is recoverable, per
`docs/DISCLOSURE-LOG.md`. See `docs/THREATS.md` threat 17 for the measurement this came from.

**Not a security report.** No severity, no identifier, no deadline, no CVE framing. The behaviour
is deliberate on ReadabiliPy's part and is documented as a fallback in its own code. What the
report adds is a context its authors did not have when they wrote it: the caller is now frequently
an autonomous agent, and the same behaviour has different consequences there.

**Two addressees, two different asks.** They are separated on purpose, because sending one text to
both would make each read as the other's problem.

1. `alan-turing-institute/ReadabiliPy`, where the install happens. The ask is a lockfile and an
   opt-out, and it is a supply-chain determinism question.
2. The `mcp-server-fetch` maintainers, who take the dependency. The ask is documentation and a
   deployment note, and it is an "installing at call time" question.

**Send before publishing.** Gate rule 7. Both projects are active and reachable, unlike the
archived server in the other disclosure.

---

## 1. To `alan-turing-institute/ReadabiliPy`

### Title

`npm install` runs at first use from unpinned ranges with no lockfile, so two runs can execute different code

### Body

Hello, and thanks for ReadabiliPy. The Node path is the reason the output quality is what it is,
and none of what follows suggests removing it.

While instrumenting where outbound traffic goes during automated pipelines, I traced a burst of
connections to the npm registry back to ReadabiliPy and would like to raise the determinism side
of it.

`simple_json.py` calls `have_node()` during extraction. When
`readabilipy/javascript/node_modules` is absent, that calls `run_npm_install()` in `utils.py`,
which runs:

```python
cp = subprocess.run(["npm", "install"], check=True)
```

The shipped `javascript/package.json` declares:

```json
"@mozilla/readability": ">=0.4.1",
"jsdom": ">=12.2.0",
"minimist": "^1.2.3"
```

There is no `package-lock.json` in the distribution. Two observations, both measured rather than
theoretical:

**1. The installed tree is not reproducible.** Open upper bounds with no lockfile mean the
resolved versions are whatever the registry serves at that moment. Measuring the same pinned
ReadabiliPy on two days a day apart, the install produced a different number of registry requests
each time (87, then 82 on two separate runs). Pinning ReadabiliPy therefore does not pin the
JavaScript it executes.

**2. The install output goes to stdout.** `subprocess.run` here does not capture output, so npm's
`added N packages, and audited N packages in Ns` reaches the parent's stdout. For a CLI that is
cosmetic. For a caller that uses stdout as a protocol channel, it corrupts the stream, which is
how I noticed this at all.

Three things that would each help, roughly in order of how much:

- Ship a `package-lock.json` and use `npm ci` instead of `npm install`, so the executed tree is
  the tested tree.
- Capture the subprocess output (`capture_output=True`) and log it, rather than letting it reach
  the parent's stdout.
- Offer an explicit opt-out, an environment variable or an argument, so an embedder can say "never
  install at runtime, fall back to the Python extractor" and get a deterministic deployment. Right
  now the only way to guarantee it is to pre-create `node_modules` or remove `npm` from PATH.

Happy to open a PR for any of these if that is useful, and happy to share the measurement method
if it is of interest.

---

## 2. To the `mcp-server-fetch` maintainers

### Title

Docs: `fetch` installs npm packages during a tool call, which is worth stating for deployments

### Body

Hello, and thanks for the server. This is a documentation and deployment note rather than a bug
report, and the behaviour originates in a dependency rather than in this code.

While measuring where MCP tool calls cause outbound traffic to go, I drove `mcp-server-fetch`
(pinned at `2026.8.18`, launched with `uvx`, inside a container behind a recording proxy) against
a corpus of URLs on a single reserved domain. On the first call that converts HTML, the server
opened a burst of connections to `registry.npmjs.org`: 82 requests on each of two runs, against 4
to the host the call actually named. The package caches were warmed before the proxy started, so
these are not the launcher's.

The cause is `readabilipy`, which runs `npm install` from inside the extraction path to fetch
`@mozilla/readability` and `jsdom`. I have raised the lockfile and stdout points with ReadabiliPy
separately.

The part that seems worth surfacing here is what it means for anyone deploying this server:

- A tool call reaches a second package registry that the tool's documentation does not mention.
  In a deployment where egress is allowlisted, the first `fetch` of HTML fails in a way that is
  hard to attribute, because the failure appears inside an unrelated-looking conversion step.
- The JavaScript executed is resolved at call time from unpinned ranges, so pinning
  `mcp-server-fetch` does not pin everything that runs. Two runs a day apart resolved different
  trees here.
- npm's output reaches stdout, which is this server's JSON-RPC channel.

Possible responses, in increasing order of effort, and entirely your call:

- A line in the README noting that HTML conversion may install npm packages on first use, and that
  `registry.npmjs.org` therefore belongs in an egress allowlist.
- Pre-creating `readabilipy`'s `node_modules` at image or install time, so nothing is fetched
  during a call.
- Passing through whatever opt-out ReadabiliPy adds, so operators who want the pure-Python
  extractor can ask for it.

I am writing up the measurement and would rather you saw this before it is published than after.
Nothing in the write-up frames either project as vulnerable; the finding is about tool calls that
install code while they run, of which this is the clearest example I found.

---

## What was actually sent

Not yet sent. Fill in the date, the URL and the response here when it is, and add the row to
`docs/DISCLOSURE-LOG.md`, which is what gate rule 7 checks.
