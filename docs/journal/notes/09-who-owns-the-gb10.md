---
id: note-09-who-owns-the-gb10
type: implementation
title: "Who owns the GB10 while a simulation runs?"
date: 2026-08-26
audience: [engineer, leader]
tags: [gb10, litellm, orchestration, residency, operations]
prerequisites: "None."
one_line: "LiteLLM routes and meters inference, but QAOA Grid Ops is not an inference client: it calls a dedicated simulation API. The shared resource is GB10 memory, so safe operation requires the demo's claim/release workflow to cooperate with the vLLM orchestrator rather than route quantum requests through LiteLLM."
---

# Who owns the GB10 while a simulation runs?

!!! info "Superseded in part by [note 10](10-an-owner-only-hand-on-the-gb10.md)"
    The *analysis* below still holds: the integration point is residency, not request
    routing, and the four-step workflow is still the right one. The *implementation* it
    describes — a shell script keeping its evacuation record in the invoking user's state
    directory — was replaced on 2026-08-26 by a service on the GB10 that owns the record,
    serializes every operation, and enforces authorization itself. Two independent things
    that can each evacuate the machine, with no shared lock, is a race. Read note 10
    before implementing anything from this page.


LiteLLM and QAOA Grid Ops use the same physical GB10 for different protocols. LiteLLM routes
OpenAI-compatible inference requests to models managed by the GB10 vLLM orchestrator. Grid Ops
sends Ising couplings and circuit parameters to a dedicated FastAPI service, `gridops-qsim`, on
port 8600. Treating the simulator as a LiteLLM model would discard its typed optimization,
verification, noise, and health APIs without providing useful metering semantics.

The integration point is therefore residency, not request routing.

On 2026-08-26 the live orchestrator reported `nemotron-120b` and `qwen35-a3b` loaded, with 117.7
GiB used from a 121.6 GiB visible pool. Port 8600 was not serving. The project's claim script
still checked for the retired `nim-llama8b` container, reported the machine as idle, and did not
evacuate either orchestrator-managed model.

The corrected workflow is:

1. query `GET :9000/status` and record exactly which models are loaded;
2. unload that set through `POST :9000/unload`;
3. start `gridops-qsim` and verify `GET :8600/health`;
4. on release, stop qsim and restore exactly the recorded set through `POST :9000/load`.

The LiteLLM gateway remains available during a claim, but model lanes backed by the evacuated
GB10 processes are unavailable. The script states that impact before unloading anything.

The evacuation record is intentionally durable in the invoking user's state directory. If a
claim is interrupted after unloading one model, `release` still has enough information to restore
the pre-claim set. If no record exists, release does not guess which models should be loaded.

This workflow was syntax checked and its read-only status path was verified against the live
orchestrator. The mutating claim/release cycle was not run during implementation because it would
interrupt active inference traffic.

