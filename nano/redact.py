"""Keeping secrets out of the record — the gate Nano did not have.

WHY THIS EXISTS, and it is not a hypothetical. On 2026-07-23, during the first real
rebuild of the lab, ``cloudstack-setup-databases`` failed and printed its own argument
list back as part of the error. One of those arguments was an expanded password. Nano
captured 600 characters of that output, exactly as designed, and wrote it to the run
record on disk. The audit trail is the thing Nano is FOR, and the first time a command
handling a secret failed, the audit trail is where the secret went.

The record had to be rewritten in place to remove it — the one thing a record is never
supposed to need.

WHAT THIS CAN AND CANNOT DO, said plainly because the alternative is a false sense of
safety. Nano never sees the reader's secrets: they live in a root-only file on the
target host and are expanded there, inside the command, on the far side of an SSH
connection. So Nano cannot redact by VALUE — it does not know the values. It redacts by
SHAPE, and shape-matching is best-effort by nature. A password that appears in output
in a form none of these patterns anticipate will not be caught.

That limitation is stated in the report rather than hidden, because a reader deciding
whether to paste a record into a bug report deserves to know it is "scrubbed of the
things we know how to recognise" and not "guaranteed clean".

WHERE IT IS APPLIED. At ``Record.add_check`` — the single point where command output
enters the record — rather than at each call site. A redactor a future code path can
forget to call is not a gate.
"""

import re

PLACEHOLDER = "<redacted>"

# Each entry is (name, compiled pattern, replacement). The name is recorded on the
# record so a reader can see WHICH kind of thing was removed without seeing the thing.
_RULES = [
    # The exact shape that leaked: a MatrixClaw secret variable echoed as NAME=value.
    ("secret-env-assignment",
     re.compile(r"\b(MC_[A-Z0-9_]*(?:PASS|PASSWORD|SECRET|TOKEN|KEY)[A-Z0-9_]*)\s*=\s*\S+"),
     r"\1=" + PLACEHOLDER),

    # Generic labelled credentials: password: x, passwd=x, api_key: x, token = x.
    ("labelled-credential",
     re.compile(r"\b(password|passwd|pwd|secret|token|api[_-]?key)(\s*[=:]\s*)(?!\s)\S+",
                re.IGNORECASE),
     r"\1\2" + PLACEHOLDER),

    # CloudStack / cmk API credentials in the JSON shape registerUserKeys RETURNS —
    # "apikey": "...", "secretkey": "...". Added nano-03 for the Route (a) cmk zone/
    # guest packages: registerUserKeys is the one call whose RESPONSE carries the secret,
    # and the labelled-credential rule above misses this shape (the closing quote sits
    # between the label and the colon) and misses "secretkey"/"signature" outright. The
    # step captures that response into a shell var and never echoes it, but a failure
    # path could still surface it, exactly as the 2026-07-23 leak did.
    ("cloudstack-api-key-json",
     re.compile(r'"(api[_-]?key|secret[_-]?key|signature)"\s*:\s*"[^"]*"', re.IGNORECASE),
     r'"\1": "' + PLACEHOLDER + '"'),

    # The same credentials in assignment / label / URL-query form: apikey=..., or
    # secretkey: ..., or &signature=... in a signed CloudStack API URL. Value stops at
    # whitespace, a quote or an ampersand so a single query param is redacted, not the URL.
    ("cloudstack-api-key-assignment",
     re.compile(r'\b(api[_-]?key|secret[_-]?key|signature)(\s*[=:]\s*)(?!\s)[^"\s&]+',
                re.IGNORECASE),
     r"\1\2" + PLACEHOLDER),

    # The cmk config-writing form: `cmk set apikey VALUE` / `cmk set secretkey VALUE`
    # (space-separated, no delimiter). Specific to `set`, so ordinary prose is untouched.
    ("cli-set-api-credential",
     re.compile(r"\b(set\s+(?:api[_-]?key|secret[_-]?key))\s+\S+", re.IGNORECASE),
     r"\1 " + PLACEHOLDER),

    # MySQL's own habit: -pTHEPASSWORD glued to the flag. Six characters minimum so a
    # bare -p, or -p followed by a short flag-like token, is left alone.
    ("mysql-p-flag",
     re.compile(r"(?<![\w-])-p(?=\S{6,})\S+"),
     "-p" + PLACEHOLDER),

    # user:password@host — CloudStack's setup-databases argument form, and every URI
    # with credentials in it.
    ("credential-in-uri",
     re.compile(r"\b([A-Za-z0-9_.\-]+):([^\s:@/]{6,})@"),
     r"\1:" + PLACEHOLDER + "@"),

    # A cephx key. `ceph auth get-or-create` prints these, and they are unmistakable:
    # base64 beginning AQ. The runbook already discards that command's stdout, but a
    # failure path could still surface one.
    ("cephx-key",
     re.compile(r"\bAQ[A-Za-z0-9+/]{28,}={0,2}"),
     "<redacted cephx key>"),

    # A private key block, whole. Nothing about it belongs in an audit trail.
    ("private-key-block",
     re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
                re.DOTALL),
     "<redacted private key>"),
]


def redact(text):
    """Return (cleaned_text, [rule names that fired]).

    Order matters a little: the specific env-assignment rule runs before the generic
    labelled-credential rule, so MC_DB_PASS=x is reported as what it is rather than as
    a generic match.
    """
    if not text:
        return text, []
    fired = []
    for name, pattern, replacement in _RULES:
        cleaned = pattern.sub(replacement, text)
        if cleaned != text:
            fired.append(name)
            text = cleaned
    return text, fired


def scan(text):
    """Which rules WOULD fire, without changing anything. For tests and for auditing."""
    return [name for name, pattern, _ in _RULES if text and pattern.search(text)]
