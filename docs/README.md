# What is in docs/

Seven documents. This page exists so a reader picks one instead of opening all of them, and it
says how long each is, because "read the docs" is not an answer when there are forty thousand words
of them.

| Document | Read it for | Size |
| --- | --- | --- |
| [`METHOD.md`](METHOD.md) | how the observation works and what each of the six numbers is. The one to read first after the README | 3,400 words |
| [`PROTOCOL.md`](PROTOCOL.md) | the ten gate rules, the three phases, the two phase B passes and their measured results, and when to stop. Contains the sealed phase B predictions | 5,800 words |
| [`THREATS.md`](THREATS.md) | nineteen ways the measurement could be wrong, each with what it does to the numbers. **Threat 19 is the headline result** and threat 17 is second | 6,700 words |
| [`PREREG-F2.md`](PREREG-F2.md) | what was predicted before the structural matcher existed, frozen by digest, including the prediction that turned out false | 6,800 words |
| [`CALIBRATION.md`](CALIBRATION.md) | how the matcher was calibrated on language that shares structure and no information, and what the chosen k cost | 4,200 words |
| [`DOCTRINE.md`](DOCTRINE.md) | the four negatives, the line between decomposing structure and inferring meaning, and why a digest of a short token is obfuscation rather than control | 1,400 words |
| [`DISCLOSURE-LOG.md`](DISCLOSURE-LOG.md) | what was reported to which maintainer, when, in what words, and whether they answered | 1,200 words |

Plus [`disclosure/`](disclosure/), the text of what was actually sent, and
[`figures/`](figures/), every committed aggregate and the two generated SVGs.

**If you have five minutes**, read threat 19 and the honesty curve in the README. Everything else
is the apparatus that makes those two checkable.

**If you are repeating this work**, read `PROTOCOL.md` first: the order in which things may be
measured is a gate, not a preference, and gate rule 8 is the one that invalidates a result obtained
in the wrong order.
