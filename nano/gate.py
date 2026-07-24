"""The gate — nothing runs on a reader's machine without them saying yes to it.

This is the part of Nano that is the product rather than the overhead. Three rules,
and they are not configurable:

  1. NO SILENT EXECUTION. Every command Nano will run is printed, in full, before
     anything runs. Not a summary, not a count — the actual command text.
  2. APPROVAL IS BOUND TO THE PLAN AS PRESENTED — not merely to what executes. The
     digest covers every command in order, the host each is aimed at, and what the
     reader was told about it, including whether it changes their machine. If any of
     that moves after approval, the approval is void. Saying yes to one set of
     commands is not saying yes to a different set, and saying yes to a plan that
     declared one dangerous step is not saying yes to the same commands described as
     nine.
  3. THE DEFAULT IS NO. An empty answer, a closed pipe, or anything that is not an
     explicit yes declines.

Read-only checks are gated too. They are not destructive, but a reader is entitled to
know what is about to touch their machine before it does, and building the habit on
the safe path is how it holds on the unsafe one.
"""

import hashlib
import sys


class GateDeclined(Exception):
    """Raised when approval was not given. Not an error — a decision."""


def _wrap(text, width):
    """Minimal word wrap. stdlib textwrap would do, but this keeps the module bare."""
    words, lines, current = text.split(), [], ""
    for word in words:
        if current and len(current) + 1 + len(word) > width:
            lines.append(current)
            current = word
        else:
            current = (current + " " + word).strip()
    if current:
        lines.append(current)
    return lines


def plan_digest(package, items):
    """A short, stable digest of THE PLAN THE READER WAS SHOWN, in order.

    Not merely of what executes. The distinction was found in use, on 2026-07-23:
    correcting a package so the gate stopped over-reporting which steps change the
    machine left the digest untouched, because the commands had not moved. That is a
    hole. A reader's yes is given to a description as much as to a command list, and a
    package edit that changes what they were WARNED about — while running exactly the
    same commands — must void that yes just as surely.

    So the digest covers every field the plan text presents as material: the package's
    own framing, and for each item its host, its command, whether it is declared to
    change the machine, its title and its stated reason.

    It deliberately does NOT cover the formatting. Re-indenting the plan, or rewording
    a label in a later version of Nano, is not a change to what the reader agreed to,
    and invalidating every stored approval on a cosmetic edit would train people to
    ignore the warning that followed.
    """
    h = hashlib.sha256()

    def field(text):
        h.update(("" if text is None else str(text)).encode("utf-8"))
        h.update(b"\0")

    field(package.get("name", ""))
    field(package.get("title", ""))
    field(package.get("description", ""))
    for item in items:
        field(item["_target"].name)
        field(item["run"])
        field("mutates" if item.get("mutates") else "read-only")
        # Covered because it is DISPLAYED, and displayed prominently. Removing a
        # destructive marking must void an approval: the reader said yes to a plan
        # that warned them, and a plan that no longer warns is a different plan.
        field("destructive" if item.get("destructive") else "non-destructive")
        field(item.get("destroys", ""))
        field(item.get("title", item["id"]))
        field(item.get("why", ""))
        # THE PROBE IS PART OF THE PLAN TOO. It decides whether a step executes at
        # all - and for a destructive step it is, in the gate's own words, the only
        # thing preventing the loss. A package edit that changed a probe while
        # leaving every command identical would otherwise keep an approval alive
        # and turn a skipped wipe into a performed one.
        field(item.get("already", ""))
    return "sha256:" + h.hexdigest()[:16]


def format_plan(package, items):
    """The text a reader sees before deciding. Complete, not summarised.

    Where a command runs on another machine, the ssh invocation is shown in full
    underneath it. Nano's promise is that nothing runs that was not displayed; hiding
    the transport behind a friendly summary would quietly break that promise.
    """
    from . import transport

    lines = []
    lines.append("")
    lines.append("  %s" % package.get("title", package["name"]))
    if package.get("description"):
        lines.append("  %s" % package["description"])
    lines.append("")

    targets = []
    for item in items:
        if item["_target"].name not in targets:
            targets.append(item["_target"].name)
    lines.append("  Nano will run %d command(s) on: %s" % (len(items), ", ".join(targets)))
    for name in targets:
        target = next(i["_target"] for i in items if i["_target"].name == name)
        lines.append("    - %s" % target.describe())
    lines.append("")

    for i, item in enumerate(items, 1):
        target = item["_target"]
        lines.append("   %2d. %s   [on %s]" % (i, item.get("title", item["id"]), target.name))
        lines.append("       $ %s" % item["run"])
        if not target.local:
            lines.append("       via: %s" % transport.command_line(item["run"], target))
        if item.get("why"):
            lines.append("       why: %s" % item["why"])
        lines.append("")

    mutating = [i for i in items if i.get("mutates")]
    if mutating:
        lines.append("  %d of these CHANGE a machine:" % len(mutating))
        for item in mutating:
            lines.append("    - %s  [on %s]" % (item.get("title", item["id"]),
                                                item["_target"].name))
    else:
        lines.append("  All of these are READ-ONLY. None of them changes anything.")
    lines.append("")

    # DESTRUCTIVE STEPS GET THEIR OWN SECTION, LAST, WHERE IT CANNOT BE SKIMMED PAST.
    # A step that merely changes configuration and a step that wipes a database are
    # not the same risk, and burying the second in a list of the first is how a
    # reader loses data they had no idea was at stake. They are the ones with no
    # backup and no way to know which is which.
    destructive = [i for i in items if i.get("destructive")]
    if destructive:
        lines.append("  " + "!" * 68)
        lines.append("  %d of these DESTROY EXISTING DATA if this machine is already built:"
                     % len(destructive))
        lines.append("")
        for item in destructive:
            lines.append("    %s  [on %s]" % (item.get("title", item["id"]),
                                              item["_target"].name))
            if item.get("destroys"):
                for line in _wrap(item["destroys"], 62):
                    lines.append("      %s" % line)
            # Show the probe verbatim. Telling a reader that a probe protects them
            # while hiding what it tests asks them to trust rather than to check,
            # and the whole point of this gate is that they need not trust anyone.
            if item.get("already"):
                lines.append("      skipped only if this command succeeds:")
                lines.append("        $ %s" % item["already"])
            else:
                lines.append("      THIS STEP HAS NO PROBE. It will run unconditionally.")
            lines.append("")
        lines.append("  Each of these carries a probe that skips it when the work is already")
        lines.append("  done. That probe is the only thing preventing the loss described above.")
        lines.append("  If you are re-running this phase on a machine that was previously")
        lines.append("  built, STOP and take a backup before answering yes.")
        lines.append("  " + "!" * 68)
        lines.append("")
    lines.append("  Plan digest: %s" % plan_digest(package, items))
    lines.append("")
    return "\n".join(lines)


def ask(package, items, approver=None, assume_yes=False, stream=None):
    """Present the plan and obtain a decision. Returns the approver's name.

    ``assume_yes`` exists for non-interactive use and is recorded in the audit trail
    as exactly that, so a record never implies a human read something they did not.
    """
    out = stream or sys.stdout
    out.write(format_plan(package, items))

    if assume_yes:
        name = approver or "--yes (non-interactive; no human confirmed this at run time)"
        out.write("  Approved non-interactively.\n\n")
        return name

    if not sys.stdin.isatty():
        raise GateDeclined(
            "no terminal to ask on, and --yes was not given. Nano will not run "
            "commands on your machine without an explicit decision.")

    try:
        answer = raw_input("  Run these now? [y/N] ")      # noqa: F821  (py2 name)
    except NameError:
        answer = input("  Run these now? [y/N] ")
    except (EOFError, KeyboardInterrupt):
        raise GateDeclined("cancelled at the gate")

    if answer.strip().lower() not in ("y", "yes"):
        raise GateDeclined("declined at the gate")

    if approver:
        return approver
    try:
        who = raw_input("  Your name for the record [you]: ")   # noqa: F821
    except NameError:
        who = input("  Your name for the record [you]: ")
    except (EOFError, KeyboardInterrupt):
        raise GateDeclined("cancelled at the gate")
    return who.strip() or "you"


def verify(record, package, items):
    """Re-check that the approval on the record still matches the plan as presented."""
    approval = record.data.get("approval")
    if not approval:
        raise GateDeclined("this record carries no approval")
    now = plan_digest(package, items)
    if approval["plan_digest"] != now:
        raise GateDeclined(
            "the package changed after approval (approved %s, now %s) — approval is void"
            % (approval["plan_digest"], now))
    return True
