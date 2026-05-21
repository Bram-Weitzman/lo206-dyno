# Bill of Materials & LO206 Reference Data

## LO206 slide configurations

The LO206 uses interchangeable carburetor slides/restrictors (referred to by
color and opening size) to set the power level for different racing classes. The
simulator's torque curve (`simulator/torque_curve.py`) currently models the
**Black Slide (.520 opening)** — the unrestricted club/senior setup — using
digitized B&S dyno sheet data. This curve peaks near 9.8 ft-lbs around 3500 RPM,
consistent with the project's ~10 ft-lbs / 8.8 HP hardware target.

### Black Slide (.520 opening) — digitized, in use by the sim

| RPM  | Torque (ft-lbs) |
|------|-----------------|
| 2500 | 9.06            |
| 3000 | 9.39            |
| 3500 | 9.83            |
| 4000 | 9.18            |
| 4500 | 7.38            |
| 5000 | 6.62            |
| 5500 | 5.37            |
| 6000 | 4.96            |

### Black Slide (.440 opening) — alternate (restricted senior), not in use

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

> TODO: The torque/HP figures for the non-Black slides are not yet digitized.
> Pull them from the official Briggs & Stratton LO206 dyno sheets rather than
> estimating — class legality depends on accurate numbers. The class/usage
> notes above are approximate and also need confirmation.

## Hardware BOM (rough, CAD price ranges)

| Item                                              | Est. price (CAD) |
|---------------------------------------------------|------------------|
| Raspberry Pi 4 or 5 + SD card + PSU               | $120 - 180       |
| Load cell 50 lbf compression + HX711 amplifier — confirmed | $35 - 65         |
| Hall-effect RPM sensor (gear tooth) + mounting bracket — confirmed | $15 - 35         |
| Pressure transducer 0-1500 PSI, 4-20mA — confirmed | $35 - 75         |
| K-type thermocouple + MAX31855 interface          | $25 - 40         |
| ADS1115 ADC                                       | $15              |
| Proportional valve + inline body — confirmed (see below) | $360 - 500       |
| Valve driver — Option A custom / Option B Sun card — confirmed | $15 - 150        |
| Hydraulic pump (1.52 cu.in. gear pump) — confirmed| $170             |
| Back-pressure valve (return line) — confirmed     | $70              |
| System relief valve — confirmed                   | $70              |
| Chain drive (#219, 20T/70T, 3.5:1) — confirmed    | $25 - 90         |
| Hilliard Flame clutch — on hand (kart)            | $0               |
| Torque arm mechanical assembly (axle stub, carriers, hub, arm) | $120 - 230       |
| Wiring, enclosure, connectors, hydraulic fittings | $50 - 100        |
| **Subtotal (without wideband O2)**                | **~$1,125 - 1,780**|
| Wideband O2 + controller (Phase 2)                | +$150 - 250      |

### Cost driver

The **proportional valve** is the largest single line item and dominates the
build cost. **RESOLVED:** the valve is now confirmed — Sun Hydraulics RPGC-LBN
(C10-2 cartridge). Full spec, driver options, Canadian sources, and confirmed
pricing are in the **Proportional valve — CONFIRMED** section below
(~$375–525 CAD with the Option A driver). This supersedes the earlier rough
$150–400 estimate and the "source surplus/used first" guidance — buying new
from a Sun distributor is now the plan. The valve-driver sub-decision (custom
MCP4725 DAC vs Sun PRZE-LBN amp card) is detailed in that section.

## Confirmed hydraulic circuit hardware

These items are locked from engineering analysis of the LO206's power output
(8–10 ft-lbs torque, ~8.8 HP) against affordable gear-pump options.

| Item              | Description                                     | Source                       | Price (CAD) |
|-------------------|-------------------------------------------------|------------------------------|-------------|
| Hydraulic pump    | 1.52 cu.in. aluminum-body gear pump             | Princess Auto Item 8375446   | $169.99     |
| Back-pressure valve (return line) | Adjustable relief valve, 50-3,000 PSI, 10 GPM | Princess Auto Item 8688939 | $69.99 |
| System relief valve | Adjustable relief valve, 50-3,000 PSI, 30 GPM | Princess Auto Item 8688947   | $69.99      |
| #219 drive sprocket (20T) | 20-tooth #219 sprocket | On hand (kart spares) | $0 |
| #219 driven sprocket (70T) | 70-tooth #219 sprocket | Kart supply / online | ~$25–40 CAD |
| Custom hub (if required) | Driven sprocket to pump shaft adapter | Machine shop / DIY | ~$20–50 CAD |
| #219 chain | Standard #219 kart chain | On hand (kart spares) | $0 |

### Hydraulic pump (Item 8375446) — notes

- Rated 400-3,000 RPM, 2,850 PSI max, 19.8 GPM
- Driven via #219 chain, 3.5:1 reduction (engine 6,200 RPM → pump 1,771 RPM —
  well within 3,000 RPM rating)
- Sized to absorb full LO206 output (10 ft-lbs peak torque) at ~595 PSI
  operating pressure (3.5:1 reduction multiplies torque at pump shaft to
  ~35 ft-lbs)

### Back-pressure valve (Item 8688939) — notes

- Installed in the return line, set to ~200 PSI
- Creates a minimum pump load at all RPMs — eliminates the low-RPM floor
  observed in pure-proportional simulation
- Allows the proportional valve to modulate brake authority **above** this
  baseline, rather than from zero

### System relief valve (Item 8688947) — notes

- High-pressure side, set to 1,500 PSI
- Protects pump and circuit from overpressure spikes
- Software `OVERPRESSURE_TRIP_PSI` fires at 900 PSI (applied in commit 0dd0a7a,
  `simulator/modbus_map.py`) before this valve opens, so a fault latches in
  software before mechanical relief is exercised

### #219 drive sprocket (20T) — notes

- Same sprocket used on kart — no new purchase required
- Confirm bore fits Hilliard clutch drum or engine PTO shaft

### #219 driven sprocket (70T) — notes

- 3.5:1 reduction (70/20) — matches kart gear ratio exactly
- Check bore: if available in 3/4 in., custom hub may not be required
- Otherwise: machine custom hub to suit 3/4 in. pump shaft (Item 8375446)

### Custom hub (if required) — notes

- Required only if 70T sprocket bore does not match 3/4 in. pump shaft
- Simple turned part: 3/4 in. bore, keyed, set screw
- Good candidate for DIY on a lathe

### #219 chain — notes

- Same chain used on kart — no new purchase required
- Cut to length at time of build based on pump-to-engine center distance

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
- Confirm pump shaft diameter is 3/4 in. (19.05mm) on Item 8375446
  before finalizing hub dimensions

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
- Arm attaches to pump body mounting flange bolts — confirm flange bolt
  pattern on Item 8375446 before fabricating arm. Most gear pumps of this
  size use a 2-bolt SAE A-mount (70mm bolt spacing) or 4-bolt metric pattern.
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
| Range            | 0–1,500 PSI                                                    |
| Output           | 4–20 mA current loop                                           |
| Supply voltage   | 12–24 VDC (loop supply)                                        |
| Connection       | 1/4 in. NPT male (confirm against pump outlet port thread)     |
| Signal path      | 4–20 mA → 250 Ω burden resistor → 1–5 V → ADS1115 → I2C → Pi |
| Modbus register  | 30003 HYDRAULIC_PSI (existing, no register map change)         |
| Normal reading   | 500–700 PSI (clutch locked, full throttle)                     |
| Software trip    | 900 PSI (OVERPRESSURE_TRIP_PSI, simulator/modbus_map.py)       |
| Mechanical relief| 1,500 PSI (system relief valve, Item 8688947)                  |
| Resolution       | 1,500 PSI ÷ ~24,000 usable ADS1115 counts ≈ 0.06 PSI/count    |
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

#### Why 0–1,500 PSI (not 0–1,000 PSI)

The system relief valve (Item 8688947) fires at 1,500 PSI. A 0–1,000 PSI
transducer clips before the relief fires — the reading saturates at 1,000 PSI
and the system has no visibility into pressure between 1,000 and 1,500 PSI.
A 0–1,500 PSI transducer covers the full system range while still providing
adequate resolution across the normal operating range (500–700 PSI):
0.06 PSI/count with a 16-bit ADS1115.

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
  At 20 mA: V = 0.020 × 250 = 5.000 V → 1,500 PSI

  ADS1115 PGA setting: ±6.144 V (covers full 1–5 V range).
  PSI = (V_measured - 1.0) / 4.0 × 1500.0

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

- Generic 4–20 mA pressure transducers (0–1,500 PSI, 1/4 NPT):
  Amazon.ca, AliExpress (search: "4-20mA pressure transducer 1500 PSI 1/4 NPT")
  Typical cost: $30–50 CAD
- Omega PX309 series (higher quality, longer warranty):
  ca.omega.com — PX309-1.5KI5V or similar; ~$80–120 CAD
- 250 Ω precision resistor (0.1% tolerance recommended): Digi-Key Canada,
  Mouser Canada — ~$1–3 CAD

#### Open items before ordering

- Confirm pump outlet port thread is 1/4 in. NPT (verify against Princess
  Auto Item 8375446 spec sheet before ordering transducer)
- Confirm loop supply voltage available on the dyno (12 V or 24 V) — affects
  transducer selection (most 4–20 mA units accept 12–30 VDC, confirm range)
- Confirm ADS1115 I2C address against other I2C devices on the bus before
  wiring (default 0x48 — no conflict with MCP4725 at 0x60)
- TODO: on first hardware run, verify 4 mA live-zero reading with no pressure
  applied; calibrate PSI conversion against a known reference pressure

## Proportional valve — CONFIRMED

Sun Hydraulics (Helios Technologies) proportional pressure relief valve. A
fixed-displacement gear pump with proportional backpressure control is the
correct architecture for a hydraulic brake dyno: a pressure relief valve sets
the pump outlet backpressure electronically — higher command = more engine
braking load = lower RPM, which is exactly what the PID loop closes on.

| Spec              | Value                                                          |
|-------------------|----------------------------------------------------------------|
| Manufacturer      | Sun Hydraulics (Helios Technologies)                           |
| Model             | RPGC-LBN (24 VDC coil); RPGC-LAN = 12 VDC variant              |
| Type              | Proportional pressure relief, cartridge-style, normally closed |
| Cavity            | C10-2                                                          |
| Rated pressure    | 5,000 PSI max                                                  |
| Operating range   | 500–700 PSI normal for this build                              |
| Software trip     | 900 PSI (`OVERPRESSURE_TRIP_PSI` in `simulator/modbus_map.py`) |
| Mechanical relief | 1,500 PSI (upstream relief valve, Item 8688947)                |
| Rated flow        | 15 GPM (build needs ~10 GPM max at peak pump RPM)              |
| Coil              | 24 VDC proportional solenoid (current-controlled)              |

### Why this valve — notes

- **Normally closed** = at zero command (zero coil current) the valve is closed
  and the circuit holds at maximum spring-set pressure. This is the correct
  e-stop behavior: when the PLC drives SAFETY_ENABLE to 0, VALVE_POSITION_CMD
  goes to 0 (zero current), the pump circuit pressurizes, and the engine is
  braked to a stop. Fail-safe to maximum braking is the right safe-stop mode
  for a brake dyno.
- The PLC overspeed interlock (6,500 RPM trip) provides independent protection
  in the event of runaway.
- 15 GPM rated comfortably covers the ~10 GPM max pump output at peak RPM (1,743
  pump RPM at 6,100 engine RPM through the 3.5:1 reduction with 1.52 cu.in.
  displacement).
- 5,000 PSI rating gives ~7× margin over normal operating pressure.

### Required mounting hardware

- Sun C10-2 inline body, part **C102-2-B** — simplest option for a prototype
  build. Est. $80–120 CAD.
- Alternative: custom ported manifold block (if combining multiple functions).

### Driver options — choose one before ordering

**Option A — custom driver circuit (recommended for first build):**
- MCP4725 I2C DAC on the Pi (12-bit, 0–3.3 V, ~$5 CAD) → rail-to-rail op-amp
  scaler (3.3 V → 10 V) → DRV8871 or L298N coil current driver (~$5–10 CAD)
- Pi interface: I2C on pins 3 + 5 (GPIO 2/3), no additional HAT needed
- Total driver cost: ~$15–25 CAD in components

**Option B — Sun PRZE-LBN proportional amplifier card:**
- Accepts 0–10 V command, outputs calibrated proportional coil current; no
  custom circuit needed
- Recommended if the build will be reproduced or documented for others
- Est. $120–150 CAD from a Sun distributor

### Modbus interface — no register map changes needed

- Pi writes VALVE_POSITION_CMD (holding register 40001, 0–10000 = 0.00–100.00%)
- Driver circuit scales the command to 0–10 V (or directly via the MCP4725 DAC output)
- Coil current proportional to command → relief pressure proportional to command

### Estimated cost (CAD, new)

| Item                       | Price (CAD)      |
|----------------------------|------------------|
| Valve cartridge (RPGC-LBN) | $280 – 380       |
| Inline body (C102-2-B)     | $80 – 120        |
| Driver — Option A          | $15 – 25         |
| Driver — Option B          | $120 – 150       |
| **Total, Option A driver** | **~$375 – 525**  |
| **Total, Option B driver** | **~$480 – 650**  |

Budget remaining of the $1,000 CAD target after the valve system:
- Option A driver: ~$475–625 CAD remaining for all other BOM items
- Option B driver: ~$350–520 CAD remaining

### Canadian sources

- Hydraquip (distributor — Ontario, BC, AB locations)
- Applied Hydraulics (Ontario)
- Sun Hydraulics direct: sunhydraulics.com (ships to Canada)

NOTE: Confirm the exact part number with the distributor before ordering. Sun
uses suffix codes for coil voltage, seal material, and flow variants. Confirm:
RPGC-LBN = 24 VDC, RPGC-LAN = 12 VDC.

### Open items before ordering

- Confirm the C102-2-B body is in stock at the chosen distributor
- Confirm coil voltage (LBN = 24 V vs LAN = 12 V) matches the driver circuit
- Confirm bore size / port thread spec on the C102-2-B body
- TODO: validate actual operating pressure on the first hardware run and compare
  to the simulator model (target: 595 PSI at peak torque, 900 PSI software trip)

## System pressure specs

- **Normal operating range:** 500 - 700 PSI
- **Back-pressure baseline:** ~200 PSI (set by return-line relief valve, Item 8688939)
- **System relief (mechanical):** 1,500 PSI (Item 8688947)
- **Software overpressure trip:** 900 PSI (applied in commit 0dd0a7a,
  `simulator/modbus_map.py`) — fires before mechanical relief opens
- **Basis:** 3.5:1 chain reduction, 1.52 cu.in. pump, ~595 PSI at peak engine torque
