"""Render a compiled test into a human-readable Markdown paper and answer key.

Kept separate from build.py so the rendering can change without touching the
compiler or its validation rules.
"""


def _facts(data):
    bits = ["%d questions" % data["questionCount"]]
    if data["recommendedMinutes"]:
        bits.append("%d minutes" % data["recommendedMinutes"])
    if data["passPercent"]:
        bits.append("pass mark %d%%" % data["passPercent"])
    return " \u00b7 ".join(bits)


def render(data):
    """Return the paper and the answer key as one Markdown document."""
    out = []
    add = out.append

    add("# %s" % data["title"])
    add("")
    if data["objective"]:
        add("**%s**" % data["objective"])
        add("")
    if data["description"]:
        add(data["description"])
        add("")
    add(_facts(data))
    add("")
    add("The answer key begins after the final question. Work through the whole")
    add("paper before consulting it.")
    add("")

    # ── questions ────────────────────────────────────────
    section = None
    for q in data["questions"]:
        if q["section"] and q["section"] != section:
            section = q["section"]
            add("")
            add("---")
            add("")
            add("## %s" % section)
            add("")
        add("**%d.** %s" % (q["n"], q["stem"].replace("\n", " ")))
        add("")
        for o in q["options"]:
            add("- %s. %s" % (o["letter"], o["text"]))
        add("")

    # ── compact grid ────────────────────────────────────
    add("")
    add("---")
    add("")
    add("# Answer key")
    add("")

    qs = data["questions"]
    per_row = 10
    for start in range(0, len(qs), per_row):
        chunk = qs[start:start + per_row]
        add("| " + " | ".join("Q%d" % q["n"] for q in chunk) + " |")
        add("|" + "---|" * len(chunk))
        add("| " + " | ".join("**%s**" % q["answer"] for q in chunk) + " |")
        add("")

    # Spread across option letters, so a reader can see the key is not lopsided.
    counts = {}
    for q in qs:
        counts[q["answer"]] = counts.get(q["answer"], 0) + 1
    add("Answer spread: " +
        ", ".join("%s %d" % (k, counts[k]) for k in sorted(counts)) +
        ". Option position carries no information.")
    add("")

    # ── per-question rationale ─────────────────────────────
    if any(q["explain"] for q in qs):
        add("")
        add("## Explanations")
        add("")
        section = None
        for q in qs:
            if q["section"] and q["section"] != section:
                section = q["section"]
                add("### %s" % section)
                add("")
            correct = [o for o in q["options"] if o["letter"] == q["answer"]]
            label = correct[0]["text"] if correct else ""
            add("**%d. %s** \u2014 %s" % (q["n"], q["answer"], label))
            if q["explain"]:
                add("")
                for para in q["explain"].split("\n\n"):
                    if para.strip():
                        add(para.strip().replace("\n", " "))
            add("")

    return "\n".join(out).rstrip() + "\n"
