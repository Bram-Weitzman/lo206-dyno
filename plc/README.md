# PLC — OpenPLC control logic

This directory holds the dyno control program in IEC 61131-3 Structured Text
and the Modbus register contract it depends on.

| File               | Role                                                    |
|--------------------|---------------------------------------------------------|
| `dyno_control.st`  | PID speed control + safety interlocks (Structured Text) |
| `register_map.md`  | **The contract** — Modbus register definitions          |

## What `dyno_control.st` does

Closes a speed-control loop on the LO206 engine using the hydraulic pump brake.
The valve is the only actuator: raising it increases pump restriction, which
increases braking torque and lowers RPM. The program holds a target RPM at full
throttle by modulating that valve.

It is **I/O-agnostic**: every value it touches crosses the Modbus boundary in
`register_map.md`. It does not know whether the far end is the Python simulator
or the real rig.

Structure (one scan, top to bottom):

1. **Scale inputs** — raw register counts → engineering units (RPM, PSI, °C).
2. **Safety interlock** (highest priority, every scan, before any output):
   - **Hard fault** — `SIM_STATUS = 2`, *or* a PLC-side overspeed / over-pressure
     / over-temp trip → close the valve, clear `SAFETY_ENABLE`, dump the
     integrator, and **latch**. The latch releases only when the condition
     clears; because `SAFETY_ENABLE` was forced to 0, the operator must
     re-command run to resume. A momentary spike still stops the rig.
   - **Operator stop** — `SAFETY_ENABLE = 0` → close the valve and reset the
     integrator, *not* latched (operator can re-run immediately).
3. **Mode gating + control** (only when enabled and not faulted):
   - **Manual (0)** — operator owns the valve command; pass-through.
   - **PID (1)** — hand-rolled PID drives the valve to hold `TARGET_RPM`.
   - **Sweep (2)** — not implemented this session; falls back to manual
     pass-through (defined, never auto-commands an unsafe move).
4. **Output clamp + scale** — hard-clamp to 0–100%, scale to register counts
   (×100), clamp to the wire range.

### PID details

- **Hand-rolled** (not OpenPLC's PID function block) so the math is explicit,
  portable, and readable.
- **Reverse-acting with positive gains.** Error is computed as `actual − target`
  (PV − SP), not the usual SP − PV, because the valve is a *brake*: too fast →
  positive error → more valve → more braking → slows down. This keeps `Kp`,
  `Ki`, `Kd` all positive.
- **Derivative on measurement**, not on error — differentiating the RPM (not the
  error) means a step change in `TARGET_RPM` produces no derivative kick.
- **Anti-windup by conditional integration** — integrate normally in the linear
  region; while the output is saturated at 0% or 100%, only integrate in the
  direction that pulls it back out of saturation.
- **Bumpless-ish start** — on the disabled→enabled (or PID-mode-entry) edge, the
  integrator is zeroed and the derivative seeded so the loop doesn't kick.

Starting gains (`KP = 0.3`, `KI = 0.05`, `KD = 0.01`) and all trip limits are
named `VAR CONSTANT`s at the top of the file. Every value needing real-rig
calibration is flagged `(* TODO: calibrate against real hardware *)`.

## Prerequisites

- OpenPLC runtime installed and running on `dyno-dev` (service `openplc`).
- Web UI reachable at `http://10.20.99.55:8080`.
- The simulator running and reachable as a Modbus TCP slave. Note the port it
  logs on startup: it prefers **502** and falls back to **5020** when run
  unprivileged (the usual case).

## Configure OpenPLC to talk to the simulator

OpenPLC is the Modbus **master**; the simulator is the **slave/server**.

1. Open the web UI: `http://10.20.99.55:8080`
   (default credentials are OpenPLC's `openplc` / `openplc` — change them).
2. **Slave Devices → Add new device**:
   - Protocol: **Modbus TCP**.
   - IP: the simulator host; Port: **5020** (or 502 if the sim logged 502).
   - Map the registers per `register_map.md`:
     - **Input registers** 30001–30007 → read into the PLC (`%IW…`).
     - **Holding registers** 40001–40004 → written by the PLC (`%QW…`).
   - The order you add points sets their `%IW`/`%QW` indices — keep that order
     consistent with how `dyno_control.st`'s variables are bound.
3. Set a **poll rate** comfortably faster than the loop period (see below) —
   e.g. 50 ms — so fresh telemetry is available each scan.

## Load and run the program

1. **Programs → Upload Program** → select `dyno_control.st`, name it, then
   **Compile**. Fix any compile errors before continuing.
2. Make sure the **task cycle time matches `DT_S`** in the program (default
   **50 ms**). The integral and derivative use `DT_S` as `dt`; if the cycle and
   `DT_S` disagree, the effective `Ki`/`Kd` are wrong. Change one to match.
3. **Run** the program. Open **Monitoring** to confirm live values.

## PID tuning guidance (against the simulator)

Tune here first — it's free and safe. Drive `TARGET_RPM` to a setpoint in PID
mode at full throttle and watch `ENGINE_RPM` (PV) and `VALVE_POSITION_ACT`.

- **Watch for:** rise time to setpoint, overshoot, steady-state error, and
  oscillation/hunting around the setpoint.
- **`Kp`** — raise for faster response; too high → oscillation/hunting. This is
  the gain to set first.
- **`Ki`** — raise to eliminate steady-state RPM error; too high → slow
  oscillation and overshoot. The anti-windup keeps it sane near the valve stops.
- **`Kd`** — small amounts damp overshoot; too high amplifies sensor noise.
  Start near zero and add cautiously.
- **Expected behavior against the sim:** the valve lag is ~120 ms (tau), so
  expect a smooth, slightly lagged approach to setpoint rather than an instant
  snap. A well-tuned loop settles without sustained hunting and holds RPM as load
  changes. Step the setpoint and confirm there's no derivative kick (that's the
  derivative-on-measurement design working).

## Moving to real hardware — what changes

**Only the OpenPLC I/O configuration changes. `dyno_control.st` does not.**
Re-point the Modbus master / Slave Device config from the simulator to the field
I/O that exposes the *identical* register map, then re-calibrate the
`(* TODO: calibrate against real hardware *)` constants (gains and trip limits).
The control law and safety interlock are reused unchanged. The whole point of
sim-first is that this transition touches config, not logic.

## Known limitation — soft real time

OpenPLC on Linux is **not** hard real-time; scan times jitter. That is
acceptable here: the valve's actuation lag (~120 ms tau) is far slower than any
realistic scan-period jitter, so the loop is dominated by plant dynamics, not by
millisecond-scale timing noise. (If a future actuator were much faster, this
assumption would need revisiting.)

## Safety note

The Structured Text safety interlock (software e-stop, overspeed, over-pressure,
over-temp) is the *first* block evaluated each scan and forces the valve closed.
On real hardware this software interlock does **not** replace a hardwired
physical e-stop — that is a separate, non-negotiable circuit.

## Verified Step Response (sim) — 2026-05-20

First end-to-end run of `dyno_control.st` against `simulator/modbus_server.py`.
PLC and sim both on `dyno-dev`; OpenPLC v3 runtime; Modbus TCP master on
port 5020. The closed loop **does hold target RPM** with the committed gains,
with caveats noted below.

### Setup

- Simulator: fresh start (no residual engine state).
- OpenPLC Slave Device: TCP, `127.0.0.1:5020`, slave id `1`, polling `50 ms`.
  Input registers `ai_start=0 ai_size=7` → `%IW100..106`.
  Holding registers `aow_start=0 aow_size=4` → `%QW100..103` (write-only;
  PLC owns them).
- Task cycle: `T#50ms` (matches `DT_S = 0.05` in the program).
- Operator commands written to OpenPLC's own Modbus server on port 502
  (which exposes `%QW101..103`): `TARGET_RPM = 5000`, `CONTROL_MODE = 1`,
  `SAFETY_ENABLE = 1`.
- Gains as committed: `Kp = 0.3`, `Ki = 0.05`, `Kd = 0.01`.

### Observed step response (setpoint 0 → 5000 RPM)

| Metric                                    | Value         |
|-------------------------------------------|---------------|
| Rise time (0 → 5000 RPM, first crossing)  | ~1.4 s        |
| Peak overshoot                            | 5197 RPM (~4%)|
| Settling time (within ±1 % = ±50 RPM)     | ~14 s         |
| Steady-state RPM                          | 5015–5030     |
| Steady-state error                        | +15–25 RPM    |
| Steady-state valve %                      | ~64–70 %      |
| `SIM_STATUS` transition                   | 0 → 1 on enable |
| Safety trips                              | none          |

### Behavior

- The loop closes. RPM rises smoothly to the setpoint, overshoots ~4 %, then
  hunts down toward steady state.
- The reverse-acting law (`error = PV − SP`, positive gains) works as designed
  on the brake-style valve.
- The derivative-on-measurement design suppresses the setpoint kick — there
  is no large initial valve spike on the step.
- **Visible hunting in steady state.** With these gains the valve oscillates
  ~25 % peak-to-peak (e.g. 56 % → 100 % between scans early on, narrowing to
  ~62 % → 70 % once settled) while RPM cycles ±20 RPM around 5015. The loop is
  stable but under-damped; `Kp` is large enough to provoke continuous
  micro-corrections.
- **Safety interlock verified.** A separate run against a sim left at
  RPM = 7000 (from a prior diagnostic) tripped the PLC's overspeed latch
  (`RPM_TRIP_RPM = 6500`): the program forced `iValveCmdRaw = 0` and
  `iSafetyEnable = 0` every scan, the sim stayed in `STATUS_STOPPED`, and
  the loop never armed. Restarting the sim cleared the trip on the next run.

### Final gains

Unchanged. `Kp = 0.3`, `Ki = 0.05`, `Kd = 0.01`. They produce a usable closed
loop and prove the architecture. They are **not** the final tuning — the
hunting above should be reduced before extended use. The brief allowed gain
changes only with before/after data; one verified run is not enough evidence
to re-set the gains. **Next tuning pass:** drop `Kp` to ~0.15–0.2 and watch
whether hunting collapses without losing the ~1 s rise time, then re-tune
`Ki` if steady-state error widens.

### Wiring changes required to make this run

These were not gain changes but were required for the program to actually
exchange data with the slave device. They live in `dyno_control.st`:

- **`AT %IW100..106` / `AT %QW100..103` clauses** added to the I/O image
  `VAR` block. Without these, OpenPLC's slave-device data never reaches the
  program's named variables — the program would compile cleanly and run with
  all-zero inputs, and its computed `iValveCmdRaw` writes would go nowhere.
- **`CONFIGURATION Config0 / RESOURCE Res0 / TASK Main` block** appended at
  the end of the file. OpenPLC v3's build pipeline expects `Config0.c` and
  `Res0.c` from `iec2c`; those are only emitted when the ST file declares a
  resource. `TASK Main` is declared with `INTERVAL := T#50ms` to match
  `DT_S` exactly.

Both changes are I/O-agnostic in the sense the file's docstring intends: the
addresses are the local OpenPLC address space, not the Modbus wire layout. The
slave-device configuration in OpenPLC is still the one thing that changes when
moving sim → real hardware.

## PID Tuning Log

Each pass is a 0 → 5000 RPM step response captured against a freshly restarted
simulator, sampled at 50 ms (matches the PLC scan). Steady-state metrics are
computed over the last 5 s of a 25 s capture. SS band is the min–max RPM in
that window; valve swing is the peak-to-peak range of the PID's commanded
valve position (`VALVE_POSITION_CMD`, not the post-lag actual) in the same
window — the raw command is what shows the controller's hunting amplitude
without the 120 ms valve-lag smoothing.

| Pass | Kp   | Ki   | Kd   | Rise (s) | Overshoot % | Settle (s) | SS band (RPM) | Valve swing |
|------|------|------|------|----------|-------------|------------|---------------|-------------|
| 1    | 0.30 | 0.05 | 0.01 | ~1.4     | ~4%         | ~14        | 5015–5030     | 62–70% (~8 pp) |
| 2    | 0.20 | 0.05 | 0.01 | ~1.5     | ~6%         | ~10        | 5001–5006     | 66.6–67.9% (1.3 pp) |

**Pass 2 — 2026-05-20.** Dropped `Kp` from 0.30 → 0.20 in `dyno_control.st`,
recompiled and reloaded into the OpenPLC runtime, and re-ran the same
0 → 5000 RPM step. `Ki` and `Kd` left untouched per the brief (only re-tune
`Ki` if SS error widens past ±25 RPM, which it did not — it tightened from
~+15 RPM to +3 RPM).

Result (vs pass 1):
- **Hunting collapsed.** Valve swing 5.31 pp → 1.30 pp (≈75 % reduction);
  steady-state RPM band 14 RPM → 5 RPM.
- **Settling faster.** Within ±1 % (±50 RPM): 13.85 s → 10.1 s (~28 % faster).
- **Steady-state error tighter.** Mean SS error 8.4 RPM → 3.0 RPM.
- **Rise effectively unchanged.** 1.4 s → 1.5 s; the difference is within one
  50 ms sample, and during the rise the PID output saturates at 0 % (engine
  cranks to idle and accelerates on full engine torque against zero brake),
  so the rise is dominated by plant dynamics, not by `Kp`.
- **Overshoot slightly larger.** 5197 RPM (~4 %) → 5310 RPM (~6 %); expected
  with lower `Kp`, since once RPM crosses the setpoint the brake builds
  proportionally slower. Still well inside the safety overspeed trip
  (`RPM_TRIP_RPM = 6500`).

All pass-2 acceptance criteria from the brief were met: settling improved,
hunting under 5 % valve swing, rise ≤ 2 s, SS error within ±25 RPM. Pass 2
gains accepted as the new committed defaults.

**Why no pass 3.** The brief allowed escalating to `Kp = 0.15` if hunting
persisted, or `Kp = 0.25` if rise grew above ~2.5 s. Neither condition was
true, so dropping `Kp` further would just trade a couple of RPM of SS
tightness for slower response. `Kd` was deliberately not touched this pass;
it stays a future knob if the real hardware shows noisier RPM than the sim.

### Reproducing a tuning pass

For repeat captures on the dev VM, the sim has no mechanical-loss model, so
killing the engine (SAFETY_ENABLE → 0) does not bleed RPM to zero — the sim
must be restarted to get a clean step from 0. The pass-2 capture script
sequence used was: disarm via OpenPLC port 502 (write `SAFETY_ENABLE = 0`,
`TARGET_RPM = 0`), `fuser -k -n tcp 5020` the sim, restart `modbus_server.py`,
wait ~1 s for OpenPLC's slave-device master to reconnect and push the zero'd
holding registers, then arm with `TARGET_RPM = 5000`, `CONTROL_MODE = 1`,
and finally trigger the step with `SAFETY_ENABLE = 1` (the PLC's bumpless-
start logic clears the integrator on the rising edge).

(One gotcha encountered this session: OpenPLC's `/compile-program` endpoint
silently 302-redirects to `/login` if the session cookie has expired, and the
existing binary remains in place. Verify a recompile actually happened by
checking `core/openplc`'s mtime, not just the HTTP status.)
