"""MatrixClaw Nano — command line.

    mcnano packages                 what Nano can run
    mcnano hosts                    where it will run, and whether they answer
    mcnano plan <package>           show every command and its host, run nothing
    mcnano run  <package>           ask, then run, then record
    mcnano report <record-id>       the report for a run
    mcnano records                  runs on this machine

Stdlib only, Python 3. Nothing to install, nothing to sign up for, nothing sent
anywhere. Exit codes: 0 ok - 1 checks did not pass - 2 usage - 3 declined at the gate -
4 the machine is ready but something the build installs is not there yet.
"""

import argparse
import sys

from . import __version__
from . import gate, packages, record as record_mod, report as report_mod, runner, transport


def _p(msg=""):
    sys.stdout.write(msg + "\n")


def cmd_packages(args):
    names = packages.available()
    if not names:
        _p("No packages found in %s" % packages.package_dir())
        return 2
    loaded = []
    for name in names:
        pkg = packages.load(name)
        loaded.append((pkg.get("order", 99), name, pkg))
    loaded.sort()
    _p("")
    _p("  The lab build, in order. Run them in this sequence; each assumes the last.")
    _p("")
    for order, name, pkg in loaded:
        steps, checks = len(pkg.get("steps", [])), len(pkg.get("checks", []))
        shape = "%d step(s) that change the machine, %d check(s)" % (steps, checks) \
            if steps else "%d read-only check(s)" % checks
        _p("  %-24s %s" % (name, pkg.get("title", "")))
        _p("  %-24s %s%s" % ("", shape,
                             "  [host: %s]" % pkg["target_host"] if pkg.get("target_host") else ""))
        _p("")
    _p("  mcnano plan <name>   shows every command and runs nothing.")
    _p("")
    return 0


def cmd_hosts(args):
    """Where Nano will run things, and — with --check — whether they answer.

    Worth running before the first package that targets a VM. A host that does not
    answer here will not answer mid-build either, and finding out now costs nothing.
    """
    host_map = transport.load_map(getattr(args, "hosts", None))

    if getattr(args, "forget", False):
        # Rebuilding the estate mints fresh host keys for the same addresses, and a
        # stale entry then fails every connection with a warning about a changed key.
        # Explicit rather than automatic: silently discarding a host key Nano has seen
        # before is exactly the check that warning exists to make.
        forgotten = transport.forget_known_hosts()
        _p("")
        _p("  %s" % forgotten)
        _p("")
        return 0

    _p("")
    _p("  Host map: %s" % transport.hosts_path(getattr(args, "hosts", None)))
    _p("")
    for name in sorted(host_map):
        target = host_map[name]
        line = "  %-12s %s" % (name, target.describe())
        if args.check:
            ok, detail = transport.reachable(target)
            line += "\n               %s %s" % ("OK  " if ok else "FAIL", detail)
        _p(line)
        if target.note:
            _p("               %s" % target.note)
    _p("")
    if not args.check:
        _p("  `mcnano hosts --check` connects to each one, read-only, and says which answer.")
        _p("")
    return 0


def _resolved(args):
    """Load a package, substitute its variables and bind each item to its host."""
    pkg = packages.load(args.package)
    overrides = {}
    for pair in getattr(args, "set_var", None) or []:
        if "=" not in pair:
            raise ValueError("--set expects name=value, got %r" % pair)
        key, value = pair.split("=", 1)
        overrides[key.strip()] = value.strip()
    resolved = packages.resolve(pkg, overrides)

    # The host map is only needed when something declares a target. A package that
    # runs entirely here should not require a reader to have configured hosts at all.
    needs_hosts = any(packages.target_host(resolved, i)
                      for i in resolved.get("steps", []) + resolved.get("checks", []))
    host_map = transport.load_map(getattr(args, "hosts", None)) if needs_hosts else {}
    return resolved, packages.plan_items(resolved, host_map)


def cmd_plan(args):
    """Show everything, run nothing. Safe to run first, and meant to be."""
    pkg, items = _resolved(args)
    _p(gate.format_plan(pkg, items))
    _p("  Nothing has been run. `mcnano run %s` will ask before it does." % args.package)
    _p("")
    return 0


def cmd_run(args):
    pkg, items = _resolved(args)

    rec = record_mod.Record.create(pkg, __version__)
    try:
        approver = gate.ask(pkg, items, approver=args.approver, assume_yes=args.yes)
    except gate.GateDeclined as exc:
        rec.event("declined", str(exc))
        rec.finish("declined")
        rec.save()
        _p("  Declined: %s" % exc)
        _p("  Nothing was run. Record: %s" % rec.record_id)
        return 3

    rec.approve(approver, gate.plan_digest(package=pkg, items=items))
    gate.verify(rec, pkg, items)    # belt and braces: the plan cannot have moved
    rec.save()

    _p("  Running %d command(s)..." % len(items))
    _p("")

    marks = {"pass": "PASS", "fail": "FAIL", "skipped": "SKIP", "error": "ERR!",
             "already": "DONE"}

    def show(check, status, detail):
        _p("   [%-4s] %-32s %-9s %s"
           % (marks.get(status, status.upper()[:4]), check.get("title", check["id"])[:32],
              check["_target"].name, detail[:110]))

    status = runner.run_package(items, rec, on_result=show)
    rec.finish(status)
    rec.save()

    counts = rec.counts()
    _p("")
    # The 'already' count was missing here until 2026-07-23. Phase 01 ran sixteen
    # commands, skipped eight as already-done, and reported "8 passed" - leaving a
    # reader to wonder what happened to the other eight. A summary that does not
    # add up invites the reader to stop trusting the summary.
    # And the 'pending' count was missing here until 2026-07-24, three lines under the
    # note above, which is the more embarrassing half of the story: the run printed
    # "6 passed, 0 did not pass" against 8 commands. The lesson did not need relearning,
    # it needed applying to the new state.
    summary = "  %d passed, %d did not pass, %d skipped, %d could not run" % (
        counts["pass"], counts["fail"], counts["skipped"], counts["error"])
    if counts.get("pending"):
        summary += ", %d not installed yet" % counts["pending"]
    if counts.get("already"):
        summary += ", %d already done" % counts["already"]
    _p(summary + ".  (%d command(s) in total)" % sum(counts.values()))
    if rec.redaction_count():
        _p("  %d entr(y/ies) had credential-shaped output removed before writing."
           % rec.redaction_count())
    _p("  Record: %s" % rec.path)
    _p("  Report: mcnano report %s" % rec.record_id)
    _p("")
    # 'pending' gets its own exit code rather than borrowing 1. A reader whose CPU
    # cannot do nested virtualisation and a reader who simply has not run package 01
    # yet have completely different problems, and one of them does not have a problem.
    if status == "passed":
        return 0
    return 4 if status == "pending" else 1


def cmd_report(args):
    rec = record_mod.Record.load(args.record_id)
    pkg = None
    try:
        pkg = packages.load(rec.data["package"]["name"])
    except ValueError:
        pass                         # the package may have been removed since; report anyway
    advice = runner.advice_for(pkg, rec) if pkg else []
    md = report_mod.render(rec, advice, heading_offset=args.heading_offset)

    # d-mc-033: check anything we generate against Markua before it leaves the tool.
    problems = report_mod.check_markua(
        md, expect_chapter_heading=(args.heading_offset == 0))
    if problems:
        _p("  This report is not Markua-conformant and was NOT written:")
        for pr in problems:
            _p("    - %s" % pr)
        return 2

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(md)
        _p("  Wrote %s (%d bytes)" % (args.out, len(md)))
    else:
        sys.stdout.write(md)
    return 0


def cmd_records(args):
    ids = record_mod.list_records()
    if not ids:
        _p("No runs yet on this machine. Records live in %s" % record_mod.records_dir())
        return 0
    for rid in ids:
        rec = record_mod.Record.load(rid)
        c = rec.counts()
        _p("  %-40s %-14s %d/%d passed" % (rid, rec.data.get("status", "?"),
                                           c["pass"], sum(c.values())))
    return 0


def build_parser():
    p = argparse.ArgumentParser(
        prog="mcnano",
        description="MatrixClaw Nano - get the book's CloudStack lab running, with a "
                    "record of everything that happened on your machine.")
    p.add_argument("--version", action="version", version="mcnano " + __version__)
    sub = p.add_subparsers(dest="command")

    sp = sub.add_parser("packages", help="list what Nano can run")
    sp.set_defaults(fn=cmd_packages)

    sp = sub.add_parser("hosts", help="where Nano will run things")
    sp.add_argument("--hosts", default=None, metavar="PATH", help="use this host map")
    sp.add_argument("--check", action="store_true",
                    help="connect to each host, read-only, and report which answer")
    sp.add_argument("--forget", action="store_true",
                    help="discard the host keys Nano has learned (do this after a teardown)")
    sp.set_defaults(fn=cmd_hosts)

    sp = sub.add_parser("plan", help="show every command and its host; run nothing")
    sp.add_argument("package")
    sp.add_argument("--set", action="append", dest="set_var", metavar="NAME=VALUE",
                    help="override a package variable (repeatable)")
    sp.add_argument("--hosts", default=None, metavar="PATH", help="use this host map")
    sp.set_defaults(fn=cmd_plan)

    sp = sub.add_parser("run", help="ask, then run, then record")
    sp.add_argument("package")
    sp.add_argument("--approver", default=None, help="name for the audit record")
    sp.add_argument("--yes", action="store_true",
                    help="skip the question (recorded as non-interactive)")
    sp.add_argument("--set", action="append", dest="set_var", metavar="NAME=VALUE",
                    help="override a package variable (repeatable)")
    sp.add_argument("--hosts", default=None, metavar="PATH", help="use this host map")
    sp.set_defaults(fn=cmd_run)

    sp = sub.add_parser("report", help="render the report for a run")
    sp.add_argument("record_id")
    sp.add_argument("--out", default=None)
    sp.add_argument("--heading-offset", type=int, default=0, dest="heading_offset",
                    help="shift headings down N levels to paste inside an existing chapter")
    sp.set_defaults(fn=cmd_report)

    sp = sub.add_parser("records", help="runs recorded on this machine")
    sp.set_defaults(fn=cmd_records)
    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "fn", None):
        parser.print_help()
        return 2
    try:
        return args.fn(args)
    except ValueError as exc:
        _p("  %s" % exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
