# gridops-residency — the owner-only GB10 residency control plane

`http://10.0.13.200:8610` · systemd `--user` on the GB10 · **no public route**

Two tenants share the GB10's 128 GiB of **unified** memory, and only one can
hold it:

| Tenant | Port | Protocol | Routed through LiteLLM? |
|---|---|---|---|
| GB10 vLLM orchestrator | `:9000` | OpenAI-compatible model lanes | **yes** — that is what the gateway is for |
| `gridops-qsim` | `:8600` | a **typed** simulation API (`optimize` / `evaluate` / `realism` / `health`) | **no, never** |

`gridops-qsim` is not an LLM and must not be registered as a gateway model.
Routing it as one would discard every verb it has and buy no metering in
return. LiteLLM remains the inference gateway; the integration point between
these two is **residency**, not request routing — and this service is the one
place that arbitrates it.

```
claim    GET :9000/status  → record the loaded set   (durable, BEFORE any change)
         POST :9000/unload → evacuate exactly that set
         start gridops-qsim, wait for GET :8600/health

release  stop gridops-qsim
         POST :9000/load   → restore exactly the recorded set, no more, no less
```

---

## The trusted-proxy identity contract

### What the identity proxy forwards to the QAOA upstream

The lab's front door (Caddy + Authentik forward-auth) defines one `authgate`
snippet, imported by every protected site including this one. The exact
hostnames and addresses are deployment detail and live in the platform's own
runbook, `docs/runbooks/GB10-RESIDENCY-CONTROL.md`; what matters here is the
shape, which the service depends on. It does two things, **in this order**:

1. **Strips** all twelve `X-Authentik-*` request headers coming from the client:

   ```
   X-Authentik-Username   X-Authentik-Groups        X-Authentik-Entitlements
   X-Authentik-Email      X-Authentik-Name          X-Authentik-Uid
   X-Authentik-Jwt        X-Authentik-Meta-Jwks     X-Authentik-Meta-Outpost
   X-Authentik-Meta-Provider   X-Authentik-Meta-App X-Authentik-Meta-Version
   ```

2. **Replaces** them from Authentik's forward-auth response
   (`forward_auth <outpost> { uri /outpost.goauthentik.io/auth/caddy;
   copy_headers <the same twelve>; trusted_proxies private_ranges }`).

The strip is the load-bearing half. `copy_headers` only overwrites headers
Authentik actually returns; one it happens *not* to return would otherwise pass
straight through from the client. **Strip first, trust second.**

The two this service cares about:

| Header | Meaning | Note |
|---|---|---|
| `X-Authentik-Username` | the authenticated account (`rollik`) | |
| `X-Authentik-Groups` | the account's groups | separator has been `\|` **and** `,` across Authentik versions — parse both |

### Where that trust stops

**It stops at the proxy.** Both the application and this service listen on the
lab's internal network, and the proxy is not the only path to a listening
socket — it is simply the path a browser takes. A request that did not traverse
it carries whatever headers its sender chose. So:

> An `X-Authentik-Groups` header arriving at **this** service could be a header
> from an unauthenticated network peer. It is never trusted, never read, and
> never honoured.

### What this service accepts instead

Deliberately renamed, so the two can never be confused:

| Header | Who sets it | Trusted because |
|---|---|---|
| `Authorization: Bearer <token>` | the caller | it is one of two pre-shared credentials |
| `X-Gridops-Auth-User` | the qaoa-grid-ops app | copied verbatim from `X-Authentik-Username`, and the bearer token proves who copied it |
| `X-Gridops-Auth-Groups` | the qaoa-grid-ops app | copied verbatim from `X-Authentik-Groups`, same reason |

**Two principals, two different authorities:**

- **`GRIDOPS_APP_TOKEN`** — held by the qaoa-grid-ops container. On its own it
  grants **nothing**. It must arrive together with a forwarded identity whose
  groups include `lab-owner`. The app's job is to *carry* Ken's authority, not
  to *have* any.
- **`GRIDOPS_OPERATOR_TOKEN`** — held by Ken on xr7620 for `tools/gb10-gpu`.
  Self-authorizing, because possession of an operator secret on the operator's
  own host **is** operator authority, the same way SSH is. There is no Authentik
  session behind a shell.

Both tokens live in `~/.config/gridops/residency.env` on the GB10 at `600`, and
in the caller's own secret store (never in this repository). Never on a command line — `ps` is
world-readable.

### Three more refusals

- **Fail closed.** With neither token configured the service returns `503` to
  every caller rather than serving residency controls to the DMZ.
- **Not browser-reachable.** Any request carrying `Sec-Fetch-Mode`,
  `Sec-Fetch-Site` or `Origin` is refused with `403`. No CORS headers are
  emitted anywhere, so a page that somehow reached this port could neither
  navigate to it nor read a response. There is no Caddy site block and no
  hostname — this is defence behind that, not instead of it.
- **Optional network allowlist.** `GRIDOPS_ALLOW` (space/comma separated IPs or
  CIDRs) restricts which peers may even present a token.

**Hiding the buttons in Streamlit is not access control.** The UI hides them
because showing an operator a control they cannot use is bad manners; this
service refuses them because that is the boundary.

---

## API

`GET /health` is the only unauthenticated endpoint. It reports liveness and
nothing about the lab, which is why it can be.

Everything below requires the credential contract above.

### `GET /status` — **non-mutating, always**

Reads. Never claims, releases, loads, unloads, starts or stops anything —
including as a side effect. Returns the durable record *and* what is observably
true right now, so a disagreement between them is visible rather than hidden:

```jsonc
{
  "state": "released",              // see the state machine below
  "holder": null,
  "pre_claim_models": [],           // the evacuation record
  "pending_restore": [],
  "lease_expires_at": null,
  "lease_remaining_seconds": 0,
  "progress": [ /* last 40 steps, each {t, step, status, detail} */ ],
  "observed": {
    "orchestrator_reachable": true,
    "loaded_models": ["nemotron-120b", "qwen35-a3b"],
    "qsim_serving": false,
    "qsim_max_qubits": null
  }
}
```

### `POST /claim` — take the machine

Body (all optional): `{"lease_seconds": 3600, "reason": "..."}`.

Idempotent:

- already `claimed` and qsim healthy → `200`, `changed:false`, **lease renewed**
- `claiming`/`releasing` in flight → `409`
- `degraded` → `409`, telling you to retry `release` first
- interrupted (`needs_release`) → **resumes** from the existing record

### `POST /release` — give it back

Body (all optional): `{"reason": "..."}`.

Idempotent, and the recovery path: it restores exactly the recorded set from
whatever state got you here. Already released with nothing outstanding →
`200 changed:false`. If a model does not come back, the state goes `degraded`
and **the record is kept**, so a retry finishes the job.

---

## State machine

| State | Means | Get out of it by |
|---|---|---|
| `released` | nothing claimed, nothing outstanding | `POST /claim` |
| `claiming` | evacuation in flight | waiting |
| `claimed` | qsim holds the machine, lease running | `POST /release`, or the lease expiring |
| `releasing` | restoration in flight | waiting |
| `needs_release` | **interrupted** — a record exists, the machine is not claimed | `POST /release` (finish) or `POST /claim` (resume) |
| `degraded` | release ran, something did not come back; record kept | `POST /release` again |

## Durability, serialization, leases

- **The record is written and fsynced BEFORE the first unload.** Reverse that
  ordering and a crash between the two leaves a model unloaded with nothing on
  disk saying it should come back. It is cleared only once every recorded model
  is loaded again.
- **If there is no record, release does not guess** which models belong.
- **Two locks.** An `asyncio.Lock` serializes requests inside the process; an
  `flock` on `residency.lock` stops a second process from evacuating the
  machine at the same time.
- **Restart is safe.** Startup reconciles the record against what is observably
  true and *never mutates the GB10 on its own*. A restart mid-claim with an
  outstanding record lands in `needs_release`, which names the work rather than
  silently performing or forgetting it.
- **Leases auto-release.** Default 3600s, max 86400s, checked every 30s. A demo
  that ends when someone shuts a laptop must not hold the lab's inference
  hostage until Ken notices. Re-claiming renews.

## Impact of a claim, stated plainly

Unloading the orchestrator's models takes their LiteLLM lanes with them.
**LiteLLM stays up** — it is unaffected as a gateway — but any lane backed by an
evacuated GB10 process cannot serve until release restores it. `claim` says so
in its progress log before it unloads anything.

## Files

```
residency.py                 the service       (module is `residency`, NOT `server` — see below)
start.sh                     manual launcher
gridops-residency.service    systemd --user unit
~/.config/gridops/residency.env    tokens + config, 600
~/.local/state/gridops-residency/  residency.json (durable) + residency.lock
```

**The module name is load-bearing.** `gridops-qsim` is stopped with
`pkill -f "uvicorn server:app --host 0.0.0.0 --port 8600"`, and its own
`start.sh` does the same before booting. If this service also ran as
`server:app`, every qsim start or stop would kill the control plane driving it —
mid-evacuation, with models unloaded and nobody left to put them back.
