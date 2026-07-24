#!/usr/bin/env python3
"""Prove that "not installed yet" is neither a pass nor a failure, and never silent.

The defect this suite guards was found on the first real reader machine, 2026-07-24.
preflight-laptop32 scored 8/8 on the maintainer's lab host and 6/8 on a fresh Ubuntu
Server -- because two of its checks look for libvirt and virt-install, which package
01 is what installs. The lab host had them already. Every reader's machine will not,
and the guide said "all eight must pass", so a capable laptop was told it had failed.

The fix must not become the loophole. An advisory check still runs, still declares an
expectation, and is still never counted as a pass -- it simply does not decide the
verdict, and it must name what will satisfy it.

    tools/test-advisory.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nano import packages

FAILURES = []


def check(name, condition, detail=""):
    if condition:
        print("  PASS  %s" % name)
    else:
        print("  FAIL  %s %s" % (name, detail))
        FAILURES.append(name)


def raises(fn, *a, **k):
    try:
        fn(*a, **k)
    except ValueError as exc:
        return exc
    return None


def test_validate():
    print("\nvalidate() -- an advisory check must name its prerequisite")

    bad = {"name": "t", "checks": [
        {"id": "c", "run": "true", "expect_output": "OK", "advisory": True}]}
    exc = raises(packages.validate, bad)
    check("refuses advisory without satisfied_by", exc is not None)
    check("...and says why",
          exc is not None and "must name its prerequisite" in str(exc))

    good = {"name": "t", "checks": [
        {"id": "c", "run": "true", "expect_output": "OK", "advisory": True,
         "satisfied_by": "package 01-platform-host"}]}
    check("accepts advisory WITH satisfied_by", raises(packages.validate, good) is None)

    # The older rule must still bite: advisory is not a way past it.
    no_expect = {"name": "t", "checks": [
        {"id": "c", "run": "true", "advisory": True, "satisfied_by": "package 01"}]}
    exc2 = raises(packages.validate, no_expect)
    check("an advisory check STILL needs an expectation", exc2 is not None,
          "advisory must not be a way around d-nano-04")


def test_shipped_preflight():
    print("\nthe shipped preflight -- read from packages/, not invented here")

    pkg = packages.load("preflight-laptop32")
    by_id = {c["id"]: c for c in pkg["checks"]}
    check("preflight has nine checks", len(pkg["checks"]) == 9,
          "found %d" % len(pkg["checks"]))

    advisory = sorted(c["id"] for c in pkg["checks"] if c.get("advisory"))
    check("exactly the three advisory checks are advisory",
          advisory == ["graphical-session", "libvirt-present",
                       "virt-install-present"], str(advisory))

    for cid in ("libvirt-present", "virt-install-present"):
        check("%s names package 01 as what satisfies it" % cid,
              "01" in by_id[cid].get("satisfied_by", ""),
              by_id[cid].get("satisfied_by"))

    # The desktop warning is advisory for a DIFFERENT reason than the other two, and
    # must not borrow their wording: a reader who installed a desktop deliberately is
    # not waiting for a package to be installed.
    g = by_id["graphical-session"]
    check("the desktop check carries its own wording",
          bool(g.get("advisory_detail")))
    check("...which does not claim something will install it",
          "installs this" not in (g.get("advisory_detail") or ""))
    check("...and tells the reader how to free the memory",
          "multi-user.target" in (g.get("advisory_detail") or ""))

    hardware = [c["id"] for c in pkg["checks"] if not c.get("advisory")]
    check("the six hardware checks are NOT advisory", len(hardware) == 6, str(hardware))
    check("...and none of them can be waived",
          all(not by_id[c].get("satisfied_by") for c in hardware))

    # The point of the whole exercise: a reader cannot fix a missing CPU feature by
    # running the build, so those checks must never become advisory.
    for cid in ("cpu-virtualisation", "nested-virtualisation", "memory-for-profile",
                "disk-space", "kvm-device", "host-is-linux"):
        check("%s still decides the verdict" % cid, not by_id[cid].get("advisory"))


def test_runner_and_report():
    print("\nthe verdict, and the summary that has to add up")

    from nano import runner  # noqa: F401

    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "nano", "runner.py"), encoding="utf-8").read()
    check("a failing advisory check becomes 'pending', not 'fail'",
          'status = "pending"' in src and 'check.get("advisory")' in src)
    check("per-check advisory wording is preferred over the default",
          'check.get("advisory_detail")' in src)
    check("pending is checked BEFORE the passed verdict",
          src.index('counts.get("pending")') < src.index('return "passed"'))
    check("pending does not short-circuit a real failure",
          src.index('counts["fail"]') < src.index('counts.get("pending")'))

    cli = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "nano", "cli.py"), encoding="utf-8").read()
    check("the CLI summary counts pending, so the totals add up",
          '", %d advisory"' in cli)
    # The summary must not describe every advisory as a missing package: one of them
    # is a desktop session that is very much installed.
    check("the summary does not call every advisory 'not installed yet'",
          "not installed yet" not in cli)
    check("pending gets its own exit code, not borrowed from failure",
          'return 4 if status == "pending" else 1' in cli)

    rep = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "nano", "report.py"), encoding="utf-8").read()
    check("the report has its own wording for pending",
          "READY - WITH ADVISORIES" in rep)
    check("the report's results line counts pending too",
          "%d advisory" in rep)


def main():
    print("\nMatrixClaw-Nano -- advisory checks and the 'pending' verdict")
    test_validate()
    test_shipped_preflight()
    test_runner_and_report()
    print("")
    if FAILURES:
        print("%d FAILED: %s\n" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("All advisory checks passed.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
