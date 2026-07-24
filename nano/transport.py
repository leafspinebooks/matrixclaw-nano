"""Where a command runs — this machine, or a host reached over SSH.

Nano started able to run commands only on the machine it was invoked from. That was
enough for the first three packages, which build the platform host, its networks and
its virtual machines. It was not enough for the six after them, which configure the
machines that were just created: Ceph, secondary storage, the management server and
the two compute hosts all live on the nested VMs, and Nano had no way to reach them.

Worse than "no way to reach them", and this is the defect this module actually fixes:
those packages already carried ``target_host: ceph-01`` and Nano IGNORED it. Running
04-ceph-bootstrap would have bootstrapped a Ceph cluster on the lab host itself. A
declared target that is silently not honoured is more dangerous than no target at all,
so ``resolve`` REFUSES a host it does not know rather than quietly falling back to
local. Falling back is only correct when nothing was declared.

Three rules, and they are the gate's rules carried onto the network:

  1. THE HOST IS PART OF THE PLAN. The gate prints the target host beside every
     command, and the approval digest covers the host as well as the command text.
     Moving a command to a different machine voids an existing approval, exactly as
     editing the command does — it is a different thing being done.
  2. KEY AUTH, NO PROMPTS. BatchMode=yes throughout, so a missing key fails cleanly
     and immediately instead of hanging on a password prompt inside a gated run.
  3. THE RECORD SAYS WHERE. Every step and check records the host it executed on, so
     a reader reading the trail afterwards never has to infer it.

Stdlib only, and written for Nano (d-nano-01). This shares no code with MatrixClaw's
transport; it does not need to, because it does much less. There is no ProxyJump here
and no inventory: Nano runs ON the lab host, which is where a reader sits, and the
estate VMs are one hop away on the management network.
"""

import json
import os

DEFAULT_PORT = 22
DEFAULT_CONNECT_TIMEOUT = 15


class Target(object):
    """One place a command can run. ``local`` is the machine Nano is running on."""

    def __init__(self, name, local=False, user=None, address=None, port=DEFAULT_PORT,
                 identity_file=None, known_hosts=None, strict_host_key_checking="accept-new",
                 connect_timeout=DEFAULT_CONNECT_TIMEOUT, note=""):
        self.name = name
        self.local = local
        self.user = user
        self.address = address
        self.port = port
        self.identity_file = identity_file
        self.known_hosts = known_hosts
        self.strict_host_key_checking = strict_host_key_checking
        self.connect_timeout = connect_timeout
        self.note = note

    # -- description -------------------------------------------------------
    @property
    def destination(self):
        if self.local:
            return None
        return "%s@%s" % (self.user, self.address) if self.user else self.address

    def describe(self):
        """One line for the gate. A reader must be able to tell local from remote."""
        if self.local:
            return "%s (this machine)" % self.name
        port = "" if self.port == DEFAULT_PORT else " port %d" % self.port
        return "%s (%s%s, over ssh)" % (self.name, self.destination, port)

    # -- execution ---------------------------------------------------------
    def ssh_options(self):
        opts = [
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=%d" % self.connect_timeout,
            "-o", "StrictHostKeyChecking=%s" % self.strict_host_key_checking,
        ]
        if self.known_hosts:
            opts += ["-o", "UserKnownHostsFile=%s" % os.path.expanduser(self.known_hosts)]
        if self.identity_file:
            # IdentitiesOnly only makes sense once an identity is named; without it
            # ssh would be told to use only the keys it has not been given.
            opts += ["-o", "IdentityFile=%s" % os.path.expanduser(self.identity_file),
                     "-o", "IdentitiesOnly=yes"]
        if self.port != DEFAULT_PORT:
            opts += ["-p", str(self.port)]
        return opts

    def invocation(self, command):
        """(argv, use_shell) for one command on this target.

        Local commands go to a shell because packages use pipes, redirections and
        multi-line loops that only a shell understands. Remote commands are passed to
        ssh as a SINGLE argument and interpreted by the shell on the far end, so
        nothing here has to quote a command into a local shell and get it wrong.
        """
        if self.local:
            return command, True
        return ["ssh"] + self.ssh_options() + [self.destination, command], False


def _quote(text):
    """A POSIX-shell-safe rendering, for DISPLAY only — nothing is executed from this."""
    if text and all(c.isalnum() or c in "@%_-+=:,./" for c in text):
        return text
    return "'" + text.replace("'", "'\"'\"'") + "'"


def command_line(command, target):
    """Exactly what will run, as a reader could type it. Shown at the gate.

    For a remote target this is the real ssh invocation with the real options, not a
    tidied summary. The gate's promise is that nothing runs that was not displayed,
    and a display that hides the transport would not keep it.
    """
    argv, use_shell = target.invocation(command)
    if use_shell:
        return command
    return " ".join(_quote(a) for a in argv)


# -- the host map ----------------------------------------------------------

def hosts_path(explicit=None):
    """Where the host map comes from: --hosts, then MCNANO_HOSTS, then the shipped one."""
    if explicit:
        return explicit
    env = os.environ.get("MCNANO_HOSTS")
    if env:
        return env
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(here), "hosts", "laptop32.json")


def load_map(explicit=None):
    """Read the host map. Returns {name: Target}. Refuses a malformed file loudly."""
    path = hosts_path(explicit)
    if not os.path.isfile(path):
        raise ValueError(
            "no host map at %s. Nano needs one to run a package that declares a "
            "target host. Point at yours with --hosts, or set MCNANO_HOSTS." % path)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except UnicodeDecodeError as exc:
        raise ValueError("host map %s is not valid UTF-8 text: %s" % (path, exc))
    except ValueError as exc:
        raise ValueError("host map %s is not valid JSON: %s" % (path, exc))

    defaults = data.get("defaults", {})
    targets = {}
    for name, spec in (data.get("hosts") or {}).items():
        if spec.get("local"):
            targets[name] = Target(name, local=True, note=spec.get("note", ""))
            continue
        if not spec.get("address"):
            raise ValueError(
                "host '%s' in %s has no address and is not marked local" % (name, path))
        targets[name] = Target(
            name,
            user=spec.get("user", defaults.get("user")),
            address=spec["address"],
            port=int(spec.get("port", defaults.get("port", DEFAULT_PORT))),
            identity_file=spec.get("identity_file", defaults.get("identity_file")),
            known_hosts=spec.get("known_hosts", defaults.get("known_hosts")),
            strict_host_key_checking=spec.get(
                "strict_host_key_checking",
                defaults.get("strict_host_key_checking", "accept-new")),
            connect_timeout=int(spec.get(
                "connect_timeout", defaults.get("connect_timeout", DEFAULT_CONNECT_TIMEOUT))),
            note=spec.get("note", ""))
    if not targets:
        raise ValueError("the host map at %s declares no hosts" % path)
    return targets


LOCAL = Target("this machine", local=True)


def resolve(host_name, host_map):
    """The target for a declared host name.

    No declaration means this machine — that is the fallback, and it is the ONLY
    fallback. A name that is declared but unknown raises, because the alternative is
    running a command meant for ceph-01 on the reader's own host.
    """
    if not host_name:
        return LOCAL
    if host_map and host_name in host_map:
        return host_map[host_name]
    known = ", ".join(sorted(host_map or {})) or "(none)"
    raise ValueError(
        "package targets host '%s', which is not in the host map. Known hosts: %s. "
        "Nano will not guess, and will not run it here instead."
        % (host_name, known))


def known_hosts_path():
    """Nano's own known_hosts. Never the reader's — Nano does not edit ~/.ssh."""
    home = os.environ.get("MCNANO_HOME")
    if home:
        return os.path.join(home, "known_hosts")
    return os.path.join(os.path.expanduser("~"), ".matrixclaw-nano", "known_hosts")


def forget_known_hosts():
    """Discard the host keys Nano has learned. Returns a line describing what happened.

    Needed after a teardown: the rebuilt estate answers on the same seven addresses
    with new keys, and every connection would otherwise fail with a warning about a
    changed host key. Nano keeps its own file precisely so this is one command rather
    than an edit to the reader's ~/.ssh/known_hosts, which it never touches.
    """
    path = known_hosts_path()
    if not os.path.exists(path):
        return "Nothing to forget: %s does not exist." % path
    with open(path, "r", encoding="utf-8") as fh:
        count = sum(1 for line in fh if line.strip())
    os.remove(path)
    return ("Forgot %d host key(s) and removed %s. Your own ~/.ssh/known_hosts was "
            "not touched." % (count, path))


def reachable(target):
    """Cheap read-only liveness probe. (ok, detail). Never used to judge a check."""
    if target.local:
        return True, "this machine"
    import subprocess
    argv, _ = target.invocation("echo NANO-REACHABLE")
    try:
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out, _unused = proc.communicate()
    except Exception as exc:
        return False, "could not start ssh: %s" % exc
    if isinstance(out, bytes):
        out = out.decode("utf-8", "replace")
    if proc.returncode == 0 and "NANO-REACHABLE" in out:
        return True, "answered over ssh as %s" % target.destination
    return False, "ssh exited %s: %s" % (proc.returncode, out.strip()[-200:] or "(no output)")
