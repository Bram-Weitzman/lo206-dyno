# CLAUDE.md — Dev context for Claude Code

## Project purpose

Build a hybrid hydraulic/mechanical dynamometer for the Briggs & Stratton
LO206 kart engine, controlled by a Raspberry Pi running OpenPLC. We are
**sim-first**: a Python simulator stands in for the engine + load so the
entire control system can be validated before any hardware is bought.

## Current phase

**Current phase: hardware procurement.**

The full software stack is complete and verified end-to-end on dyno-dev:
- Simulator: DynoEngine class (clutch model bypassed 2026-05-22 — see below), RPM noise model, 15/15 tests passing
- PLC control logic: PID hold, manual, sweep modes; safety interlocks
- Logger: Modbus TCP → SQLite at ~100 ms poll rate
- Dashboard: Next.js, live chart (RPM/torque/HP), run history, CSV export —
  verified 2026-05-21 with PLC holding 5000 RPM in PID mode
- Clutch model REMOVED from the physics loop (2026-05-22): the bench dyno
  measures the engine directly across the full rev range. This also resolved the
  old below-engagement pressure/CHT inconsistency.
- Brake model RE-DERIVED from spec'd hardware (2026-05-23): the linear
  PUMP_LOAD_GAIN placeholder was replaced with physics from the 2.14 cu in/rev
  pump + 2.909:1 gear set + non-compensated throttle valve. New torque-balance
  floor ~2510 RPM (was ~3360 under the placeholder). See "Current session state".
- Hardware: brake pump + valve TYPE + gear set now locked (see docs/bom.md);
  exact part numbers, valve coil drive, and several line items still TBD.

**Phase 4 (presentation/blog): not started, deadline May 29.**

**Hydraulic brake hardware locked (2026-05-22) — SUPERSEDES the old 1.52 cu.in. / chain design:**
- **Brake pump:** fixed-displacement gear pump, **~2.14 cu in/rev, 3000 PSI** rated.
  Candidate: Dalton Hydraulic. (Was: 1.52 cu.in. Princess Auto 8375446 — dropped.)
- **Drive:** **22T engine / 64T pump gear set = 2.909:1 reduction.** Engine 2500 RPM
  → pump 859 RPM; engine 6100 → pump 2097 RPM. (Was: #219 chain 20T/70T 3.5:1 — dropped.)
- **Brake valve:** electro-proportional **THROTTLE cartridge valve (NON-compensated)** —
  builds back-pressure by restricting pump-outlet flow. **Rated ~30 GPM** so the
  8–19.4 GPM window sits in the accurate mid-range; pressure ≥3000 PSI; **likely
  pilot-operated** at this size (needs minimum pilot/supply pressure, adds slight
  lag). Candidate families: Sun **FPFK**-class, **HydraForce**, or **Bosch Rexroth**
  electro-proportional cartridges. **NOT** a pressure-compensated flow-control valve
  (that holds flow constant and would fight the brake — wrong part). (Was: ~3–6 GPM
  Sun FPCH/Brand EFC sizing, re-spec'd 2026-05-23 for the corrected flow; originally
  Sun RPGC-LBN pressure-relief — both dropped.)
- **Three-tier pressure scheme:** **working ~1128 PSI / mechanical relief ~2000 PSI /
  pump rating 3000 PSI.** Worked point: absorbing the engine's ~11 ft-lb low-end
  torque needs ~32 ft-lb (384 in-lb) at the pump shaft (×2.909) = ~1128 PSI (~38% of
  rating). Torque→pressure is speed-independent; only flow varies with RPM.
- **Pump flow (VERIFIED, 2026-05-23):** **8.0 GPM at 2500 engine RPM → 19.4 GPM at
  6100** (Q = 2.14 × pump_rpm / 231, pump_rpm = engine_rpm / 2.909). An earlier
  0.8–2.0 GPM figure was wrong by ~10× (a 0.214-vs-2.14 cu in/rev displacement slip)
  and is fully superseded. This 8–19.4 GPM window is what the valve / relief /
  reservoir / plumbing are sized for (see `docs/bom.md`).
- **Coil drive: TBD (recommendation recorded).** Prefer a **current-controlled
  proportional amplifier card with adjustable dither (~100–250 Hz)** — carried as
  its own BOM line item — over raw PWM from the Pi (a ~30 GPM proportional cartridge
  wants stable dithered coil current). Valve TYPE is locked; coil drive NOT finalized.
- **Pressure transducer range** widened to **0–3000 PSI** (was 0–1500) for this scheme;
  `PSI_REG_MAX` in `modbus_map.py` bumped 1500→3000 (behavior-neutral under current trips).
- **Brake-capacity floor (new model):** torque-balance floor **~2510 RPM** —
  brake torque 11.1 = engine torque 11.1 ft-lb at ~1141 PSI. (Was ~3360 under the
  old PUMP_LOAD_GAIN=18.5 placeholder.) With the **trip raised to 1700 PSI
  (2026-05-23)**, full braking now settles at this floor without faulting (steady
  ~1141 PSI / transient peak ~1290 PSI, both under 1700).

## Stack

- **Simulator**: Python 3.12 (pymodbus, numpy, pytest), venv at `/opt/dyno-venv`
- **PLC**: OpenPLC runtime, IEC 61131-3 Structured Text
- **Transport**: Modbus TCP (port 502)
- **Dashboard**: Next.js — complete (live RPM/torque/HP chart, run history, CSV export)
- **Persistence**: SQLite for local runs, PostgreSQL if/when we centralize

## Critical design principle

**The control logic is I/O-agnostic. The Modbus register map is the contract.**
The PLC reads sensor values and writes a valve command over Modbus. It does not
know or care whether the other end is the Python simulator or real hardware.
Never branch the control logic on "sim vs real". If the sim and the hardware
disagree, the register map (`plc/register_map.md`) is the source of truth and
must be changed *first*, deliberately, before either side.

## VM info

- Host alias: **dyno-dev** (Ubuntu 24.04 LTS dev stand-in for the Pi)
- IP: **10.20.99.55** (lab network 10.20.99.0/24)
- OpenPLC web UI: **http://10.20.99.55:8080** (service: `systemctl status openplc`)
- Python venv: **/opt/dyno-venv**
- Repo: **/home/ubuntu/projects/lo206-dyno**

## Key file locations

| Path                          | What it does                                      |
|-------------------------------|---------------------------------------------------|
| `simulator/engine_sim.py`     | LO206 engine + load physics model                 |
| `simulator/torque_curve.py`   | LO206 torque lookup table + interpolation         |
| `simulator/modbus_server.py`  | Modbus TCP server wrapping the sim                 |
| `plc/dyno_control.st`         | PID control loop + safety interlocks (ST)         |
| `plc/register_map.md`         | **The contract** — Modbus register definitions    |
| `docs/architecture.md`        | System design and rationale                       |
| `scripts/start_sim.sh`        | Launch the simulator                              |
| `scripts/provision_vm.sh`     | Reproduce the dev VM environment                  |

## Before writing any code

1. **Read `plc/register_map.md` first.** If your change touches any value that
   crosses the Modbus boundary, the register map must be updated *before* the
   code on either side.
2. Confirm which side *owns* the register you are touching (PLC-writes vs
   sim-writes). Owners are documented in the register map.
3. Keep the control logic free of sim-specific assumptions.
4. Run `pytest` in `simulator/` before committing simulator changes.

## Known open questions

- **Proportional valve**: TYPE LOCKED — an electro-proportional **THROTTLE
  cartridge valve (non-compensated)**, **rated ~30 GPM** for the verified 8–19.4
  GPM window (re-spec'd 2026-05-23; was ~3–6 GPM). Candidate families Sun FPFK /
  HydraForce / Bosch Rexroth; **likely pilot-operated** at this size. NOT a
  pressure-compensated flow-control valve, and no longer the Sun RPGC-LBN. Full
  spec + VERIFY-before-purchase list in `docs/bom.md`. **Coil drive still TBD —
  recommendation recorded: a current-controlled proportional amplifier card with
  dither, over raw Pi PWM.** Exact part number + amplifier selection still TBD.
- **Engine inertia / valve lag constants**: placeholders in `engine_sim.py`;
  need real values once we can bench-measure the engine and valve.
- **Torque curve fidelity**: we currently use published B&S 206 Racing data for the Stock/Unrestricted 206 slide (#555590, commonly called the black slide).
  Other slide configs are not yet digitized (see `docs/bom.md`).
- **Safety thresholds**: RPM > 6500 remains a first-guess — confirm against
  engine builder recommendations once on real hardware. **PSI trips RAISED
  900/750 → 1700 PSI (2026-05-23)** to match the corrected brake model: sim
  `OVERPRESSURE_TRIP_PSI` (`modbus_map.py`) and PLC `PSI_TRIP_PSI`
  (`dyno_control.st`) are both **1700 PSI** (they must agree). Ordering is now
  **working ~1128 < trip 1700 < mechanical relief ~2000 < pump rating 3000** —
  the trip rides ~50% above the steady working point for PID transients and fires
  before the ~2000 PSI relief. The ~2000 PSI relief replaces the old 1,500 PSI;
  the old ~200 PSI return-line back-pressure valve is dropped (no baseline in the
  new model). RPM (6500) and CHT (250 °C) trips unchanged.
- **AFR channel (30006)**: reserved but unpopulated — wideband O2 is a Phase 2
  hardware addition.
- **Dashboard data path**: RESOLVED — the logger polls Modbus TCP and writes
  SQLite (`data/dyno.db`); the dashboard reads that SQLite DB. Verified
  end-to-end 2026-05-21.
- **Clutch model pressure/CHT scope** (RESOLVED 2026-05-22): fixed by removing
  the clutch from the physics loop entirely (see Current session state). With the
  clutch gone, torque, pressure and CHT all compute from the same (full) pump
  load — the old below-engagement inconsistency is gone.

## Real-world calibration data

Measured from actual LO206 race session (RPM + GPS logs, May 2026).
Use these as ground truth when setting sim constants and validating
the control system.

### Engine idle
- Warm idle RPM: **2,400–2,500 RPM**
- Cold/high idle during warmup: up to 3,000–3,200 RPM before settling
- Warm idle is safely below clutch engagement (~3,400 RPM) — engine can
  be started and warmed without loading the pump
- Dyno startup procedure: do not blip throttle above ~3,400 RPM until
  operator is ready to load the pump

### Clutch engagement profile (Hilliard Inferno Flame, stock config)
> **REFRAMED 2026-05-22:** the clutch model was removed from the dyno's engine
> physics (the bench dyno measures the engine directly). The numbers below are
> REAL measured drivetrain reference data — hard-won from race logs and the
> Hilliard spring chart — and are RETAINED as such. They no longer drive the sim
> engine model, but remain the reference for future clutch work (e.g. the
> load-profile run mode, GitHub issue #8) and for tuning a real clutch.
- Spring config: 2 black + 2 white springs, 0 heavy weights per shoe
- First engagement RPM: **~3,400 RPM** (confirmed — matches Hilliard spring
  chart spec, validated against race data cursor reading of 3,537 RPM at
  the visible transition point)
- Engagement behavior: **no RPM dip**. Engine RPM acceleration rate visibly
  reduces as clutch absorbs inertia torque, but RPM does not drop.
- Estimated full lockup RPM: **~4,200 RPM** under pump load (TBD — on-track
  data not conclusive; pump load is much heavier than kart rolling resistance)
- Sim model: torque_transfer = linear ramp from 0 at CLUTCH_ENGAGEMENT_RPM
  to 1.0 at CLUTCH_LOCKUP_RPM. No RPM dip modeled.
- Blog note: on-track clutch engagement is nearly transparent because kart
  rolling resistance is trivial. On the dyno, engagement against a pressurized
  pump circuit will be more pronounced — lockup RPM will shift higher under load.

### RPM signal characteristics
- Real RPM signal shows consistent ~±100 RPM noise band at steady state
- Visible across all zoom levels of race data
- Source: likely Hall-effect pickup with single trigger tooth — normal for kart
- Sim should add representative noise to RPM output so PID is tuned against
  realistic input, not a perfectly clean signal
- DONE: `RPM_NOISE_BAND = 100` applied in `engine_sim.py` (commit 4b126e1) —
  ±100 RPM injected on `get_rpm()` output only; internal physics state stays clean.

### Calibrated sim constants (applied)
The following constants are confirmed from real-world data and have been
applied to the simulator. IDLE_RPM, RPM_NOISE_BAND, and OVERPRESSURE_TRIP_PSI
were applied in the prior code session. The clutch constants
(CLUTCH_ENGAGEMENT_RPM, CLUTCH_LOCKUP_RPM) are RETAINED in engine_sim.py as
validated reference data but are NO LONGER wired into the physics loop — the
clutch was bypassed 2026-05-22 so the dyno measures the engine directly.
Note: `OVERPRESSURE_TRIP_PSI` lives in `simulator/modbus_map.py`, not `engine_sim.py`.
The real simulator API uses `set_engine_enable()` and valve positions as 0–100 (int),
not `set_safety_enable()` or 0.0–1.0 floats — use the correct API when applying these.

```python
# engine_sim.py
IDLE_RPM = 2400               # APPLIED -- warm idle, measured from race data
CLUTCH_ENGAGEMENT_RPM = 3400  # RETAINED reference -- bypassed from physics 2026-05-22
CLUTCH_LOCKUP_RPM = 4200      # RETAINED reference -- bypassed from physics 2026-05-22
RPM_NOISE_BAND = 100          # APPLIED -- +/-RPM noise on output only, steady state from race data

# engine_sim.py -- NEW brake model (2026-05-23), replaces PUMP_LOAD_GAIN placeholder
GEAR_RATIO = 64.0 / 22.0      # 2.909:1; pump_rpm = engine_rpm / GEAR_RATIO; engine
                              # brake torque = pump-shaft torque / GEAR_RATIO (NOT * --
                              # the brief prose was inverted vs its own worked example)
PUMP_DISP_CUIN = 2.14         # cu in/rev gear pump, 3000 PSI; VERIFY before purchase
VALVE_ORIFICE_K = 17.8        # PSI/(GPM^2 * restriction^2); non-comp orifice, pinned to the
                              # 1128 PSI @ valve100%/2500 RPM worked point; BENCH-MEASURE
# pressure = VALVE_ORIFICE_K * (valve_act/100)^2 * flow_gpm^2 ; flow = 2.14*pump_rpm/231
# brake_ftlb = pressure * PUMP_DISP_CUIN/(2*pi)/12/GEAR_RATIO  (1128 PSI -> 11.0 ft-lb)

# simulator/modbus_map.py
PSI_REG_MAX = 3000            # APPLIED 2026-05-22 -- 0-3000 range for the 3-tier scheme
OVERPRESSURE_TRIP_PSI = 1700  # RAISED 900 -> 1700 (2026-05-23) for the corrected model;
                              # working ~1128 < trip 1700 < relief ~2000 < rating 3000.
                              # MUST equal PSI_TRIP_PSI in plc/dyno_control.st.
```

## Git author note

Git on the VM is configured as `Bram Weitzman <bram.weitzman@gmail.com>`.
**Confirm/replace** these if a different identity should own the commits.

## Current session state

### Session 2026-05-23 (newest) -- Coastdown model + binary throttle; sweep RE-VERIFIED

Fixed the run-43 freewheel-at-the-limiter failure and added engine throttle
control. Root cause: the sim had no friction, so a disabled/unloaded engine
coasted forever near 6000 RPM; a sweep started against that brake-grabbed past
the 1700 trip and faulted. **PID gains, pressure trips, and pump/torque physics
were NOT touched.**

- **Coastdown / friction (`engine_sim.py`, commit `481fbd1`):** engine internal
  friction + pumping/compression braking, viscous + static
  (`FRICTION_VISCOUS_FTLB_PER_RPM = 0.0016`, `FRICTION_STATIC_FTLB = 1.5`,
  calibratable). Coasts 6000→2500 RPM in ~1.7 s unloaded. Applied **only
  off-power** (engine not firing) so the WOT path -- and the validated sweep
  physics -- are byte-identical (the curve is already net-of-friction).
- **Binary throttle** (contract `ef1cb96`, sim+plc `c133b38`, addr fix `20e5263`):
  a **THROTTLE coil** (idle vs wide-open). Sim coil 0; **PLC located `%QX100.0`**;
  **:502 coil address 800** (the dashboard read/writes this). At idle the engine
  makes NO drive torque → friction/coastdown brings RPM to a low idle (idle
  governor holds IDLE_RPM while enabled); at WOT it follows the existing curve.
  PLC drives it fail-safe: idle on startup/fault/disable, forced WOT when a
  PID/sweep run is armed, operator-owned in MANUAL mode. **This is BINARY only --
  a precursor to, NOT a replacement for, the post-interview proportional-throttle
  / two-axis (throttle × brake) work.**
- **GUI (`1cbc40b`):** Manual/diagnostics panel -- throttle accelerator/lift-off
  button (writes the coil) + manual valve override slider (0-100%, deliberate
  Apply). Both disabled while a PID/sweep run is open, and `set_valve` forces
  CONTROL_MODE=manual (mutually exclusive with PID/sweep), so they cannot fight
  the PID.
- **OpenPLC runtime config changed (NOT version-controlled -- see bring-up
  notes):** the slave device gained a **Coils-Write block (start 0, size 1)** so
  `%QX100.0` mirrors to sim coil 0. Without it the throttle never reaches the sim.

**RE-VERIFIED end-to-end (remote-equivalent, via the dashboard API → OpenPLC :502):**
- (a) idle throttle → engine sits at low idle **~2500 RPM**, NOT the limiter.
- (b) lift throttle from WOT (revved to **6209**) → decelerates to idle (**2374**).
- (c) clean stepped sweep **run 46** (`docs/verification/sweep_run46.csv`, 716
  samples, 4000→6100 / step 400 / dwell 10 s): **no fault** (peak 1689 PSI),
  auto-completed. Torque falls **9.74→7.56 ft-lb** (4000-6000); **HP rises
  7.47 → peak 9.61 @ ~5600 → 8.60 @ 6000** (the ~8.6 HP top; 6100 is the
  rev-limiter band, invalid). Matches the prior run-38 curve, now with the engine
  properly fired by the throttle.

**WHAT REMAINS:** real-hardware calibration (friction/gains/trips are sim
values); **proportional throttle + two-axis throttle×brake mapping (post-
interview)**; coil-drive choice; circuit procurement. Nothing is BLOCKED.

---

### Session 2026-05-23 -- PID retuned + trips raised + sweep VERIFIED

The control loop is now tuned to the corrected brake model and a clean full-band
verification sweep was captured -- the work the prior notes flagged as "next
session." This UNBLOCKS the design-document headline torque/HP figure.

- **Pressure trips raised 900/750 -> 1700 PSI** (sim `OVERPRESSURE_TRIP_PSI` +
  PLC `PSI_TRIP_PSI`). Ordering: working ~1128 < trip 1700 < relief ~2000 <
  rating 3000. (commit `6bb9e28`)
- **PID retuned KP/KI/KD 0.2/0.05/0.01 -> 0.02/0.02/0.0** (P+I), tuned against
  the sim over Modbus at the 50 ms control period. The old gains bang-banged the
  valve and tripped; the new gains hold tight (mean error ~45-65 RPM = the +-100
  noise floor, valve std ~1-3%, no bang-bang). KD=0 because the +-100 RPM sensor
  noise makes derivative-on-measurement counterproductive. (commit `ca0c026`)
- **OpenPLC recompiled** with the new gains+trip (`st_files/472060.st` rebuilt
  via `/compile-program`), then the full stack was brought up.

**VERIFIED SWEEP -- run_id 38** (CSV: `docs/verification/sweep_run38.csv`, 728
samples). Stepped 4000 -> 6100 RPM, step 400, dwell 10000 ms, driven through the
dashboard command API -> OpenPLC :502 -> PLC sweep supervisor -> sim. **Completed
cleanly, NO fault** (peak pressure 1594 PSI < 1700 trip), PLC self-completed
(SWEEP_STATE 1->2, dropped SAFETY_ENABLE), run auto-closed. Settled per step:

| setpoint | act RPM | torque ft-lb | HP   | PSI  | valve % |
|---------:|--------:|-------------:|-----:|-----:|--------:|
| 4000     | 3989    | 9.74         | 7.39 | 997  | 58.6    |
| 4400     | 4438    | 9.19         | 7.77 | 951  | 52.0    |
| 4800     | 4821    | 9.30         | 8.54 | 953  | 47.8    |
| 5200     | 5210    | 9.40         | 9.32 | 976  | 44.6    |
| 5600     | 5582    | 9.05         | 9.62 | 932  | 40.6    |
| 6000     | 5983    | 7.61         | 8.67 | 768  | 34.4    |
| 6100     | 6037    | 4.25*        | 4.89*| 443  | 25.7    |

**Torque falls** gently (9.74 -> 7.61 over 4000-6000) and **HP RISES** to a peak
~**9.6 HP at ~5580 RPM**, ~**8.67 HP at 6000** (the ~8.6 HP ballpark; matches the
published Stock-206 curve). *The 6100 row is degraded -- it sits in the rev-limiter
band (spark cut at 6100), so torque is intermittently cut; not a valid power
point. The usable power curve is 4000-6000 RPM.

**DWELL NOTE:** the gentle PID needs >2 s to settle each step; 2000 ms (the prior
default) leaves the first idle->setpoint acquisition overshooting (it free-
accelerates past the target). 10000 ms dwell settles cleanly. The dashboard dwell
slider is the knob for this. **SWEEP MUST START FROM IDLE:** the sim models no
coastdown drag, so a back-to-back sweep starts with the engine still at ~6000 RPM
and the brake-grab overpressure-trips -- restart the sim (or otherwise return to
idle) before each verification sweep. Start RPM ~4000 (below ~3800 the valve
saturates / the grab can trip).

**WHAT REMAINS (the sim control system is now fully validated end-to-end):**
- **Real-hardware calibration.** Every gain/constant is sim-tuned. On the real
  rig the valve gain, pump displacement, inertia (J_ENGINE), valve lag, and the
  pressure trips must be re-calibrated against measured behavior. The PID gains
  (0.02/0.02/0) are a starting point, not final.
- **Coil drive still TBD** (12 V PWM vs proportional amplifier card — amplifier
  recommended; not finalized).
- **Hardware procurement** of the re-spec'd circuit (30 GPM throttle valve +
  amplifier, 2.14 cu in/rev pump, gear set, ≥20 GPM relief, multi-gal reservoir +
  likely oil cooler) — and the budget is now likely over the $1000 CAD target.
- Optional: re-run the sweep at a longer dwell with a lower start if a cleaner
  near-floor data point is wanted for the doc.
This session closed the control-loop validation; nothing further is BLOCKED.

---

### Session 2026-05-23 -- Pump flow corrected (10x) + valve/circuit re-spec'd

A focused **flow correction**. The prior session had flagged the pump flow as
~10× too low; this session confirmed and fixed it, then re-spec'd the
flow-dependent hardware. **Docs + one sim comment only — no PID retune, no
safety-trip change, no verification sweep, coil drive still not finalized.**

- **Corrected flow window: 8.0 GPM at 2500 engine RPM → 19.4 GPM at 6100**
  (Q = 2.14 cu in/rev × pump_rpm / 231, pump_rpm = engine_rpm / 2.909). The old
  0.8–2.0 GPM figure was wrong by ~10× — a 0.214-vs-2.14 cu in/rev displacement
  slip — and is fully superseded.
- **Torque/pressure math UNCHANGED.** It has no flow term: the ~1128 PSI working
  point, 2.14 cu in/rev displacement, 3000 PSI rating, and the three-tier
  1128/2000/3000 scheme all still stand. Pump displacement, gear ratio, PID gains,
  and the safety trips were NOT touched.
- **Valve re-spec'd** (commit `d30178c`): from a ~3–6 GPM valve to a **~30 GPM
  electro-proportional THROTTLE cartridge** (non-compensated), so the 8–19.4 GPM
  window sits in the accurate mid-range (bottom two-thirds of rated flow). Candidate
  families Sun **FPFK** / **HydraForce** / **Bosch Rexroth**. **Likely
  PILOT-OPERATED** at this flow size (minimum pilot/supply pressure, slight added
  lag) — the sim's 50–200 ms valve-lag model already covers a plausible range.
- **Coil drive still TBD**, but the **recommendation is recorded**: a
  current-controlled proportional **amplifier card with adjustable dither
  (~100–250 Hz)**, as its own BOM line item, over raw Pi PWM. Not finalized.
- **Flow-dependent circuit sized for 8–19 GPM:** system relief **≥20 GPM** / ~2000
  PSI; **multi-gallon reservoir** (~5–10 gal) with an **oil cooler likely needed**
  for sustained sweeps (~5–6 HP dumped as heat); **#8/#10 plumbing** for ~19 GPM
  peak (not #6).
- **Size/weight + budget impact:** the 30 GPM valve + amplifier + ≥20 GPM relief +
  multi-gallon reservoir + larger plumbing make the brake circuit the **size/weight
  driver** of the build (matters for the transportable/trailer constraint) and
  **likely push the build OVER the sub-$1000 CAD target** once priced (see
  `docs/bom.md` Budget).
- **Sim:** the brake model already derived flow correctly from displacement × RPM
  (no stale flow constant); only a stale `VALVE_ORIFICE_K` comment was updated
  (commit `be36b14`). 16/16 tests still pass, physics unchanged.

**NEXT SESSION (unchanged by this flow correction):** PID retune for the new
plant, review of `PSI_TRIP_PSI` (750) + `OVERPRESSURE_TRIP_PSI` (900) against the
~2000 PSI relief, and the full verification sweep + HP-rise re-confirm (remote
browser, not curl) all remain outstanding. This session changed circuit *sizing*,
not the control loop or the plant physics.
> [SUPERSEDED 2026-05-23 — all three are now DONE; trips raised to 1700, PID
> retuned to 0.02/0.02/0, and sweep verified (run 38). See the newest entry above.]

---

### Session 2026-05-23 -- Brake hardware locked + sim brake model re-derived

Locked two brake-hardware decisions and rebuilt the sim brake physics around
them. This was a **docs + sim-model + contract** change only — **no PID retune,
no safety-trip change, no verification sweep** (all explicitly next session).

**Hardware locked** (full spec + VERIFY-before-purchase lists in `docs/bom.md`):
- Brake pump: fixed-displacement gear pump, ~2.14 cu in/rev, 3000 PSI (Dalton
  candidate). Replaces the dropped 1.52 cu.in. Princess Auto pump.
- Drive: 22T engine / 64T pump gear set, **2.909:1**. Replaces the dropped #219
  chain (3.5:1).
- Brake valve: proportional **pressure/throttle control valve (NON-compensated)**,
  Sun FPCH-class or Brand EFC-class. **NOT** a flow-control (compensated) valve —
  that holds flow constant and would fight the brake. Replaces the dropped Sun
  RPGC-LBN. **Coil drive (12 V PWM vs 0–10 V amp card) deliberately left TBD.**
- Three-tier pressure: **working ~1128 / relief ~2000 / pump rating 3000 PSI.**

**Sim brake model re-derived** (`engine_sim.py`, commit `4782021`): the linear
`PUMP_LOAD_GAIN=18.5` placeholder (tuned to the dead chain design) is gone.
New physics, every constant documented inline + flagged for bench measurement:
```
pump_rpm        = engine_rpm / 2.909
pump_flow_gpm   = 2.14 * pump_rpm / 231
pump_pressure   = VALVE_ORIFICE_K(17.8) * restriction^2 * flow^2   (non-comp orifice)
engine_brake_ftlb = pump_pressure * 2.14/(2*pi) / 12 / 2.909
```
Anchored to the documented worked point and verified to reproduce it exactly
(valve 100% @ 2500 RPM / 7.96 GPM → 1128 PSI → 11.0 ft-lb). Published pressure
now caps at `PSI_REG_MAX` (3000), not the trip, so overpressure is visible to
the trip. No back-pressure baseline (the new design has no return-line valve).
16/16 sim tests pass (the old brake-floor test was split into two: one for the
overpressure-fault-under-current-cap behavior, one for the trips-raised floor).

**GEAR-DIRECTION CORRECTION (flagged, not silently changed):** the session
brief's prose said "engine brake torque = pump-shaft torque × 2.909," which is
**inverted** vs the brief's own worked example (11 ft-lb engine ↔ 32 ft-lb pump
↔ 1128 PSI). Built to the physically correct **/2.909** (pump is the slow,
high-torque side), which is what reproduces the worked point. Noted in code +
`docs/bom.md`.

**FLOW INCONSISTENCY (RESOLVED 2026-05-23):** the earlier 0.8–2.0 GPM figure was
confirmed wrong by ~10× (a 0.214-vs-2.14 cu in/rev displacement slip). The verified
window is **8.0–19.4 GPM**; the sim already used the displacement-consistent flow.
The valve was subsequently re-spec'd to a ~30 GPM throttle cartridge for this window
— see the newest session entry and `docs/bom.md`.

**Floor re-probe (full throttle, valve 100%):**
- **Under the UNCHANGED 900 PSI sim trip:** develops >900 PSI at ~2749 RPM →
  latches a fault → valve forced shut → engine runs up to the ~6100 limiter.
  **No holdable floor exists under the current trips.**
- **Torque-balance floor (trips conceptually raised):** **~2510 RPM** (1141 PSI,
  brake 11.1 = engine 11.1 ft-lb), vs the old placeholder's ~3360.

**SWEEP_START_RPM defaults: NOT changed this session.** The current default (3400)
still sits above the new ~2510 floor, and — more importantly — the sweep cannot
run at all until the trips/PID are addressed (full braking faults immediately).
Revisiting the default belongs with next session's retune, once a clean hold is
possible. `register_map.md` + dashboard left as-is.

**>>> NEXT SESSION (blocked on a deliberate control/safety change) <<<**
> [DONE 2026-05-23 — all three items below were completed: trips raised to 1700
> PSI, PID retuned to 0.02/0.02/0, and the verification sweep passed (run 38,
> CSV in docs/verification/). See the newest "Current session state" entry.]
The brake model changed, so before any client-doc HP figure is taken:
1. **Retune the PID** for the new (much stronger) plant.
2. **Review the pressure trips** against the three-tier scheme: sim
   `OVERPRESSURE_TRIP_PSI` (900) and **PLC `PSI_TRIP_PSI` (750)** both sit below
   the ~1128 PSI working point — raise them toward the ~2000 PSI relief. (Trips
   were left untouched this session per scope.)
3. **Re-run the verification sweep** and re-confirm the HP-rise curve end to end
   (remote browser at http://10.20.99.55:3000, not curl).
Until then the sim faults at full braking — expected, and the reason this work
was sequenced "brake model correct first, then retune."

---

### Session 2026-05-22 -- Torque curve corrected to Stock/Unrestricted 206 (#555590)

The simulator torque table held the WRONG slide data: restricted-slide values
that fell to ~4.96 ft-lb at 6000 RPM and produced a physically wrong FALLING HP
curve (peak HP only ~7). A diagnostic had already confirmed the HP PATH is
correct (HP = torque*RPM/5252, derived in the logger) -- the bug was the torque
DATA. Replaced `simulator/torque_curve.py` `TORQUE_CURVE_FT_LBS` with the
published B&S 206 Racing data for the **Stock/Unrestricted 206 slide (#555590,
commonly called the black slide)**:

| RPM   | 2500 | 3000 | 3500 | 4000 | 4500 | 5000 | 5500 | 6000 |
|-------|------|------|------|------|------|------|------|------|
| ft-lb |11.13 |11.12 | 9.83 | 9.76 | 9.09 | 9.45 | 9.45 | 7.52 |

Table structure + interpolation unchanged; only the torque VALUES changed. HP
stays derived in the logger -- no chart HP loaded anywhere. 15/15 sim tests pass
(updated midpoint neighbours, the 6000-RPM comment, and the peak-torque RPM,
which is now 2500).

**6000-RPM point (7.52 ft-lb) -- kept as published, NOT smoothed.** No graph
image exists in the repo to eyeball, so the call rested on the HP cross-check:
7.52*6000/5252 = 8.59 HP, which matches the chart own HP column at 6000 and the
LO206 ~8.8 HP rating. A gentle taper holding ~9.45 to 6000 would imply ~10.8 HP
-- implausibly above rating. So the top-end dip is real, not a transcription
artifact.

**HP now RISES across the band** (computed from the new torque): ~6.5 HP at
3400 -> ~9.0 at 5000 -> ~9.7 around 5500-5600 -> 8.59 HP at 6000. The whole-band
trend climbs and peaks near the top, as physics expects -- the falling-HP bug is
gone.

**Floor re-probed:** full throttle + valve 100% now settles at **~3,360 RPM**
(was ~3,135 under the old restricted curve). Higher low-end torque (11.13 vs
9.06 at 2500) lets the engine resist the brake to a higher RPM. The floor-aware
SWEEP_START_RPM DEFAULT was bumped 3200 -> 3400 (register_map.md + dashboard) so
the default sweep starts just above the new floor; the 2500 lower CLAMP is
unchanged.

**VERIFICATION SWEEP -- PARTIAL PASS then BLOCKED (Step 4, 2026-05-23):** ran a
remote-browser stepped sweep (run #30, 3400->6100, step 400, dwell 2000ms).
Through the 5400 step the corrected curve behaves EXACTLY as intended -- torque
falls gently (11.1 -> 9.4 ft-lb) and **HP RISES 5.99 -> 9.16** (set 3400 hp 5.99;
set 5000 hp 8.78; set 5400 hp 9.16). The falling-HP bug is gone. BUT the sweep
could not complete the top of the band: at the 5400 step the PID went unstable
(valve_cmd slamming 0<->100%), hydraulic pressure spiked to 767 PSI and crossed
the PLC-side overpressure interlock `PSI_TRIP_PSI := 750.0` (dyno_control.st:98).
The PLC latched a fault and forced SAFETY_ENABLE->0; pressure then decayed and
the latch released, but the run was left stopped with SWEEP_STATE stuck at 1
(the sweep supervisor is gated on SAFETY_ENABLE=1, so it neither advances nor
completes). No sim status=2 was logged -- the sim own overpressure cap is 900,
never reached. No full-band CSV could be exported.

ROOT CAUSE is the corrected (higher) torque, NOT the data or HP path: the
unrestricted-206 curve makes ~9.4 ft-lb across the upper-mid band (vs ~5-6 with
the old restricted curve), so the brake must work far harder to hold each step.
Steady-state hold pressure (~556 PSI at 5400) is under the trip, but the PID --
still tuned for the old, weaker plant -- oscillates and the valve-to-100%
transients spike pressure past 750.

DECISION NEEDED before Step 4 can pass (a control/safety change beyond the
torque-data fix, left for a deliberate call): (a) re-tune the PID gains for the
corrected plant so the valve stops oscillating (most likely the right fix);
and/or (b) revisit `PSI_TRIP_PSI` (750, flagged TODO-calibrate) and/or
`PUMP_LOAD_GAIN` (18.5) so the pressure needed to hold the upper band stays under
the trip. The torque-curve correction itself (Steps 1-3) is committed, pushed,
and verified correct through 5400 RPM. This note stays until a clean full-band
sweep passes.

---

### Session 2026-05-22 (latest) -- PID target updatable MID-RUN from the dashboard

The PID hold target can now be retuned **without ending the run.** In the
**PID hold** panel, while a run is open the target number field and slider
stay editable and the **Start (PID)** button is replaced by an enabled
**Update Target** button that sends a single deliberate write of the new
TARGET_RPM (%QW101). One write per click, not continuous-on-drag — matches
the rest of the dashboard's "every command is a deliberate button" pattern
and is the safer shape for commanding a real engine.

- `/api/command` gained a `set_target` action that writes ONLY %QW101 —
  CONTROL_MODE and SAFETY_ENABLE are NOT touched. Server-side clamp to
  3200–6100, same band as `start`. The existing PID loop reads %QW101 every
  scan, so the engine tracks the new setpoint without re-arming.
- `OperatorControls.tsx` swaps Start (PID) for Update Target while a PID run
  is open (gate: run open AND not sweepActive). Not shown during a sweep run
  or when no run is open. Client-clamped to the same 3200–6100 band.
- **No contract change.** %QW101's mode-scoped ownership (operator in PID,
  sweep logic in SWEEP) already documents the operator writing it in PID
  mode; mid-run is still within that. No PLC change, no ST recompile/redeploy.

**Browser verification PASSED 2026-05-22** (remote browser at
`http://10.20.99.55:3000`, not curl).
- PID hold at 4000 RPM: avg ~4112 RPM, within ±100 RPM noise band.
- Mid-run target updated 4000→5500: engine tracked UP, avg ~5511 RPM, `run_id`
  unchanged (run #21).
- Mid-run target updated 5500→4500: engine tracked DOWN, avg ~4576 RPM, no
  overpressure trip, `run_id` still #21.
- Client clamping: typing 2000 sent target 3200, typing 9000 sent target 6100
  (readback confirmed).
- Server clamping: raw `fetch('/api/command', set_target, target=1000)` clamped
  to 3200; target=12000 clamped to 6100; missing target → HTTP 400. `set_target`
  did NOT touch `control_mode` or `safety_enable` (verified via readback).
- Update Target visibility: hidden when no run is open, hidden during a sweep
  run (including across page reloads), shown during a PID run (including
  across page reloads).
- Sweep regression: in-session sweep 3200→6100, step 400, dwell 2000ms
  staircased the full band and auto-closed the run (run #24).

**Reload-state bug found & fixed during verify** (commit 8e4b9b9): on a page
reload during a sweep run, the in-component `sweepActive` flag reset to false
and Update Target was wrongly shown. Fixed by polling `/api/command` while ANY
run is open (not only while `sweepActive`) and gating Update Target on
`readback.control_mode === 1`. The fix also makes the in-session PID flow more
robust (readback populates faster across reloads).

---

### Session 2026-05-22 (earlier) — PID target-RPM settable from the dashboard

PID hold target RPM is now set from the UI. The operator panel has a dedicated
**PID hold** panel (target number field + slider, mirroring the sweep panel), and
`/api/command` "start" writes TARGET_RPM (%QW101) — clamped server-side to
3200-6100 RPM — before enabling, so a PID run holds the operator's chosen RPM
instead of a stale register value.

This closes the **last manual-Modbus operator gap**: the dashboard now fully
drives both PID hold and stepped sweep. (Manual valve mode is intentionally NOT
exposed in the UI.) **Issue #3's intent is now completely fulfilled** — the rig is
operable end-to-end from a remote browser with no manual `pymodbus` pokes.

%QW101's mode-scoped ownership is unchanged (operator in PID, sweep logic in
SWEEP) — this is the operator-write side only, no contract change. No PLC change,
no ST recompile/redeploy.

**Browser verification PASSED 2026-05-22** (remote browser, not curl): PID hold
held the chosen target (4500 -> avg 4513 RPM; 5500 -> avg 5431 RPM, both within
the +/-100 RPM sensor-noise band); clamping confirmed client-side (UI-typed 2000
sent as 3200) and server-side (1000 -> 3200, 9000 -> 6100); the stepped sweep
still staircases (3200 -> 6100, auto-closed). Engine left stopped, no open runs.
The build is now FEATURE-COMPLETE: the dashboard fully drives PID hold and sweep
from a remote browser with no manual Modbus pokes.

---

### Session 2026-05-22 (later) — sweep setpoint visibility + chart legibility

The build is now FEATURE-COMPLETE. Two scoped polish jobs, each verified
end-to-end from a remote browser:

1. **Sweep target mirrored to TARGET_RPM (%QW101).** MODE_SWEEP now writes its
   internal stepping target into %QW101 on entry and at each step, exposing it on
   :502 and logging it. The dashboard dashed setpoint line tracks the sweep
   staircase instead of sitting flat at zero, and the logged `rpm_setpoint` steps
   with the sweep (verified 3200→3600→…→6100). This is **mode-scoped ownership**,
   documented in `plc/register_map.md`: in PID mode the OPERATOR owns %QW101; in
   SWEEP mode the sweep logic owns it, overwriting any operator value — a
   documented hand-off, NOT a conflict. PID mode is unaffected (still reads %QW101
   as the operator setpoint; verified the line shows a flat operator target).
   Closes the rpm_setpoint=0-during-sweep observability gap.
2. **Chart legibility.** Legend moved ABOVE the plot (no longer collides with the
   "seconds ago" x-axis title); fixed axis frames (RPM 0–7000 left, ft-lbs/HP
   0–12 right) so torque and HP use a real share of the height instead of hugging
   the bottom; distinct setpoint colour (light dashed) vs amber RPM; all four
   traces at 2–2.5 px. Presentation only — data and polling unchanged.

---

### Session 2026-05-22 (Session C) — MODE_SWEEP implemented + clutch removed

**Issue #3 is now FULLY CLOSED.** The sweep half is done: MODE_SWEEP is
implemented in `plc/dyno_control.st` and verified end-to-end from a remote
browser.

- **MODE_SWEEP (CONTROL_MODE=2)** — a SUPERVISOR over the mode-1 PID. Steps an
  internal setpoint from SWEEP_START_RPM to SWEEP_END_RPM by SWEEP_STEP_RPM,
  dwelling SWEEP_DWELL_MS (counted off the PLC scan, NOT wall-clock) at each
  step, reusing the PID to hold each step. At the final step's dwell it sets
  SWEEP_STATE=2 and drops SAFETY_ENABLE itself — the first time the control
  logic ends a run on its own, not on a fault. The safety interlock stays fully
  live throughout (overspeed/overpressure/CHT trips all active during sweep).
- **Sweep registers** (`plc/register_map.md`): SWEEP_START_RPM %QW104/40005,
  SWEEP_END_RPM %QW105/40006, SWEEP_STEP_RPM %QW106/40007, SWEEP_DWELL_MS
  %QW107/40008 (operator inputs); SWEEP_STATE %QW108/40009 (PLC output, dashboard
  reads). They live in the PLC %QW space exposed by OpenPLC's built-in :502
  server; they are **NOT mirrored to the sim**, so the OpenPLC slave-device
  config and `simulator/modbus_map.py` are UNCHANGED. SWEEP_STATE is a %QW (PLC
  output), not an input register, because OpenPLC input registers come from the
  slave device and cannot be written by the program.
- **SWEEP_DWELL_MS capped 500–30000 ms** — the PLC reads it as a signed 16-bit
  INT (max 32767).
- **Dashboard**: `/api/command` gained a `start_sweep` action + a GET to poll
  SWEEP_STATE (still the SOLE Modbus path; server-side clamps to the contract
  ranges). `OperatorControls` has a Sweep panel (start/end/step inputs + a
  dwell-per-step slider) that auto-closes the run when SWEEP_STATE hits 2.
- **Verified from a remote browser** (not curl): sweep 3200→6100 / step 400 /
  dwell 2000 created run #11, stepped RPM 4030→6036 with a real torque curve
  logged (9.2→5.0 ft-lbs across the band), SWEEP_STATE 1→2, the PLC dropped
  SAFETY_ENABLE, and the dashboard auto-closed the run. Stop mid-sweep ends it
  cleanly and leaves the run OPEN (run lifecycle stays independent of engine
  enable).

**Clutch model REMOVED from the physics loop.** A bench dyno must measure the
engine across the FULL rev range; the clutch imposed a ~4,200 RPM lockup floor,
blinding the dyno in exactly the range a clutch change would affect. `tick()`
now couples the pump brake directly (no `clutch_torque_fraction()` multiplier).
The clutch fn + CLUTCH_* constants are RETAINED as validated drivetrain
reference data (see "Clutch engagement profile"). Removing it also resolved the
old below-engagement pressure/CHT inconsistency (torque, pressure, CHT now all
use the same full pump load).

- **New floor (re-probed)**: full throttle, valve 100% → RPM settles at **~3,135
  RPM**, set by brake capacity vs the engine torque curve (was clutch-limited
  ~4,004). SWEEP_FLOOR_RPM clamp lowered 4000→2500; SWEEP_START_RPM range
  2500–6100; dashboard default start 3200 (just above the floor).

**Sim-fidelity gap (still open):** the sim does NOT model the return-line
back-pressure valve's brake-torque contribution — `BACKPRESSURE_BASELINE_PSI`
only floors the reported pressure telemetry, not the braking force. So the sim
floor (~3,135) and the real-hardware floor will DIFFER: the real back-pressure
valve adds brake torque and should pull the real floor lower. SWEEP_START_RPM is
operator-settable precisely so the real floor can be found empirically on
hardware without recompiling the PLC.

**Deferred (filed):** GitHub issue #8 — "Load-profile run mode" (simulate kart
launch load instead of RPM-hold), on the project board Backlog. A separate,
substantial control mode; not part of sweep work.

**Sweep observability (CLOSED 2026-05-22):** previously the logged
`rpm_setpoint` (TARGET_RPM / %QW101) read 0 during a sweep because the sweep's
internal stepping target was never mirrored to that register. Now MODE_SWEEP
writes its current target into %QW101 each step (mode-scoped ownership, see
register_map.md), so `rpm_setpoint`, the dashboard setpoint line, and the sweep
panel readout all track the staircase. See the later 2026-05-22 session note at
the top of this section.

**Real hardware:** sweep parameters that work in the sim are FIRST GUESSES — real
engine inertia and valve lag change the dwell needed for a clean torque reading;
the dwell slider exists so this is tunable on the real rig without recompiling
the PLC. The dashboard E-stop remains a CONVENIENCE control, NOT a safety device
— the real rig needs a physically wired E-stop breaking the enable circuit.

---

### Session 2026-05-22 — Issue #3: dashboard operator command path (partially closed)

The dashboard now has its first WRITE path. Issue #3 (no software start/throttle
path; engine could only be enabled by a manual `pymodbus` poke to OpenPLC :502)
is **partially closed**:

- **Write route `dashboard/app/api/command/route.ts`** — POST `{action}` where
  action is `start` | `stop` | `estop`. Writes operator commands to **OpenPLC
  :502** (the PLC's `%QW` image), never to the sim on :5020. `start` writes
  CONTROL_MODE=PID then SAFETY_ENABLE=1 (TARGET_RPM left as-is — sweep params are
  Session C); `stop`/`estop` write SAFETY_ENABLE=0. The route is the ONLY place
  the dashboard opens Modbus (per-request connection, closed in `finally`), has
  NO sim-vs-real branching, and returns the post-write read-back of TARGET_RPM /
  CONTROL_MODE / SAFETY_ENABLE. Uses the `modbus-serial` npm package (added this
  session). E-stop deliberately does NOT write the valve: the PLC interlock
  already forces VALVE_POSITION_CMD=0 on SAFETY_ENABLE=0 (verified end-to-end —
  `%QW100` read back 0 after stop/e-stop).
- **Run lifecycle moved from logger to dashboard.** The dashboard is now the
  SOLE creator/closer of `test_runs` rows: POST `/api/runs` opens a run, PATCH
  `/api/run/[id]` stamps `ended_at`. The logger (`logger/logger.py`) no longer
  INSERTs a run or UPDATEs `ended_at` — it polls for the newest open run, attaches
  samples to it, logs "Waiting for an open run" while none exists, and returns to
  waiting when the run closes (no restart needed). This removes the split-brain
  `run_id` failure mode from the earlier ops sessions: exactly ONE writer of run
  rows. The logger `--notes` flag is now a no-op (kept for start_all.sh / CLI
  compat); run notes are owned by the dashboard.
- **UI controls** (`dashboard/components/OperatorControls.tsx`, "use client"):
  Start (opens a run + enables engine), End Run (closes the run; does NOT stop
  the engine), Stop (SAFETY_ENABLE=0), and a large red always-visible Emergency
  Stop (immediate, no confirm). Start is disabled while a run is open; End Run is
  disabled while none is. Each command shows the `/api/command` read-back. Ending
  a run and stopping the engine are independently triggerable.
- **register_map.md ownership table corrected** — TARGET_RPM / CONTROL_MODE /
  SAFETY_ENABLE are now documented as OPERATOR inputs (the PLC consumes them);
  only VALVE_POSITION_CMD is PLC-written (operator-written in manual mode). This
  matches `dyno_control.st`'s header, which was already authoritative.

**Verified end-to-end from a REMOTE browser** (http://10.20.99.55:3000 from the
operator PC, not curl-from-VM — the cross-origin reload-storm class of bug is
invisible to localhost). After `./stop_all.sh && ./start_all.sh` the logger came
up "Waiting for an open run"; Start created run #9, the logger attached and
telemetry populated (PID holding ~5000 RPM, status dot green); End Run stamped
`ended_at` and the logger returned to waiting; Stop and E-stop both read back
SAFETY_ENABLE=0 and the sim went to STATUS=0. Network tab showed a steady
`/api/live` + `/api/runs` poll with NO `GET /` reload storm — the
`allowedDevOrigins` fix from the prior session is holding. Engine left STOPPED.

**What remains (NOT closed by this session):**
- **Sweep mode** is still a stub in `dyno_control.st` and there is no UI/route
  for sweep parameters (start/stop band, ramp rate, TARGET_RPM entry). That is
  **Session C**. `start` currently always uses CONTROL_MODE=PID with whatever
  TARGET_RPM is already in the register.
- Minor UI nuance (pre-existing, not introduced here): `/api/live` returns the
  last sample of the newest run even when that run is closed, so when no run is
  open the telemetry cards show the last-known (frozen) values rather than going
  blank. The operator-controls panel correctly shows "No run open". Worth a
  follow-up if it confuses operators.

**REAL-HARDWARE WARNING:** the dashboard Emergency Stop is a **convenience
control, NOT a safety device.** It issues the same software SAFETY_ENABLE=0
write as Stop and depends on the dashboard, network, OpenPLC, and the field bus
all being healthy. The real rig MUST have a **physically wired E-stop that breaks
the enable/power circuit** independently of any software — the on-screen button
sits beside it, it does not replace it.

Last worked on: 2026-05-21 — end-to-end integration validated. Simulator, PLC
control logic, SQLite logger, and Next.js dashboard are all complete, committed,
and verified together. Next.js bumped 14.2 -> 16.2 / React 18 -> 19 to clear 4
security advisories; required async-API migrations (`serverExternalPackages`,
async dynamic-route `params`) applied. `start_all.sh` / `stop_all.sh` added so
the whole stack comes up with one command.

Integration test (`/tmp/integration_test.py`, throwaway) ran the brief's
sweep 3000 -> 4000 -> 5000 -> 6100 -> 4000 RPM via OpenPLC's slave port 502
(operator writes go to `%QW100`-`%QW103`, not directly to the sim's holding
registers, because the PLC mirrors its own variables down to the sim every scan
and would overwrite direct writes). Results:

| Setpoint | Avg RPM (last 5s) | Steady err | Limiter? | OVERSPEED? |
|---------:|------------------:|-----------:|:--------:|:----------:|
| 3000     | 4236.0            | +1236.0    | no       | no         |
| 4000     | 4238.4            | +238.4     | no       | no         |
| 5000     | 5019.6            | +19.6      | no       | no         |
| 6100     | 6038.6            | -61.4      | **yes**  | no         |
| 4000     | 4244.8            | +244.8     | no       | no         |

- OK: OVERSPEED_TRIP (6500) never fired; max observed RPM 6106.
- OK: Limiter fired only at the 6100 setpoint step (34 of 1337 samples that run).
- NOTE: **Physical floor at ~4236 RPM.** With the brake at 100% the dyno cannot
  pull the engine below ~4236 RPM at full throttle — engine torque exceeds max
  brake torque at lower RPMs. The 3000/4000 setpoints in the brief are below
  this floor and saturate. The 5000 RPM step tracks within 20 RPM, which is
  the realistic working band.

**Known bug surfaced during integration:** the logger's default `--db`
is `data/dyno.db` *relative to CWD*, and the dashboard reads
`<cwd>/../data/dyno.db`. If the logger is launched from `logger/` they end up
on different files. `start_all.sh` runs the logger from the repo root so both
land on `data/dyno.db`. If you ever start the logger by hand, cd to the repo
root first (or pass `--db /home/ubuntu/projects/lo206-dyno/data/dyno.db`).

Immediate next step: write up the project (blog/docs) and prep the demo
presentation. Future calibration: tune J_ENGINE / cut-duration so per-cut RPM
drop at the limiter approaches the ~800 RPM real-world target.
Blocking questions: None.

### Bring-up notes — 2026-05-21 live-debug session

**Symptom:** full stack running (sim :5020, OpenPLC, logger, dashboard :3000) but
the dashboard showed "No live run" / "Waiting for data" and all telemetry was zero.

**Root cause (failure mode A + C): the engine was never enabled, and it cannot be
enabled by poking the sim.** `SAFETY_ENABLE` (40004 / `iSafetyEnable AT %QW103`)
is an *operator* command, but `dyno_control.st` has no code path that ever sets it
to 1 — it only reads it, or forces it to 0 on a latched fault. The OpenPLC
slave-device master writes all four holding registers (`%QW100..103`) to the sim
every 50 ms scan, so a manual write of SAFETY_ENABLE=1 directly to the sim
(port 5020) is overwritten back to 0 within one scan (verified: wrote
[_,5000,1,1], read back [_,4000,1,0] after 1 s). The dashboard is read-only and
has no Modbus write path, so nothing commands a start. This is the Issue #3 gap.

**Two suspected modes ruled out by evidence:**
- *Not a slave-mapping bug.* OpenPLC `ir_size = 7` is CORRECT, not a typo for 8.
  The PLC binds only `%IW100..106` (7 telemetry words) and deliberately omits
  `LIMITER_ACTIVE@30008` (the control law must not branch on it); the logger reads
  the 8th register straight from the sim. **Do not "fix" ir_size to 8.**
- *Not a DB-path mismatch.* Logger and dashboard share the same file (inode
  verified); `/api/live` was already serving valid JSON.

**Fix / how to enable the engine today:** write the operator commands to
**OpenPLC's own Modbus server on port 502** (exposes the PLC's `%QW` image), NOT
to the sim on 5020: addr 101 = TARGET_RPM, addr 102 = CONTROL_MODE (1 = PID),
addr 103 = SAFETY_ENABLE (1 = run). The PLC reads `%QW103=1`, runs the PID, and
mirrors the holding registers down to the sim — where SAFETY_ENABLE now *stays* 1.
Verified end-to-end: sim left STOPPED, RPM settled at 5004 (target 5000),
SIM_STATUS=1, `/api/live` live, dashboard populated.

**Full-stack launch order (one command: `./start_all.sh`):**
1. OpenPLC runtime (systemd `openplc` + start PLC via web API / :8080)
2. Simulator `simulator/modbus_server.py` — prefers 502, falls back to **5020**
   when unprivileged (the usual case)
3. Logger `logger/logger.py` from the **repo root** so `--db data/dyno.db`
   resolves to the same file the dashboard reads
4. Dashboard `npm run dev` in `dashboard/` (:3000)
Then enable via the port-502 writes above.

**OpenPLC slave-device config (runtime config — NOT version controlled; re-enter
in the web UI after a fresh OpenPLC install):** Protocol TCP, IP 127.0.0.1, Port
**5020**, Slave ID **1**, Input Registers start 0 size **7** (`%IW100..106`),
Holding Registers-Write start 0 size **4** (`%QW100..103`), Holding-Read size 0.

**Sweep registers (MODE_SWEEP, added 2026-05-22):** the four sweep parameter
registers (%QW104-107 = 40005-40008) and the sweep status word (%QW108 = 40009)
are NOT part of this slave-device mirror -- the sim does not model the sweep, so
the Input-Register (size 7) and Holding-Write (size 4) blocks above are
UNCHANGED. OpenPLC built-in Modbus server on :502 exposes these located %QW
automatically (holding registers 104-108), which is how the dashboard writes the
params and reads SWEEP_STATE. NOTE this deviates from the session brief, which
expected the slave sizes to grow: they do not, because nothing about the sweep
crosses the PLC-to-sim boundary. See plc/register_map.md (Sweep Registers).

**Open architectural gap (Issue #3):** there is no software start/throttle command
path. The engine can be enabled today only by a manual write to OpenPLC port 502
(or a hardwired operator panel on the real rig). The dashboard is a read-only
observer. Building the dashboard's command-write path (TARGET_RPM / CONTROL_MODE /
SAFETY_ENABLE -> OpenPLC port 502) is Issue #3 and is the real fix that makes the
rig operable without a manual pymodbus poke.

**OpenPLC Monitoring page empty:** the located `%IW/%QW` vars were not published to
the web Monitoring table this session, so `%QW103` could not be forced from the UI
— which is why the port-502 write is the working enable path. Data flow itself was
fine; only the web Monitoring view was empty.

### Bring-up notes — 2026-05-21 ops/split-brain session

**Symptom (Round 2):** dashboard intermittently showed "No live run" / zeros
even though `./start_all.sh` had succeeded and the sim was clearly running on
:5020.

**Root cause: duplicate sim + duplicate logger — split-brain on `run_id`.** Two
`modbus_server.py` and two `logger/logger.py` processes were alive. The losing
sim couldn't bind 5020 but the winning logger and losing logger each opened a
fresh row in `test_runs` and wrote samples under different run IDs. The
dashboard's `/api/live` reads "the latest run" — whichever logger opened the
newer row owned the dashboard, regardless of which sim was actually being
driven by the PLC. NOT a code bug. **Slave `ir_size=7` is still correct by
design — do not "fix" it.**

**Operational fix:** `start_all.sh` and `stop_all.sh` are now idempotent
(commit 1ddc623):
- `start_all.sh` gates each service on `pgrep -f` of its cmdline pattern. If
  something already matches, it records that PID into the pidfile and skips
  the spawn instead of blindly launching a second instance.
- `stop_all.sh` kills ALL pids matching each pattern (not just the one in the
  pidfile), so orphans started outside `start_all.sh` (e.g. by
  `scripts/start_sim.sh` or a manual `python3 logger/logger.py`) are also
  cleaned up.

**Clean cold-start sequence (now safe to re-run any time):**
1. `./stop_all.sh`   — kills any sim/logger/dashboard duplicates by pattern,
   leaves OpenPLC runtime alone
2. `./start_all.sh`  — idempotent; brings up exactly one of each service.
   Verify with `ps -eo pid,cmd | grep -E 'modbus_server|logger|next' | grep -v grep`
3. Confirm sim is on **:5020** (`ss -tln | grep 5020`) and OpenPLC slave is
   pointed there
4. Enable via OpenPLC port **:502** — write `%QW101=TARGET_RPM`,
   `%QW102=1` (CONTROL_MODE = PID), `%QW103=1` (SAFETY_ENABLE). Do NOT
   write SAFETY_ENABLE directly to the sim on :5020; the PLC overwrites it
   within one scan (see prior session note).

**Engine left RUNNING at 5000 RPM** at end of session so the operator sees
live data on the dashboard. To stop cleanly: write `%QW103=0` via :502.

**Still open: Issue #3.** No software start/throttle path — enabling the
engine still requires a manual `pymodbus` write to OpenPLC :502. The
dashboard remains read-only. Closing #3 (adding a dashboard command-write
path) is the real fix for ergonomic operation.

### Bring-up notes — 2026-05-21 remote-browser HMR reload storm

**Symptom (Round 3):** the operator's browser at `http://10.20.99.55:3000`
showed "No live run" and empty cards even though all server-side checks
passed: one of each process, logger writing the same `data/dyno.db` the
dashboard reads (inode-verified), run #8 open, `SAFETY_ENABLE=1` at the
PLC, and `/api/live` returning valid live JSON when curled from the VM
itself.

**Root cause: Next 16 cross-origin dev guard.** Browsing the dev server
from any host other than `localhost` (the operator PC -> `10.20.99.55`)
counts as cross-origin in Next 16. With no `allowedDevOrigins` in
`next.config.js`, the HMR WebSocket (`/_next/webpack-hmr`) was blocked at
startup -- visible in the dev-server log as a one-time warning. The HMR
reconnect path then fell back to force-reloading `/` several times per
second; the access log showed hundreds of `GET /` against only ~3
`GET /api/live` calls. Each reload re-mounted `<Page>`, scheduled
`setInterval(tick, 500)` -- and then the next reload tore the component
down before the first 500 ms tick fired. The poll never got a chance to
run on the client even though `page.tsx` correctly declared `"use client"`
and the useEffect was structured properly.

**This bug is undetectable by curl-from-VM testing.** `curl http://localhost:3000/api/live`
from inside the VM is same-origin -- Next never trips the guard, the API
returns fine, and the server side looks healthy. The failure mode lives
entirely in the remote browser. **Future verification of dashboard
behavior MUST include opening the URL in a real browser on the operator
PC -- a healthy `/api/live` curl from the VM is not sufficient.**

**Fix (commit 0b625b7):** added `allowedDevOrigins: ["10.20.99.55"]` to
`dashboard/next.config.js` and restarted the dashboard only (sim, logger,
OpenPLC, and run #8 left untouched). Post-restart the dev-server access
log shows a steady stream of `GET /api/live` and zero new `GET /` rows
over a 15-second window -- the reload storm is gone. No recharts /
hydration / React-19 errors in the log, so the secondary recharts-vs-
React-19 suspect does not need a bump right now.

**Recharts caveat for future migrations:** `recharts ^2.13.3` is what the
Next 14 -> 16 / React 18 -> 19 migration left in `package.json`. It
worked here without a render-time throw, but recharts 2.13.x had
documented React-19 incompatibilities; if `<LiveChart>` ever starts
throwing during render after a dependency bump, suspect recharts first
and try bumping to 2.15+.
