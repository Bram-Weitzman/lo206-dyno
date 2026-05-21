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
| Load cell 25-50 lbf + HX711 amplifier             | $40 - 80         |
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
