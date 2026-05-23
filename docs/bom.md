# Bill of Materials & LO206 Reference Data

## LO206 slide configurations

The LO206 uses interchangeable carburetor slides/restrictors (referred to by
color and opening size) to set the power level for different racing classes. The
simulator's torque curve (`simulator/torque_curve.py`) currently models the
**Stock/Unrestricted 206 slide (#555590, black slide)** — the unrestricted club/senior setup — using
digitized B&S dyno sheet data. This curve makes strong low-end torque (~11.1 ft-lbs at 2500-3000 RPM) and HP rises across the band toward the top,
consistent with the project's ~10 ft-lbs / 8.8 HP hardware target.

### Stock/Unrestricted 206 slide (#555590, black slide) — digitized, in use by the sim

| RPM  | Torque (ft-lbs) |
|------|-----------------|
| 2500 | 11.13            |
| 3000 | 11.12            |
| 3500 | 9.83            |
| 4000 | 9.76            |
| 4500 | 9.09            |
| 5000 | 9.45            |
| 5500 | 9.45            |
| 6000 | 7.52            |

### Restricted .440 slide — alternate (restricted senior), not in use

Retained for reference; this was the originally-scaffolded curve. Swap it back
into `torque_curve.py` to model the .440 restriction.

| RPM  | Torque (ft-lbs) |
|------|-----------------|
| 2500 | 4.73            |
| 3000 | 5.31            |
| 3500 | 5.96            |
| 4000 | 5.82            |
| 4500 | 5.40            |
| 5000 | 4.97            |
| 5500 | 4.54            |
| 6000 | 4.14            |

### Other slide configurations

| Slide  | Class context (typical) | Torque / HP data        |
|--------|-------------------------|-------------------------|
| Purple | restricted / junior     | TODO: digitize from official B&S sheet |
| Red    | restricted / junior     | TODO: digitize from official B&S sheet |
| Green  | restricted / junior     | TODO: digitize from official B&S sheet |
| Blue   | restricted / junior     | TODO: digitize from official B&S sheet |
| Yellow | restricted / junior     | TODO: digitize from official B&S sheet |
| Stock  | baseline                | TODO: digitize from official B&S sheet |

> TODO: The torque/HP figures for the other restricted slides are not yet digitized.
> Pull them from the official Briggs & Stratton LO206 dyno sheets rather than
> estimating — class legality depends on accurate numbers. The class/usage
> notes above are approximate and also need confirmation.

## Hardware BOM (rough, CAD price ranges)

| Item                                              | Est. price (CAD) |
|---------------------------------------------------|------------------|
| Raspberry Pi 4 or 5 + SD card + PSU               | $120 - 180       |
| Load cell 50 lbf compression + HX711 amplifier — confirmed | $35 - 65         |
| Hall-effect RPM sensor (gear tooth) + bracket — confirmed | $15 - 35         |
| Pressure transducer 0-3000 PSI, 4-20mA — confirmed (range revised, see below) | $35 - 75         |
| K-type thermocouple + MAX31855 interface          | $25 - 40         |
| ADS1115 ADC                                       | $15              |
| Proportional pressure/throttle control valve + body — spec'd (see below) | $300 - 500 (TBD) |
| Valve driver — coil drive TBD (12 V PWM vs 0-10 V amp card) | $15 - 150 (TBD)  |
| Brake pump (2.14 cu in/rev gear pump, 3000 PSI) — spec'd (see below) | $TBD (verify)    |
| Gear set (22T/64T kart gears, 2.909:1) + coupling/adapter — TBD-spec | $TBD             |
| Hydraulic reservoir (heat-sized, see below) — TBD-spec | $TBD             |
| System relief valve (set ~2000 PSI) — confirmed   | $70              |
| Inlet / charge plumbing (flooded pump suction) — TBD-spec | $TBD             |
| Hilliard Flame clutch — on hand (kart)            | $0               |
| Torque arm mechanical assembly (axle stub, carriers, hub, arm) | $120 - 230       |
| Wiring, enclosure, connectors, hydraulic fittings | $50 - 100        |
| **Subtotal (without wideband O2) — ESTIMATE, several items unpriced** | **see "Budget" below** |
| Wideband O2 + controller (Phase 2)                | +$150 - 250      |

### Cost driver

The **proportional valve** is still the largest single electronic line item. The
valve **type** is now locked — a proportional **pressure/throttle control valve**
(non-compensated cartridge; Sun Hydraulics FPCH-class or Brand Hydraulics
EFC-class). The exact part number, rated flow, and price remain to be confirmed
with a distributor; see the **Proportional pressure/throttle control valve —
SPEC'D** section below. The coil drive (12 V PWM vs 0-10 V amp card) is
deliberately left TBD.

### Budget (recompute, 2026-05-22)

The brake-hardware re-spec replaced two previously-priced items (the 1.52 cu.in.
Princess Auto pump and the Sun RPGC-LBN relief valve) with parts that are not yet
priced from a source, and added several TBD-spec line items (gear set, reservoir,
inlet/charge plumbing). **The subtotal is therefore an ESTIMATE, not a firm
number.** Priced + on-hand items total roughly **$420–730 CAD** (Pi, load cell,
RPM sensor, transducer, thermocouple, ADC, system relief, torque arm, wiring,
clutch on-hand). The following are **unpriced** and must be quoted before the
total is meaningful against the **sub-$1000 CAD** target:

- Brake pump (2.14 cu in/rev, 3000 PSI gear pump — Dalton Hydraulic candidate)
- Proportional pressure/throttle control valve + body (Sun FPCH / Brand EFC class)
- Valve coil driver (12 V PWM circuit vs 0-10 V amp card — TBD)
- Gear set (22T/64T) + shaft coupling/adapter
- Hydraulic reservoir (heat-sized)
- Inlet / charge plumbing for flooded pump suction

A realistic guess for the unpriced block is **~$500–800 CAD**, which would put the
build **at or slightly over the $1000 CAD target** — confirm the pump and valve
quotes first, as they dominate the uncertainty.

## Hydraulic circuit hardware (brake pump + drive)

> **SUPERSEDES the earlier chain-drive / 1.52 cu.in. design.** The locked brake
> design is a fixed-displacement **2.14 cu in/rev gear pump (3000 PSI rated)**
> driven through a **22T/64T gear set (2.909:1 reduction)**, with a proportional
> **pressure/throttle control valve** building back-pressure (see its own section
> below). The previous Princess Auto 1.52 cu.in. pump, #219 chain 3.5:1 drive, and
> Sun RPGC-LBN relief valve are no longer the plan. Downstream references that
> still mention the #219 20T sprocket (e.g. the RPM-sensor trigger target) need
> reconciling against the gear set — flagged, not yet rewritten here.

These items size to the LO206's output (~8–11 ft-lbs torque, ~8.8 HP).

| Item                       | Description                                              | Source / candidate            | Price (CAD)     |
|----------------------------|----------------------------------------------------------|-------------------------------|-----------------|
| Brake pump                 | Fixed-displacement gear pump, ~2.14 cu in/rev, 3000 PSI  | Dalton Hydraulic (candidate)  | $TBD (verify)   |
| Gear set (22T / 64T)       | 22T engine gear / 64T pump gear, 2.909:1 reduction       | Kart gears / supply           | $TBD            |
| Shaft coupling / adapter   | Couples pump shaft to the 64T gear; tolerates misalignment | Machine shop / coupling supplier | $TBD          |
| System relief valve        | Adjustable relief, set ~2000 PSI, ≥ pump flow            | Princess Auto Item 8688947 (or equiv.) | $69.99 |
| Hydraulic reservoir        | Heat-sized tank + return; see heat note below            | Hydraulic supply / fabricated | $TBD            |
| Inlet / charge plumbing    | Flooded or low-pressure-charged pump suction (anti-cavitation) | Hydraulic supply        | $TBD            |

### Brake pump (2.14 cu in/rev gear pump) — notes

- **Type:** fixed-displacement gear pump (a gear pump's displacement is constant
  per rev; the *brake load* is set by the downstream proportional throttle valve,
  not by the pump). Displacement ~**2.14 cu in/rev**, pressure rating **3000 PSI**.
- **Drive:** 22T engine / 64T pump = **2.909:1 reduction**. Engine 2500 RPM →
  pump 859 RPM; engine 6100 RPM → pump 2097 RPM (within a 3000-RPM-class pump's
  range).
- **Worked point (torque → pressure is speed-independent):** absorbing the
  engine's ~11 ft-lb low-end torque needs ~**32 ft-lb (384 in-lb) at the pump
  shaft** (× 2.909 through the gear set), which the 2.14 cu in/rev pump develops
  at ~**1128 PSI** — only ~**38% of the 3000 PSI rating**. Pressure to hold a
  given torque does not change with RPM; only flow does.
- **Flow across the band (per Q = disp × pump_RPM / 231):** ~**8.0 GPM at 2500
  engine RPM**, rising to ~**19.4 GPM at 6100**.
  > ⚠ **FLOW INCONSISTENCY — resolve before sizing the valve & reservoir.** The
  > project brief quotes the operating flow as **0.80–1.94 GPM**, ~10× lower than
  > the 8–19 GPM that 2.14 cu in/rev actually produces at these pump speeds. The
  > 2.14 cu in/rev displacement is load-bearing (it is what makes the 1128 PSI ↔
  > 11 ft-lb worked point and the 3-tier pressure scheme self-consistent), so the
  > **flow figures appear to be the error**, not the displacement. This matters:
  > the valve flow-capacity selection (below) and the reservoir/cooling sizing
  > both depend on real flow. **Confirm the pump's actual displacement and the
  > resulting flow band with the distributor before buying the valve.**
- **VERIFY BEFORE PURCHASE:**
  - Exact displacement (cu in/rev) — confirm it is ~2.14, not a near value
  - 3000 PSI pressure rating (continuous, not burst)
  - Price (CAD)
  - Shaft size / type (diameter, keyed vs splined) — drives the coupling spec
  - Rotation (CW/CCW as viewed from shaft end) — must match the drive
  - SAE mount pattern (SAE-A 2-bolt is typical for this size) — drives the
    torque-arm reaction-mount bolt pattern
  - Canadian availability / lead time (Dalton Hydraulic or equivalent)

### Gear set (22T / 64T) + coupling — notes (TBD-spec)

- 64/22 = **2.909:1** reduction. The 22T is on the engine, the 64T on the pump.
- Confirm the gears are compatible kart gears and that a hub/coupling bridges the
  64T gear to the verified pump shaft size/type. The coupling should tolerate
  minor angular/parallel misalignment to keep side load off the pump bearing.
- This replaces the earlier #219 chain (3.5:1). Center distance, gear mesh
  backlash, and guarding are build-time details.

### System relief valve — notes

- High-pressure side, **set ~2000 PSI** — the mechanical relief of the new
  three-tier scheme (working ~1128 / **relief ~2000** / pump rating 3000).
- Protects pump and circuit from overpressure spikes above the working band.
- Must pass at least full pump flow at relief (see the flow note above — size to
  the *real* flow band, not the brief's 0.8–1.9 GPM figures).
- Software/PLC overpressure trips are **not changed this session** (sim
  `OVERPRESSURE_TRIP_PSI` = 900, PLC `PSI_TRIP_PSI` = 750); they must be reviewed
  next session against this ~2000 PSI relief scheme.

### Hydraulic reservoir — notes (TBD-spec)

- **Size for heat.** The dyno dumps the engine's full output as heat into the oil
  continuously during a sweep: ~**3.9 HP (≈2.9 kW) at the brake-capacity floor**
  up to ~**6.3 HP (≈4.7 kW) near redline** (HP = torque × RPM / 5252 on the
  Stock-206 curve). A small reservoir will heat-soak quickly; size the tank (and
  consider a cooler) so oil temperature stays in range across a full sweep.
- Confirm fluid type/viscosity, filtration, and breather.

### Inlet / charge plumbing — notes (TBD-spec)

- The pump suction must be **flooded or low-pressure charged** to avoid
  cavitation, *especially at the low-flow end* (~8 GPM at 2500 RPM, lower if the
  flow inconsistency above resolves toward the brief's figures). Cavitation
  damages gear pumps and corrupts the pressure (hence torque) reading.
- Generously sized suction line, reservoir mounted at/above the pump inlet, and a
  suction strainer rather than a restrictive filter on the inlet.

## Confirmed drivetrain hardware

| Item                          | Description                       | Source          | Price (CAD) |
|-------------------------------|-----------------------------------|-----------------|-------------|
| Hilliard Inferno Flame clutch | Centrifugal clutch, #219 drive    | On hand (kart)  | $0          |

### Hilliard Inferno Flame clutch — notes

- Stock spring config: 2 black + 2 white springs, 0 heavy weights per shoe
- Engagement RPM: ~3,400 RPM (confirmed — spring chart + race data)
- Estimated full lockup RPM: ~4,200 RPM under pump load
- Reused from kart — no new purchase required
- Dyno startup procedure must account for clutch engaging above ~3,400 RPM

## Torque measurement assembly — CONFIRMED

The load cell and mechanical torque arm assembly implement the reaction-torque
measurement architecture. The pump body is free to rotate on its shaft; reaction
torque is transmitted through a rigid 1-foot torque arm to a compression load
cell mounted on the dyno chassis. Torque (ft-lbs) = cell reading (lbf) × 1.000 ft.

### Load cell

| Spec            | Value                                                         |
|-----------------|---------------------------------------------------------------|
| Type            | Compression disc / button load cell                          |
| Capacity        | 50 lbf (23 kg)                                               |
| Moment arm      | 1.000 ft (measured shaft centerline to cell contact centerline) |
| Peak load       | ~10 lbf (10 ft-lbs ÷ 1 ft)                                   |
| Safety margin   | 5× at rated capacity (50 lbf ÷ 10 lbf)                       |
| Interface       | 4-wire Wheatstone bridge — HX711 amplifier (existing BOM)    |
| Contact face    | Button / dome face — point contact accommodates slight arc   |
| Signal path     | HX711 → Pi GPIO (SPI or bit-bang) → Modbus register 30002   |
| Est. cost (CAD) | $25–40 (cell) + $10–15 (HX711) = ~$35–55 total              |

#### Why compression button type (not S-type or bending beam)

The torque arm pushes the cell in one direction only — compression. There is
never a tension load on the cell. An S-type load cell handles both tension and
compression, which adds cost and complexity for no benefit here. A bending beam
cell typically requires a flat-on-flat contact, which introduces off-axis moments
when the torque arm traces its small arc. A button/dome face load cell naturally
accepts point contact and self-aligns — the force vector stays on the cell axis
regardless of the arc.

#### Resolution check

With the HX711 at 24-bit resolution and 50 lbf capacity:
- Theoretical LSB: 50 lbf ÷ 16,777,216 ≈ 3 µlbf
- Practical resolution (HX711 noise floor): ~0.01 lbf
- Torque resolution: 0.01 lbf × 1 ft = 0.01 ft-lbs
- As a fraction of peak torque: 0.01 ÷ 10 = 0.1% — more than adequate

#### Canadian sources

- Generic compression/button load cells widely available on Amazon.ca,
  AliExpress (allow 2–3 weeks), or eBay
- Search: "button load cell 50 lbf" or "compression disc load cell 25kg"
- HX711 modules: Amazon.ca, Digi-Key, Mouser

#### Open items before ordering

- Confirm pump body mounting flange bolt pattern (see hub/coupler section below)
  — torque arm attachment points depend on this
- Confirm HX711 wiring to Pi GPIO before finalizing load cell connector type
- TODO: calibrate load cell with known weights on first hardware run;
  verify 1.000 ft moment arm dimension against actual assembly

---

### Torque arm mechanical assembly

| Item                        | Description                                              | Source                    | Est. price (CAD) |
|-----------------------------|----------------------------------------------------------|---------------------------|------------------|
| 40mm axle stub              | Cut from spare 40mm kart axle, ~250mm length             | On hand (kart spares)     | $0–20            |
| 40mm bearing carriers (×2)  | Standard kart 40mm bearing carriers                      | Kart supply               | $15–30 each      |
| 40mm bearings (×2)          | 6205-2RS or equivalent (40mm ID kart axle bearing)       | Kart supply / Bearing shop| $10–20 each      |
| Custom hub / coupler        | Adapts 40mm axle to 3/4 in. pump shaft — see notes       | Machine shop or DIY lathe | $30–80           |
| Flex coupling element       | Jaw-type spider insert — tolerates minor misalignment    | Kart supply / McMaster    | $15–30           |
| Torque arm (fabricated)     | 1 ft rigid steel flat bar or square tube — see notes     | Steel supplier / on hand  | $10–20 material  |
| Hardened contact button     | M10 bolt end ground to dome, or purchased button         | Hardware / machine shop   | $5–10            |
| Hard stop bracket           | Slotted steel bracket + bolt — limits rotation to ±5°    | Fabricated                | $5–10 material   |
| Load cell mount bracket     | Steel bracket — mounts cell to chassis at correct height | Fabricated                | $5–10 material   |
| **Assembly subtotal**       |                                                          |                           | **~$120–230**    |

#### 40mm axle stub — notes

- Cut from a spare or damaged 40mm kart axle
- Required length: ~250mm — enough for two bearing carriers with ~100mm
  spacing plus hub overhang
- 40mm is the kart industry standard; spares are common
- Confirm the stub is straight before use — a bent axle introduces
  runout at the pump shaft and measurement error

#### Bearing carriers and bearings — notes

- Standard 40mm kart bearing carriers bolt to a flat plate or tube on the
  chassis — design the chassis mounting surface to accept standard carrier
  bolt patterns (typically 70mm × 70mm or similar; confirm against carriers
  on hand)
- Use sealed bearings (2RS suffix) — the dyno environment has oil mist and
  chain lube; open bearings will contaminate quickly
- Wider carrier spacing = lower bearing loads from chain side load.
  Target: carriers at least 80mm apart, more is better

#### Custom hub / coupler — notes

- Bridges the 40mm axle bore to the 3/4 in. pump shaft
- Two surfaces that are not concentric by default — misalignment here
  becomes vibration and a side load on the pump shaft bearing
- Recommended approach: machine a rigid hub with a jaw-type flex coupling
  insert (Lovejoy-style spider). The flex element tolerates 0.5–1° angular
  misalignment and slight parallel offset — achievable on a prototype build
  without a precision alignment fixture
- If a lathe is available: simple turned part, 40mm bore one end (keyed,
  set screw), jaw coupling hub face on the other end
- If no lathe: have it machined — this is a simple turned part, <1 hr on
  a manual lathe, ~$50–80 at a local machine shop
- Confirm the spec'd 2.14 cu in/rev brake pump's shaft diameter/type
  (see VERIFY list) before finalizing hub dimensions

#### Flex coupling element — notes

- A rigid coupling between the axle and pump shaft will transmit any
  misalignment directly as a bending load on the pump shaft bearing —
  a jaw-type flex spider absorbs this
- Size to suit the hub OD and torque requirement — the Lovejoy L050 or
  L075 series covers this torque range easily
- Available at most industrial suppliers (McMaster-Carr, Motion Industries,
  Grainger Canada)

#### Torque arm — notes

- Rigid steel flat bar or square tube, minimum 25mm × 6mm flat bar for
  stiffness — arm deflection under load changes the effective moment arm length
- CRITICAL DIMENSION: moment arm = distance from pump shaft centerline to
  load cell contact button centerline, measured along the arm axis.
  This must be exactly 1.000 ft (304.8mm). Drill or mark this dimension
  before welding/bolting the contact button. Verify after assembly with
  a steel rule against the shaft centerline.
- Arm attaches to pump body mounting flange bolts — confirm the spec'd brake
  pump's flange/SAE mount pattern (see VERIFY list) before fabricating arm. Most
  gear pumps of this size use a 2-bolt SAE A-mount (70mm bolt spacing) or 4-bolt
  metric pattern.
- Arm must be rigid in torsion (twisting around its long axis would change
  the contact geometry). Use square tube or add a gusset if using flat bar.

#### Hardened contact button — notes

- The contact point on the torque arm must be hardened to resist wear from
  repeated loading cycles
- Simplest option: a grade 10.9 M10 bolt, end ground to a dome radius of
  ~10mm, threaded into the arm tip. Lock with a jam nut.
- Alternative: purchase a hardened steel ball stud or contact button
  (available from load cell suppliers as accessories)
- The dome bears on the flat top button of the load cell — do not use a
  flat-on-flat contact

#### Hard stop — notes

- A slotted bracket welded or bolted to the chassis, with a bolt through
  the slot bearing against the torque arm
- Set clearance so the arm can travel 3–5mm toward the cell (normal
  operating range) before the hard stop engages on the other side
- Hard stop must be set BEFORE the cell is in place, then the cell is
  shimmed to its 3–5mm gap position
- Hard stop takes crash loads (hose burst, overspeed surge) — size the
  bolt and bracket for 10× normal load (500 lbf) to be conservative

#### Load cell mounting — notes

- Mount the cell to the chassis with a small steel bracket that allows
  fine adjustment of the cell position (slotted holes or shim stack)
- The 3–5mm gap at zero load must be set after the full assembly is in
  place — you need to adjust the cell forward until the gap is correct
  with the pump body floating freely
- Cell must be mounted so its axis is aligned with the force vector from
  the torque arm (perpendicular to the arm, through the shaft centerline).
  Off-axis mounting introduces a cosine error in the torque reading.

## RPM sensor — CONFIRMED

Hall-effect gear tooth sensor reading directly off the existing 20T drive
sprocket on the engine/clutch output shaft. No additional trigger wheel is
required — the sprocket teeth are the trigger target.

| Spec             | Value                                                              |
|------------------|--------------------------------------------------------------------|
| Type             | Hall-effect gear tooth sensor, digital output                     |
| Trigger target   | 20T #219 drive sprocket (existing hardware, no modification)      |
| Pulses per rev   | 20 (one per sprocket tooth)                                       |
| Max frequency    | 6,100 RPM × 20 ÷ 60 = 2,033 Hz at redline                        |
| Min frequency    | 2,400 RPM × 20 ÷ 60 = 800 Hz at warm idle                        |
| Output           | Digital square wave, active-low or push-pull                      |
| Supply voltage   | 5 VDC (resistor divider to 3.3 V for Pi GPIO — see wiring notes)  |
| Pi interface     | GPIO interrupt → period measurement → RPM → Modbus register 30001 |
| Modbus register  | 30001 ENGINE_RPM (existing, no register map change)               |
| Air gap          | 0.5–2.0 mm to sprocket tooth face (confirm with sensor datasheet) |
| Est. cost (CAD)  | $10–20 (sensor) + $5–15 (bracket + hardware) = ~$15–35 total      |

#### Why period measurement, not pulse counting

Two approaches exist for computing RPM from a pulse train:
- **Pulse counting:** count pulses in a fixed window (e.g., 100ms), multiply
  to get RPM. Simple, but response lags by the window width — at 2,400 RPM
  you wait 100ms to confirm the engine is at idle.
- **Period measurement:** measure the time between successive pulses.
  At 2,033 Hz (redline), each period is 0.49ms. At 800 Hz (idle), 1.25ms.
  RPM is computed immediately from each pulse. This is the correct approach
  for a real-time control loop — faster response and better low-speed
  resolution, which matters near the clutch engagement zone (3,400 RPM).

The Pi uses **pigpio** for GPIO interrupt timing (microsecond resolution).
Python's `RPi.GPIO` library has too much jitter for reliable period measurement
at these frequencies; pigpio's C daemon handles timing at the kernel level.

#### Wiring notes

Most Hall-effect sensors in this form factor (e.g., Honeywell SS441A, generic
gear tooth sensors) are 5 V devices with open-collector or push-pull output.
The Pi's GPIO pins are 3.3 V — applying 5 V will damage the Pi.

Use a simple resistor voltage divider on the sensor output:
- 10 kΩ from sensor output to Pi GPIO
- 20 kΩ from Pi GPIO to GND
- Divides 5 V output → 3.33 V (within Pi's 3.3 V tolerance)
- Pull-up to 3.3 V (Pi internal) for open-collector sensors

Total resistor cost: negligible (~$0.10 from parts bin).

Alternatively: source a sensor rated for 3.3 V operation directly — several
AliExpress gear tooth sensors run from 3.3–24 V and output 3.3 V logic.
Confirm supply and output voltage before ordering.

#### Mounting notes

- The sensor body needs a rigid bracket with 0.5–2 mm clearance to the
  sprocket tooth face — confirmed at assembly, not assumed at design
- Bracket mounts to the dyno chassis or chain guard structure near the
  drive sprocket
- Keep the sensor wire away from the ignition coil and plug wire — the
  kart ignition produces significant RF; route sensor wiring along the
  chassis (not alongside ignition wiring) and use a twisted pair or
  shielded cable if noise is observed in testing
- The RPM_NOISE_BAND of ±100 RPM in the simulator (engine_sim.py) is
  calibrated from real LO206 race data with a Hall-effect pickup and
  single trigger tooth. Using 20 teeth will give 20× better raw resolution;
  the ±100 RPM figure is a conservative bound and the actual noise may be
  lower. Validate on first hardware run.

#### RPM calculation (real hardware implementation note)

  # On real hardware (logger or dedicated RPM process):
  # pulse_period_s = time between last two GPIO interrupts (pigpio tick delta)
  # pulses_per_rev = 20  (20T sprocket)
  # rpm = (1.0 / pulse_period_s) * 60.0 / pulses_per_rev
  #
  # Write rpm (as uint16) to Modbus input register 30001.
  # Add ±RPM_NOISE_BAND if testing the PID response with the real sensor
  # during hardware bring-up — the sim already applies this; the real
  # hardware will have its own natural noise.

#### Canadian sources

- Generic Hall-effect gear tooth sensors: Amazon.ca, AliExpress
  (search: "Hall effect gear tooth sensor NPN 5V", confirm air gap spec)
- Honeywell SS441A or SS443A: Digi-Key Canada, Mouser Canada
- ATS667LSG (Allegro, designed for ferrous gear teeth): Digi-Key Canada

#### Open items before ordering

- Confirm sensor supply voltage and output voltage before ordering —
  some are 5 V only, some are 3.3–24 V; avoid post-order level-shifting work
- Confirm minimum air gap specification against the sprocket tooth height on
  the 20T #219 sprocket (tooth height is typically ~3–4mm on #219)
- Confirm pigpio is installed on the Pi before hardware bring-up:
  `sudo apt install pigpio python3-pigpio && sudo systemctl enable pigpiod`
- TODO: on first hardware run, measure actual RPM noise band and compare to
  the ±100 RPM simulator model; update RPM_NOISE_BAND in engine_sim.py if
  the real figure differs significantly

## Pressure transducer — CONFIRMED

| Spec             | Value                                                           |
|------------------|-----------------------------------------------------------------|
| Type             | Piezoresistive, 2-wire loop-powered                            |
| Range            | 0–3,000 PSI (revised for the 3-tier pressure scheme — see below) |
| Output           | 4–20 mA current loop                                           |
| Supply voltage   | 12–24 VDC (loop supply)                                        |
| Connection       | 1/4 in. NPT male (confirm against pump outlet port thread)     |
| Signal path      | 4–20 mA → 250 Ω burden resistor → 1–5 V → ADS1115 → I2C → Pi |
| Modbus register  | 30003 HYDRAULIC_PSI (range doc'd 0–3000 in register_map.md)    |
| Normal reading   | ~1128 PSI working (≈38% of pump rating), full braking near band low end |
| Mechanical relief| ~2,000 PSI (system relief valve)                               |
| Software trip    | 900 PSI sim / 750 PSI PLC — NOT changed this session; under review next session vs the ~2000 PSI relief |
| Resolution       | 3,000 PSI ÷ ~24,000 usable ADS1115 counts ≈ 0.13 PSI/count    |
| Est. cost (CAD)  | $30–60 (transducer) + $5 (burden resistor) = ~$35–65 total     |

#### Why 4–20 mA over 0–5 V

Two interface options exist for pressure transducers in this price range:

- **0–5 V:** Simple. Pi reads it via ADS1115 directly. No burden resistor.
  Susceptible to common-mode voltage noise on the cable. On a trailer
  next to a running kart ignition system, this is a real liability — the
  ignition coil and plug wire radiate significant RF that couples into
  unshielded signal wiring.

- **4–20 mA current loop:** Slightly more complex (needs a burden resistor
  and a loop supply). Immune to voltage noise — interference on the cable
  changes the wire voltage but the loop current is unaffected, so the
  reading is clean. The 4 mA live-zero also provides wire-break detection:
  a reading below 4 mA means the cable is open or the sensor has failed,
  not that pressure is zero.

For a trailer-based dyno with a running kart engine, 4–20 mA is the correct
professional choice. The added complexity is one 250 Ω resistor.

#### Why 0–3,000 PSI

The three-tier pressure scheme is **working ~1128 PSI / mechanical relief ~2000
PSI / pump rating 3000 PSI**. The transducer must read past the ~2000 PSI relief
to see spikes before relief opens, and ideally up to the 3000 PSI pump rating.
A 0–3,000 PSI transducer covers the full system range and puts the ~1128 PSI
working point near mid-scale (good linearity region). Resolution is ~0.13
PSI/count with a 16-bit ADS1115 — coarser than the old 0–1500 part but still far
finer than the ~1 PSI the control loop needs.

#### Signal conditioning — wiring

  Loop supply (12-24 VDC)
       (+) ──── Transducer V+ (red)
                Transducer V- / signal out (black) ──┐
                                                      │
                                                 250 Ω resistor
                                                      │
                ADS1115 AIN0 ────────────────────────┘
                ADS1115 GND ──── Loop supply (-)

  At 4 mA:  V = 0.004 × 250 = 1.000 V → 0 PSI
  At 20 mA: V = 0.020 × 250 = 5.000 V → 3,000 PSI

  ADS1115 PGA setting: ±6.144 V (covers full 1–5 V range).
  PSI = (V_measured - 1.0) / 4.0 × 3000.0

  Wire-break detection: reading < 0.8 V (< ~3.2 mA) = sensor fault.
  This complements the SIM_STATUS fault register — on real hardware,
  implement a sensor-fault check in the I/O layer and set SIM_STATUS = 2
  if the transducer reading drops below the live-zero threshold.

#### ADS1115 note

The ADS1115 (already in BOM, $15) has 4 channels and runs on I2C alongside
the MCP4725 DAC (valve driver Option A). Confirm I2C addresses don't conflict:
- ADS1115 default address: 0x48 (ADDR pin to GND)
- MCP4725 default address: 0x60
No conflict — both can share the Pi's I2C bus (GPIO 2/3, pins 3/5).

#### Mounting notes

- Mount the transducer on the high-pressure side of the pump (pump outlet,
  before the proportional valve)
- Use a hydraulic tee fitting to tap into the pressure line — do not install
  inline (would restrict flow)
- Use hydraulic-rated thread sealant (not PTFE tape) on NPT threads in a
  hydraulic system
- Keep signal cable away from ignition wiring — the 4–20 mA loop is noise-
  immune but the cable can still act as an antenna; route along chassis ground

#### Canadian sources

- Generic 4–20 mA pressure transducers (0–3,000 PSI, 1/4 NPT):
  Amazon.ca, AliExpress (search: "4-20mA pressure transducer 3000 PSI 1/4 NPT")
  Typical cost: $30–50 CAD
- Omega PX309 series (higher quality, longer warranty):
  ca.omega.com — PX309-3KI5V or similar; ~$80–120 CAD
- 250 Ω precision resistor (0.1% tolerance recommended): Digi-Key Canada,
  Mouser Canada — ~$1–3 CAD

#### Open items before ordering

- Confirm pump outlet port thread is 1/4 in. NPT (verify against the spec'd
  2.14 cu in/rev brake pump's port spec before ordering transducer)
- Confirm loop supply voltage available on the dyno (12 V or 24 V) — affects
  transducer selection (most 4–20 mA units accept 12–30 VDC, confirm range)
- Confirm ADS1115 I2C address against other I2C devices on the bus before
  wiring (default 0x48 — no conflict with MCP4725 at 0x60)
- TODO: on first hardware run, verify 4 mA live-zero reading with no pressure
  applied; calibrate PSI conversion against a known reference pressure

## Proportional pressure/throttle control valve — SPEC'D

The brake valve is a proportional **pressure/throttle control valve**
(non-compensated cartridge). It builds back-pressure by **restricting the pump
outlet flow** — higher command = more restriction = higher pump-outlet pressure =
more engine braking torque = lower RPM, which is exactly what the PID loop closes
on.

> **TERMINOLOGY — do not call this a "proportional flow-control valve."** A
> proportional *flow-control* (pressure-**compensated**) valve holds a commanded
> flow constant regardless of pressure — it would actively fight the brake and is
> the **wrong** device here. What we want is a **non-compensated** proportional
> pressure/throttle valve, which simply throttles the outlet so pressure rises
> with flow and with closure. The two are easy to confuse by name; this is the
> single most important spec to get right when ordering.

| Spec              | Value                                                          |
|-------------------|----------------------------------------------------------------|
| Type              | Proportional pressure/throttle control, **non-compensated**, cartridge |
| Candidate classes | Sun Hydraulics **FPCH**-class or Brand Hydraulics **EFC**-class |
| Rated flow        | ~3–6 GPM rated (puts the operating band in the accurate lower-mid range, clear of the ~0.25 GPM low-accuracy floor) — **see flow caveat below** |
| Pressure rating   | ≥ 3000 PSI (covers the full 3-tier scheme to pump rating)      |
| Coil drive        | **TBD** — 12 V PWM vs 0–10 V amp card (NOT chosen this session) |
| Operating pressure| ~1128 PSI working (38% of pump rating); develops up to ~2000 PSI before mechanical relief |

> ⚠ **FLOW CAVEAT (read with the pump's flow note).** The ~3–6 GPM rated-flow
> target was chosen against the brief's **0.8–2.0 GPM** operating band. But
> 2.14 cu in/rev at the spec'd pump speeds produces **~8–19 GPM** (Q = disp ×
> pump_RPM / 231). If the real flow is 8–19 GPM, a 3–6 GPM valve is **undersized**
> and would be the dominant restriction even wide open. **Resolve the
> pump-displacement-vs-flow inconsistency (see Brake pump notes) before selecting
> the valve's rated flow.** The valve *type* (non-compensated pressure/throttle)
> is locked regardless; only its flow size depends on this.

### Why this valve type — notes

- A non-compensated proportional throttle modulates pump resistance by
  restricting outlet flow: pressure rises with both flow (RPM) and closure
  (command). That is the brake authority the PID modulates.
- A pressure-**compensated** flow-control valve would instead hold flow constant
  and resist the brake — wrong device. (This is the terminology trap above.)
- Fail-safe direction (which command = open vs closed at zero coil current) and
  the coil drive are TBD and depend on the chosen part + driver — see VERIFY list.

### VERIFY BEFORE PURCHASE

- Exact part number (Sun FPCH-/Brand EFC-class or equivalent non-compensated
  proportional pressure/throttle valve)
- Rated flow capacity (GPM) — **after** the pump flow band is resolved
- Pressure rating (confirm ≥ 3000 PSI)
- Coil voltage / drive option (12 V PWM vs 0–10 V amp card) — decide the driver
- Price (CAD)
- Canadian availability / lead time

### Modbus interface — no register-numbering change

- The Pi/PLC writes VALVE_POSITION_CMD (holding register 40001, 0–10000 =
  0.00–100.00%). The register *number* does not change; its *physical meaning* is
  now a restriction/back-pressure command into this valve (see
  `plc/register_map.md`).
- The driver scales the command to the valve's coil drive (PWM current or 0–10 V →
  amp card → coil current). Restriction ∝ command → pump-outlet pressure ∝
  (command, flow).

### Driver — coil drive TBD

The coil drive is **not chosen this session.** Two families:
- **12 V PWM** directly from a current driver (e.g. DRV8871) — cheap, needs a
  current-control loop or a valve that tolerates PWM.
- **0–10 V command into a proportional amp card** — the card does the
  current control; simplest if the build is reproduced/documented.

Both are viable; pick after the valve part number (and its coil) is chosen.

### Canadian sources

- Sun Hydraulics distributors: Hydraquip, Applied Hydraulics (Ontario; also BC/AB)
- Brand Hydraulics distributors / industrial hydraulic suppliers
- Confirm the exact suffix codes (coil voltage, seal, flow variant) with the
  distributor — these vary by manufacturer.

### Open items before ordering

- Resolve the pump-flow / valve-flow-capacity inconsistency (above)
- Choose the coil drive (12 V PWM vs 0–10 V amp card)
- Confirm fail-safe direction at zero command is acceptable for e-stop behavior
- TODO: validate actual operating pressure on the first hardware run vs the sim
  model (target: ~1128 PSI working)

## System pressure specs (three-tier)

- **Working pressure:** ~**1128 PSI** — develops the pump-shaft torque (×2.909
  gear ratio) to absorb the engine's ~11 ft-lb low-end torque; ~38% of pump rating.
- **System relief (mechanical):** ~**2000 PSI** — relief valve protects the
  circuit above the working band.
- **Pump rating:** **3000 PSI** — the 2.14 cu in/rev gear pump's rated pressure.
- **Software/PLC overpressure trips:** sim `OVERPRESSURE_TRIP_PSI` = 900,
  PLC `PSI_TRIP_PSI` = 750 — **NOT changed this session.** Both sit *below* the
  ~1128 PSI working point and must be reviewed next session against this scheme
  (alongside the PID retune); until then the sim faults at full braking.
- **Basis:** 2.909:1 gear reduction, 2.14 cu in/rev pump, torque→pressure
  speed-independent (P = engine_torque × 2.909 × 12 / (disp / 2π)).
