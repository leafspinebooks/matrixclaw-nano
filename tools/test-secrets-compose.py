#!/usr/bin/env python3
"""Prove the secrets composition, without a host and without a real secret.

The placement itself needs three live VMs and cannot be unit-tested; the part that can
be got wrong on a keyboard is the COMPOSITION -- which variable lands on which host,
whether the two-must-match password really matches, and whether a value with an awkward
character survives being written and sourced back. That is pure, so it is tested here.

The decisive test reads the SHIPPED packages and asserts the mapping in nano/secrets.py
still matches what each package actually sources, so the two cannot drift apart in
silence. Every value below is invented.

    tools/test-secrets-compose.py
"""

import glob
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nano import secrets

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "packages")
FAILURES = []


def check(name, ok, detail=""):
    print("  %s  %s%s" % ("PASS" if ok else "FAIL", name, ("  " + detail) if detail else ""))
    if not ok:
        FAILURES.append(name)


VALUES = {
    "mysql_root_password": "mysql-Root-1",
    "cloudstack_db_password": "db-Pass-2",
    "host_root_password": "host-Root-3",
}
RBD = "AQBd0aFakeCephKeyForTestOnly==="


def test_mapping():
    print("\ncompose() -- the right variables on the right hosts")
    files = secrets.compose(VALUES, RBD)

    check("three hosts get a file", sorted(files) == ["kvm-01", "kvm-02", "mgmt-01"])

    mgmt = files["mgmt-01"]
    for v in ("MC_MYSQL_ROOT_PASS", "MC_DB_PASS", "MC_HOST_ROOTPASS", "MC_RBD_SECRET"):
        check("mgmt-01 carries %s" % v, ("%s=" % v) in mgmt)
    check("mgmt-01 does NOT carry the kvm-only var", "MC_KVM_ROOT_PASS" not in mgmt)

    kvm = files["kvm-01"]
    check("kvm-01 carries MC_KVM_ROOT_PASS", "MC_KVM_ROOT_PASS=" in kvm)
    check("kvm-01 carries nothing else secret",
          not any(v in kvm for v in ("MC_MYSQL", "MC_DB_PASS", "MC_RBD", "MC_HOST_ROOTPASS")))
    check("both compute hosts get the identical file", files["kvm-01"] == files["kvm-02"])


def test_two_must_match():
    print("\ncompose() -- the host and kvm passwords cannot fail to match")
    files = secrets.compose(VALUES, RBD)
    # Extract the quoted values back the way the shell would, by sourcing.
    host = _sourced(files["mgmt-01"])["MC_HOST_ROOTPASS"]
    kvm = _sourced(files["kvm-01"])["MC_KVM_ROOT_PASS"]
    check("MC_HOST_ROOTPASS == MC_KVM_ROOT_PASS", host == kvm and host == "host-Root-3",
          "host=%r kvm=%r" % (host, kvm))


def test_awkward_values_survive():
    print("\ncompose() -- a password with hostile characters sources back intact")
    hostile = "a b'c\"d$e`f\\g;h|i"
    vals = dict(VALUES, mysql_root_password=hostile)
    files = secrets.compose(vals, RBD)
    got = _sourced(files["mgmt-01"])["MC_MYSQL_ROOT_PASS"]
    check("value with space/quote/dollar/backtick survives byte-for-byte",
          got == hostile, "got %r" % got)
    # And the fetched Ceph key, which ends in '==', must not be mangled.
    check("the Ceph key with trailing == survives",
          _sourced(files["mgmt-01"])["MC_RBD_SECRET"] == RBD)


def test_refusals():
    print("\ncompose()/parse -- refusing incomplete input")
    from_missing = _raises(secrets.compose, dict(VALUES, host_root_password=""), RBD)
    check("refuses a blank password", from_missing is not None)
    check("...naming the missing key",
          from_missing is not None and "host_root_password" in str(from_missing))
    check("refuses an empty Ceph secret",
          _raises(secrets.compose, VALUES, "") is not None)

    parsed = secrets.parse_template(
        "# a comment\n\nmysql_root_password = a\ncloudstack_db_password=b\nhost_root_password=c\n")
    check("parse ignores comments and blanks, trims spaces",
          parsed == {"mysql_root_password": "a", "cloudstack_db_password": "b",
                     "host_root_password": "c"})
    check("parse refuses an unknown key",
          _raises(secrets.parse_template, "surprise=1") is not None)


def test_matches_shipped_packages():
    """The check that stops drift: the mapping must match what packages source."""
    print("\nthe mapping matches the SHIPPED packages")
    want = {}  # host -> set(vars the packages source there)
    host_of = {"07-management-server": "mgmt-01", "10-manchester-zone": "mgmt-01",
               "08-compute-host-1": "kvm-01", "09-compute-host-2": "kvm-02"}
    for f in glob.glob(os.path.join(PKG, "*.json")):
        stem = os.path.basename(f)[:-5]
        if stem not in host_of:
            continue
        d = json.load(open(f))
        found = set()
        for it in d.get("steps", []) + d.get("checks", []):
            found |= set(re.findall(r"MC_[A-Z_]+", it.get("run", "") + it.get("already", "")))
        want.setdefault(host_of[stem], set()).update(found)

    files = secrets.compose(VALUES, RBD)
    for host, needed in want.items():
        placed = set(re.findall(r"(MC_[A-Z_]+)=", files[host]))
        check("%s: everything the packages source is placed" % host,
              needed <= placed, "packages want %s, placed %s" % (sorted(needed), sorted(placed)))


def _sourced(contents):
    """Source the file in a real shell and dump the MC_ vars back out."""
    script = contents + "\nfor v in ${!MC_@}; do printf '%s\\t%s\\n' \"$v\" \"${!v}\"; done"
    out = subprocess.run(["bash", "-c", script], capture_output=True, text=True).stdout
    result = {}
    for line in out.split("\n"):
        if "\t" in line:
            k, v = line.split("\t", 1)
            result[k] = v
    return result


def _raises(fn, *a):
    try:
        fn(*a)
    except Exception as exc:
        return exc
    return None


def main():
    print("\nMatrixClaw-Nano -- secrets composition")
    test_mapping()
    test_two_must_match()
    test_awkward_values_survive()
    test_refusals()
    test_matches_shipped_packages()
    print("")
    if FAILURES:
        print("%d FAILED: %s\n" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("All secrets-compose checks passed.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
