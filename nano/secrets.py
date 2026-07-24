"""Compose the on-target secrets files. Pure functions, no I/O, no network.

This module is DELIBERATELY separate from the runner, the gate and the record, and
imports none of them. It is the one place in the project that arranges the reader's
secret VALUES, and it exists apart from Nano's engine on purpose:

  Nano never sees a secret, and that is a structural guarantee, not a careful habit.
  Secrets live in a root-only file on each target host and are expanded THERE, on the
  far side of an SSH connection, so the value never enters the process that writes the
  audit record. That guarantee was bought the hard way -- on 2026-07-23 a command that
  handled a password failed, printed its own arguments, and Nano wrote the password
  into a run record exactly as designed (d-nano-09). The fix was not better redaction;
  it was to keep the value out of Nano entirely.

The placement helper (bin/mc-place-secrets) that uses this module is likewise NOT the
runner: it writes no record, and the value transits it no more than it transits a
reader's own shell when they type it. What this module does is compose the exact file
CONTENTS from the reader's three chosen passwords and the fetched Ceph key, quoting
each value so a password with any character sources back byte-for-byte. It is pure so
it can be tested without a host, which is where the composition logic can actually be
got wrong.

The variable-to-host mapping is the single source of truth for which secret each
package needs, and it is asserted against the shipped packages in
tools/test-secrets-compose.py -- a check the packages themselves cannot drift from
without the test noticing.
"""

import shlex

# Which MC_* variable each host must carry, derived from what the packages source:
#   07-management-server  (mgmt-01)  MC_MYSQL_ROOT_PASS, MC_DB_PASS
#   10-manchester-zone    (mgmt-01)  MC_HOST_ROOTPASS, MC_RBD_SECRET
#   08-compute-host-1     (kvm-01)   MC_KVM_ROOT_PASS
#   09-compute-host-2     (kvm-02)   MC_KVM_ROOT_PASS
#
# The three reader-chosen passwords are the KEYS a reader fills in; the fourth value,
# MC_RBD_SECRET, is the Ceph client key, fetched from a storage node rather than typed.
#
# MC_HOST_ROOTPASS and MC_KVM_ROOT_PASS are the SAME password by construction here,
# both taken from `host_root_password`. The two-must-match rule (the host password
# CloudStack uses to add a compute host is the password that host was given) used to
# be a sentence in the guide that a reader could get wrong; deriving both from one
# input makes it impossible to get wrong.
TEMPLATE_KEYS = ("mysql_root_password", "cloudstack_db_password", "host_root_password")


def compose(values, rbd_secret):
    """Return {host_name: file_contents} for every host that needs a secrets file.

    `values` is the parsed template: the three reader-chosen passwords.
    `rbd_secret` is the Ceph client.cloudstack key, fetched separately.

    Every value is shell-quoted, so the file sources back to the exact bytes the reader
    supplied no matter what characters the password contains -- the failure a naive
    `NAME=value` invites the moment a password holds a space or a quote.
    """
    missing = [k for k in TEMPLATE_KEYS if not values.get(k)]
    if missing:
        raise ValueError(
            "the template is missing a value for: %s. Every password must be filled in."
            % ", ".join(missing))
    if not rbd_secret:
        raise ValueError(
            "no Ceph secret was supplied. It is read from client.cloudstack on a "
            "storage node; if that could not be reached, the storage cluster "
            "(package 05) may not be built yet.")

    host_root = values["host_root_password"]

    mgmt = _file([
        ("MC_MYSQL_ROOT_PASS", values["mysql_root_password"]),
        ("MC_DB_PASS", values["cloudstack_db_password"]),
        ("MC_HOST_ROOTPASS", host_root),
        ("MC_RBD_SECRET", rbd_secret),
    ])
    kvm = _file([
        ("MC_KVM_ROOT_PASS", host_root),
    ])
    return {"mgmt-01": mgmt, "kvm-01": kvm, "kvm-02": kvm}


def _file(pairs):
    """One env file. A leading comment says what wrote it; values are shell-quoted.

    No trailing newline is omitted and no value is echoed anywhere: the whole point is
    that these bytes exist only inside an SSH pipe and the root-only file at the end
    of it.
    """
    lines = [
        "# MatrixClaw-Nano lab secrets. Root-only, mode 600. Placed by mc-place-secrets.",
        "# Sourced on this host by the build; never sent anywhere.",
    ]
    for name, value in pairs:
        lines.append("%s=%s" % (name, shlex.quote(value)))
    return "\n".join(lines) + "\n"


def parse_template(text):
    """Parse a `key=value` template. Comments (#) and blank lines ignored.

    Values are taken verbatim after the first '=', with surrounding whitespace removed
    -- a trailing space in a password is far more likely to be a typo than intended,
    and an invisible one would be a miserable thing to debug on a host you cannot see
    the value on.
    """
    values = {}
    for raw in text.split("\n"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError("template line is not key=value: %r" % raw)
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    unknown = sorted(set(values) - set(TEMPLATE_KEYS))
    if unknown:
        raise ValueError(
            "the template has key(s) it should not: %s. Expected only: %s"
            % (", ".join(unknown), ", ".join(TEMPLATE_KEYS)))
    return values
