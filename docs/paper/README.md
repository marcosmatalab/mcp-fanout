# The draft write-up

This branch is `main` plus this directory. The draft was taken out of `main` on 2026-09-22 and
kept here, for one reason: 10,540 words of half-written paper inside a code repository say
"unfinished" louder than they say "rigorous", and everything the draft argues is already in the
README, `docs/THREATS.md` and `docs/PREREG-F2.md`, in the form the commands can check.

| File | What it is |
| --- | --- |
| `DRAFT.md` | the write-up, ten sections, roughly 8,100 words |
| `OUTLINE.md` | the record of the structural decisions behind that shape, kept because the shape was argued rather than assumed |
| `RELEASE-CHECKLIST.md` | superseded. The part of it that was not a one-use document, the Zenodo ordering, is in `CONTRIBUTING.md` on `main` |

**Every figure in the draft must be checkable against `main`.** This branch tracks `main` so that
`make claims-check`, `make figures-check` and `make reproduce` run here too: a draft that quotes a
number the repository no longer produces is the exact defect those gates exist for, arriving in the
one place where nobody would look for it.

When it is finished it goes out as a PDF attached to the release, not as a file in `main`.
