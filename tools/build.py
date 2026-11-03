#!/usr/bin/env python3
"""
Compile Markdown test files into the JSON the site consumes, and validate them.

Usage:
    python3 tools/build.py            # build into dist/
    python3 tools/build.py --strict   # build, but exit 1 on any warning

Reads  : tests/**/*.md
Writes : dist/  (site files + data/manifest.json + data/<id>.json + papers/<id>.md)

Dependency-free on purpose: Python 3 standard library only, so the build never
breaks because of a package update.
"""

import argparse
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paper  # noqa: E402  (local module, sits beside this file)

ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = ROOT / "tests"
SITE_DIR = ROOT / "site"
DIST_DIR = ROOT / "dist"

OPTION_RE = re.compile(r"^\s*-\s*([A-Za-z])[.)]\s+(.*)$")
ANSWER_RE = re.compile(r"^\s*Answer\s*:\s*([A-Za-z])\s*$")
EXPLAIN_RE = re.compile(r"^\s*Explain\s*:\s*(.*)$")

# A test with at least this many questions gets its answer spread checked.
BALANCE_MIN_QUESTIONS = 12
# Warn if any single option letter holds more than this share of the answers.
BALANCE_MAX_SHARE = 0.40


class TestError(Exception):
    """A defect that must stop the build."""


def parse_frontmatter(text, path):
    """Pull the leading --- key: value --- block off the top of the file."""
    if not text.startswith("---"):
        raise TestError(f"{path.name}: file must open with a --- frontmatter block")
    end = text.find("\n---", 3)
    if end == -1:
        raise TestError(f"{path.name}: frontmatter block is never closed with ---")
    raw = text[3:end].strip()
    body = text[end + 4:]
    meta = {}
    for offset, line in enumerate(raw.splitlines(), start=2):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise TestError(
                f"{path.name} line {offset}: frontmatter needs 'key: value', got {line!r}")
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip()
    return meta, body


def parse_questions(body, path, section=None):
    """Walk the body, collecting '## Section' headings and '### Qn' questions.

    Returns (questions, trailing_section). The trailing section is fed into the
    next file of a split test so a section can span files.
    """
    questions = []
    current = None
    mode = None  # None | stem | options | answer | explain

    def close():
        if current is not None:
            finish_question(current, path)
            questions.append(current)

    for line_no, line in enumerate(body.splitlines(), start=1):
        stripped = line.strip()

        if stripped.startswith("### "):
            close()
            current = {
                "label": stripped[4:].strip(),
                "section": section,
                "stem": [],
                "options": [],
                "answer": None,
                "explain": [],
                "line": line_no,
            }
            mode = "stem"
            continue

        if stripped.startswith("## "):
            close()
            current = None
            section = stripped[3:].strip()
            mode = None
            continue

        if current is None:
            continue

        option = OPTION_RE.match(line)
        if option:
            letter, text = option.group(1).upper(), option.group(2).strip()
            if any(o["letter"] == letter for o in current["options"]):
                raise TestError(
                    f"{path.name} line {line_no}: question {current['label']!r} "
                    f"lists option {letter} twice")
            current["options"].append({"letter": letter, "text": text})
            mode = "options"
            continue

        answer = ANSWER_RE.match(line)
        if answer:
            if current["answer"] is not None:
                raise TestError(
                    f"{path.name} line {line_no}: question {current['label']!r} "
                    f"has more than one Answer: line")
            current["answer"] = answer.group(1).upper()
            mode = "answer"
            continue

        explain = EXPLAIN_RE.match(line)
        if explain:
            current["explain"].append(explain.group(1).strip())
            mode = "explain"
            continue

        if mode == "stem":
            current["stem"].append(line.rstrip())
        elif mode == "explain":
            current["explain"].append(line.rstrip())

    close()
    return questions, section


def finish_question(q, path):
    """Normalise one question and reject it if it is unusable."""
    q["stem"] = "\n".join(q["stem"]).strip()
    q["explain"] = "\n".join(q["explain"]).strip()

    where = f"{path.name} line {q['line']}: question {q['label']!r}"

    if not q["stem"]:
        raise TestError(f"{where} has no question text")
    if len(q["options"]) < 2:
        raise TestError(
            f"{where} has {len(q['options'])} option(s); at least 2 are needed")
    if q["answer"] is None:
        raise TestError(f"{where} has no 'Answer:' line")

    letters = [o["letter"] for o in q["options"]]
    if q["answer"] not in letters:
        raise TestError(
            f"{where} marks '{q['answer']}' as correct, but its options are "
            f"{', '.join(letters)}. A mismatched answer letter teaches the wrong fact.")

    for o in q["options"]:
        if not o["text"]:
            raise TestError(f"{where} has an empty option {o['letter']}")


def check_balance(questions, path, warnings):
    """Catch a key that clusters on one letter, which rewards pattern-guessing."""
    if len(questions) < BALANCE_MIN_QUESTIONS:
        return
    counts = Counter(q["answer"] for q in questions)
    total = len(questions)
    letters = sorted({o["letter"] for q in questions for o in q["options"]})

    top_letter, top_count = counts.most_common(1)[0]
    share = top_count / total
    if share > BALANCE_MAX_SHARE:
        warnings.append(
            f"{path.name}: {top_count} of {total} answers ({share:.0%}) are option "
            f"{top_letter}. Above {BALANCE_MAX_SHARE:.0%} a candidate can score by "
            f"always guessing {top_letter}. Reorder some options.")

    unused = [l for l in letters if counts.get(l, 0) == 0]
    if unused and total >= 20:
        warnings.append(
            f"{path.name}: option(s) {', '.join(unused)} are never the correct answer "
            f"across {total} questions, so they can be eliminated on sight.")


def discover(tests_dir):
    """Find every test, as (display_name, [paths]) pairs.

    A test is either a single .md file, or a directory holding a `test.md`
    (frontmatter, and optionally questions) plus any number of sibling .md
    files that are appended in filename order. The split form exists so an
    author can add a batch of questions as a NEW small file instead of
    rewriting a large one, which is the failure mode when the writer can only
    replace whole files rather than patch them.
    """
    groups = []
    claimed = set()

    for meta_file in sorted(tests_dir.rglob("test.md")):
        folder = meta_file.parent
        parts = [meta_file] + sorted(
            p for p in folder.glob("*.md") if p != meta_file)
        groups.append((folder, parts))
        claimed.update(parts)

    for path in sorted(tests_dir.rglob("*.md")):
        if path not in claimed:
            groups.append((path, [path]))

    return groups


def build_test(label, paths, warnings):
    """Compile one test from one or more Markdown files."""
    path = paths[0]
    text = path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(text, path)

    for required in ("id", "title"):
        if not meta.get(required):
            raise TestError(f"{path.name}: frontmatter is missing '{required}'")

    if not re.fullmatch(r"[A-Za-z0-9._-]+", meta["id"]):
        raise TestError(
            f"{path.name}: id {meta['id']!r} may only contain letters, digits, "
            f"dot, dash and underscore (it becomes a filename)")

    # Parse each file on its own so an error names the right file and line.
    questions, section = parse_questions(body, path)
    for extra in paths[1:]:
        extra_text = extra.read_text(encoding="utf-8")
        if extra_text.lstrip().startswith("---"):
            raise TestError(
                f"{extra.name}: only test.md may carry frontmatter; the other "
                f"files in a split test hold questions only")
        more, section = parse_questions(extra_text, extra, section)
        questions.extend(more)

    if not questions:
        raise TestError(
            f"{label}: no questions found (each one starts with '### ')")

    check_balance(questions, path, warnings)

    def as_int(key, default):
        raw = meta.get(key)
        if raw in (None, ""):
            return default
        try:
            return int(raw)
        except ValueError:
            raise TestError(f"{path.name}: '{key}' must be a whole number, got {raw!r}")

    out_questions = []
    for i, q in enumerate(questions, start=1):
        out_questions.append({
            "n": i,
            "label": q["label"],
            "section": q["section"],
            "stem": q["stem"],
            "options": q["options"],
            "answer": q["answer"],
            "explain": q["explain"],
        })

    sections = []
    for q in out_questions:
        if q["section"] and q["section"] not in sections:
            sections.append(q["section"])

    return {
        "id": meta["id"],
        "title": meta["title"],
        "objective": meta.get("objective", ""),
        "description": meta.get("description", ""),
        "source": meta.get("source", ""),
        "recommendedMinutes": as_int("time", 0),
        "passPercent": as_int("pass", 0),
        "sections": sections,
        "questionCount": len(out_questions),
        "questions": out_questions,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true",
                    help="treat warnings as errors (used by CI)")
    args = ap.parse_args()

    if not TESTS_DIR.is_dir():
        print(f"error: no tests/ directory at {TESTS_DIR}", file=sys.stderr)
        return 1

    groups = discover(TESTS_DIR)
    if not groups:
        print("error: tests/ contains no .md files", file=sys.stderr)
        return 1

    warnings = []
    built = []
    seen_ids = {}

    for label, paths in groups:
        name = label.name
        try:
            data = build_test(name, paths, warnings)
        except TestError as exc:
            print(f"FAIL  {exc}", file=sys.stderr)
            return 1

        if data["id"] in seen_ids:
            print(f"FAIL  {name}: id {data['id']!r} is already used by "
                  f"{seen_ids[data['id']]}", file=sys.stderr)
            return 1
        seen_ids[data["id"]] = name
        data["_parts"] = len(paths)
        built.append(data)

    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    shutil.copytree(SITE_DIR, DIST_DIR)
    data_dir = DIST_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    papers_dir = DIST_DIR / "papers"
    papers_dir.mkdir(parents=True, exist_ok=True)

    manifest = []
    for data in built:
        parts = data.pop("_parts", 1)
        (data_dir / f"{data['id']}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

        # Readable paper plus key, for printing, sharing or offline study.
        paper_name = f"{data['id']}.md"
        (papers_dir / paper_name).write_text(paper.render(data), encoding="utf-8")

        manifest.append({
            "id": data["id"],
            "title": data["title"],
            "objective": data["objective"],
            "description": data["description"],
            "questionCount": data["questionCount"],
            "recommendedMinutes": data["recommendedMinutes"],
            "passPercent": data["passPercent"],
            "sections": data["sections"],
            "paper": f"papers/{paper_name}",
        })
        data["_parts"] = parts

    manifest.sort(key=lambda m: (m["objective"], m["title"]))
    (data_dir / "manifest.json").write_text(
        json.dumps({"tests": manifest}, ensure_ascii=False, indent=1), encoding="utf-8")

    for data in built:
        counts = Counter(q["answer"] for q in data["questions"])
        spread = " ".join(f"{k}:{counts[k]}" for k in sorted(counts))
        missing = sum(1 for q in data["questions"] if not q["explain"])
        note = f", {missing} without explanation" if missing else ""
        parts = data.get("_parts", 1)
        src = f", {parts} files" if parts > 1 else ""
        print(f"  ok  {data['id']}  {data['questionCount']} questions  "
              f"[{spread}]{note}{src}")

    for w in warnings:
        print(f"WARN  {w}", file=sys.stderr)

    print(f"\nBuilt {len(built)} test(s) into {DIST_DIR.name}/")

    if warnings and args.strict:
        print("strict mode: warnings above are treated as errors", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
