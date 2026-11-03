# Authoring question sets (for AI agents)

Read this before adding or editing anything under `tests/`. It is written for an
AI agent working through a GitHub API that can only **replace whole files**, not
patch them.

## The format is Markdown, and that is deliberate

Question sets are Markdown. The site consumes JSON, but that JSON is **generated**
by `tools/build.py`. Never write JSON by hand and never edit anything in `dist/`.

Markdown is used because of how an agent writes files, not because of how a human
reads them:

- **No escaping.** Explanations contain quotes, apostrophes and backslashes.
  In JSON every one of those is an escape you can get wrong.
- **No structural nesting.** A JSON set is 60 nested objects held together by
  brace and comma placement. One stray comma invalidates the entire file and the
  parse error can point hundreds of lines away from the real mistake.
- **Damage stays local.** A malformed Markdown question breaks that question, and
  the validator names it by file and line. A malformed JSON file breaks everything.

So: the cost of a small slip is one question, not one test.

## Write a NEW file. Do not rewrite a large one.

This is the most important rule here.

Rewriting a 25 KB file to append ten questions means re-emitting every byte you
are not changing, and any drift silently corrupts questions that were already
correct. Avoid that entirely:

- **A new question set** is a new file. No existing file is touched.
- **Adding questions to an existing set** uses the split form below, so the new
  questions go in a new file and the existing file is left alone.

Only rewrite an existing file when you are genuinely correcting its contents, and
verify the result afterwards.

## Two layouts

**Single file** — the normal case for a new set:

```
tests/secplus/sy0-701-1.2-cia-triad.md
```

**Split folder** — use when a set is large, or when adding to an existing set:

```
tests/secplus/sy0-701-1.2/
    test.md        frontmatter, and optionally the first questions
    part-02.md     questions only
    part-03.md     questions only
```

A folder containing `test.md` is treated as **one test**. Every other `.md` file
in it is appended in filename order. Only `test.md` may carry frontmatter;
putting frontmatter in a part file is an error. Sections carry across files, so a
`## ` heading in `test.md` still applies to questions in `part-02.md` until a new
heading replaces it. Questions are numbered by final merged order, so you never
have to track numbering across files.

Prefer parts of roughly 10 to 20 questions.

## Format specification

````markdown
---
id: secplus-sy0701-1-2
title: CIA Triad and AAA
objective: CompTIA Security+ SY0-701, Objective 1.2
description: Thirty items on confidentiality, integrity, availability and AAA.
source: Course notes chapter 4
time: 40
pass: 80
---

## Section name

### Q1
The question stem. May span several lines and use **bold**, *italic*, `code`.

- A. First option
- B. Second option
- C. Third option
- D. Fourth option

Answer: B
Explain: Why B is right, and why the most tempting wrong option is wrong.
May run to several paragraphs; it ends at the next question.
````

| Field | Required | Meaning |
|---|---|---|
| `id` | yes | Unique across all tests. Becomes a filename, so letters, digits, `.`, `-`, `_` only. |
| `title` | yes | Shown on the test card. |
| `objective` | no | Objective or topic line. |
| `description` | no | One sentence on the card. |
| `source` | no | Provenance. Not displayed. |
| `time` | no | Minutes for the "Recommended" timer. Omit for none. |
| `pass` | no | Pass mark percentage. Omit to score without a verdict. |

Structure: `## ` starts a section, `### ` starts a question, `- A. ` is an option,
`Answer: X` marks the correct one, `Explain:` is optional prose.

Two or more sections produce a per-section breakdown on the results screen, which
is what turns a score into a study plan. Use them.

## Hard rules the build enforces

The workflow runs `python3 tools/build.py --strict`. If any of these is true the
build fails and **nothing is published**:

1. An `Answer:` letter is not among that question's options. This is the one that
   matters most: it silently teaches the wrong fact and is invisible on reading.
2. A question has fewer than two options, an empty option, or no stem.
3. A question has no `Answer:` line, or more than one.
4. A question lists the same option letter twice.
5. Two tests share an `id`.
6. Frontmatter is missing, unclosed, or has no `id` or `title`.
7. A part file carries frontmatter.
8. **The answer key is lopsided**: more than 40% of answers on one letter across
   twelve or more questions, or a letter that is never correct across twenty or
   more questions.

### On rule 8

Check it before you push. A model writing multiple choice has a strong tendency to
put the correct answer in the same position repeatedly, usually B or C. When that
happens the test stops measuring knowledge and starts measuring whether the
candidate noticed the pattern.

This is not hypothetical. The first draft of the 60-item set in this repository
had every single correct answer on B or C, with no D at all. "Never pick D" would
have scored well on it. Rule 8 exists because of that draft.

After writing a set, count the answers per letter and reorder options until the
spread is roughly even. Reorder the **options**, never change which answer is
correct to hit a quota.

## Writing good items

- One defensible answer. If two options are arguably correct, the stem must make
  the intended one clear, usually with BEST, MOST or PRIMARY.
- Distractors should be plausible and wrong for a nameable reason. An option
  nobody would pick is a wasted option.
- Keep options similar in length. An answer noticeably longer than the rest is a
  giveaway.
- Avoid "all of the above" and "none of the above".
- Explanations should say why the right answer is right **and** why the most
  tempting wrong one is wrong. That contrast is where the learning is.
- If the source material is ambiguous on a point, say so in the explanation
  rather than inventing a ruling. A candidate who picked the other reading
  deserves to know the source is unclear, not to be told they were wrong.

## Before you finish

Run the build. It is dependency-free, so no setup is needed:

```bash
python3 tools/build.py --strict
```

Read its summary line, which prints the answer spread:

```
ok  secplus-sy0701-1-1  60 questions  [A:15 B:15 C:15 D:15]
```

If you cannot run it, state plainly that the set is unverified. Do not claim a
set is correct on the basis of having written it carefully.

Optional deeper checks:

```bash
python3 tools/selftest.py     # compiler and validator behaviour
python3 tools/servecheck.py   # every published asset resolves
```

## What you must not touch

- `dist/` is generated output. It is gitignored and rebuilt on every push.
- `site/` is the application. Changing it is a separate task from authoring
  questions.
- `tools/` is the compiler. If a question set will not build, fix the question
  set, not the validator. The validator exists to catch exactly these mistakes,
  and loosening it to make a bad set pass defeats the point.
