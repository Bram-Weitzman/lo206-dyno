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
