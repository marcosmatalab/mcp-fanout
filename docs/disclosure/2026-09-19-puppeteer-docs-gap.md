# Draft: documentation gap, background traffic from a browser-embedding server

Written for the maintainers of the MCP reference server set. Kept here so the text that was sent
is recoverable, per `docs/DISCLOSURE-LOG.md`.

**Not a security report.** No severity, no identifier, no deadline, no security framing anywhere
in the text below. It reports one thing: the documentation describes the navigation a tool
performs and does not mention the traffic the embedded browser performs on its own, which matters
to anyone deploying the server where egress has to be accounted for.

**Where it can be filed, which is the open question.** `src/puppeteer` no longer exists in
`modelcontextprotocol/servers`; it lives in `modelcontextprotocol/servers-archived`, and that
repository is archived, so GitHub does not accept new issues on it. The text below is therefore
written for the active repository and raises the point as a convention for the reference set,
naming the archived server as the concrete case rather than as the addressee. Filing it against
the archived repository is not possible; filing it against the active one asks maintainers about a
pattern they still own even though they no longer ship this particular server.

---

## Title

Docs: tool descriptions for browser-embedding servers do not mention the browser's own background traffic

## Body

Hello, and thanks for the reference servers: having a set of them with real schemas is what made
the measurement below possible at all.

While measuring where MCP tool calls cause outbound traffic to go, I ran
`@modelcontextprotocol/server-puppeteer@2025.5.12` in a container behind a terminating proxy and
drove a single `puppeteer_navigate` call at one URL. Besides the requested navigation, the run
recorded connections to two destinations that the tool's description does not mention:
`clients2.google.com` and `accounts.google.com`.

These are the embedded Chromium's own background requests, not something the server asks for. I
checked rather than assumed: launching the same browser binary with the same flags through the
same proxy, with no MCP server in the process tree and the same navigation, reproduces both
destinations. Neither request carried any of the call's arguments.

So this is not a report about the server doing something unexpected with a user's data. It is a
documentation gap, and I think it is worth a line because of where these servers get deployed:

- `puppeteer_navigate` is documented as navigating to a URL. A reader reasonably concludes that
  the destinations a call produces are the URL they passed.
- Anyone deploying an MCP server in an environment where egress is reviewed (a regulated network,
  an allowlisted proxy, an air-gapped-ish build system) will size their allowlist from that
  reading, and the first background request will fail or will show up in an audit as unexplained.
- The property belongs to the class, not to this package: any MCP server that embeds a browser
  engine will carry the same background traffic, whoever writes it.

A sentence in the README or in the tool description, along the lines of "this server runs a full
browser; the browser makes its own background requests (update and connectivity checks) in
addition to the navigation you request", would close the gap.

I realise `src/puppeteer` has moved to the archived set, so this may be better framed as a
convention for any future server that embeds a browser engine rather than as a fix to that
package. Happy to send a PR against whichever document you think is the right home for it, or to
drop it if you would rather not document archived servers.

Measurement details, if useful: container-only, no real credentials, a single navigation to an
RFC 2606 reserved domain, three repetitions of the control. I am not publishing anything that
identifies a deployment, and I am happy to share the method.

Thanks again.
