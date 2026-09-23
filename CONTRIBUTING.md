# Working on this repository

This is a measurement harness, not a product, so "contributing" mostly means changing a number or
changing what a number is allowed to say. Both are governed by the same rule: a figure without a
command that produces it does not ship (doctrine rule 6), and an instrument without a test that
fails when it is ABSENT does not ship either (gate rule 10). Read
[`docs/DOCTRINE.md`](docs/DOCTRINE.md) and [`docs/PROTOCOL.md`](docs/PROTOCOL.md) before the first
change.

## Set up

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"     # the measurement core is stdlib-only; dev adds pytest, ruff, mypy, coverage
```

Docker is needed only to take a NEW capture (`make run`, `make run-concurrent`, `make bench`,
`make control`). Every gate below runs offline.

## Run every gate the way CI runs it

```bash
make gates
```

That is the whole pipeline. **61 seconds** on the machine this was measured on, of which the
suite is 16 and `figures-check` is most of the rest, because it regenerates every calibration
artifact rather than inspecting it. Individually:

| Gate | Command | What it checks, and what it caught |
| --- | --- | --- |
| tests | `make verify` | the suite. Regressions of logic |
| claims-check | `make claims-check` | every figure in the README's six-number table against the committed aggregate of the pass that may publish it, and the k curve in `shingle.py`'s docstring against the artifact. **It caught the README publishing number 1 as `p95 1` from the concurrent pass, where the pass that may answer says `84`** |
| figures-check | `make figures-check` | regenerates every calibration artifact and both SVGs and fails on a non-empty `git diff`, or on an untracked figure. **It caught four figures that had stopped reproducing eight commits earlier**, 654 lines of difference, while a test that checked their SHAPE stayed green |
| corpus-check | `make corpus-check` | that the generated halves of the negative corpus were not hand-edited |
| prereg | `make f2 && make f2-reserved` | that the pre-registered F2 predictions still reproduce |
| reproduce | `make reproduce` | that the headline number still comes out of the committed example runs in a clean clone, with no Docker and no network |
| lint | `make lint` | `ruff`, configured in `pyproject.toml` |
| types | `make types` | `mypy --strict` over `src/mcpfanout` |
| cov | `make cov` | coverage floors: 85% on `src/mcpfanout`, 60% on `tools/` |

Two of these exit non-zero **as a result rather than as a failure**, and neither may be wrapped in
`|| true`: `make rarity`, whose non-zero exit is the measured verdict that rarity weighting did not
lower the false-positive rate, and `make control`, whose non-zero exit means the browser control did
NOT explain a flagged destination.

## The rules that will fail your change if you skip them

- **Never tune against the reserved half** of the negative corpus. `calibrate.load_negative`
  refuses it for a calibration purpose and tests fail if the refusal is bypassed. A reserve loaded
  once is spent.
- **Never re-tune `k` by hand.** It is the output of `calibrate.choose_k`, and the registry, the
  capture addon and `run.sh` all read the shipped constant rather than keeping copies. Four copies
  is how the addon ended up matching at a k no published figure described.
- **The measurement core stays standard-library only.** `shingle`, `redact`, `match`, `classify`,
  `record`, `aggregate`, `disclosure`, `control`, `calibrate`, `rarity`, `structure`, `demo` and
  `cli` may not gain a third-party dependency; `tests/test_core_has_no_dependencies.py` and a CI
  job that installs without the `capture` extra both enforce it. The capture layer may use the
  extra. This is why every registry file the core reads is JSON and not YAML.
- **Never commit a captured run.** Two REDACTED runs are committed and the difference is the whole
  point; see [`runs/README.md`](runs/README.md).
- **Never discard unstaged work.** `git checkout -- <path>` and `git restore <path>` are forbidden
  on unstaged work. To throw something away use `git stash push -m "<why>"`, which is recoverable.
  To mutate a file in order to prove a test bites, copy it outside the repository first, or
  `git add` it before mutating.
- **Editing a sealed block fails the suite**, by design. The pre-registered blocks in
  `docs/PROTOCOL.md` and `docs/PREREG-F2.md` are frozen by digest. A genuine re-registration is its
  own commit, landed BEFORE the run it predicts, with the reason in the message.

## Adding a number

1. Write the command first: a `make` target and, where it belongs there, an `aggregate`
   subcommand.
2. Write the test that goes red when the instrument is absent, and **watch it go red** before you
   make it green. A test written after the fix has never been observed to fail.
3. Publish the artifact under `docs/figures/` if the figure is quoted anywhere, and add it to
   `make figures-check` so it cannot go stale.
4. Quote it in prose only with the command beside it.

## Commit style

Imperative subject. Body explaining why and the trade-off, not just what. Commits are signed with
GPG, from `c6d4e64` onward; earlier commits are deliberately not re-signed, because back-signing
history replaces real provenance with manufactured provenance.

## Releasing, and the Zenodo order that is counter-intuitive

Zenodo mints a DOI when it DETECTS a release, so the integration is connected FIRST and the release
published SECOND. Connecting afterwards archives nothing retroactively.

1. Connect Zenodo to the repository in the GitHub settings. Nothing is minted by connecting.
2. Record the disclosure outcome in [`docs/DISCLOSURE-LOG.md`](docs/DISCLOSURE-LOG.md) BEFORE
   tagging: either the maintainers' responses, or `no response as of the publication date`. The
   absence of a reply is itself data, and the log is the procedure.
3. Tag, signed, and push it. `.github/workflows/release.yml` force-fetches the annotated tag
   object and checks it is one (a tag push leaves a LIGHTWEIGHT tag in the checkout, whatever the
   fetch depth), runs every gate, then derives the release notes from the **tag object** with
   `tools/release_notes.py`, publishes with `--notes-file`, and reads the published body back
   from the API to check it is the signed text.
   The job fails if it is not, and it fails on a tag whose annotation it cannot read at all. That
   check exists because the workflow used to pass `--notes-from-tag` under a depth-1 checkout and
   assert the result in a comment instead of checking it: the first release it published carried
   the COMMIT message as its notes, and the text was corrected by hand afterwards, which hides the
   defect from anyone reading the release page later (gate rule 10's ninth instance, with the
   timestamps). Zenodo mints the DOI on detection.
4. **Record both DOIs, in different places, because they answer different questions.** The VERSION
   DOI resolves to the exact deposit and goes in `CITATION.cff`, because a citation must point at
   what the reader actually read. The CONCEPT DOI always resolves to the latest version and goes in
   `README.md`, where drifting to the current version is the desired behaviour. Commit both as a
   follow-up: a DOI cannot be inside the artifact it names.

The current tag is whichever one
[releases/latest](https://github.com/marcosmatalab/mcp-fanout/releases/latest) resolves to, and
that link is the answer rather than a tag name written here, which would be right until the next
tag and wrong afterwards with nothing to notice.
`tests/test_no_stale_release_pointer.py` fails if a document names a pre-release as the current
one. `v1.0.0` is reserved for 19 October 2026, when the disclosure window closes, because minting
a DOI before that date would break a commitment made in writing.
