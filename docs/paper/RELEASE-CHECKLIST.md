# Release checklist. DO NOT publish before 2026-10-19.

**The date is a commitment, not a preference.** Both disclosure reports state a publication window
of about thirty days, around 2026-10-19 (`docs/DISCLOSURE-LOG.md`). Minting a DOI before that date
breaks the window we gave the maintainers, whatever the repository already contains publicly.

**Order matters, and it is counter-intuitive.** Zenodo mints a DOI when it DETECTS a release, so
the integration must be connected FIRST and the release published SECOND. Connecting afterwards
archives nothing retroactively.

## Before the date

- [x] Draft complete, all ten sections (`docs/paper/DRAFT.md`).
- [x] `CITATION.cff` at the repository root, pointing at the archived release rather than the
      default branch, because the argument depends on the sealed block and the signed history and
      only a tag fixes both.
- [x] Every figure in the draft checked against the committed artifacts under `docs/figures/`.
- [x] Commits signed from `a167a54` onward. Earlier commits are deliberately NOT re-signed:
      back-signing history replaces real provenance with manufactured provenance.
- [ ] Connect Zenodo to the repository (github.com settings, toggle on `marcosmatalab/mcp-fanout`).
      Nothing is minted by connecting.
- [x] Version decided: **`v1.0.0`**, no suffix. A pre-release suffix announces something
      provisional on its way to a version that does not exist, and this is not a draft. Semver
      alone already makes a later correction visible as one (`v1.0.1`). **Editorial status is not
      a property of the artifact**: "preprint" belongs in the release TITLE, not in the tag. If a
      venue later publishes it with changes, that is `v1.1.0` and the history reads itself.

## On or after 2026-10-19

- [ ] Record the disclosure outcome in `docs/DISCLOSURE-LOG.md` BEFORE tagging: either the
      maintainers' responses, or `no response as of the publication date`. The absence of a reply
      is itself data and the log is the procedure.
- [ ] `make verify` green, and the count in `CLAUDE.md` matching.
- [ ] Tag, signed: `git tag -s v1.0.0 -m "..."` and push the tag.
- [ ] Title the GitHub release with the editorial status, for example
      "v1.0.0 preprint". The tag stays clean.
- [ ] Publish the GitHub release from the tag. Zenodo mints the DOI on detection.
- [ ] **Record both DOIs, in different places, because they answer different questions.** Zenodo
      mints two: a VERSION DOI, which resolves to this exact deposit, and a CONCEPT DOI, which
      always resolves to the latest version.

      - The **version DOI** goes in `CITATION.cff`, because a citation must point at the object
        the person actually read. A citation that drifts to a later version is a citation to
        something the author never saw, and in a paper whose argument is provenance that is not a
        small inconsistency.
      - The **concept DOI** goes in `README.md`, because someone arriving through a link should
        land on the current version rather than on a frozen one.

      Then commit both as a follow-up. The DOI cannot be inside the artifact it names; that is the
      ordinary circularity and the follow-up commit is how it is resolved.

## What is deliberately not in the release

- The runs. They carry per-flow records and salted digests tied to specific components, so they
  are gitignored. The normalized aggregates are committed instead, which is what makes a figure
  re-derivable without shipping a run.
- The three matcher-variant scripts from the external review. They import a module under a
  different name and do not run as committed; `make f2` supersedes them.
- Any credential. `tests/test_credentials_never_persisted.py` fails if one reaches a tracked file
  or a produced artifact, and proves its own scanner against a planted canary first.

## If a maintainer replies between now and the date

Record it in the log, and decide then whether it changes section 6. A fix shipped upstream before
publication would be worth a sentence in 6.1 and would not change the measurement, which describes
the versions pinned in `registry/servers.yaml` on the date they were driven.
