#!/usr/bin/env python3
"""Prove the SSH transport's safety properties. Stdlib only; no network needed.

These are the claims the transport makes, and a claim without a test is an opinion.
Everything here is offline — the one test that needs a real host is deliberately NOT
here, because a reachability test that mocks the network proves nothing about the
network. That one is `mcnano hosts --check` against the real estate, and its output
belongs in the session record.

    tools/test-transport.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nano import gate, packages, transport            # noqa: E402

FAILURES = []
SKIPPED = []


def check(name, condition, detail=""):
    if condition:
        print("  PASS  %s" % name)
    else:
        print("  FAIL  %s %s" % (name, detail))
        FAILURES.append(name)


def skip(name, reason):
    """A test that cannot run HERE. Recorded, never counted as a pass (d-nano-04)."""
    print("  SKIP  %s — %s" % (name, reason))
    SKIPPED.append("%s (%s)" % (name, reason))


def expect_raises(name, fn, fragment):
    try:
        fn()
    except Exception as exc:
        check(name, fragment in str(exc), "raised %r, wanted %r in it" % (str(exc), fragment))
        return
    check(name, False, "did not raise at all")


HOST_MAP = {
    "lab-host": transport.Target("lab-host", local=True),
    "ceph-01": transport.Target("ceph-01", user="labadmin", address="10.100.99.21",
                                identity_file="~/.ssh/id_ed25519"),
    "kvm-01": transport.Target("kvm-01", user="labadmin", address="10.100.99.31",
                               identity_file="~/.ssh/id_ed25519"),
}


def main():
    print("\nTransport: resolution\n")

    # An undeclared host is the ONLY case that falls back to this machine.
    check("no declared host resolves to this machine",
          transport.resolve(None, HOST_MAP).local)
    check("a declared local host resolves local",
          transport.resolve("lab-host", HOST_MAP).local)
    check("a declared remote host resolves remote",
          not transport.resolve("ceph-01", HOST_MAP).local)

    # The defect this module exists to fix: a declared host that Nano does not know
    # must STOP, not quietly run the command here instead.
    expect_raises("an unknown host is refused, not run locally",
                  lambda: transport.resolve("ceph-99", HOST_MAP),
                  "will not guess")

    print("\nTransport: invocation\n")

    local_argv, local_shell = HOST_MAP["lab-host"].invocation("echo hello")
    check("local commands go to a shell", local_shell and local_argv == "echo hello")

    argv, use_shell = HOST_MAP["ceph-01"].invocation("echo hello && ls | wc -l")
    check("remote commands do NOT go through a local shell", use_shell is False)
    check("remote command is one argument, unmangled",
          argv[-1] == "echo hello && ls | wc -l",
          "got %r" % argv[-1])
    check("remote destination is user@address", argv[-2] == "labadmin@10.100.99.21")
    check("BatchMode is always set", "BatchMode=yes" in argv)
    check("IdentitiesOnly accompanies an identity file",
          "IdentitiesOnly=yes" in argv and any("IdentityFile=" in a for a in argv))

    # No identity file named means ssh picks its own keys; forcing IdentitiesOnly
    # there would tell ssh to use only the keys it was never given.
    bare = transport.Target("x", user="u", address="1.2.3.4")
    check("no identity file means no IdentitiesOnly",
          "IdentitiesOnly=yes" not in bare.invocation("true")[0])

    print("\nTransport: display\n")

    shown = transport.command_line("echo 'it worked'", HOST_MAP["ceph-01"])
    check("the display includes the real ssh options", "BatchMode=yes" in shown)
    check("the display quotes the remote command", "'echo '\"'\"'it worked'\"'\"''" in shown,
          "got %s" % shown)
    check("a local display is just the command",
          transport.command_line("echo hi", HOST_MAP["lab-host"]) == "echo hi")

    print("\nGate: the host is part of the approval\n")

    pkg = {"name": "t", "steps": [{"id": "s1", "run": "whoami", "mutates": True}], "checks": []}

    PKG_CEPH = dict(pkg, target_host="ceph-01")
    PKG_KVM = dict(pkg, target_host="kvm-01")
    PKG_LOCAL = dict(pkg, target_host="lab-host")
    on_ceph = packages.plan_items(PKG_CEPH, HOST_MAP)
    on_kvm = packages.plan_items(PKG_KVM, HOST_MAP)
    on_local = packages.plan_items(PKG_LOCAL, HOST_MAP)

    check("same command, different host, different digest",
          gate.plan_digest(PKG_CEPH, on_ceph) != gate.plan_digest(PKG_KVM, on_kvm))
    check("same command, remote vs local, different digest",
          gate.plan_digest(PKG_CEPH, on_ceph) != gate.plan_digest(PKG_LOCAL, on_local))
    check("the same plan digests the same twice",
          gate.plan_digest(PKG_CEPH, on_ceph) == gate.plan_digest(
              PKG_CEPH, packages.plan_items(PKG_CEPH, HOST_MAP)))

    edited = packages.plan_items(
        dict(pkg, target_host="ceph-01",
             steps=[{"id": "s1", "run": "whoami ", "mutates": True}]), HOST_MAP)
    check("editing the command still voids the approval",
          gate.plan_digest(PKG_CEPH, on_ceph) != gate.plan_digest(PKG_CEPH, edited))

    # The hole found in use on 2026-07-23: the commands do not move, but what the
    # reader was WARNED about does. That must void the approval too.
    reclassified = packages.plan_items(
        dict(pkg, target_host="ceph-01",
             steps=[{"id": "s1", "run": "whoami", "mutates": False}]), HOST_MAP)
    check("re-declaring a step read-only voids the approval",
          gate.plan_digest(PKG_CEPH, on_ceph) != gate.plan_digest(PKG_CEPH, reclassified))

    retitled = packages.plan_items(
        dict(pkg, target_host="ceph-01",
             steps=[{"id": "s1", "run": "whoami", "mutates": True,
                     "title": "Something else entirely"}]), HOST_MAP)
    check("retitling a step voids the approval",
          gate.plan_digest(PKG_CEPH, on_ceph) != gate.plan_digest(PKG_CEPH, retitled))

    reframed = dict(PKG_CEPH, description="A completely different explanation.")
    check("rewriting the package's own description voids the approval",
          gate.plan_digest(PKG_CEPH, on_ceph) !=
          gate.plan_digest(reframed, packages.plan_items(reframed, HOST_MAP)))

    print("\nGate: destructive steps are called out and cannot be quietly unmarked\n")

    danger = {"name": "d", "target_host": "ceph-01",
              "steps": [{"id": "wipe", "run": "deploy-db", "mutates": True,
                         "destructive": True, "already": "test -d /db",
                         "destroys": "the existing database and everything in it"}],
              "checks": []}
    danger_items = packages.plan_items(danger, HOST_MAP)
    text_d = gate.format_plan(danger, danger_items)
    check("the plan says DESTROY EXISTING DATA", "DESTROY EXISTING DATA" in text_d)
    check("the plan says what is destroyed",
          "the existing database and everything in it" in text_d)
    check("the plan tells the reader to back up first", "take a backup" in text_d)
    check("the plan credits the probe as the thing preventing it",
          "only thing preventing" in text_d)

    unmarked = dict(danger, steps=[dict(danger["steps"][0], destructive=False, destroys="")])
    check("the plan shows the destructive step's own probe",
          "skipped only if this command succeeds" in text_d and "test -d /db" in text_d)

    reprobed = dict(danger, steps=[dict(danger["steps"][0], already="false")])
    check("changing a probe voids the approval",
          gate.plan_digest(danger, danger_items) !=
          gate.plan_digest(reprobed, packages.plan_items(reprobed, HOST_MAP)))

    check("un-marking a step as destructive voids the approval",
          gate.plan_digest(danger, danger_items) !=
          gate.plan_digest(unmarked, packages.plan_items(unmarked, HOST_MAP)))

    print("\nGenerator: a destructive step without a probe is refused\n")

    # build-packages.py is a development tool: it reads the framework repository, which
    # readers do not have, so it is not part of the published release. These two checks
    # therefore cannot run from a published clone. They SKIP with their reason rather
    # than failing — a test that cannot run here is not a failure — and equally they are
    # never counted as passes, which is the half of that rule that actually costs
    # something (d-nano-04). Found by the export's own "does it stand alone" check.
    generator = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build-packages.py")
    if not os.path.isfile(generator):
        skip("refuses a destructive step with no already probe",
             "build-packages.py is not in a published clone")
        skip("refuses a destructive step that does not say what it destroys",
             "build-packages.py is not in a published clone")
    else:
        import importlib.util
        spec = importlib.util.spec_from_file_location("bp", generator)
        bp = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bp)
        unprobed = bp.audit({"name": "u", "checks": [],
                             "steps": [{"id": "wipe", "run": "true", "destructive": True}]})
        check("refuses a destructive step with no already probe",
              any("no 'already' probe" in p for p in unprobed))
        check("refuses a destructive step that does not say what it destroys",
              any("does not say what it destroys" in p for p in unprobed))

    print("\nGate: the plan text tells the truth\n")

    text = gate.format_plan(dict(pkg, target_host="ceph-01"), on_ceph)
    check("the plan names the target host", "ceph-01" in text)
    check("the plan shows the ssh invocation", "via: ssh " in text)
    check("the plan says a step changes a machine", "CHANGE a machine" in text)

    print("\nA step may override its package\n")

    mixed = {"name": "m", "target_host": "lab-host",
             "steps": [{"id": "here", "run": "true"},
                       {"id": "there", "run": "true", "target_host": "ceph-01"}],
             "checks": []}
    items = packages.plan_items(mixed, HOST_MAP)
    check("the package host applies by default", items[0]["_target"].name == "lab-host")
    check("a step's own host wins", items[1]["_target"].name == "ceph-01")

    print("\nEvery shipped package resolves against the shipped host map\n")

    shipped = transport.load_map()
    for name in packages.available():
        pkg_ = packages.load(name)
        try:
            items = packages.plan_items(pkg_, shipped)
            hosts = sorted({i["_target"].name for i in items})
            check("%s resolves (%s)" % (name, ", ".join(hosts)), True)
        except ValueError as exc:
            check("%s resolves" % name, False, str(exc))

    print("")
    if FAILURES:
        print("%d FAILED: %s\n" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    if SKIPPED:
        # Said out loud, because "all passed" over a suite that quietly ran fewer
        # checks than it looks like is the exact dishonesty d-nano-04 exists to stop.
        print("All transport checks passed, %d NOT RUN here:" % len(SKIPPED))
        for item in SKIPPED:
            print("  - %s" % item)
        print("")
        return 0
    print("All transport checks passed.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
