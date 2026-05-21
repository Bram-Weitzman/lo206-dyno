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
| Hall-effect RPM sensor + mounting bracket         | $20 - 40         |
| Pressure transducer 0-1000 PSI                    | $30 - 60         |
| K-type thermocouple + MAX31855 interface          | $25 - 40         |
| ADS1115 ADC                                       | $15              |
| Proportional valve                                | $150 - 400       |
| Valve driver (amp card, or MOSFET + parts)        | $20 - 80         |
| Hydraulic pump (1.52 cu.in. gear pump) — confirmed| $170             |
| Back-pressure valve (return line) — confirmed     | $70              |
| System relief valve — confirmed                   | $70              |
| Chain drive (#219, 20T/70T, 3.5:1) — confirmed    | $25 - 90         |
| Hilliard Flame clutch — on hand (kart)            | $0               |
| Wiring, enclosure, connectors, hydraulic fittings | $50 - 100        |
| **Subtotal (without wideband O2)**                | **~$805 - 1,195**|
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
