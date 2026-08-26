# Residency control-plane test harness

Exercises `services/gb10_residency` against **stub** orchestrator and simulator
endpoints on isolated loopback ports. Nothing here touches the real `:9000` or
`:8600` — that is the whole point: the mutating cycle cannot be rehearsed on the
live GB10 without interrupting inference.

```bash
rsync -a tests/residency/ gb10:restest/
ssh gb10 'chmod +x ~/restest/*.sh'
ssh gb10 '~/restest/t_interrupt.sh'   # hard-kill mid-claim → needs_release → recovery
ssh gb10 '~/restest/t_degraded.sh'    # a model refuses to load → degraded → retry finishes
ssh gb10 '~/restest/t_lease.sh'       # resume-not-re-record, then lease auto-release (~90s)
ssh gb10 '~/restest/teardown.sh'      # kill the stubs, confirm production is untouched
```

`env.sh` points the service at ports 19000 (stub orchestrator), 18600 (stub
qsim) and 18610 (the service under test), with 60-second leases and a 2-second
watchdog tick so the timeout path is observable in a test run.

**Run the scripts as FILES, never as `ssh gb10 '<inline>'`.** The inline form puts
the pkill patterns into the remote shell's own command line and the test kills
the session running it — the same class of bug the `residency:app` module name
guards against in production.
