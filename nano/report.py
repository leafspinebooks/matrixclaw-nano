"""The final report — what Nano hands back, in Markdown the reader keeps.

Written to be Markua-safe, because a reader may well paste this into a book or a
course later and because the project it serves is published on Leanpub. Markua maps
headings to structure rather than to font size:

    #     a chapter        ##    a section        ###   a sub-section

so a report that opens with `#` is a chapter. That is correct for a standalone file
and wrong the moment it is pasted inside one — hence ``heading_offset``.

``check_markua`` below is Nano's own, written for Nano. It is deliberately small and
deliberately not borrowed: this project shares no code with MatrixClaw, and the
licensing boundary is the reason the project exists separately at all.
"""

import re

MAX_HEADING = 6
_BANNED_CHARS = {"→": "->", "←": "<-", "⇒": "=>"}


def _h(level, offset):
    return "#" * min(level + offset, MAX_HEADING)


def check_markua(text, expect_chapter_heading=True):
    """Structural checks over generated Markdown. Returns a list of problems."""
    problems = []
    in_fence = False
    headings = []
    for n, line in enumerate(text.split("\n"), 1):
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue                      # '#' in a code block is a comment, not a heading
        m = re.match(r"^(#{1,10})\s+(\S.*)$", line)
        if m:
            headings.append((n, len(m.group(1)), m.group(2)))

    if in_fence:
        problems.append("a code fence is left open")

    tops = [h for h in headings if h[1] == 1]
    if expect_chapter_heading and len(tops) != 1:
        problems.append("expected exactly one chapter heading, found %d" % len(tops))
    if not expect_chapter_heading and tops:
        problems.append(
            "line %d uses '#', a CHAPTER heading — embedded content must not, "
            "it breaks out of the chapter around it" % tops[0][0])

    previous = None
    for n, level, title in headings:
        if level > MAX_HEADING:
            problems.append("line %d: heading depth %d exceeds Markua's 6" % (n, level))
        if previous is not None and level > previous + 1:
            problems.append("line %d: heading jumps %d -> %d" % (n, previous, level))
        previous = level

    for bad, good in _BANNED_CHARS.items():
        if bad in text:
            problems.append("contains %r; use %r" % (bad, good))
    return problems


def _status_word(status):
    return {"passed": "PASSED", "failed": "DID NOT PASS", "error": "COULD NOT COMPLETE",
            "not-applicable": "DID NOT APPLY",
            "pending": "READY - WITH ADVISORIES"}.get(status, status.upper())


def render(record, advice, heading_offset=0):
    """Render a record to Markdown. Every figure here is counted from the record."""
    d = record.data
    counts = record.counts()
    total = sum(counts.values())
    pkg = d["package"]
    host = d["host"]
    approval = d.get("approval") or {}
    out = []

    # WHERE, not just what. This sentence said "on this machine" for every run,
    # including the six phases that execute entirely on a nested VM over SSH. The
    # host table further down was right and the headline was wrong, which is the
    # worse way round: the headline is the sentence people quote.
    hosts = []
    for chk in d.get("checks", []):
        if chk.get("host") and chk["host"] not in hosts:
            hosts.append(chk["host"])
    if not hosts:
        where = "on this machine"
    elif hosts == ["this machine"]:
        where = "on this machine"
    elif len(hosts) == 1:
        where = "on **%s**" % hosts[0]
    else:
        where = "on %s" % ", ".join("**%s**" % h for h in hosts)

    out.append("%s MatrixClaw Nano report" % _h(1, heading_offset))
    out.append("")
    out.append("Package **%s** ran %d command(s) %s and **%s**."
               % (pkg["title"], total, where, _status_word(d.get("status", "unknown"))))
    out.append("")
    out.append("%s What ran, and on what" % _h(2, heading_offset))
    out.append("")
    out.append("| | |")
    out.append("|---|---|")
    out.append("| Record | `%s` |" % d["record_id"])
    out.append("| Package | %s |" % pkg["name"])
    out.append("| Started | %s |" % d["created_utc"])
    out.append("| Ran from | %s %s (%s) |" % (host["system"], host["release"], host["machine"]))
    out.append("| Python | %s |" % host["python"])
    out.append("| Approved by | %s |" % (approval.get("approver") or "(not approved)"))
    out.append("| Plan digest | `%s` |" % (approval.get("plan_digest") or "-"))
    out.append("")

    out.append("Results: **%d passed**, %d did not pass, %d advisory, "
               "%d skipped, %d could not run."
               % (counts["pass"], counts["fail"], counts.get("pending", 0),
                  counts["skipped"], counts["error"]))
    out.append("")

    out.append("%s Every check, and what it found" % _h(2, heading_offset))
    out.append("")
    mark = {"pass": "PASS", "fail": "FAIL", "skipped": "SKIP", "error": "ERR ",
            "already": "DONE", "pending": "PEND"}
    for chk in d.get("checks", []):
        out.append("- **[%s] %s** (on %s) - %s"
                   % (mark.get(chk["status"], "?"), chk["title"],
                      chk.get("host", "this machine"), chk.get("detail", "")))
    out.append("")

    if counts["skipped"]:
        out.append("%s What was NOT checked" % _h(2, heading_offset))
        out.append("")
        out.append("%d check(s) did not apply to this machine and were skipped. A skipped "
                   "check is not a passed one, and nothing below should be read as "
                   "evidence about the things they would have covered."
                   % counts["skipped"])
        out.append("")
        for chk in d.get("checks", []):
            if chk["status"] == "skipped":
                out.append("- **%s** - %s" % (chk["title"], chk.get("detail", "")))
        out.append("")

    if advice:
        out.append("%s What to do next" % _h(2, heading_offset))
        out.append("")
        out.append("This advice is written into the package beside the check it belongs to. "
                   "Nano does not improvise remedies for your machine.")
        out.append("")
        for item in advice:
            out.append("%s %s" % (_h(3, heading_offset), item["title"]))
            out.append("")
            out.append(item["advice"])
            out.append("")

    redacted = [c for c in d.get("checks", []) if c.get("redacted")]
    if redacted:
        out.append("%s What was removed from this record" % _h(2, heading_offset))
        out.append("")
        out.append("%d command(s) printed output that matched a credential pattern. The "
                   "matching text was replaced with a placeholder before this record was "
                   "written to disk, and the exit codes and everything else are untouched."
                   % len(redacted))
        out.append("")
        for chk in redacted:
            out.append("- **%s** (on %s) - matched: %s"
                       % (chk["title"], chk.get("host", "this machine"),
                          ", ".join(chk["redacted"])))
        out.append("")
        out.append("This is pattern matching, not proof. Nano never sees your secrets - they "
                   "live in a root-only file on the target host and are expanded there - so it "
                   "cannot recognise a value it has never been told. It removes what it knows "
                   "how to recognise. Read a record before you paste it anywhere.")
        out.append("")

    out.append("%s What this report does not tell you" % _h(2, heading_offset))
    out.append("")
    out.append("It reports what these checks observed, at the time they ran, on this machine "
               "and nothing else. It is not a guarantee that the full lab will build: that is "
               "proven by building it. Where a check could not run, the report says so above "
               "rather than staying quiet about it.")
    out.append("")
    out.append("The full record, including the exit code and output of every check, is at "
               "`%s`. It is yours; Nano sends it nowhere." % record.path)
    out.append("")
    return "\n".join(out)
