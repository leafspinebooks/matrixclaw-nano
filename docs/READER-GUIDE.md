# MatrixClaw-Nano: A Reader's Guide to Building the Lab

This guide takes you from a 32 GB laptop to a working Apache CloudStack lab -- the
seven-VM "Manchester in miniature" estate the book builds -- using MatrixClaw-Nano to
run the build for you, one gated step at a time.

Nano is a fast path, not a replacement for the book. Every command Nano runs is one
you could read and type yourself; the book explains *why* each one matters, and not
every reader wants an agent driving. Use this guide to move quickly and keep an audit
trail; use the book to understand what you built.

Everything below was demonstrated by a real from-zero build: the estate was torn down
to nothing and rebuilt by Nano, packages 01 through 11, then measured against the
lab's 24-checkpoint acceptance suite, which passed 24 of 24. The durations quoted are
measured from that build's run records, not estimated.

## Before anything else: what you are taking on

This lab is **provided as is, without warranty, and built entirely at your own risk.**
The full statement is in `DISCLAIMER.md`, and it is worth two minutes. The short
version, because these three affect what you do next:

- **Some steps destroy data by design.** Package 03 rebuilds all seven virtual machines
  from a fresh image and discards their disks. Nano shows you every command before it
  runs one and will not proceed without your approval -- but the approval is yours.
  Take your own backups, and build this on a machine you can afford to rebuild.
- **This is a laboratory, not a production system.** It is deliberately convenient
  rather than hardened: SSH password authentication is on, the admin account has
  passwordless `sudo`, the compute hosts get a root password because CloudStack needs
  one to add them, and the addresses and account names are the book's published
  defaults. **Build it on an isolated machine or a network you control, and do not
  expose it to the internet.** Do not reuse its credentials anywhere that matters.
- **It is unofficial.** This project is not affiliated with, authorised by, sponsored
  by, or endorsed by The Apache Software Foundation, and it installs a great deal of
  software written by other people under their own licences.

Nano exists to support readers of *Sovereign Cloud: Apache CloudStack 4.22.1.0 LTS --
A Production Deployment Guide*, available at
<https://leanpub.com/apache-cloudstack-deployment-guide>. This guide gets the lab
built; the book explains why each step matters, which is the part that transfers to
systems other than this one.

## What this guide is, and is not

Nano does four things, and only these:

- It runs the published lab packages -- the same build the book describes, expressed
  as gated commands.
- It keeps an audit record you own: plain JSON on your disk, one file per run, sent
  nowhere.
- It does basic troubleshooting and tells you what it checked and what it did not.
- It produces a final report you can read or paste into a bug report.

Nano is not MatrixClaw-lite. It does not design topologies, drive a browser, or manage
an estate over time. It builds the reader lab and proves it, and says plainly where its
knowledge ends.

Publishing anything from this lab -- scripts, screenshots, records -- is your decision,
taken by hand. Nano never sends your data anywhere.

## Before you start: the preflight

Nano ships a read-only preflight package that answers one question: can this machine
host the 32 GB lab? Run it first.

```
bin/mcnano run preflight-laptop32
```

It checks eight things. **Six of them judge your machine, and all six must pass** --
they are the ones you cannot fix by running the build:

| Marker | Means |
|---|---|
| `LINUX-OK` | the host runs Linux |
| `VIRT-OK` | the processor supports hardware virtualisation |
| `NESTED-OK` | nested virtualisation is enabled |
| `KVM-DEV-OK` | `/dev/kvm` exists and is usable |
| `RAM-OK` | there is enough memory (30 GiB floor) |
| `DISK-OK` | there is enough free disk (200 GB floor) |

The other three are **advisory**. Nano reports them as `PEND` rather than as failures,
because none of them is a fault in your machine:

| Marker | Means |
|---|---|
| `LIBVIRT-OK` | libvirt is installed and running -- package 01 installs it |
| `VIRTINSTALL-OK` | `virt-install` is available -- package 01 installs it |
| `NO-DESKTOP-OK` | no graphical desktop session is competing for memory |

The first two look for software the build itself installs, so on a fresh machine they
are *expected* to be missing. Run preflight again after package 01 and they pass.

The third is a note about memory rather than a missing tool. The estate allocates
about 29 GiB, and on a 32 GB machine that leaves little spare, so a desktop session
shares what is left. **This is not a prediction of failure** -- the lab this tool was
validated on also ran a desktop session and completed. It is here so that you know
where the memory went if something does go wrong: if a package dies part-way with a
process killed for no visible reason, check `dmesg | grep -i oom`. To free the memory
anyway, without reinstalling anything:

```
sudo systemctl isolate multi-user.target
```

So a good first run on a clean machine looks like **six passed and two or three
advisory**, reported as `READY - WITH ADVISORIES`, with `mcnano` exiting code 4. Six
passed is the part that matters: it means the machine can host the lab.

If any of the first six fails, stop and fix that before going further. `VIRT-OK` or
`NESTED-OK` failing usually means virtualisation is switched off in your BIOS or UEFI
firmware, not that your processor cannot do it.

### Why those floors

The floors are measured, not guessed. A successful build allocates about 29 GiB of RAM
across the seven VMs and uses about 70 GB of disk. The 30 GiB memory floor is therefore
tight and correct: a 32 GB laptop fits the estate with almost nothing to spare, which is
exactly why the 32 GB profile does not attempt live migration -- there is no headroom to
rehearse it honestly. The 200 GB free-disk floor is deliberate headroom (about 2.8 times
the estate's real footprint) for guest volumes and snapshots.

## Getting Nano

Nano is stdlib-only Python 3 and needs no installation. Clone it and run `bin/mcnano`
from the clone:

```
git clone https://github.com/leafspinebooks/matrixclaw-nano.git
cd matrixclaw-nano
python3 bin/mcnano packages
```

`packages` lists every package Nano can run. Nano runs on your lab host -- the physical
machine the estate stands on -- and reaches the seven VMs over SSH on the management
network (10.100.99.0/24, the book's fixed address plan).

## Root, passwords, and what Nano never asks for

Building a lab means installing packages, creating networks and writing to system
directories, so parts of this build need root. It is worth being precise about where
that happens, because the answer is the difference between a tool you can run at work
and one you cannot.

**Run Nano in a terminal, on the machine you are building.** That is the whole model:
Nano runs where you are sitting. When a step needs root it runs `sudo`, and `sudo`
asks *you*, in your own terminal, exactly as it would if you had typed the command
yourself. Around sixty of the build's commands are of this kind, spread across the
platform-host, storage and management phases.

**Nano never sees, stores, or transmits your password.** It does not read it, it has
nowhere to put it, and it makes no network calls at all. `sudo` handles the whole
exchange with you directly.

Expect to be asked more than once. `sudo` remembers your password for a few minutes
and then forgets it, so a long phase may ask again part-way through. That is `sudo`
working normally, not Nano repeating itself.

### Do not grant passwordless sudo to make this smoother

You may be tempted, especially if you want to drive Nano from another machine over
SSH -- Nano never prompts for a password on a connection it opens, so a remote,
non-interactive run fails immediately with `sudo: a terminal is required to read the
password`.

**Do not solve that by giving your account passwordless root.** On a personal machine
it is a poor trade; on a work machine it is the kind of change that a security team or
a compliance auditor will rightly refuse, and you should not have to make it to read a
book. Run Nano on the machine you are building, in a terminal, and answer the prompt.

The seven virtual machines are a different matter, and the difference is deliberate.
Package 03 creates them from a cloud image with a lab account, key authentication and
passwordless `sudo`, and that is what Nano's SSH transport uses. Those are disposable
machines you built a few minutes earlier, on a private network, for a lab -- not your
workstation and not your account. They are meant to be destroyed and rebuilt, and the
build does exactly that more than once.

## How Nano runs: the gate

Every package goes through the same gate:

```
bin/mcnano plan <package>      # shows every command, runs nothing
bin/mcnano run  <package>      # asks before it does anything
```

Four things are worth knowing about the gate:

- **Nothing runs that you were not shown.** `plan` prints every command in full, and the
  exact SSH invocation for anything that runs on a remote host.
- **Your approval is bound to a digest of the plan.** If a package changes, the digest
  changes, and an old approval no longer counts. The digest covers the plan as you were
  shown it -- the commands, the target hosts, and the warnings -- not just what executes.
- **Steps are idempotent.** Each carries an `already` probe, so a stopped or repeated
  build skips what is done rather than repeating it. You can re-run a package safely.
- **Destructive steps announce themselves.** A step that could destroy data (rebuilding
  the VMs, recreating the database) gets its own banner, states the consequence in plain
  language, and shows the exact probe that decides whether it is skipped. Read it before
  you answer yes.

The default answer is no. An empty reply, a closed pipe, or a non-interactive shell all
decline and run nothing.

## The build, package by package

The lab is eleven packages, run in order. Packages 01 to 03 build the platform host and
the seven VMs; 04 to 09 build storage, the management server, and the compute hosts; 10
and 11 build the CloudStack zone and the first guest.

### The one value you have to supply: your SSH public key

Package 03 builds the seven virtual machines and puts your SSH public key into each
one, so you can reach them afterwards. Nano cannot guess that key, and it deliberately
does not ship anybody else's -- the packages you cloned had the author's own key and
account name stripped out before they were published, because a key that is not yours
is worse than no key at all.

What that leaves is a variable you must set. Run package 03 like this:

```
bin/mcnano plan 03-virtual-machines --set deployer_pubkey="$(cat ~/.ssh/id_ed25519.pub)"
bin/mcnano run  03-virtual-machines --set deployer_pubkey="$(cat ~/.ssh/id_ed25519.pub)"
```

If you have no key yet, make one first with `ssh-keygen -t ed25519` and accept the
default path. If you forget the `--set`, Nano refuses to plan the package at all and
tells you which variable is missing -- it will not build seven machines around a
placeholder.

This is the only variable of its kind. Every other value in every other package has a
working default taken from the book's own lab profile.

### Placing your secrets

Some packages need secrets -- two database passwords and a root password for the
compute hosts. Nano never holds these. They live in a root-only file,
`/root/.mc-secrets.env`, on the host that needs them, and Nano's steps read them there,
over SSH, on the far side of the connection. **A secret never enters a package, a plan,
a record, or Nano itself** -- which is deliberate, and is why placing them is a separate
step you run, not something Nano does for you.

The timing matters. The VMs are rebuilt from a fresh image by package 03, so any secrets
you placed earlier are gone with the old disks. Place them **after package 03 and before
packages 07, 08, 09, and 10** -- which is to say, now.

**The easy way.** Nano ships a small helper that places all of them from one file. Copy
the template, fill in three passwords, and run it:

```
cp mc-secrets.env.example mc-secrets.env
nano mc-secrets.env          # fill in the three passwords, save
bin/mc-place-secrets
```

You choose three passwords: the MySQL root password, the CloudStack database password,
and one root password for the compute hosts. You do **not** supply the Ceph storage key
-- the helper reads it for you from the cluster you built in package 05. It shows you
which files it will write, on which hosts, and asks before it does anything; it never
prints a value. When it reports all three verified, delete `mc-secrets.env` so the
passwords do not linger on your disk.

The helper is not part of Nano's gated engine and keeps no record. It reaches the hosts
the same way Nano does, over SSH, and puts each value straight into the root-only file
on the far side.

**By hand, if you prefer.** The helper does nothing you could not do yourself. Each host
needs `/root/.mc-secrets.env`, mode 600, containing `NAME=value` lines:

| Host | Variables |
|---|---|
| mgmt-01 (10.100.99.11) | `MC_MYSQL_ROOT_PASS`, `MC_DB_PASS`, `MC_HOST_ROOTPASS`, `MC_RBD_SECRET` |
| kvm-01, kvm-02 (.31, .32) | `MC_KVM_ROOT_PASS` |

`MC_HOST_ROOTPASS` on mgmt-01 must equal `MC_KVM_ROOT_PASS` on the compute hosts: it is
the password package 10 uses to add each compute host, and the password packages 08 and
09 set on those hosts. (The helper takes one value for both, so it cannot be got wrong.)
`MC_RBD_SECRET` is the `client.cloudstack` Ceph key, readable on a Ceph node with
`sudo cephadm shell -- ceph auth get-key client.cloudstack`.

Either way, if a secret is missing the package that needs it fails fast at its first
step, before it changes anything -- it tells you the file exists and yields the variable,
not merely that a file is present.

### Packages 01 to 11

| # | Package | What it does |
|---|---|---|
| 01 | platform-host | nested virt, KVM/libvirt toolchain, storage pools, the lab keypair, the cloud image, the snapshot scripts |
| 02 | networks | the five libvirt networks, with the jumbo storage pair at MTU 9000 |
| 03 | virtual-machines | build and first-boot the seven VMs; clears stale SSH host keys first |
| 04 | ceph-bootstrap | bootstrap Ceph on the first storage node with cephadm |
| 05 | ceph-cluster | join the other two storage nodes, six OSDs, the pools, the scoped client |
| 06 | secondary-storage | the NFS secondary export |
| 07 | management-server | MySQL, the CloudStack management server, the database, the system-VM template |
| 08 | compute-host-1 | kvm-01: the cloud bridges, the agent and Ceph packages, the host root password |
| 09 | compute-host-2 | kvm-02, the same |
| 10 | manchester-zone | the zone, physical network, pod, cluster, both compute hosts, RBD and NFS storage, then enable |
| 11 | first-guest | an isolated guest network and one CentOS guest, pinned to the production storage pool |

Packages 10 and 11 drive CloudStack through `cmk`, the book's command-line client, over
the same SSH transport. Package 10 registers an API key for the admin account as its
first step; that key is written into `cmk`'s own config on the management server and never
returned to Nano.

## Operational notes the build teaches

Three things about running the build are not in any single package, but the build teaches
them.

### If your lab host is on wifi, turn off the adapter's power saving

Found on the machine this guide was proved on, and it cost an hour before it was
understood. A laptop's wireless adapter powers its radio down when idle. The machine
stays up and stays connected -- but it stops answering anything it did not start
itself, so it vanishes from the network until it next transmits. Ping *out* from it and
it reappears immediately, which makes the symptom look like a firewall problem and
sends you looking in the wrong place.

This matters if you reach your lab host from another machine, or if a long download
stalls part-way through the build. It is not covered by the desktop's power settings:
"High Performance" governs the platform, while the radio's power saving lives in the
wireless driver underneath it. Check with:

```
iwconfig 2>/dev/null | grep -i "power management"
```

If it says `Power Management:on`, turn it off -- substituting your own interface name,
which `ip -br link` will show:

```
sudo iwconfig wlp0s20f3 power off
```

That takes effect at once and lasts until reboot. To make it stick, put the same
command in a small unit that runs at boot:

```
sudo tee /etc/systemd/system/wifi-powersave-off.service >/dev/null <<'UNIT'
[Unit]
Description=Disable wifi power saving for the lab host
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/sbin/iwconfig wlp0s20f3 power off

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl enable --now wifi-powersave-off.service
```

None of this applies to the seven virtual machines. They talk to each other over
libvirt networks inside the host, where there is no radio involved.

### After a rebuild: refresh known_hosts

Package 03 rebuilds the seven VMs from a fresh image, so they present new SSH host keys.
Nano keeps its own `known_hosts` and clears it for you when you tear the estate down. But
if you also reach the VMs directly from your shell (to place secrets, say), your own
`~/.ssh/known_hosts` still holds the old keys and those connections will fail with a
changed-key warning. Clear the estate's entries and let them re-add:

```
for ip in 11 21 22 23 31 32 41; do ssh-keygen -R 10.100.99.$ip; done
for ip in 11 21 22 23 31 32 41; do ssh-keyscan -T5 10.100.99.$ip >> ~/.ssh/known_hosts; done
```

### Letting the zone settle

When package 10 enables the zone, CloudStack starts its two system VMs (the secondary
storage VM and the console proxy), and the secondary storage VM then downloads the
built-in template. This takes a couple of minutes. Package 11 needs that template, so
if you run it too early it will not find it. In the validating build the system VMs were
running within about a minute and the template was ready within about two minutes.

### The snapshot drill

The lab's snapshot script (`lab-snapshot.sh`) is a real drill, not a quiet backup: it
cleanly shuts down all seven VMs, takes an offline `baseline` snapshot of each, and
restarts them. The estate is down for the duration and comes back up afterward. Because
your CloudStack guest runs inside the compute hosts, it stops when they do -- start it
again after the drill. Running the drill once is what proves you could revert the estate
deliberately.

## Acceptance: proving the lab with lab-smoke

The build is done when the lab passes its 24-checkpoint acceptance suite, `lab-smoke`.
Each checkpoint is a read-only command judged on an exact marker in its output, so a
check cannot pass on its own error text. The suite proves, among other things: nested
virtualisation, the five networks and the jumbo path, seven VMs answering with the right
hostnames, the management UI, Ceph healthy with three monitors and six OSDs, the secondary
export, both compute hosts prepared, the zone enabled with its system VMs and both hosts
up, the template ready, and the first guest running with its volume genuinely on the
production Ceph pool.

In the validating build, `lab-smoke` passed **24 of 24**.

## How long it takes

Measured from the validating build's run records. These are package execution times only;
they exclude the time you spend reading a plan and approving it, placing secrets, and
waiting for the zone to settle.

| Package | Measured |
|---|---|
| preflight | under 1 s |
| 01-platform-host | see note |
| 02-networks | 1 s |
| 03-virtual-machines | 48 s |
| 04-ceph-bootstrap | 71 s |
| 05-ceph-cluster | 108 s |
| 06-secondary-storage | 8 s |
| 07-management-server | 203 s |
| 08-compute-host-1 | 62 s |
| 09-compute-host-2 | 68 s |
| 10-manchester-zone | 188 s |
| 11-first-guest | 233 s deploy, plus about 56 s to pin the volume |

Note on 01: in the validating build the platform host already carried its toolchain, so
every step was already-satisfied and the package measured near-zero. On your first build
these steps run for real -- package installs and a cloud-image download -- so expect
several minutes.

Discrete operations you may run:

| Operation | Measured |
|---|---|
| zone settle (system VMs running, template ready) | about 120 s |
| pin a guest volume to the production pool (stop, migrate, start) | 56 s (26 s the migrate itself) |
| snapshot drill (seven VMs) | 312 s, plus about 39 s to re-settle |

## What Nano does, and does not, do

It does: run the eleven lab packages through a gate, over SSH, on real hardware; keep an
audit record of every command's exit code, output, and host; scrub secrets out of that
record by shape before it is written, and say what it removed; and report honestly, marking
what it could not check rather than pretending it passed.

It does not: see your secrets (they live root-only on the target and are read there);
guarantee a record is free of every secret (it redacts by pattern, which is best-effort,
and says so); or claim any capability a recorded run has not shown. If a check cannot run
on your machine it is recorded as skipped with its reason, and the run is marked
not-applicable rather than passed.

## Troubleshooting

- **Package 03 refuses to plan, naming `deployer_pubkey`.** That is the refusal doing
  its job: the package ships with a placeholder where your SSH public key belongs, and
  Nano will not substitute a value it knows cannot work. Re-run it with
  `--set deployer_pubkey="$(cat ~/.ssh/id_ed25519.pub)"` (see "The one value you have
  to supply").

- **A package fails at its first step with a secrets error.** The secret it needs is
  missing or empty on the target host, or was placed before package 03 rebuilt the VMs.
  Place it again (see "Placing your secrets") and re-run the package.

- **Package 10 fails at "Register cmk API keys".** `cmk` could not authenticate to the
  management server. Confirm the management server is up (`curl` its `:8080/client/` should
  return 200) and that `cmk` can reach it: `cmk list users username=admin` should return a
  result. Nano prints this hint on failure.

- **Package 11's guest lands on the wrong storage pool.** CloudStack's allocator does not
  guarantee which cluster pool an untagged guest uses. Package 11 handles this by migrating
  the guest's root volume to the production pool after deploy; if you deployed the guest by
  hand, migrate it yourself (stop the guest, migrate the volume, start it).

- **Connections fail with a changed-host-key warning after a rebuild.** Your own
  `known_hosts` holds the old keys. Refresh them (see "After a rebuild").

- **A step you expected to run says "already done".** That is the idempotency probe working:
  the step's result is already in place, so Nano skipped it. Re-running a package is safe.
