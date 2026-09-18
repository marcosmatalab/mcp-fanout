# Threats to validity

A measurement that does not state how it could be wrong is not a measurement. At least four,
gate rule 6. Each names the threat and what it does to the numbers.

1. **The corpus biases what is observed.** We drive a fixed set of tool calls. A server only
   egresses in response to what we call, so the fan-out we see is the fan-out of our corpus, not
   the server's full behavior. Mitigation: align each corpus to the server's real tools
   (tools/list) and exercise the egress-bearing tools; report the corpus SHA in the manifest so
   the input is pinned to the output.

2. **A sandbox run observes one execution, not the behavior.** Deadbugz served its malicious tool
   description only from the fourth request onward. A single pass can miss time-gated or
   count-gated behavior. Mitigation: repeat runs, vary order, and treat any number as "observed in
   these runs", never "always".

3. **A server that detects the sandbox does nothing.** A server that fingerprints the container,
   the proxy CA, or the absence of a real TTY can suppress its egress and look clean. This biases
   every number downward. It is unfixable in a sandbox and is stated, not hidden. eBPF SSL uprobes
   (docs/METHOD.md) reduce the proxy-detection surface but not the sandbox-detection surface.

4. **The most-installed do not represent the long tail.** Ten popular servers are curated,
   audited, and unrepresentative of the thousands of small servers where supply-chain risk
   concentrates. The numbers describe the head of the distribution. The tail is future work and is
   labeled as such.

5. **Absent credentials change behavior.** Servers that need a token are run without one and fail
   auth. A failed call may egress less (or differently) than a successful one. We measure the
   attempt, which is honest for destination and argument-forwarding, but the fan-out of a fully
   authenticated session can be larger. Stated.

6. **Proxy blind spots undercount fan-out.** The terminating proxy reads only HTTP(S) it can
   decrypt. Non-HTTP protocols and certificate-pinned clients bypass it, so numbers 1 and 2 are
   lower bounds. The pcap backstop records the connections the proxy missed; until reconciliation
   is implemented, treat the proxy fan-out as a floor.

7. **Sequential-driving attribution.** Number 5's ground truth relies on driving one call at a
   time, so exactly one call is active per server. This is correct for the measurement and is the
   point (it lets us measure content-match recall against ground truth), but it means the harness
   does not itself exercise the concurrent case that makes attribution hard in production. Number 5
   estimates how well content matching would do there; it does not reproduce there.
