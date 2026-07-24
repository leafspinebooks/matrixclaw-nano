# MatrixClaw Nano

A small, honest helper for getting the CloudStack lab from *Sovereign Cloud: Apache
CloudStack 4.22.1.0 LTS - A Production Deployment Guide* running on your own machine,
with a record of everything it did.

Nano was designed and engineered to support readers of that book, which is available
at <https://leanpub.com/apache-cloudstack-deployment-guide>. It builds the book's
reader lab, and it is of little use without it.

Nano is a **fast path through the book, never a substitute for it**. Not every reader
wants a tool, and the book carries the full detail in its own right - Appendix B has
the entire build, command by command, including the parts that went wrong. If you
would rather work from the page, work from the page. Nano is for when you would
rather not.

Start with [docs/READER-GUIDE.md](docs/READER-GUIDE.md). It walks the whole build in
order. This file is the shorter answer to "what is this, and should I trust it".

## What it does

- **Preflight.** Checks whether your machine can host the lab at all - virtualisation
  extensions, nested virtualisation, `/dev/kvm`, memory, disk, libvirt. Read-only, and
  the right thing to run first.
- **Builds the whole lab, in eleven gated packages** - the platform host, the five
  networks, the seven virtual machines, Ceph, secondary storage, the management
  server, both compute hosts, then the CloudStack zone and the first guest. Every
  command comes from the runbooks that built the real estate.
- **Reaches the machines it builds.** You run Nano on the platform host - the machine
  in front of you. The seven virtual machines it creates are then configured over SSH,
  with key authentication and no interactive prompts. Each package says which host it
  targets, and Nano shows you that host before it runs anything.
- **Asks before it runs anything.** Every command is printed in full first, together
  with the machine it will run on and, where that machine is not this one, the exact
  `ssh` invocation. Your approval is bound to that list, so if a command changes - or
  if it is aimed at a different host, or if the warning you were shown changes - the
  approval is void.
- **Keeps a record you own.** Plain JSON on your own disk, with the exit code and
  output of every command and the host it ran on. Nothing is sent anywhere. Nano has
  no network calls at all. Output is scrubbed of credential-shaped text before it is
  written, and any entry that was scrubbed says so - see the limits of that below.
- **Writes a report** in Markdown you can keep, paste, or send to whoever is helping.

## What it does not do

Said plainly, because a tool that overstates itself is worse than no tool:

- **It is not MatrixClaw.** MatrixClaw is the research framework the lab was actually
  built with. Nano is a separate, much smaller, fresh implementation that shares no
  code with it.
- **It does not decide anything for you.** Every mutating step is gated, always, with
  the default answer being no.
- **It does not phone home.** No telemetry, no accounts, no uploads.
- **A passing preflight is not a promise.** It reports what those checks observed on
  this machine at that moment. The lab is proven by building it.
- **Redaction is pattern matching, not a guarantee.** Nano never sees your secrets -
  they live in a root-only file on the target host and are expanded there - so it
  cannot recognise a value it has never been told. It removes what it knows how to
  recognise, and says when it did. Read a record before you paste it anywhere.
- **Publishing anything is your decision, taken by hand.** Nothing here uploads a
  record, a report or a screenshot anywhere. That is not a setting you have to find
  and turn off; there is no code that could.

## Requirements

Python 3, and nothing else. No dependencies, no install step, no virtualenv. The lab
host itself must run Linux; Nano will tell you plainly if the machine you run it on
cannot host the lab.

The 32 GB profile is the target: a successful build allocates about 29 GiB of RAM
across the seven VMs and uses about 70 GB of disk. Those are measured from a real
build, not estimated, which is why preflight's floors are 30 GiB and 200 GB.

## Using it

```bash
./bin/mcnano packages                    # the build, in order
./bin/mcnano hosts                       # where each phase will run
./bin/mcnano hosts --check               # ... and whether those hosts answer
./bin/mcnano plan preflight-laptop32     # show every command, run nothing
./bin/mcnano run  preflight-laptop32     # ask, then run, then record
./bin/mcnano plan 01-platform-host       # the first build phase
./bin/mcnano records                     # what has run on this machine
./bin/mcnano report <record-id>          # the report for a run
```

`plan` is always safe and always the right place to start: it runs nothing at all.

One value has no default and cannot have one - your SSH public key, which package 03
puts on the seven machines it builds:

```bash
./bin/mcnano run 03-virtual-machines --set deployer_pubkey="$(cat ~/.ssh/id_ed25519.pub)"
```

The published packages had the author's own key and account name stripped out before
release. Nano refuses to plan package 03 until you supply yours, rather than building
seven machines around a placeholder.

## Where things run

Run Nano **on the platform host**. Phases 01 to 03 build that host, its networks and
its virtual machines, and run locally. Phases 04 to 11 configure those virtual
machines and run on them over SSH.

`hosts/laptop32.json` maps each name to an address and a login. It holds no
credentials - only the *path* to your private key, which never leaves your disk and
never enters a package, a record or a report. Point Nano at your own map with
`--hosts`, or by setting `MCNANO_HOSTS`.

```bash
./bin/mcnano hosts --check               # read-only; connects and reports
```

Worth running before phase 04. A host that does not answer now will not answer in the
middle of a build either.

Two things Nano will not do. It will not fall back to running a command locally when a
package names a host it cannot find - it stops instead, because a command meant for
`ceph-01` is not a command you want run on your own machine. And it will not prompt for
a password: every connection is `BatchMode`, so a missing key fails immediately and
visibly rather than hanging inside an approved run.

Nano keeps its own `known_hosts` under `~/.matrixclaw-nano/` rather than editing yours.
Rebuilding the estate mints fresh host keys for the same addresses, and this way that
is Nano's problem rather than yours - delete that file when you tear the lab down.

Run the phases in the order they are numbered - each assumes the one before it. Every
step carries an `already` probe, so if a phase stops half way you can simply run it
again: the parts that landed are skipped rather than repeated.

Records live in `~/.matrixclaw-nano/records/`. Set `MCNANO_HOME` to put them
elsewhere. They are yours - delete them whenever you like.

## Where the checks come from

Every check derives from a real run recorded in the MatrixClaw lab, on the 32 GB
profile. Checks that have never been executed against a real host do not ship. If Nano
tells you something passed, a machine actually said so.

The packages are generated from the lab's own runbooks rather than hand-copied, so
they cannot quietly drift from the artefacts that were proven. The generator itself
needs the framework repository and is not part of this release or of Nano's runtime.

The same rule governs this README: nothing above is a plan or an intention. It is what
the tool does today.

## Disclaimer, warranty and risk

**This software is provided "as is", without warranty of any kind, and is used
entirely at your own risk.** To the fullest extent permitted by law, the authors and
copyright holders accept no liability for any loss or damage arising from it,
including loss of data. See `DISCLAIMER.md` for the full statement and `LICENSE`
sections 15 and 16, which govern.

Three things worth knowing before you start, rather than after:

- **Some steps destroy data by design.** Package 03 rebuilds the seven virtual
  machines from a fresh image and discards their disks. Take your own backups, and use
  a machine you can afford to rebuild.
- **This is a laboratory, not a production system.** It is deliberately convenient
  rather than hardened: SSH password authentication is enabled, the admin account has
  passwordless `sudo`, the compute hosts get a root password because CloudStack
  requires one, and the addressing and account names are the book's published
  defaults. Build it on an isolated machine or a trusted private network, and do not
  expose it to the internet.
- **It installs software we did not write** - Apache CloudStack, Ceph, MySQL, libvirt,
  Ubuntu - under those projects' own licences and their own absence of warranty.

This is an unofficial, independent project. It is **not affiliated with, authorised
by, sponsored by, or endorsed by The Apache Software Foundation** or by any other
company or project named here. Apache, Apache CloudStack, CloudStack, and the Apache
feather logo are trademarks or registered trademarks of The Apache Software
Foundation; all other product names and brands are the property of their respective
owners, used for identification and reference only.

Published under the **Leaf Spine Books** imprint, which is real. The similarly-named
publisher appearing in the book's narrative is fictional -- a narrative device, with
any resemblance to real organisations coincidental.

Nothing here is professional advice, and none of it creates a support obligation.

## Licence

**AGPL-3.0.** See `LICENSE` - the full, unmodified text from gnu.org.

Copyright (c) 2026 Spiral Matrix Limited and Michael John Leslie Hinsley.

See `DISCLAIMER.md` for the full statement.

Nano is a fresh implementation and contains no MatrixClaw code. That separation is
deliberate: the framework's own licence is a separate question, and deriving an AGPL
tool from it would make the licensing story incoherent.

The lab scripts the book publishes are Apache-2.0, which flows into an AGPL-3.0 tool
cleanly.

## What Nano has actually done

On **23 July 2026** Nano tore down a working seven-VM CloudStack estate on real
hardware and rebuilt it from nothing, on a 32 GB laptop-class host, through its own
gate and over its own SSH transport. Every phase was approved by a human against a
plan digest before it ran.

On **24 July 2026** it did so again, from zero, and went further: the two packages
that build the CloudStack zone and the first guest ran too, and the rebuilt estate
passed the lab's 24-checkpoint acceptance suite **24 of 24** - against a suite that
had been deliberately hardened first, so that score is measured with a stricter ruler
than the previous run's, not an easier one.

Those two runs found **fourteen defects between them**, and this is the part worth
reading before you trust the tool. Among them:

- five checks that **could not fail** - including one that reported a MySQL password
  as already set when no password had ever been set, and one that reported a
  management server as ready when it was returning 503 to every request
- both compute hosts configured with the **wrong IP address**, the same copy-paste
  trap the book itself warns about
- a target host that packages **declared and Nano ignored**, so a phase meant for a
  storage node would have run on the reader's own machine
- **a password written into a run record**, because a failing command printed its own
  arguments and Nano had no redaction gate
- a guest whose root volume landed on **whichever storage pool the allocator felt
  like**, so an earlier run's "correct" result had been luck

All are fixed. The point is not that they existed - it is that a first clean build had
already passed and had shown none of them. Every one needed a machine that was already
in some state. If you are running Nano a second time after a failed attempt, you are on
the path where these live, and that path is now the tested one.

## Status

Early, real, and exercised. Twelve packages: preflight plus the eleven build phases.
Preflight is proven on a machine that passes it and on one that does not. The build
packages have been run end to end, by Nano, against real hardware, and the estate they
produced passed the full acceptance suite.

What has **not** happened yet, stated because it is the honest gap: nobody has built
this lab from the *published* release, on hardware other than the machine Nano was
developed on. That test is the next one, and until it has run, treat "it will work on
your laptop" as likely rather than proven.
