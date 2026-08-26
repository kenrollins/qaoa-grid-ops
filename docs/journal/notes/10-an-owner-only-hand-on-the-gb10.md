---
id: note-10-an-owner-only-hand-on-the-gb10
type: implementation
title: "An owner-only hand on the GB10"
date: 2026-08-26
audience: [engineer, leader]
tags: [gb10, residency, authorization, forward-auth, operations, litellm]
prerequisites: "Note 09, which establishes that the integration point between inference and simulation is residency rather than request routing."
one_line: "Turning claim/release from a shell script into a service made Grid Ops an operator tool, so it left the guest demo floor; the interesting engineering is the trust chain from Caddy's header strip to a control plane that re-checks the group itself, and a durable evacuation record that makes a half-finished claim recoverable."
---

# An owner-only hand on the GB10

Note 09 established the workflow: record what the vLLM orchestrator has loaded, unload exactly
that, start `gridops-qsim`, and on release restore exactly that set. It was implemented as a
shell script an operator ran by hand. Putting the same controls in the application changed what
the application *is*, and three consequences followed.

## A demo that can take the machine is not a demo

Grid Ops was guest-visible. A visitor could open it, drive an islanding scenario, and see real
silicon do real work — which is the point of a demo floor.

A visitor cannot be one click from evacuating the lab's resident inference models. That is not a
statement about any particular visitor; it is that the blast radius of the control is the whole
lab, and the control's audience should match its blast radius. So the entitlement moved to
`lab-owner` alone, and the card left the guest floor.

The rule this establishes, worth applying to the next demo: **a demo that can take a shared
resource away from the rest of the lab is owner-only, however good it looks on a floor.**

Removing it from the floor turned out to need a server-side change, not a styling one. The portal
had been filtering cards in the browser — fetch the viewer's catalog, delete the nodes they are
not entitled to. That is cosmetic by construction: the guest's browser had already been sent the
card's full prose, its launch URL and its specs, all readable in view-source. The floor is now
assembled per viewer on the server, and the browser-side filter stays as a second line.

## Where a trusted header stops being trusted

The lab's front door strips all twelve `X-Authentik-*` request headers from the client and then
replaces them from Authentik's forward-auth response. Strip first, trust second — because
`copy_headers` only overwrites headers Authentik actually returns, and one it happens not to
return would otherwise pass straight through from whoever sent it.

That makes `X-Authentik-Groups` believable *on traffic that came through the front door*. The
application's own address is directly reachable on the DMZ, and so is the new control plane's. A
request that did not traverse the proxy carries whatever headers its sender chose.

So the control plane does not read `X-Authentik-*` at all. The application forwards the identity
under different names — `X-Gridops-Auth-User`, `X-Gridops-Auth-Groups` — alongside a service
credential that proves who did the forwarding. The rename is the point: had the names been kept,
a header arriving from an unauthenticated network peer would have been indistinguishable, by name
alone, from one the proxy had stripped and replaced. Two things that must never be confused
should not be spelled the same way.

The application's credential grants nothing on its own; it must arrive with a `lab-owner`
identity. The operator CLI's credential is self-authorizing, because possession of an operator
secret on the operator's own host *is* operator authority, the same way SSH is — there is no
browser session behind a shell.

**Hiding the buttons is not access control.** The interface hides them so an operator is not
offered a control that would be refused; the service refuses them because that is the boundary.
Deleting the entire interface file would leave the boundary exactly as strong.

## The record is the recovery story

The evacuation record is written and fsynced to disk *before* the first unload, and cleared only
once every recorded model is loaded again. That single ordering decision is what makes an
interrupted operation recoverable rather than a mystery.

Verified by hard-killing the control plane mid-evacuation, with one model already unloaded: on
restart it reported `needs_release` — naming the outstanding work rather than silently performing
or forgetting it — and a subsequent release restored exactly the recorded pair. A claim from that
state resumes instead, explicitly keeping the existing record. The tempting simplification is to
re-read the machine and record what is loaded now; that would replace the truth with an empty
list and strand the models permanently.

When a model refuses to come back, the state becomes `degraded` and **the record is kept**, so a
retry finishes the job. When there is no record at all, release does not guess which models
belong.

A lease closes the last gap. A demo that ends because someone shut a laptop must not hold the
lab's inference until the owner notices, so a claim carries an expiry and the machine releases
itself.

## One trap, worth stating plainly

`gridops-qsim` is stopped with `pkill -f "uvicorn server:app …"`, and its own start script does
the same before booting. The control plane runs under uvicorn on the same host. Had it also been
named `server:app`, every start or stop of the simulator would have killed the process driving
the evacuation — mid-flight, with models unloaded and nothing left running to put them back. The
control plane is `residency:app`, and both pkill patterns are now fully qualified with host and
port. A process-matching pattern is an interface, and a loose one is a defect.

The same shape bit the test harness: running the tests as an inline `ssh host '…'` command put
the pkill patterns into the remote shell's own command line, and the test killed the session
running it.

## What was verified, and what was not

Against the live service: every authorization refusal (no credential, wrong credential, forged
`X-Authentik-*`, an app credential carrying a non-owner identity, browser-shaped requests, and
the network allowlist), and that `GET /status` leaves residency unchanged.

Against stub orchestrator and simulator endpoints on isolated loopback ports: the whole mutating
cycle — claim, exact restoration on release, idempotent repeat calls, hard-kill recovery,
resume-instead-of-re-record, the `degraded` retry, concurrent-operation refusal, and automatic
release on lease expiry.

The mutating cycle was **not** run against the live GB10, because doing so would have interrupted
inference traffic that other things depend on. Both resident model containers were confirmed
untouched afterwards. That end-to-end run is the one outstanding step, and it is the owner's call
when to take it.
