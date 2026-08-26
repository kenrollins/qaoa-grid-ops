---
id: note-10-claiming-a-shared-accelerator
type: implementation
title: "What does it take to let software claim a shared machine?"
date: 2026-08-26
audience: [engineer, leader]
tags: [residency, authorization, forward-auth, durability, operations]
prerequisites: "Note 09, which establishes that the integration point between an inference server and a simulator is residency rather than request routing."
one_line: "Moving a claim/release workflow from an operator's shell into an application turns three implicit assumptions into requirements: the audience must match the blast radius, the identity a proxy vouches for stops being trustworthy at the proxy's edge, and the record of what to restore must reach disk before the first thing is taken away."
---

# What does it take to let software claim a shared machine?

[Note 09](09-who-owns-the-gb10.md) establishes the contract: record which models are
resident, unload them, run the simulator, then restore exactly that set. Running those four
steps by hand is straightforward. Exposing them to an application — so that a demonstration
can take the machine when it needs it — turns three things that were implicitly true into
requirements that have to be built.

## The audience has to match the blast radius

A control's blast radius is the set of things it can affect. For most controls in a
demonstration, that set is the demonstration. For this one it is every other workload on
the machine: claiming evacuates the inference models, and any service depending on them
cannot be served until release restores them.

The gateway itself stays up throughout — this is worth stating because it is the usual
misunderstanding. What becomes unavailable is not the routing layer but the specific lanes
backed by evacuated processes.

!!! quote ""
    A control whose blast radius is the whole machine belongs to whoever is accountable
    for the whole machine, however good it looks in a demonstration.

This is not a statement about any particular viewer's trustworthiness. It is that
authorization should be derived from consequence, and the consequence here reaches well
past the application holding the button. The demonstration was accordingly restricted to
its owner when it gained the control.

## Trust in a forwarded identity ends at the proxy

A common pattern places applications behind an identity proxy that authenticates the user
and forwards the result as request headers — a username, a group list. The pattern is sound
and it has one edge that is easy to miss.

The proxy must **strip** those headers from the incoming request before it sets them.
Otherwise a client can simply send its own. The subtlety is that setting headers from an
authentication response only overwrites the ones that response actually contains; any
header the authenticator happens not to return passes through from the client untouched.
Strip first, trust second.

That establishes the headers as trustworthy **on requests that traversed the proxy**. It
establishes nothing about requests that did not. A service listening on an internal network
is reachable directly, and the proxy is not the only route to a listening socket — it is
the route a browser takes.

So a residency control plane must not read those headers at all. In this implementation the
application forwards the identity under **different header names**, accompanied by a
credential that proves which service did the forwarding. The rename is the mechanism, not
decoration: had the names been preserved, a header arriving from an unauthenticated peer
would have been indistinguishable, by name alone, from one the proxy had verified.

Two credentials with deliberately different authority:

| Credential | Authority |
|---|---|
| The application's | **none alone.** It must arrive with a forwarded owner identity. The application carries authorization; it does not possess any |
| The operator's | self-authorizing. Possession of an operator secret on the operator's own host *is* operator authority, as SSH already assumes. There is no browser session behind a shell |

**Hiding a control in an interface is not authorization.** The interface hides it so that
nobody is offered an action that would be refused; the service refuses it because that is
where the decision belongs. Deleting the interface entirely would leave the boundary
exactly as strong, and that is the test of whether a boundary is real.

## The record has to be written before the thing it describes changes

The evacuation record — which models to restore — is written and flushed to disk **before
the first unload**, and cleared only once every recorded model is loaded again.

Reversing that order produces a state with no recovery: a model unloaded, and nothing
anywhere saying it should come back. The tempting simplification is worse. On restart, read
the machine and record what is loaded now — which, after a partial evacuation, records an
empty set and strands the models permanently. **A recovery record must never be
regenerated from a state the failure already corrupted.**

Three properties follow from that record, and they are what make an interrupted operation
recoverable rather than a mystery:

- **A resumed claim keeps the existing record** rather than re-deriving one.
- **A failed restore keeps the record too**, so a retry can finish the job instead of
  starting from nothing.
- **With no record, release does not guess.** Restoring a plausible set is worse than
  restoring none, because it looks like success.

Verified by killing the control plane mid-evacuation with one model already unloaded: on
restart it reported the outstanding work rather than performing or forgetting it, and the
subsequent release restored exactly the recorded pair. Failure paths that are never
exercised are not features, and the mutating cycle here was exercised against stub
endpoints precisely so that it could be interrupted repeatedly without disturbing live
work.

A lease closes the remaining gap. A demonstration that ends because someone closed a laptop
must not hold the machine indefinitely, so a claim carries an expiry and the machine
releases itself.

## A process-matching pattern is an interface

The simulator is stopped by matching its command line and signalling it. The control plane
runs on the same host, under the same process supervisor.

Had both been named such that one pattern matched the other, every start or stop of the
simulator would have killed the control plane driving it — mid-evacuation, with models
unloaded and nothing left running to restore them. The two are therefore named distinctly
and every pattern is qualified with host and port.

This generalises past process names. Any string used to select "the thing I mean" out of a
shared namespace is an interface with a compatibility contract, whether or not anyone wrote
it down. The same class of mistake reappeared immediately in this project's own test
harness, where running the tests through a remote shell placed the match patterns into that
shell's command line and the test terminated the session running it.

## Limits of this note

The authorization model assumes an operator host that is not itself compromised; a
self-authorizing credential is exactly as strong as the machine holding it. Nothing here
addresses multiple simultaneous claimants wanting **shares** of the machine — the design is
whole-machine, one holder, by construction. And a lease bounds how long a claim can be held
by accident, not how long it can be held on purpose.
