#!/usr/bin/env python3
"""Prove that a secret cannot reach the record on disk.

The important tests here read THE FILE BACK, not the return value of the redactor.
A redactor that scrubs correctly but is bypassed by some other write path is worth
nothing, and a test that only exercises the function would not notice.

Every value below is invented for this test. Nothing real appears in this file.

    tools/test-redaction.py
"""

import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FAILURES = []


def check(name, condition, detail=""):
    if condition:
        print("  PASS  %s" % name)
    else:
        print("  FAIL  %s %s" % (name, detail))
        FAILURES.append(name)


# A stand-in for the shape that actually leaked on 2026-07-23. Invented value.
FAKE = "Zq7!tRv2-nOtARealPassword"


def main():
    from nano import redact

    print("\nRedaction: the shape that actually leaked\n")

    # The real incident: cloudstack-setup-databases printed its own argv on failure.
    leaked = ("There are more than one parameters for user:password@hostname "
              "(['cloud:@localhost', 'MC_DB_PASS=%s'])" % FAKE)
    cleaned, fired = redact.redact(leaked)
    check("the leaked argv shape is caught", FAKE not in cleaned, cleaned)
    check("it is reported as a secret env assignment",
          "secret-env-assignment" in fired, str(fired))
    check("the surrounding message survives", "more than one parameters" in cleaned)

    print("\nRedaction: other shapes a failing command can produce\n")

    cases = [
        ("MC_MYSQL_ROOT_PASS=%s" % FAKE, "MC_ variable"),
        ("MC_KVM_ROOT_PASS = %s" % FAKE, "MC_ variable with spaces"),
        ("password: %s" % FAKE, "labelled password"),
        ("--password=%s" % FAKE, "long flag"),
        ("api_key: %s" % FAKE, "api key"),
        ("mysql -uroot -p%s -e 'select 1'" % FAKE, "mysql -p glued to value"),
        ("cloudstack-setup-databases cloud:%s@localhost" % FAKE, "user:pass@host"),
        ("mysql://cloud:%s@10.100.99.11/cloud" % FAKE, "credentials in a URI"),
        # nano-03: the CloudStack / cmk API credentials (Route (a) zone/guest packages).
        ('{"registeruserkeysresponse":{"userkeys":{"apikey":"%s","secretkey":"%s"}}}'
         % (FAKE, FAKE), "registerUserKeys JSON response"),
        ('"secretkey": "%s"' % FAKE, "secretkey in JSON"),
        ("secretkey = %s" % FAKE, "secretkey assignment (labelled-credential misses this)"),
        ("cmk set secretkey %s" % FAKE, "cmk set secretkey (space form)"),
        ("http://10.100.99.11:8080/client/api?command=listZones&apikey=%s"
         "&signature=abcDEF123&response=json" % FAKE, "signed API URL apikey+signature"),
    ]
    for text, label in cases:
        cleaned, fired = redact.redact(text)
        check("%s is redacted" % label, FAKE not in cleaned, "-> %s" % cleaned)

    fake_cephx = "AQBd7xVnQmXyLhAAn9kZs2TtQ0pWvRcYuIoPlK1a2b3c4d=="
    cleaned, _ = redact.redact("key = %s" % fake_cephx)
    check("a cephx key is redacted", fake_cephx not in cleaned, cleaned)

    pem = ("-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAA\n"
           "-----END OPENSSH PRIVATE KEY-----")
    cleaned, _ = redact.redact("here it is:\n%s\nand more" % pem)
    check("a private key block is redacted", "b3BlbnNzaC1r" not in cleaned)
    check("text around the key block survives", "and more" in cleaned)

    print("\nRedaction: what must NOT be destroyed\n")

    keeps = [
        "HEALTH_OK",
        "6 osds: 6 up (since 4m), 6 in",
        "ssh -o BatchMode=yes labadmin@10.100.99.21 'ceph -s'",
        "quorum ceph-01,ceph-02,ceph-03",
        "sudo cephadm shell -- ceph orch daemon add osd ceph-01:/dev/vdb",
        "exit code was 1, expected 0",
        "mysql -uroot -p -e 'select 1'",
        "/export/secondary 10.100.99.0/24(rw,async,no_root_squash)",
        # nano-03: ordinary cmk JSON must survive the new API-credential rules intact.
        '"id": "4e309d72-868a-11f1-b12d-5254002d7d29"',
        '"allocationstate": "Enabled"',
        '"name": "Manchester"',
        '"networkname": "man-guest-01"',
        '"serviceofferingname": "Small Instance"',
        "cmk set profile localcloud",
    ]
    for text in keeps:
        cleaned, fired = redact.redact(text)
        check("untouched: %s" % text[:46], cleaned == text, "became %r via %s" % (cleaned, fired))

    print("\nThe test that matters: THE FILE ON DISK\n")

    home = tempfile.mkdtemp(prefix="nano-redaction-test-")
    os.environ["MCNANO_HOME"] = home
    try:
        # Imported after MCNANO_HOME is set so records_dir() resolves to the temp dir.
        from nano import record as record_mod

        rec = record_mod.Record.create({"name": "leaky", "title": "t"}, "test")
        rec.add_check("db", "Cloudstack databases", "fail", 1,
                      "argv was ['cloud:@localhost', 'MC_DB_PASS=%s']" % FAKE,
                      "exit code was 1, expected 0", host="mgmt-01")
        rec.add_check("ok", "Health ok", "pass", 0, "HEALTH_OK", "found 'HEALTH_OK'",
                      host="ceph-01")
        rec.finish("failed")
        rec.save()

        with open(rec.path, "r", encoding="utf-8") as fh:
            raw = fh.read()

        check("the secret is NOT in the file on disk", FAKE not in raw)
        check("the file is still valid JSON", isinstance(json.loads(raw), dict))

        data = json.loads(raw)
        entry = data["checks"][0]
        check("the redaction is declared on the entry",
              entry.get("redacted") == ["secret-env-assignment"], str(entry.get("redacted")))
        check("an event says something was removed",
              any(e["kind"] == "redaction" for e in data["events"]))
        check("the exit code survives redaction", entry["rc"] == 1)
        check("the clean entry is untouched and carries no redaction flag",
              data["checks"][1]["output_tail"] == "HEALTH_OK"
              and "redacted" not in data["checks"][1])
        check("redaction_count reports one", rec.redaction_count() == 1)

        # A reader pastes the REPORT, not the record, more often than not.
        from nano import report as report_mod
        md = report_mod.render(rec, [])
        check("the secret is NOT in the rendered report", FAKE not in md)
        check("the report says what was removed", "What was removed from this record" in md)
        check("the report admits pattern matching is not proof",
              "not proof" in md)
        check("the report is Markua-conformant", report_mod.check_markua(md) == [])

        # nano-03: the API-secret leak surface — a failing register-api-keys step whose
        # output surfaced the registerUserKeys JSON response. Prove it dies on disk too.
        rec2 = record_mod.Record.create({"name": "keys", "title": "t"}, "test")
        rec2.add_check(
            "regkeys", "Register cmk API keys", "fail", 1,
            'registerUserKeys failed: {"registeruserkeysresponse":{"userkeys":'
            '{"apikey":"%s","secretkey":"%s"}}}' % (FAKE, FAKE),
            "exit code was 1, expected 0", host="mgmt-01")
        rec2.finish("failed")
        rec2.save()
        with open(rec2.path, "r", encoding="utf-8") as fh:
            raw2 = fh.read()
        check("an API secret is NOT in the file on disk", FAKE not in raw2)
        check("the file is still valid JSON (api-key record)",
              isinstance(json.loads(raw2), dict))
        check("the api-key redaction is declared on the entry",
              "cloudstack-api-key-json" in (json.loads(raw2)["checks"][0].get("redacted") or []),
              str(json.loads(raw2)["checks"][0].get("redacted")))
    finally:
        shutil.rmtree(home, ignore_errors=True)
        os.environ.pop("MCNANO_HOME", None)

    print("")
    if FAILURES:
        print("%d FAILED: %s\n" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("All redaction checks passed.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
