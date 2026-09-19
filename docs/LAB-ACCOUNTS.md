# Lab accounts: what the capture needs, what it costs, what breaks without it

**Nothing here has been created.** This is the plan you asked for, to decide on. No account, no
token, no project and no workspace exists as a result of writing it.

**Why it blocks the next capture.** Threats 5 and 8: nine of ten servers ran with no credentials,
so the flows that carry real arguments to real destinations mostly do not exist, and a product
verdict drawn from that run would be a verdict about an unauthenticated sample stated as a verdict
about runtime provenance. `docs/PREREG-F2.md` section 8 refuses to freeze a product verdict for
exactly this reason. The instrument verdict does not need these accounts; the product one cannot
be reached without them.

## 0. Two of the four are not in the measured set at all

You named github, brave, slack and google-maps. `registry/servers.yaml` holds ten servers and
**slack and google-maps are not among them**. They appear in CLAUDE.md only as package versions
that resolve on npm. So for those two the account is the second problem, not the first:

| server | in registry | probe committed | corpus | so what is missing |
|---|---|---|---|---|
| github | yes | `registry/probes/github.json`, 26 tools | sequential + concurrent | a token |
| brave-search | yes | `registry/probes/brave-search.json`, 2 tools | sequential + concurrent | a key |
| slack | **no** | **none** | **none** | registry entry, probe, two corpora, declared destinations, AND a workspace plus a token |
| google-maps | **no** | **none** | **none** | the same, plus a billing-enabled cloud project |

Adding a server is roughly half a day each: probe it, write both corpora against the real schemas
(`tests/test_corpus_matches_probes.py` gates this), add declared destinations, pin the version.
That is before any account exists. Decide whether the marginal server is worth it, because the
argument for a bigger N is weaker than it looks: the thing being measured is fan-out per call, and
two well-credentialed servers driving real calls tell you more than four gagged ones.

## 1. GitHub

**What the corpus actually drives.** Every call in both corpora is READ-ONLY against public
repositories: `search_repositories`, `search_code`, `get_file_contents`, `list_commits`,
`list_issues`, `search_issues`, `search_users`. Nothing writes. The server exposes 26 tools
including `merge_pull_request` and `push_files`, and we drive none of them.

**Minimum permission: a token with NO scopes.** A classic personal access token with every
checkbox unticked authenticates and reads public data, which is all the corpus asks for. A
fine-grained token scoped to public repositories with read-only metadata is equivalent and is the
better choice because its capability is legible from the token page rather than from an absence of
ticks.

**Do not give it repository write, and do not use an account with private repositories.** A token
that can write is a token that a corpus bug can write with, against a live service, and our own
`create_issue` tool sits one line away in the same schema. An account with private repos also
makes `search_code` return material we may not store, which collides with negative 2.

**What breaks without it, measured rather than assumed.** In run `20260919T130847Z-concurrent`
github started fine and 4 of 17 calls failed, every one of them `search_code`, with
`Authentication Failed: Requires authentication`. GitHub's code search endpoint requires
authentication; the rest of the corpus works unauthenticated at 60 requests/hour. So without a
token we lose the code-search calls entirely and run the rest against a rate limit low enough that
a wave of 10 is a meaningful fraction of the hour's budget.

**Cost: 0 euros, about 10 minutes.**

**MEASURED AFTERWARDS, 2026-09-19, and it reverses the value of this account without reversing the
reasoning.** The token was minted, the capture was run (`20260919T193121Z-concurrent`), and it
worked: the four `search_code` authentication failures are gone and the only remaining error is a
query-syntax validation on `search_issues`, which is a corpus bug and not a credential one. And it
changed **nothing in any published number**, because this server's client is Node's global `fetch`
(undici), which ignores `HTTP(S)_PROXY`. `make backstop` on that run shows 10 outbound SYNs
straight to `140.82.121.5:443`, which is `api.github.com`, while `flows.jsonl` holds zero flows
for the server. See `docs/THREATS.md` threat 6.

So the honest accounting for this account: **the reasoning in this section was right and the
benefit was zero**, because the limit was never the credential. It was the instrument. Nothing was
wasted that mattered (0 euros, 10 minutes, and the token is scoped to nothing), and the run is
more informative for having been done, because it converted threat 6 from "one SYN, one server,
probably small" into a measured ten-connection hole with a working credential behind it.

**What would actually unlock this server**, and neither option is free: transparent interception
(a netfilter redirect inside the container, so a client that ignores the proxy is intercepted
anyway) or eBPF uprobes on the TLS library, which is the product-grade path `docs/METHOD.md`
already names. The first is a container-networking change of perhaps half a day and it makes the
capture layer differ from the one every published figure so far was measured with, which is a
reproducibility cost that has to be paid deliberately. **Do not credential another server whose
client ignores the proxy until one of those exists**: the result is a token in a lab and no
change in any number.

## 2. Brave Search

**What breaks without it is total.** The server exits before the handshake:
`Error: BRAVE_API_KEY environment variable is required`, and both driven calls die with
`EOFError: server closed stdout`. There is no partial measurement to be had.

**Minimum permission.** The key is the whole credential; Brave's API has no scope model. Use a key
minted for this and nothing else, so it can be revoked without collateral.

**CORRECTED 2026-09-19, and the correction reverses the recommendation.** An earlier version of
this section priced Brave at "0 euros, about 15 minutes" and treated the card-on-file step as a
formality. It is not a formality: **Brave's free plan requires a credit card**, checked against
their pricing page on 2026-09-19. That puts Brave in the same category as Google Maps, which this
document rejected for exactly that reason, and consistency requires rejecting it too. Recording
the date because this is a provider condition and providers change them; if the free tier stops
requiring a card, the decision is worth revisiting on the merits.

**Decision: not taken.** The argument that killed Google Maps applies unchanged. Attaching a
payment instrument to an automated lab is a different risk category from an API key, the exposure
is not bounded by our own volume, and Brave buys no new KIND of observation: it is an ordinary
HTTPS API like GitHub.

**What it costs us to skip it, stated so the loss is not hidden.** brave-search stays gagged, so
the measured set loses a server that would have reached a real third party. It also removes the
only server in the registry whose rate limit would have forced `max_concurrency: 1`, which is a
measurement we now do not get to make. Threat 8 already notes that brave-search is marked
deprecated upstream with its last release in 2024, so the server was the weakest candidate of the
four on independent grounds.

## 3. Slack

**Needs a workspace before it needs a token.** A free workspace created for this purpose is the
right container: the alternative, using a workspace with real colleagues in it, puts other
people's messages inside our capture, which negative 2 and the GDPR sentence in `DOCTRINE.md` both
make expensive.

**Minimum permission** depends on a corpus that does not exist yet. Written read-only it is a bot
token with `channels:history`, `channels:read` and `users:read` and nothing else. Do not grant
`chat:write` unless the corpus drives a post, and if it does, drive it into a channel created for
the purpose.

**What breaks without it: everything, and nothing, because it is not measured today.**

**Cost: 0 euros, about 1 hour for the workspace plus half a day for registry, probe and corpora.**

## 4. Google Maps

**The expensive one, and the only one with a real cost.** Google Maps Platform requires a Google
Cloud project with **billing enabled** and a card on file, even to use the monthly free credit.
That is a payment instrument attached to a lab that runs automated traffic, which is a different
risk category from the other three.

**Minimum permission.** An API key restricted two ways: to the specific APIs the corpus drives,
and by nothing else, since the container has no stable IP. An unrestricted Maps key that leaks is
billable by whoever finds it. If we do this, set a budget alert at a low figure on day one, before
the first call.

**Cost: 0 euros expected but NOT 0 euros guaranteed, about 1 hour plus half a day of repo work.**
It is the only account on this list that can generate an invoice, and that is the fact to decide
on rather than the setup time.

## 5. Terms of use: what to check, and what this document deliberately does not assert

This repository already has a rule for this. `registry/declared-destinations.json` says its
expectations are derived from committed schemas and are "NOT a quotation of upstream
documentation, and the file never pretends otherwise", because asserting what a document says
without having read it is what this project calls a plausible guess. The same standard applies
here, so what follows is the list of questions to put to each provider's current terms, not an
answer to them.

For each of the four, read the current terms and answer:

1. **Is automated access permitted at all, and under what identification?** Most API terms permit
   programmatic use by definition and restrict scraping of the human web surface. We only touch
   APIs, which is the favourable side of that line, and it should still be confirmed per provider.
2. **Is there a named rate limit, and is exceeding it a breach or just a 429?** This decides
   whether a wave of 10 is a technical inconvenience or a terms problem.
3. **May responses be stored, and for how long?** This is the one where our design helps: we store
   salted digests and counts, never content (negative 2), and the aggregate names no host. A term
   forbidding retention of results is one we already satisfy, and saying so precisely is stronger
   than claiming we are exempt.
4. **Does the provider forbid benchmarking or publishing measurements?** Some API terms restrict
   publishing performance comparisons. We publish fan-out and attributability, not quality or
   latency league tables, and gate rule 3 means the aggregate names no server. Check whether that
   distinction is enough under each provider's wording.
5. **Are lab or throwaway accounts permitted?** A term requiring accurate registration details is
   satisfied by a real account used for a stated purpose, and is not satisfied by a fictitious
   identity. Use your own identity on all four.

**My reading of the risk, stated as a judgement and not as a finding:** github and brave are
ordinary API consumption at trivial volume and are very unlikely to be contentious. Slack in a
workspace we own is equally unremarkable. Google Maps is the one where the terms interact with
billing, and it is also the one we least need.

## 6. Recommendation, as decided

**GitHub only.** Brave, Slack and Google Maps are all out, and two of the three for the same
reason: a free tier gated behind a credit card is a payment instrument attached to an automated
lab.

GitHub costs 0 euros and about 10 minutes, needs no repository work because it is already pinned,
probed and has both corpora, and converts the single most tool-rich server in the set from gagged
to reaching its real third party. It is also the only one of the four that authenticates with a
token carrying no scopes at all, which is the cleanest possible credential to put in a lab.

Slack and google-maps each cost half a day of repository work before an account helps at all, and
google-maps additionally attaches a payment instrument to an automated lab. Neither buys a new
KIND of observation: both are ordinary HTTPS APIs like github and brave. If the paper needs a
larger N later, they are the obvious next two, in that order, and google-maps last.

**What the next capture is.** One concurrent pass with github credentialed and everything else
unchanged, including brave-search left uncredentialed and failing at launch, which is recorded as
a measured fact rather than hidden. That run produces number 5 from persisted structural
fields rather than derived from the corpus, which is what closes threat 16 properly, and it does
it on a set where two servers can actually reach their destinations.

## 7. What this does not solve

Threat 8's other half. Three of the ten servers are abandoned upstream and one, brave-search, is
marked deprecated on the registry with its last release in 2024. Credentials do not make an
abandoned server representative of anything, and no account on this list changes that. The set is
what it is, and the write-up says so.
