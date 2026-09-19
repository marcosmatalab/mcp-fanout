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
- [ ] Decide the version string. Suggested `v1.0.0-preprint`, so later corrections are visibly
      corrections rather than silent replacements.

## On or after 2026-10-19

- [ ] Record the disclosure outcome in `docs/DISCLOSURE-LOG.md` BEFORE tagging: either the
      maintainers' responses, or `no response as of the publication date`. The absence of a reply
      is itself data and the log is the procedure.
- [ ] `make verify` green, and the count in `CLAUDE.md` matching.
- [ ] Tag, signed: `git tag -s v1.0.0-preprint -m "..."` and push the tag.
- [ ] Publish the GitHub release from the tag. Zenodo mints the DOI on detection.
- [ ] Put the DOI into `CITATION.cff` and into the draft's header, then commit that as a
      follow-up. The DOI cannot be in the artifact it names; this is the ordinary circularity and
      the follow-up commit is how it is resolved.

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
