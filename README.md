# Cyber Security Prep

A self-hosted practice-test site. Questions are written as Markdown files in
this repository; a GitHub Actions workflow compiles them, validates them and
publishes the site to GitHub Pages on every push to `main`.

Pick a test, set a timer, answer the questions, submit, then review every
question with the correct answer and an explanation.

- **No backend.** Plain HTML, CSS and JavaScript. Nothing is sent anywhere.
- **No build tools to install.** The compiler is a single Python script that
  uses only the standard library.
- **Adding a test means adding one Markdown file.** The site picks it up
  automatically.

---

## Contents

- [Using the site](#using-the-site)
- [Adding a question set](#adding-a-question-set)
- [Running it locally](#running-it-locally)
- [How it fits together](#how-it-fits-together)
- [First-time setup](#first-time-setup)
- [What the build checks](#what-the-build-checks)

---

## Using the site

**Choosing a test.** Every test in `tests/` appears on the home page with its
question count, recommended time and pass mark. Your best score for each test
shows on its card once you have attempted it.

**Timer.** Three choices under *Test options*:

| Mode | Behaviour |
|---|---|
| Recommended | Uses the limit the test itself declares. |
| Custom | Any number of minutes you set. |
| No timer | Untimed. |

When a timer reaches zero the test submits itself automatically and the results
say so.

**Order.** Questions and options both run in written order by default. Two
independent switches shuffle either or both. Worth turning on for a retake, so
you are recalling the material rather than the position of the right answer.

**Taking the test.** One question at a time, with previous and next buttons and
a question map showing which are answered and which are flagged. Clicking your
selected option again clears it, so a guess can be withdrawn. Keyboard
shortcuts: `A`-`D` or `1`-`9` to answer, arrow keys to move, `F` to flag.

**Answers stay hidden until you submit.** Nothing is revealed mid-test.

**Results.** Score, pass or fail against the test's own mark, time taken, a
per-section breakdown, and a full review. Filter the review to incorrect,
correct, flagged or unanswered. Each question shows your answer, the correct
answer, and the explanation where one is provided.

**Progress is saved as you go.** Close the tab mid-test and the home page
offers to resume. Attempt history is kept in the browser. Both live in
`localStorage`, so they are per-browser and per-device, and clearing site data
clears them.

**Printable paper.** Every test card links a generated Markdown document holding
the full paper followed by the answer key and explanations, for printing,
sharing or working offline. The build writes it, so it can never drift out of
step with what the site serves.

---

## Adding a question set

1. Copy `tests/TEMPLATE.md.example` to `tests/<topic>/<name>.md`.
2. Fill in the frontmatter and write the questions.
3. Commit and push to `main`.

The workflow compiles, validates and republishes. The new test appears on the
home page by itself; there is no index to update.

If an AI agent is writing the questions, point it at **[AGENTS.md](AGENTS.md)**,
which specifies the format, the rules the build enforces, and how to add to an
existing set without rewriting it.

**Large or growing sets can be split across files.** A folder containing a
`test.md` is treated as one test, with every other `.md` file in it appended in
filename order:

```
tests/secplus/sy0-701-1.2/
    test.md        frontmatter, and optionally the first questions
    part-02.md     questions only
    part-03.md     questions only
```

Only `test.md` carries frontmatter. Sections carry across files and questions are
numbered by final merged order. This matters when the author can only replace
whole files rather than patch them: adding ten questions becomes a new small
file instead of a rewrite of a large one.

The format in full:

```markdown
---
id: secplus-1-2
title: CIA Triad and AAA
objective: CompTIA Security+ SY0-701, Objective 1.2
description: Thirty items on confidentiality, integrity, availability and AAA.
time: 40
pass: 80
---

## Section name

### Q1
Which principle ensures information is not disclosed to unauthorized parties?

- A. Integrity
- B. Confidentiality
- C. Availability
- D. Non-repudiation

Answer: B
Explain: Confidentiality is about disclosure. Integrity concerns unauthorized
modification, which is the option most often confused with it.
```

That is the whole format. `## ` starts a section, `### ` starts a question,
`- A. ` lists an option, `Answer:` marks the correct one, and `Explain:` is
optional prose that runs until the next question.

Before pushing, check your work:

```bash
python3 tools/build.py --strict
```

---

## Running it locally

```bash
python3 tools/build.py        # compile tests/ into dist/
cd dist && python3 -m http.server
```

Then open <http://localhost:8000>.

Use a server rather than opening `dist/index.html` directly. Browsers block
`fetch()` on `file://` URLs, so the question data will not load from a
double-clicked file. The site says as much if it detects the problem.

Optional checks:

```bash
python3 tools/selftest.py     # validator and answer-key checks
python3 tools/servecheck.py   # confirm every asset serves
```

---

## How it fits together

```
AGENTS.md              Authoring spec, for AI agents writing question sets.
tests/**/*.md          Question sets. The only files you normally edit.
site/                  index.html, app.js, style.css
tools/build.py         Markdown to JSON compiler and validator
tools/paper.py         Renders the printable paper and answer key
tools/selftest.py      Tests the compiler and the validator
tools/servecheck.py    Serves dist/ and fetches every asset
.github/workflows/     Compile, validate, publish
dist/                  Generated. Not committed. Never edit by hand.
```

The compiler writes three things per test into `dist/`: `data/<id>.json` for the
app, `papers/<id>.md` for reading and printing, and an entry in
`data/manifest.json`. The browser reads the manifest to build the picker and
fetches one test's JSON when you start it.

Markdown is the authoring format and JSON is the delivery format because each is
good at a different job, and because of how the files get written. JSON demands
escaping inside long explanations and correct brace and comma placement across
every question, so one slip invalidates the whole file and the parse error points
somewhere other than the mistake. In Markdown a slip damages one question, and
the validator names it by file and line. That matters most when a question set is
written by an AI agent through an API that replaces whole files rather than
patching them. See [AGENTS.md](AGENTS.md).

---

## First-time setup

GitHub Pages has to be switched on once, by hand, by someone with admin rights
on the repository. Until it is, the build runs and passes but the deploy step
fails.

1. **Settings** then **Pages**
2. Under **Build and deployment**, set **Source** to **GitHub Actions**

That is all. Every later push to `main` builds and publishes automatically; there
is no button to press. If Pages was switched on after the first push, the next
push republishes, or you can use **Actions** then **Build and deploy** then
**Run workflow** to publish without changing anything.

The site URL appears on the Pages settings screen and on the completed workflow
run.

Note that this repository's contents, including the answer keys, are readable
by anyone if the repository is public. That is fine for self-study material.
Keep anything you would not want public out of `tests/`.

---

## What the build checks

The workflow runs the compiler with `--strict`, so the site is only ever
published from question sets that pass every check. A build fails if:

1. An `Answer:` letter is not among that question's options. This is the check
   that matters most: a mistyped letter silently teaches the wrong fact and is
   invisible on reading.
2. A question has fewer than two options, an empty option, or no stem.
3. A question has no `Answer:` line, or more than one.
4. A question lists the same option letter twice.
5. Two tests share an `id`.
6. Frontmatter is missing, unclosed, or has no `id` or `title`.
7. A part file of a split test carries frontmatter.
8. The answer key is lopsided: more than 40% of answers on one letter across
   twelve or more questions, or a letter that is never correct across twenty
   or more. Both let a candidate score by guessing position rather than
   knowing the material, which makes the test worthless as practice.

Every failure names the file, the line and the question.
