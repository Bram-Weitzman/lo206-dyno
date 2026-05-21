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

The **proportional valve** is by far the largest and most variable line item
($150-400) and dominates the build cost. **Source surplus/used first** before
buying new — a used industrial proportional valve can cut this dramatically. The
valve choice also drives the valve-driver decision (0-10V amp card vs PWM +
MOSFET) documented in `sim_to_real.md`.

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
- Software `OVERPRESSURE_TRIP_PSI` will fire at 900 PSI (pending code update —
  currently 1,200 PSI in `simulator/modbus_map.py`) before this valve opens, so
  a fault latches in software before mechanical relief is exercised

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

## System pressure specs

- **Normal operating range:** 500 - 700 PSI
- **Back-pressure baseline:** ~200 PSI (set by return-line relief valve, Item 8688939)
- **System relief (mechanical):** 1,500 PSI (Item 8688947)
- **Software overpressure trip:** 900 PSI (pending code update — currently
  1,200 PSI in `simulator/modbus_map.py`) — fires before mechanical relief opens
- **Basis:** 3.5:1 chain reduction, 1.52 cu.in. pump, ~595 PSI at peak engine torque
