"""The run record — the audit trail, and the reader owns it.

Nano writes every record to the reader's own machine, in plain JSON they can open
in any editor. Not telemetry, not a cloud service, not a format that needs Nano to
read it back. If Nano is deleted tomorrow the records remain readable.

The record is append-only within a run: entries are added as things happen, never
rewritten afterwards to look tidier. A check that failed stays failed in the record
even if it passes on the next run, because the point of the trail is what actually
happened, not what the current state is.
"""

import json
import os
import platform
import time

from . import redact

RECORDS_DIRNAME = os.path.join(".matrixclaw-nano", "records")


def records_dir():
    """Where records live. Honours MCNANO_HOME so a reader can put them anywhere."""
    home = os.environ.get("MCNANO_HOME")
    if home:
        return os.path.join(home, "records")
    return os.path.join(os.path.expanduser("~"), RECORDS_DIRNAME)


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def new_id(package_name, taken=None):
    """A record id that is unique on this machine.

    Timestamps alone are not enough: two runs in the same second collide, and the
    second silently overwrites the first. An audit trail that quietly loses a record
    is worse than no audit trail, because it still looks complete. So the id is
    resolved against what already exists, and a suffix is added if needed.
    """
    base = "nano-%s-%s" % (time.strftime("%Y%m%d-%H%M%S", time.gmtime()), package_name)
    exists = taken if taken is not None else _existing_ids()
    if base not in exists:
        return base
    n = 2
    while "%s-%d" % (base, n) in exists:
        n += 1
    return "%s-%d" % (base, n)


def _existing_ids():
    d = records_dir()
    if not os.path.isdir(d):
        return set()
    return set(f[:-5] for f in os.listdir(d) if f.endswith(".json"))


class Record(object):
    """One Nano run. Created at plan time, added to as the run proceeds."""

    def __init__(self, data, path):
        self.data = data
        self.path = path

    # -- lifecycle ---------------------------------------------------------
    @classmethod
    def create(cls, package, nano_version):
        rid = new_id(package["name"])
        data = {
            "record_id": rid,
            "nano_version": nano_version,
            "created_utc": _now(),
            "status": "planned",
            "package": {
                "name": package["name"],
                "title": package.get("title", package["name"]),
                "source": package.get("source", ""),
                "target_host": package.get("target_host"),
                "check_count": len(package.get("checks", [])),
            },
            # Recorded so a reader (or whoever helps them) can see what this ran on.
            # Nothing here identifies a person; it is the machine's own description.
            "host": {
                "system": platform.system(),
                "release": platform.release(),
                "machine": platform.machine(),
                "python": platform.python_version(),
            },
            "approval": None,
            "checks": [],
            "events": [],
        }
        path = os.path.join(records_dir(), rid + ".json")
        if os.path.exists(path):
            # Independent of new_id()'s own check, because a record is evidence and
            # overwriting one must be impossible rather than merely unlikely.
            raise IOError("refusing to overwrite an existing record at %s" % path)
        rec = cls(data, path)
        rec.event("create", "record created for package '%s'" % package["name"])
        rec.save()
        return rec

    @classmethod
    def load(cls, record_id):
        path = os.path.join(records_dir(), record_id + ".json")
        # UTF-8 explicitly: a record is evidence, and evidence must read the same
        # on the machine that wrote it and the machine someone reads it back on.
        with open(path, "r", encoding="utf-8") as fh:
            return cls(json.load(fh), path)

    def save(self):
        d = os.path.dirname(self.path)
        if not os.path.isdir(d):
            os.makedirs(d)
        # Write via a temporary file so an interrupted run cannot leave a
        # half-written record that neither Nano nor the reader can parse.
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, indent=2, sort_keys=False)
            fh.write("\n")
        os.rename(tmp, self.path)

    # -- content -----------------------------------------------------------
    def event(self, kind, message):
        self.data["events"].append({"at": _now(), "kind": kind, "message": message})

    def approve(self, approver, plan_digest):
        """Bind the approval to the exact plan that was shown.

        If the package changes after approval, the digest no longer matches and the
        approval is void. A reader who said yes to one set of commands has not said
        yes to a different set.
        """
        self.data["approval"] = {
            "approver": approver,
            "granted_utc": _now(),
            "plan_digest": plan_digest,
        }
        self.data["status"] = "approved"
        self.event("approve", "approved by %s for plan %s" % (approver, plan_digest))

    def add_check(self, check_id, title, status, rc, tail, detail, host=None):
        # THE REDACTION GATE, applied HERE and only here — the single point at which
        # command output enters the record. Putting it at each call site instead would
        # make it something a future code path can forget, and a gate you can forget
        # is not a gate. Nothing reaches self.data["checks"] unscrubbed.
        clean_tail, tail_rules = redact.redact(tail)
        clean_detail, detail_rules = redact.redact(detail)
        fired = sorted(set(tail_rules) | set(detail_rules))

        entry = {
            "id": check_id,
            "title": title,
            "status": status,          # pass | fail | skipped | error | already
            # WHICH MACHINE. Once Nano could reach more than one host, a record that
            # said only what happened stopped being a complete answer: the same
            # command means different things on the platform host and on ceph-01.
            "host": host or "this machine",
            "rc": rc,
            "detail": clean_detail,
            "output_tail": clean_tail,
            "at": _now(),
        }
        if fired:
            # SAY THAT SOMETHING WAS REMOVED. A record that quietly drops material is
            # a record that lies by omission, and the reader cannot tell a command
            # that printed nothing from one whose output was scrubbed.
            entry["redacted"] = fired
            self.event("redaction",
                       "'%s' produced output matching %s; the matching text was "
                       "replaced before this record was written"
                       % (check_id, ", ".join(fired)))
        self.data["checks"].append(entry)

    def finish(self, status):
        self.data["status"] = status
        self.data["finished_utc"] = _now()
        self.event("finish", "run finished with status '%s'" % status)

    # -- reading -----------------------------------------------------------
    @property
    def record_id(self):
        return self.data["record_id"]

    def redaction_count(self):
        """How many recorded entries had something removed from them."""
        return sum(1 for chk in self.data.get("checks", []) if chk.get("redacted"))

    def counts(self):
        c = {"pass": 0, "fail": 0, "skipped": 0, "error": 0, "already": 0}
        for chk in self.data.get("checks", []):
            c[chk["status"]] = c.get(chk["status"], 0) + 1
        return c


def list_records():
    d = records_dir()
    if not os.path.isdir(d):
        return []
    return sorted(f[:-5] for f in os.listdir(d)
                  if f.endswith(".json") and not f.startswith("."))
