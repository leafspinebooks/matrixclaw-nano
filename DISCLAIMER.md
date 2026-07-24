# Disclaimer, warranty and risk

MatrixClaw-Nano is licensed under the GNU Affero General Public License, version 3.
Sections 15 and 16 of that licence disclaim all warranty and limit all liability, and
they govern. This document restates them in plain language and adds the specific
warnings this software needs, as section 7(a) of the licence permits. **Where anything
here conflicts with the licence, the licence governs.**

Copyright (c) 2026 Spiral Matrix Limited and Michael John Leslie Hinsley.

In this document, "we" means Spiral Matrix Limited, Michael John Leslie Hinsley,
and any other author or contributor to this software.

## What this is, and the book it supports

MatrixClaw-Nano was designed and engineered to support readers of *Sovereign Cloud:
Apache CloudStack 4.22.1.0 LTS -- A Production Deployment Guide* (Leaf Spine Books
edition), available at:

    https://leanpub.com/apache-cloudstack-deployment-guide

It builds the book's reader lab. It is a companion to that book, not a replacement for
it, and it is of little use on its own -- the book explains why each step matters,
which is the part that transfers to systems other than this lab.

This software is published under the **Leaf Spine Books** imprint, which is real. The
similarly-named publisher that appears in the book's narrative is a fictional
organisation and a narrative device; any resemblance to real organisations,
businesses, or events is coincidental. The book's own copyright page says the same,
and if the two ever disagree, the book's is the authoritative statement.

## No warranty

**This software is provided "as is", without warranty of any kind**, express or
implied, including but not limited to the implied warranties of merchantability,
fitness for a particular purpose, and non-infringement.

We do not warrant that the software is free of defects, that it will run on your
hardware, that it will produce a working lab, or that any check it reports as passing
reflects the true state of your systems. The entire risk as to the quality and
performance of the software is with you.

## No liability

**To the fullest extent permitted by applicable law, we accept no liability** for any
claim, damages, or other liability arising from or in connection with this software or
its use, including without limitation loss of data, loss of profit, business
interruption, damage to hardware, or any indirect or consequential loss, even if we
have been advised of the possibility of such damage.

Nothing in this document excludes or limits liability where it would be unlawful to do
so, including liability for death or personal injury caused by negligence, or for
fraud or fraudulent misrepresentation.

## You are responsible for your own systems

This software builds infrastructure on machines you control. **Before you run it:**

- **Take your own backups.** We cannot recover anything you lose.
- **Use a machine you can afford to rebuild.** This is not software to try out on a
  laptop holding your only copy of anything.
- **Read every plan before you approve it.** Nano shows you every command before it
  runs one, and the default answer is no. That is the point of the gate, and it only
  protects you if you actually read what it prints.

Some steps **destroy data by design**. Package 03 rebuilds the seven virtual machines
from a fresh image, discarding their disks and everything on them. Those steps announce
themselves, state their consequence, and will not proceed without your approval. Your
approval is your decision.

## This is a laboratory, not a production system

The lab is deliberately convenient rather than hardened, because it exists to be built,
broken and rebuilt while you learn. Specifically, and so that you can judge the risk
for yourself, it:

- enables SSH password authentication on the virtual machines
- creates an administrative account with passwordless `sudo`
- sets a root password on the compute hosts, which CloudStack requires to add them
- uses fixed, well-known private addressing and documented default account names

**Build it on an isolated machine or a trusted private network. Do not expose it to
the internet, and do not place it on a network you do not control.** Do not reuse its
credentials, its keys, or its configuration anywhere that matters. If you need a
hardened deployment, this is not that, and adapting it into one is your responsibility
and your risk.

## Third-party software

This software installs, configures and operates software we did not write, including
Apache CloudStack, Ceph, MySQL, libvirt, QEMU/KVM and Ubuntu. **That software is
licensed by its own authors under its own terms, and carries its own warranties or, as
is usual, its own absence of them.** We make no representation about it, accept no
liability for it, and grant you no rights in it. You are responsible for complying with
its licences and for anything it does on your systems.

Nano downloads and installs packages and images from third-party repositories over the
network. We do not control those sources or their contents.

## Trademarks and affiliation

**This is an unofficial, independent project.**

Apache, Apache CloudStack, CloudStack, and the Apache feather logo are trademarks or
registered trademarks of The Apache Software Foundation. All other product names,
logos, and brands are the property of their respective owners, including among others
Ubuntu, Ceph, MySQL, Linux, and GitHub.

Use of these names is for identification and reference only and does not imply
endorsement. This is an independent work: it is **not affiliated with, authorised by,
sponsored by, or endorsed by The Apache Software Foundation** or by any other company
or project named within it.

## No support, and no professional advice

We are under no obligation to provide support, updates, security fixes, or
maintenance, and nothing here creates a support relationship or a contract.

This software and its documentation are educational material. **They are not
professional advice** -- not architectural, security, operational or legal advice --
and they are not a substitute for the judgement of a qualified engineer applying it to
your own circumstances. Decisions you take about your own systems remain yours.

## Reporting a problem

If you find a defect, particularly one with security consequences, please raise it on
the project's issue tracker. We would rather know. Doing so creates no obligation on
either of us.
