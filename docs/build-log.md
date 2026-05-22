# Build log — raw narrative beats

Unpolished capture for a later demo walkthrough / blog. Bullet beats, war
stories, and before/after numbers — NOT finished prose. Add to it as the
project goes.

## The sim-first thesis (why any of this exists)
- Hybrid hydraulic/mechanical dyno for a Briggs LO206 kart engine, controlled by
  a Raspberry Pi running OpenPLC.
- Sim-first: a Python physics sim stands in for the engine + hydraulic brake so
  the WHOLE control system (PID, safety interlocks, sweep, dashboard, logger) is
  validated before spending a dollar on the proportional valve or risking an
  overspeed. Sim and real hardware share ONE thing: the Modbus register map.
- The register map is THE CONTRACT. Every "build to the code, not the brief"
  moment below traces back to that.

## War story 1 — the cross-origin HMR reload storm (dashboard looked dead, server was fine)
- Symptom: operator's browser at `http://10.20.99.55:3000` showed "No live run"
  and empty cards. Every server-side check passed: one of each process, logger
  and dashboard on the same `data/dyno.db` (inode-verified), run open,
  SAFETY_ENABLE=1, and `/api/live` returned valid JSON when curled FROM THE VM.
- Root cause: Next 16 treats a browse from any non-localhost origin as
  cross-origin. With no `allowedDevOrigins`, the HMR websocket was blocked and
  the reconnect path force-reloaded `/` several times a second. Each reload
  re-mounted the page and tore down `setInterval(tick, 500)` before the first
  tick fired — the poll never ran on the client.
- The tell: access log was hundreds of `GET /` against ~3 `GET /api/live`.
- Fix: `allowedDevOrigins: ["10.20.99.55"]` in `next.config.js`. One line.
- LESSON (now a standing rule): **curl-from-the-VM is NOT a test of a dashboard
  the operator browses remotely.** Same-origin never trips the guard. Every
  dashboard verification since is done from a real remote browser.

## War story 2 — duplicate-process split-brain on run_id
- Symptom: dashboard intermittently showed "No live run" / zeros even though the
  stack was "up".
- Root cause: TWO `modbus_server.py` and TWO `logger.py` were alive. The losing
  sim couldn't bind 5020, but each logger opened its own `test_runs` row and
  wrote samples under different run_ids. `/api/live` reads "the latest run" —
  whichever logger opened the newer row won the dashboard, regardless of which
  sim the PLC was actually driving. Not a code bug — an ops/lifecycle bug.
- Fix part 1: `start_all.sh` / `stop_all.sh` made idempotent (pgrep-gated start,
  kill-all-matching stop).
- Fix part 2 (the real one): moved run-row ownership. The LOGGER used to create
  and close runs. Now the DASHBOARD is the SOLE creator/closer of `test_runs`
  (open on Start, stamp ended_at on End Run); the logger only waits for the
  newest open run and attaches samples to it. Exactly one writer → no split brain.

## War story 3 — the engine could not be started from software (Issue #3)
- The dashboard was READ-ONLY. SAFETY_ENABLE is an OPERATOR input the PLC only
  reads (or forces to 0 on fault) — nothing in the control logic ever sets it to
  1. And you can't poke the sim directly: the PLC mirrors its %QW down to the sim
  every 50 ms scan, so a direct write to the sim's holding regs is clobbered
  within one scan (verified: wrote enable=1 to :5020, read back 0 a second later).
- Fix: operator commands go to OpenPLC's OWN Modbus server on :502 (the PLC's
  %QW image), never to the sim. Built `/api/command` as the sole Modbus write
  path. Start writes CONTROL_MODE then SAFETY_ENABLE=1; Stop/E-stop write
  SAFETY_ENABLE=0 (the PLC interlock drives the valve to 0 on its own, so the
  route does NOT duplicate that — verified %QW100 read back 0 after stop).

## War story 4 — the low-RPM floor was CLUTCH-limited, not brake-limited
- Old note cited a ~4,236 RPM floor "the dyno can't pull RPM below this at full
  throttle." Re-probed it properly before designing the sweep.
- Probe (full throttle, valve 100%, let settle): floor at **~4,004 RPM**. But the
  equilibrium was CLUTCH-limited, not pump-capacity-limited — at 4,004 the
  centrifugal-clutch model only transferred 0.75 of pump torque (engagement
  3,400 → lockup 4,200), so effective brake = engine torque there.
- Also found `BACKPRESSURE_BASELINE_PSI`'s comment LIED: it claimed to "eliminate
  the low-RPM floor," but the constant only floors the reported PRESSURE
  telemetry — it never enters the brake torque. Fixed the comment.
- (Stale 4,236 was under `PUMP_LOAD_GAIN=12.0`; gain is now 18.5 → ~4,004.)

## Decision — remove the clutch model from the dyno's engine physics
- The point of a bench dyno is to measure torque/HP across the FULL rev range
  (~2,500 RPM to the limiter). A ~4,200 RPM clutch lockup floor means the dyno is
  BLIND below lockup — i.e. blind in exactly the range you'd want to measure if
  you were deciding whether to tune the clutch to a lower engagement. The
  measurement tool must not be blind where the modification it informs would act.
- So: bypassed the clutch in `tick()` — the pump brake couples to the engine
  directly, no `clutch_torque_fraction()` multiplier. KEPT the clutch function +
  constants as RETAINED reference data (Hilliard Inferno Flame, 2 black + 2 white
  springs, engagement ~3,400 / lockup ~4,200, validated against race logs) — they
  still matter for a future launch-load mode and for tuning a real clutch.
- BEFORE → AFTER floor (full throttle, valve 100%): **~4,004 RPM (clutch-limited)
  → ~3,135 RPM (brake-capacity-limited)**. The dyno can now see below lockup.
- Bonus: removing the clutch also killed a known inconsistency (pressure/CHT had
  computed off raw pump load while torque used the clutched value).
- Caveat recorded: the sim STILL doesn't model the return-line back-pressure
  valve's brake torque, so the REAL floor will sit lower again once that valve is
  in the circuit. SWEEP_START_RPM is operator-settable to find it empirically.

## MODE_SWEEP — the actual dyno run
- Sweep is a SUPERVISOR over the existing PID, not a reimplementation: it steps an
  internal setpoint up the band (start → end by step), dwelling at each step so
  the load cell torque settles, reusing the PID to hold each step.
- Dwell is counted off the PLC SCAN (DT_S), not wall-clock — the Pi is only
  soft-real-time.
- It ends ITSELF: at the final step's dwell it sets SWEEP_STATE=2 and drops
  SAFETY_ENABLE. First time the control logic ends a run not on a fault.
- OpenPLC insight: SWEEP_STATE had to be a PLC-written %QW, NOT an input register
  — input registers are sourced from the slave device (the sim), the program
  can't write them. The dashboard reads it back off :502. The new sweep registers
  are NOT mirrored to the sim (sim doesn't model sweep), so modbus_map.py and the
  slave-device config never changed.
- Verified end-to-end from a remote browser: sweep 3200→6100 / step 400 / dwell
  2000 ms → run auto-created, RPM stepped 4030→6036, torque logged across the band
  (9.2 → 5.0 ft-lbs — a real torque curve), SWEEP_STATE 1→2, PLC dropped enable,
  dashboard auto-closed the run. One click, walk away, come back to a finished run.

## Safety-of-interpretation fix
- `/api/live` used to return the last sample of the newest run even when that run
  was CLOSED — so with nothing running the cards showed a stale, live-looking RPM.
  Changed it to return null when no run is OPEN, so the cards blank out. A screen
  must never look "live" while the engine is stopped.

## Numbers worth quoting
- Floor: ~4,004 RPM (clutch-limited) → ~3,135 RPM (no clutch, brake-limited).
- Sweep torque sample (3200→6100, step 400): ~9.2 ft-lbs at ~4,000 RPM tapering to
  ~5.0 ft-lbs near 6,000 RPM — past-peak side of the LO206 curve.
- Reload storm: hundreds of `GET /` vs ~3 `GET /api/live` before the one-line fix;
  steady `/api/live` + `/api/runs` poll and zero `GET /` after.
- PLC scan / control dt: 50 ms. Logger poll: 100 ms. Dashboard poll: 500 ms.
- Tests: simulator suite 14 → 15 after swapping the obsolete clutch test.
