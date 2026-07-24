#!/usr/bin/env python3
"""Prove that a value the reader must supply cannot be run as if it were supplied.

The generator deliberately strips the author's own account name and deploy key
before a package ships (tools/build-packages.py, READER_OVERRIDES) and leaves a
REPLACE-WITH marker behind. That removal is right. The gap this suite guards is
what happened next: the marker SUBSTITUTES CLEANLY, so `unresolved()` — which only
sees a leftover {{placeholder}} — had nothing to report, and package 03 would have
written REPLACE-WITH-YOUR-OWN-SSH-PUBLIC-KEY into cloud-init's ssh_authorized_keys
on all seven machines without a word to anybody.

The decisive tests below read THE PACKAGES AS SHIPPED rather than synthetic ones,
because the defect was in a shipped package and a test over invented fixtures would
have passed on the day it existed.

    tools/test-sentinels.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nano import packages

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG_DIR = os.path.join(ROOT, "packages")

FAILURES = []


def check(name, condition, detail=""):
    if condition:
        print("  PASS  %s" % name)
    else:
        print("  FAIL  %s %s" % (name, detail))
        FAILURES.append(name)


def raises(fn, *args, **kwargs):
    """Return the ValueError a call raises, or None if it did not raise one."""
    try:
        fn(*args, **kwargs)
    except ValueError as exc:
        return exc
    return None


def test_detection():
    print("\nsentinels() — what counts as a value the reader must supply")

    check("finds a REPLACE-WITH value",
          packages.sentinels({"k": "REPLACE-WITH-YOUR-OWN-SSH-PUBLIC-KEY"}) == ["k"])
    check("finds it mid-string",
          packages.sentinels({"k": "ssh-ed25519 AAAA<<REPLACE-WITH-YOUR-KEY>> lab"}) == ["k"])
    check("leaves an ordinary string alone",
          packages.sentinels({"lab_user": "labadmin"}) == [])
    check("leaves an integer alone (no isinstance crash)",
          packages.sentinels({"mgmt_ram": 7168}) == [])
    check("leaves a value that merely says 'replace' alone",
          packages.sentinels({"note": "replace the disk if it fails"}) == [])
    check("names every stuck variable, sorted",
          packages.sentinels({"b": "REPLACE-WITH-X", "a": "REPLACE-WITH-Y",
                              "c": "fine"}) == ["a", "b"])


def test_refusal():
    print("\nvariables() — the refusal itself")

    pkg = {"name": "t", "variables": {"deployer_pubkey": "REPLACE-WITH-YOUR-OWN-SSH-PUBLIC-KEY"}}

    exc = raises(packages.variables, pkg)
    check("refuses a package carrying a sentinel", exc is not None)
    check("the message names the variable",
          exc is not None and "deployer_pubkey" in str(exc))
    check("the message says how to fix it",
          exc is not None and "--set" in str(exc))
    check("the message says why a placeholder ships at all",
          exc is not None and "not yours" in str(exc))

    check("an override clears the refusal",
          raises(packages.variables, pkg,
                 {"deployer_pubkey": "ssh-ed25519 AAAATEST reader@laptop"}) is None)
    check("the override is the value that survives",
          packages.variables(pkg, {"deployer_pubkey": "ssh-ed25519 AAAATEST r@l"}
                             )["deployer_pubkey"] == "ssh-ed25519 AAAATEST r@l")

    empty = raises(packages.variables, pkg, {"deployer_pubkey": ""})
    check("an EMPTY override is accepted rather than silently re-defaulted",
          empty is None)


def test_shipped_packages():
    """The decisive ones: the packages as a reader receives them."""
    print("\nthe shipped packages — read from packages/, not invented here")

    names = sorted(f[:-5] for f in os.listdir(PKG_DIR) if f.endswith(".json"))
    check("all thirteen packages are present", len(names) == 13,
          "found %d: %s" % (len(names), ", ".join(names)))

    exc = raises(packages.resolve, packages.load("03-virtual-machines"))
    check("03-virtual-machines REFUSES to resolve as shipped", exc is not None)
    check("...naming deployer_pubkey",
          exc is not None and "deployer_pubkey" in str(exc))

    others = [n for n in names if n != "03-virtual-machines"]
    stuck = [n for n in others if raises(packages.resolve, packages.load(n)) is not None]
    check("every OTHER shipped package still resolves cleanly", stuck == [],
          "refused: %s" % ", ".join(stuck))

    # The point of the whole exercise: with a key supplied, the marker is GONE from
    # every command — not merely absent from the variables dict.
    resolved = packages.resolve(packages.load("03-virtual-machines"),
                                {"deployer_pubkey": "ssh-ed25519 AAAATEST reader@laptop"})
    body = "\n".join(packages.commands(resolved))
    check("with a key supplied, no command carries the marker",
          packages.SENTINEL not in body)
    check("...and the supplied key is what landed in cloud-init",
          "ssh-ed25519 AAAATEST reader@laptop" in body)


def main():
    print("\nMatrixClaw-Nano — reader-supplied values (sentinel refusal)")
    test_detection()
    test_refusal()
    test_shipped_packages()

    print("")
    if FAILURES:
        print("%d FAILED: %s\n" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("All sentinel checks passed.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
