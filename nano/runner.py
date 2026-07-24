"""Running the checks, and judging them honestly.

Three rules about judgement, each of them learned from a real failure in the lab this
tool descends from:

  1. A CHECK THAT CANNOT FAIL IS NOT A CHECK. Expectations are exact-match markers,
     not bare numerals that could appear inside an error message. The lab once had a
     check pass because the digit it wanted appeared inside "ERROR 1045 (28000)".
  2. NOT APPLICABLE IS NOT A PASS. A check that cannot run here is recorded as
     'skipped', with the reason, and the report says so. Silence is not success.
  3. THE OUTPUT IS KEPT. Every check records its exit code and the tail of what it
     printed, so a reader can see why, not just what.
"""

import platform
import subprocess

from . import transport

TAIL_CHARS = 600


def _platform_key():
    return platform.system().lower()          # 'linux', 'darwin', 'windows'


def applicable(check, target=None):
    """(applies, reason). A check may declare the platforms it means anything on.

    The declaration is about the machine the command RUNS ON. For a remote target
    that is not this machine, and Nano cannot answer the question from here without
    asking the far end — so it does not pretend to. A remote check is attempted and
    judged on what it actually returns, which is the honest answer anyway: if the
    command is meaningless there, it fails there, visibly, rather than being filtered
    out on evidence about the wrong host.
    """
    only = check.get("applies_to")
    if not only:
        return True, ""
    if target is not None and not target.local:
        return True, ""
    here = _platform_key()
    if here in [p.lower() for p in only]:
        return True, ""
    return False, "this check applies to %s; this machine is %s" % (
        "/".join(only), platform.system())


def judge(check, rc, output):
    """Decide pass/fail from the recorded result. Returns (status, detail)."""
    if "expect_rc" in check and rc != check["expect_rc"]:
        return "fail", "exit code was %s, expected %s" % (rc, check["expect_rc"])
    if "expect_output" in check:
        marker = check["expect_output"]
        if marker not in output:
            return "fail", "did not find %r in the output" % marker
        return "pass", "found %r" % marker
    if "expect_rc" in check:
        return "pass", "exit code %s as expected" % rc
    # packages.validate() prevents this; kept so a bad path fails loudly, not silently
    return "error", "check declares no expectation"


def _execute(command, target, timeout):
    """Run one command on its target. Returns (rc, output) or raises.

    The only place in Nano that starts a process. Everything else decides WHAT to run
    and WHERE; this decides nothing.
    """
    argv, use_shell = target.invocation(command)
    proc = subprocess.Popen(argv, shell=use_shell,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, _ = proc.communicate()
        if isinstance(out, bytes):
            out = out.decode("utf-8", "replace")
        raise TimeoutError("no result after %ss on %s; the output so far was: %s"
                           % (timeout, target.name, (out or "").strip()[-200:] or "(nothing)"))
    if isinstance(out, bytes):
        out = out.decode("utf-8", "replace")
    return proc.returncode, out


def run_check(check, timeout=60, target=None):
    """Execute one check. Never raises for a failing check — that is data, not an error."""
    target = target or transport.LOCAL
    applies, why = applicable(check, target)
    if not applies:
        return "skipped", None, "", why

    try:
        rc, out = _execute(check["run"], target, timeout)
    except TimeoutError as exc:
        # A timeout is not a pass and not a silent failure: it is its own outcome,
        # recorded with the host it happened on so a reader knows where to look.
        return "error", None, "", "timed out: %s" % exc
    except Exception as exc:                     # the command could not be started
        return "error", None, "", "could not run on %s: %s" % (target.name, exc)

    tail = out[-TAIL_CHARS:] if out else ""
    status, detail = judge(check, rc, out)
    return status, rc, tail, detail


def probe(step, target=None):
    """Ask the machine whether a step's work is already done. rc 0 means yes.

    This is what makes a re-run safe: a package that stopped half way can simply be
    run again, and the steps that already landed are skipped rather than repeated.
    A probe never changes anything, and it asks the SAME host the step would run on —
    asking the wrong machine would answer a question nobody put.
    """
    if "already" not in step:
        return False
    target = target or transport.LOCAL
    try:
        rc, _out = _execute(step["already"], target, step.get("probe_timeout", 120))
        return rc == 0
    except Exception:
        return False


def run_steps(items, record, on_result=None):
    """Run the mutating steps, in order, FAIL-FAST.

    Unlike checks, steps stop at the first failure. Later steps assume earlier ones
    landed, so continuing past a failure builds on top of a broken machine and turns
    one clear problem into several confusing ones. The record shows exactly where it
    stopped, and on which host, and a re-run resumes there because the probes skip
    what is done.
    """
    for step in [i for i in items if i["_kind"] == "step"]:
        target = step["_target"]
        title = step.get("title", step["id"])
        applies, why = applicable(step, target)
        if not applies:
            record.add_check(step["id"], title, "skipped", None, "", why, host=target.name)
            if on_result:
                on_result(step, "skipped", why)
            continue

        if probe(step, target):
            detail = "already done on %s; not repeated" % target.name
            record.add_check(step["id"], title, "already", None, "", detail, host=target.name)
            if on_result:
                on_result(step, "already", detail)
            continue

        status, rc, tail, detail = run_check(
            dict(step, expect_rc=step.get("expect_rc", 0)),
            timeout=step.get("timeout", 900), target=target)
        record.add_check(step["id"], title, status, rc, tail, detail, host=target.name)
        if on_result:
            on_result(step, status, detail)
        if status != "pass":
            record.event("stopped", "step '%s' did not succeed on %s: %s"
                         % (step["id"], target.name, detail))
            record.save()
            return False
    return True


def run_package(items, record, on_result=None):
    """Run every step then every check, in order, recording each. Returns the status.

    Nano does not stop at the first failing CHECK. A reader wants the whole picture in
    one pass, not one problem at a time — and checks are read-only, so there is
    nothing to protect by stopping. Steps are the opposite case and stop at the first
    failure; see run_steps.
    """
    completed = run_steps(items, record, on_result=on_result)
    if not completed:
        record.save()
        return "stopped"

    for check in [i for i in items if i["_kind"] == "check"]:
        target = check["_target"]
        status, rc, tail, detail = run_check(
            check, timeout=check.get("timeout", 60), target=target)
        # A prerequisite that has not been installed YET is not a fault in the
        # reader's machine, and reporting it as one told six capable laptops in a row
        # that they had failed. It is still not a pass: it is recorded as 'pending',
        # named with the thing that will satisfy it, and it never counts toward the
        # passes. What it does not do is decide the verdict.
        if status == "fail" and check.get("advisory"):
            status = "pending"
            detail = "not yet: %s installs this." % check["satisfied_by"]
        record.add_check(check["id"], check.get("title", check["id"]),
                         status, rc, tail, detail, host=target.name)
        if on_result:
            on_result(check, status, detail)
    record.save()

    counts = record.counts()
    if counts["error"]:
        return "error"
    if counts["fail"]:
        return "failed"
    if counts.get("pending"):
        # Everything that judges the machine itself passed, but something the build
        # installs is not there yet. A distinct verdict, because "passed" would hide
        # it and "failed" would blame the reader for it.
        return "pending"
    if counts.get("already") and counts["pass"]:
        return "passed"
    if counts["pass"] == 0:
        # Everything skipped. Not a pass, and the report must not imply one.
        return "not-applicable"
    return "passed"


def advice_for(pkg, record):
    """Collect the package's own advice for whatever did not pass.

    Advice is written into the package beside the check it belongs to, so it is
    reviewable with the check rather than generated on the fly. Nano does not
    improvise remedies for a reader's machine.
    """
    by_id = {c["id"]: c for c in (pkg.get("steps", []) + pkg.get("checks", []))}
    out = []
    for chk in record.data.get("checks", []):
        if chk["status"] in ("pass",):
            continue
        source = by_id.get(chk["id"], {})
        text = source.get("advice")
        if text:
            out.append({"id": chk["id"], "title": chk["title"],
                        "status": chk["status"], "advice": text})
    return out
