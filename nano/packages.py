"""Lab packages — what Nano knows how to run.

A package is plain JSON: a list of checks, each with the command to run, what the
result should look like, why it matters, and what to do when it fails. JSON rather
than YAML on purpose — the standard library reads it, so Nano needs nothing
installed, and there is no parser here to get subtly wrong.

Where the content comes from, and the honesty rule that governs it: every check in a
shipped package derives from a real run recorded in the MatrixClaw lab. A check that
has never been executed against a real host does not go in a package. If Nano tells a
reader something passed, a machine actually said so.
"""

import json
import os
import re

PACKAGE_DIRNAME = "packages"


def package_dir():
    """Packages ship beside the code; MCNANO_PACKAGES overrides for development."""
    override = os.environ.get("MCNANO_PACKAGES")
    if override:
        return override
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(here), PACKAGE_DIRNAME)


def available():
    """Every package in the directory, ignoring what is not one.

    Dot-prefixed files are skipped, and the reason is a real failure rather than
    tidiness: unpacking Nano from an archive made on macOS leaves an AppleDouble
    `._name.json` beside every real file. Nano listed all ten of them as runnable
    packages and then crashed trying to parse the first one. A reader copying Nano
    between machines should not have to know what an AppleDouble is.
    """
    d = package_dir()
    if not os.path.isdir(d):
        return []
    return sorted(f[:-5] for f in os.listdir(d)
                  if f.endswith(".json") and not f.startswith("."))


def load(name):
    path = os.path.join(package_dir(), name + ".json")
    if not os.path.isfile(path):
        raise ValueError(
            "no package named '%s'. Available: %s" % (name, ", ".join(available()) or "(none)"))
    # UTF-8 explicitly, never the machine's locale: a package written on one machine
    # must read identically on another, and a reader whose shell has no LANG set
    # should not get a decoding traceback out of a tool that is meant to be plain.
    try:
        with open(path, "r", encoding="utf-8") as fh:
            pkg = json.load(fh)
    except UnicodeDecodeError as exc:
        raise ValueError("package file %s is not valid UTF-8 text: %s" % (path, exc))
    except ValueError as exc:
        raise ValueError("package file %s is not valid JSON: %s" % (path, exc))
    validate(pkg)
    return pkg


def validate(pkg):
    """Refuse a malformed package loudly rather than half-running it.

    A package has STEPS (which change the machine) and/or CHECKS (which do not).
    Steps carry an `already` probe so a re-run skips work that is done rather than
    repeating it; checks carry an expectation so they can honestly fail.
    """
    if "name" not in pkg:
        raise ValueError("package is missing required field 'name'")
    if not pkg.get("steps") and not pkg.get("checks"):
        raise ValueError("package '%s' has neither steps nor checks" % pkg["name"])

    seen = set()
    for step in pkg.get("steps", []):
        for field in ("id", "run"):
            if field not in step:
                raise ValueError("a step in '%s' is missing '%s'" % (pkg["name"], field))
        if step["id"] in seen:
            raise ValueError("package '%s' has duplicate id '%s'" % (pkg["name"], step["id"]))
        seen.add(step["id"])

    for chk in pkg.get("checks", []):
        for field in ("id", "run"):
            if field not in chk:
                raise ValueError("a check in '%s' is missing '%s'" % (pkg["name"], field))
        if chk["id"] in seen:
            raise ValueError("package '%s' has duplicate id '%s'" % (pkg["name"], chk["id"]))
        seen.add(chk["id"])
        # A check must say how it is judged, or it can never honestly fail.
        if not any(k in chk for k in ("expect_output", "expect_rc")):
            raise ValueError(
                "check '%s' declares no expectation — a check that cannot fail is not a check"
                % chk["id"])
        # An ADVISORY check does not decide the run's verdict, so it is exactly the
        # shape of loophole d-nano-04 exists to close. It is allowed only where the
        # package can name what will satisfy it: "not yet, and here is what installs
        # it" is a fact about sequence; "not important" is an opinion, and Nano does
        # not get to hold one about a reader's machine.
        if chk.get("advisory") and not chk.get("satisfied_by"):
            raise ValueError(
                "check '%s' is advisory but does not say what satisfies it — an "
                "advisory check must name its prerequisite, or it is simply a check "
                "that cannot fail" % chk["id"])
    return True


# The marker the generator writes where it deliberately removed a value of the
# author's own — an account name, a deploy key — because shipping it would hand
# every reader something that is not theirs (tools/build-packages.py,
# READER_OVERRIDES). The removal is right. What it leaves behind is a placeholder
# in every sense except the one `unresolved()` can see: substitution SUCCEEDS, so
# the command runs carrying a string that cannot possibly work.
SENTINEL = "REPLACE-WITH"


def sentinels(vars_):
    """Variables still holding a deliberately-unusable value the reader must supply."""
    return sorted(k for k, v in vars_.items()
                  if isinstance(v, str) and SENTINEL in v)


def variables(pkg, overrides=None):
    """Resolve a package's variables. Reader overrides win over the shipped defaults.

    Refuses a value the generator marked as one the reader must supply. This is the
    same rule as the unresolved-placeholder refusal below and exists for the same
    reason, but it has to be written separately because the two failures do not look
    alike: `{{deployer_pubkey}}` is visibly unfinished, whereas
    REPLACE-WITH-YOUR-OWN-SSH-PUBLIC-KEY substitutes cleanly and reads like a value.
    Nano would have written it into cloud-init's ssh_authorized_keys on all seven
    machines without a word. A default that is known to be wrong is not a default.
    """
    resolved = dict(pkg.get("variables", {}))
    for key, value in (overrides or {}).items():
        if key not in resolved:
            raise ValueError(
                "package '%s' has no variable '%s'. It has: %s"
                % (pkg["name"], key, ", ".join(sorted(resolved)) or "(none)"))
        resolved[key] = value

    stuck = sentinels(resolved)
    if stuck:
        raise ValueError(
            "package '%s' needs %s you have to supply: %s still holds the shipped "
            "placeholder. Nano ships a placeholder rather than the author's own value, "
            "because a key or an account that is not yours is worse than none at all. "
            "Set it with: --set %s=\"$(cat ~/.ssh/id_ed25519.pub)\" (for a public key), "
            "or --set %s=<value>."
            % (pkg["name"],
               "a value" if len(stuck) == 1 else "values",
               ", ".join(stuck), stuck[0], stuck[0]))
    return resolved


def _substitute(text, vars_):
    for key, value in vars_.items():
        text = text.replace("{{%s}}" % key, str(value))
    return text


def unresolved(text):
    """Any {{placeholder}} left after substitution — a package must never run with one."""
    return sorted(set(re.findall(r"\{\{([a-zA-Z_0-9]+)\}\}", text)))


def resolve(pkg, overrides=None):
    """Return the package with every command fully substituted.

    Refuses to return a package with an unresolved placeholder in it. Running a
    command containing a literal {{mgmt_ip}} would do something arbitrary on a
    reader's machine, and failing loudly here is the only safe answer.
    """
    vars_ = variables(pkg, overrides)
    out = json.loads(json.dumps(pkg))          # deep copy; never mutate the loaded package
    out["_variables_used"] = vars_
    for group in ("steps", "checks"):
        for item in out.get(group, []):
            for field in ("run", "already"):
                if field in item:
                    item[field] = _substitute(item[field], vars_)
                    missing = unresolved(item[field])
                    if missing:
                        raise ValueError(
                            "%s '%s' still contains unresolved variable(s): %s. "
                            "Set them with --set name=value."
                            % (group[:-1], item["id"], ", ".join(missing)))
    return out


def commands(pkg):
    """The exact command list, in order — what the gate digests and shows."""
    return ([s["run"] for s in pkg.get("steps", [])] +
            [c["run"] for c in pkg.get("checks", [])])


def target_host(pkg, item):
    """Which host an item runs on: the item's own declaration, else the package's.

    A step may override the package. 05-ceph-cluster is the case that needs it: the
    package runs on the platform host and orchestrates the Ceph nodes from there, so
    the package-level host is right for it, while other packages target a VM outright.
    Neither is a special case in the code — the item wins if it says anything.
    """
    return item.get("target_host") or pkg.get("target_host")


def plan_items(pkg, host_map=None):
    """Every step and check, in execution order, each bound to its resolved target.

    This is the single ordered list that the gate displays, the approval digest
    covers, and the runner walks. One list, built once, so the thing approved and the
    thing executed cannot drift apart.
    """
    from . import transport

    items = []
    for kind, group in (("step", pkg.get("steps", [])), ("check", pkg.get("checks", []))):
        for raw in group:
            item = dict(raw)
            item["_kind"] = kind
            item["_target"] = transport.resolve(target_host(pkg, raw), host_map)
            items.append(item)
    return items
