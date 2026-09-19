# Paper outline. Sections and one line of intent each. NOT yet written.

Status: skeleton for review. Nothing below is drafted, and the order is the argument, so the
order is the thing to object to first.

**What the paper is.** A measurement of whether an autonomous agent's outbound traffic can be tied
to the tool call that caused it, and a negative result about the instrument everyone would reach
for first.

**What it is not.** A security paper, a benchmark of MCP servers, or a product announcement. No
server is named in any figure (gate rule 3); the two named findings are disclosed and dated.

---

## 1. Abstract

Intent: state the headline in the first two sentences (an environment-variable proxy observes the
subset of clients that opted in, not the agent), then the measured attribution figure and that it
is below its own pre-registered threshold.

## 2. Introduction: what an agent's egress is, and why nobody has the number

Intent: frame the question as provenance for autonomous agents with MCP as the first environment
rather than the category, and say plainly that the paper reports a failure to reach its own bar.

## 3. The headline: a terminating proxy does not observe a modern Node client

Intent: threat 19, whole, at the front. The chain (proxy selected by environment variables, Node's
global fetch ignoring them, Node 20 in the image where the switch did not exist), the fix, and the
evidence that it was a fix: one server from 0 to 17 flows, loopback SYNs up exactly +10.

Intent, second half: generalise it. Interception by environment variable is opt-in by the
observed, the opt-in set is not knowable in advance, and therefore transparent interception or
eBPF is a requirement rather than an engineering preference. This is the section a reader who
repeats this work needs before anything else.

## 4. Method

### 4.1 The four negatives and what they cost

Intent: never inject, never store content, never infer, never act, each with the capability it
gives up, so the design reads as chosen rather than as a limitation discovered late.

### 4.2 Two instruments, because there are two problems

Intent: number 4 keeps the exact k-gram for prose; number 5 moves to structural containment,
because a call's arguments are fields that reappear as path segments and query values. Include
the diagnosis that started it: 20 bytes invisible at k = 22 and 22 bytes visible.

### 4.3 Containment, discrimination, and the one-token floor

Intent: the rule in full, including that discrimination is a principle rather than a threshold,
with the measured reason: without it, nine of twenty flows grade as confident wrong attributions.

### 4.4 Pre-registration, and the falsified prediction still inside the seal

Intent: the apparatus (digest-sealed block, commit, push), then section 13's four reserved items,
led by the prediction that turned out false and was corrected outside the seal without touching
the original. State the weakness too: the seal was pushed after the measurement, so an external
clock witnesses the bundle and not the order within it, and the rule derived from it.

## 5. Results

### 5.1 The honesty curve

Intent: 0.8947 derived, 0.8095 blind, 0.6579 with all three egressing servers visible. Every
observability fix lowered the headline. Read it explicitly: a measurement whose headline improves
as its instrument improves is measuring the instrument, and this one did the opposite. Say that
the curve is not known to have stopped.

### 5.2 The attribution figure, and the threshold it does not meet

Intent: 0.6579 over 38 content-eligible flows against a threshold of 0.80 fixed before any of it
existed. Report the failure without softening, and publish all three denominators together with
the raw one marked non-comparable.

### 5.3 Where the missing attributions went

Intent: the decomposition, 6 one-token floor, 5 contained-but-not-discriminating, 2 never
contained, as the bridge into the product claim rather than as an excuse.

### 5.4 What content attribution is for: a claim about tool shape

Intent: the transferable result. Content attribution works on tools whose arguments carry
structure and not on free-text tools, under any rule that does not manufacture false strong
attributions, with both halves of the evidence and the measured price of relaxing the rule. Give
the reader the procedure to classify their own tool inventory without running anything.

### 5.5 The limit that is in the method, not the implementation

Intent: threat 18. A call whose tokens are a subset of a concurrent call's cannot be uniquely
attributed by containment, by anyone, and the commonest way to produce one is an agent re-reading
its own document with more precision.

## 6. Two findings about the environment, reported and disclosed

### 6.1 A tool call that installs and executes third-party code while it runs

Intent: threat 17, with the causal chain, the unpinned ranges without a lockfile, and the measured
drift between days as evidence of the instability rather than as a stale figure. Say it was
disclosed, when, and where, and that it is not framed as a vulnerability.

### 6.2 A server that egresses because of what it embeds

Intent: threat 15, briefly, as the case where a control run rather than a hostname established
the cause.

## 7. Threats to validity

Intent: not a list, a ranking. Instrument limits first (19, 6, 16), then sampling (5, 8), then
method (18, 11). The point to make: threats 5 and 8 were blamed for a gap that threat 19 actually
explained, and that misattribution is itself a result.

## 8. What would change the answer

Intent: the three things that would move the number, priced. Transparent interception or eBPF;
trace-context propagation, which attributes free-text calls exactly and which 0 of 3 observed
servers do; and a tool population whose argument-shape distribution is actually estimated, which
nothing here does.

## 9. Reproducibility

Intent: every figure's command, the committed aggregates, the two pinned corpora, and the honest
statement that pre-F2 runs are not re-gradable under the new matcher because adding a field to the
record makes every earlier run un-re-gradable. Name that as a general property of evidence systems
that evolve.

## 10. Conclusion

Intent: the instrument does not meet its bar on the structured-argument share of a real tool
surface, the product question is not answered and was deliberately never frozen, and the most
useful output is the method result at the front.

---

## Deliberately NOT sections

- The per-flow candidate variant (amendment A1): declared, predicted to fail, not measured.
- F3, the improbability-weighted floor (amendment A2): formulated after the failure, needs a third
  reserve, and cannot replace 0.6579.
- The response channel and the recursion: not opened.

## Open questions for you before drafting

1. Venue and length, which decides whether sections 4.1 to 4.4 are one section or four.
2. Whether section 3 stays first. It is the strongest result and it is also a negative result
   about our own instrument, which is an unusual thing to open with.
3. Whether the two disclosed findings (6.1, 6.2) are a section or an appendix. They are the most
   quotable material here and the least central to the argument.
