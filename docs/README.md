# What is in docs/

Seven documents. This page exists so a reader picks one instead of opening all of them, and it
says how long each is, because "read the docs" is not an answer when there are forty thousand words
of them.

| Document | Read it for | Size |
| --- | --- | --- |
| [`METHOD.md`](METHOD.md) | how the observation works, what each of the six numbers is, and what the eventual product would be. The one to read first after the README | 3,700 words |
| [`PROTOCOL.md`](PROTOCOL.md) | part 1 is the ten gate rules, and it is their single source; parts 2 and 3 are the three phases, the two phase B passes with their measured results, the sealed predictions, and when to stop | 6,600 words |
| [`THREATS.md`](THREATS.md) | nineteen ways the measurement could be wrong, each with what it does to the numbers. **Threat 19 is the headline result** and threat 17 is second | 6,700 words |
| [`PREREG-F2.md`](PREREG-F2.md) | what was predicted before the structural matcher existed, frozen by digest, including the prediction that turned out false | 6,900 words |
| [`CALIBRATION.md`](CALIBRATION.md) | how the matcher was calibrated on language that shares structure and no information, and what the chosen k cost | 4,200 words |
| [`DOCTRINE.md`](DOCTRINE.md) | the four negatives, and it is their single source; the line between decomposing structure and inferring meaning; the evidence model and its six attribution grades | 1,500 words |
| [`DISCLOSURE-LOG.md`](DISCLOSURE-LOG.md) | what was reported to which maintainer, when, in what words, and whether they answered | 1,200 words |

Plus [`disclosure/`](disclosure/), the text of what was actually sent, and
[`figures/`](figures/), every committed aggregate and the two generated SVGs.

**If you have five minutes**, read threat 19 and the honesty curve in the README. Everything else
is the apparatus that makes those two checkable.

**If you are repeating this work**, read `PROTOCOL.md` first: the order in which things may be
measured is a gate, not a preference, and gate rule 8 is the one that invalidates a result obtained
in the wrong order.

## The word budget, declared rather than chased

Across every tracked markdown file in this repository, **29,770 words** of findings and
**12,358 words** of operation, plus 30 words of corpus material that is
measurement input rather than prose about it. `make words` prints both figures and
`tools/word_budget.py` decides, file by file and by section for the one document that is both,
which side of the line each belongs on.

**Findings** are what was measured, predicted, disclosed or captured, plus the method and the
corpora the numbers are read through: `METHOD`, `THREATS`, `PREREG-F2`, `CALIBRATION`,
`DISCLOSURE-LOG`, parts 2 and 3 of `PROTOCOL`, the disclosure texts, `runs/README.md` and the
corpus notes. **Operation** is how to work here and how the work presents itself: the front page,
`CLAUDE.md`, `CONTRIBUTING.md`, `SECURITY.md`, this index, `DOCTRINE.md`, and part 1 of `PROTOCOL`.

**Why a declared split and not a target total.** A word count is trivially reachable by deleting
the longest documents, and the longest documents here are the evidence: the threats, the sealed
pre-registration and the calibration record. Cutting them would improve the number and destroy the
thing the number is supposed to indicate. So the figure is published, split, and gated:
`tests/test_word_budget.py` fails when the two numbers above stop matching what `make words`
measures, and it fails when a tracked document is not classified at all, because an unclassified
file would let the published budget describe a set of files the repository does not have. What the
split is allowed to do is move: operation shrank when the four negatives and the ten gate rules
stopped being written two and a half times, and findings is the bucket that may grow.
