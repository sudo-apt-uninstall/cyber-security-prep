#!/usr/bin/env python3
"""Self-test for the build pipeline. Run: python3 tools/selftest.py

Checks the compiled output against the known answer key, then feeds the
validator deliberately broken files to confirm it rejects them.
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "tools" / "build.py"

# Answer key as published, in blocks of ten: Q1-10, Q11-20, ... Q51-60.
EXPECTED = ("ACADBADAAB"   # 1-10
            "ADDCADADAC"   # 11-20
            "DCDABBCDBB"   # 21-30
            "CACBADBCBC"   # 31-40
            "CADCDCBDBC"   # 41-50
            "BACBCDBADB")  # 51-60

failures = []


def check(label, cond, detail=""):
    if cond:
        print(f"  pass  {label}")
    else:
        print(f"  FAIL  {label} {detail}")
        failures.append(label)


def run_build(cwd, strict=False):
    cmd = [sys.executable, str(BUILD)]
    if strict:
        cmd.append("--strict")
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def run_in_sandbox(files, strict=False):
    """Build a throwaway repo whose tests/ holds `files` ({relpath: text})."""
    tmp = Path(tempfile.mkdtemp())
    (tmp / "tests").mkdir()
    (tmp / "site").mkdir()
    (tmp / "site" / "index.html").write_text("<!doctype html>", encoding="utf-8")
    for rel, text in files.items():
        dest = tmp / "tests" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
    # build.py locates tests/ relative to itself, so copy the tools in.
    (tmp / "tools").mkdir()
    for mod in ("build.py", "paper.py"):
        (tmp / "tools" / mod).write_text(
            (ROOT / "tools" / mod).read_text(encoding="utf-8"), encoding="utf-8")
    cmd = [sys.executable, str(tmp / "tools" / "build.py")]
    if strict:
        cmd.append("--strict")
    r = subprocess.run(cmd, cwd=tmp, capture_output=True, text=True)
    return tmp, r


def scenario(name, md, expect_fail, needle=None, strict=False, files=None):
    """Check that one throwaway test repo builds, or fails for the right reason."""
    payload = files if files is not None else {"t.md": md}
    tmp, r = run_in_sandbox(payload, strict=strict)
    try:
        out = r.stdout + r.stderr
        if expect_fail:
            ok = r.returncode != 0 and (needle is None or needle in out)
            check(name, ok, f"(exit {r.returncode}) {out.strip()[:160]}")
        else:
            check(name, r.returncode == 0, out.strip()[:160])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


GOOD_HEAD = "---\nid: t\ntitle: T\n---\n\n"
def q(n, ans="A", opts=("A", "B", "C", "D")):
    body = f"### Q{n}\nStem {n}?\n\n"
    for o in opts:
        body += f"- {o}. Option {o}\n"
    return body + f"\nAnswer: {ans}\n"


print("1. compiled output matches the known key")
r = run_build(ROOT)
check("build exits 0", r.returncode == 0, r.stderr.strip()[:200])

data = json.loads((ROOT / "dist" / "data" / "secplus-sy0701-1-1.json").read_text("utf-8"))
check("60 questions", data["questionCount"] == 60, f"got {data['questionCount']}")
got = "".join(x["answer"] for x in data["questions"])
check("answer key matches published key", got == EXPECTED,
      f"\n        expected {EXPECTED}\n        got      {got}")
check("4 sections detected", len(data["sections"]) == 4, str(data["sections"]))
check("every question has an explanation",
      all(x["explain"] for x in data["questions"]),
      str([x["n"] for x in data["questions"] if not x["explain"]]))
check("every answer letter exists in its options",
      all(x["answer"] in [o["letter"] for o in x["options"]] for x in data["questions"]))
check("every question has 4 options",
      all(len(x["options"]) == 4 for x in data["questions"]))
check("stems are non-empty", all(x["stem"].strip() for x in data["questions"]))
check("pass mark and time carried through",
      data["passPercent"] == 83 and data["recommendedMinutes"] == 75,
      f"{data['passPercent']} {data['recommendedMinutes']}")

man = json.loads((ROOT / "dist" / "data" / "manifest.json").read_text("utf-8"))
check("manifest lists the test", len(man["tests"]) == 1 and
      man["tests"][0]["id"] == "secplus-sy0701-1-1")
check("site files copied into dist",
      (ROOT / "dist" / "index.html").exists() and
      (ROOT / "dist" / "app.js").exists() and
      (ROOT / "dist" / "style.css").exists())

print("\n2. validator rejects broken input")
scenario("answer letter not among options",
         GOOD_HEAD + q(1, ans="E"), True, "mismatched answer letter")
scenario("missing Answer: line",
         GOOD_HEAD + "### Q1\nStem?\n\n- A. one\n- B. two\n", True, "no 'Answer:' line")
scenario("question with only one option",
         GOOD_HEAD + "### Q1\nStem?\n\n- A. one\n\nAnswer: A\n", True, "at least 2")
scenario("question with no stem",
         GOOD_HEAD + "### Q1\n\n- A. one\n- B. two\n\nAnswer: A\n", True, "no question text")
scenario("duplicate option letter",
         GOOD_HEAD + "### Q1\nStem?\n\n- A. one\n- A. two\n\nAnswer: A\n", True, "twice")
scenario("no frontmatter", "### Q1\nStem?\n\n- A. x\n- B. y\n\nAnswer: A\n",
         True, "frontmatter")
scenario("frontmatter missing id",
         "---\ntitle: T\n---\n\n" + q(1), True, "missing 'id'")
scenario("no questions at all", GOOD_HEAD + "Just prose.\n", True, "no questions found")
scenario("id with a path separator",
         "---\nid: a/b\ntitle: T\n---\n\n" + q(1), True, "may only contain")

print("\n3. answer-balance guard")
skew = GOOD_HEAD + "".join(q(i, ans="B") for i in range(1, 21))
scenario("skewed key warns under --strict", skew, True, "always guessing B", strict=True)
scenario("skewed key still builds without --strict", skew, False)
balanced = GOOD_HEAD + "".join(
    q(i, ans="ABCD"[(i - 1) % 4]) for i in range(1, 21))
scenario("balanced key passes --strict", balanced, False, strict=True)
scenario("real test passes --strict",
         (ROOT / "tests" / "secplus" / "sy0-701-1.1-security-controls.md").read_text("utf-8"),
         False, strict=True)

print("\n4. split tests (a folder with test.md plus part files)")

SPLIT = {
    "set/test.md": GOOD_HEAD.replace("id: t", "id: split") + q(1, "A") + q(2, "B"),
    "set/part-02.md": "## Later section\n\n" + q(3, "C") + q(4, "D"),
}
scenario("folder with test.md plus a part file builds", None, False, files=SPLIT)

tmp, r = run_in_sandbox(SPLIT)
try:
    check("split build reports 2 files", "2 files" in r.stdout, r.stdout.strip()[:160])
    split = json.loads(
        (tmp / "dist" / "data" / "split.json").read_text("utf-8"))
    check("split test merges to 4 questions", split["questionCount"] == 4,
          str(split["questionCount"]))
    check("questions renumber across files",
          [x["n"] for x in split["questions"]] == [1, 2, 3, 4],
          str([x["n"] for x in split["questions"]]))
    check("answers survive the merge",
          "".join(x["answer"] for x in split["questions"]) == "ABCD",
          "".join(x["answer"] for x in split["questions"]))
    check("section from the part file is picked up",
          split["questions"][2]["section"] == "Later section",
          str(split["questions"][2]["section"]))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

scenario("part file carrying frontmatter is rejected", None, True,
         "only test.md may carry frontmatter",
         files={"set/test.md": GOOD_HEAD + q(1),
                "set/part-02.md": GOOD_HEAD + q(2)})

scenario("a part file's own error names that file, not test.md", None, True,
         "part-02.md",
         files={"set/test.md": GOOD_HEAD + q(1),
                "set/part-02.md": "### Q2\nStem?\n\n- A. one\n- B. two\n"})

print("\n5. generated paper")
tmp, r = run_in_sandbox({"t.md": GOOD_HEAD + q(1, "A") + q(2, "B")})
try:
    paper_path = tmp / "dist" / "papers" / "t.md"
    check("paper file is written", paper_path.exists())
    body = paper_path.read_text("utf-8") if paper_path.exists() else ""
    check("paper holds the questions", "**1.** Stem 1?" in body)
    check("paper holds an answer key", "# Answer key" in body)
    check("paper reports the answer spread", "Answer spread:" in body)
    qs, _, key = body.partition("# Answer key")
    check("no answers leak above the key line",
          "**A**" not in qs and "**B**" not in qs,
          "an answer appeared in the question half")
    man = json.loads((tmp / "dist" / "data" / "manifest.json").read_text("utf-8"))
    check("manifest links the paper",
          man["tests"][0].get("paper") == "papers/t.md",
          str(man["tests"][0].get("paper")))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

real_paper = ROOT / "dist" / "papers" / "secplus-sy0701-1-1.md"
check("real paper generated", real_paper.exists())
if real_paper.exists():
    text = real_paper.read_text("utf-8")
    qhalf, _, keyhalf = text.partition("# Answer key")
    check("real paper: all 60 questions present",
          all(f"**{i}.** " in qhalf for i in range(1, 61)))
    check("real paper: no 'Answer:' leaks into the question half",
          "Answer:" not in qhalf)
    check("real paper: no explanations leak into the question half",
          "Explain:" not in qhalf and "Option B is the trap" not in qhalf)
    check("real paper: key matches the compiled key",
          all(f"**{c}**" in keyhalf for c in "ABCD") and
          "A 15, B 15, C 15, D 15" in keyhalf)

print()
if failures:
    print(f"{len(failures)} check(s) failed")
    sys.exit(1)
print("all checks passed")
