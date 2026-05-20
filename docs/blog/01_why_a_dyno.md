# 01 — Why Build a Dyno?

Let's start with the obvious question: what is a dynamometer, and why would a
sane person build one in their garage?

## What a dyno actually does

A dynamometer — "dyno" — measures how much **torque** an engine makes, and at
what **RPM**. Multiply torque by RPM and you get **power**. That's it. That's
the whole magic. Everything else is plumbing.

The trick is the *measuring*. You can't weigh torque on a kitchen scale. So you
make the engine fight something. You connect its output shaft to a brake — a
device that resists turning — and you measure how hard the engine has to push to
overcome that resistance at a given speed. Hold the engine at 3,500 RPM, see how
much twist it takes to keep it there, and you've got a data point. Sweep across
the rev range and you've got a torque curve: the fingerprint of the engine.

Why would you want that? Because **you can't improve what you can't measure.**
Change the carburetor jetting, swap an exhaust, adjust the timing — without a
dyno you're guessing whether it helped. With a dyno, you *know*. You get a
before curve and an after curve, and the truth is right there on the screen.

## Why the LO206 specifically

This project targets the **Briggs & Stratton LO206**, and that's a deliberate
choice. The LO206 is the engine behind one of the most popular spec classes in
kart racing. "Spec" is the key word: it's a **sealed engine class.** Every racer
runs the same engine, sealed at the factory, and you are not allowed to crack it
open and port the heads. The whole point is that the racing comes down to the
driver and the chassis, not whose wallet bought the most horsepower.

So why dyno a sealed engine you can't modify? A few good reasons:

- **Tuning the legal stuff.** You still control jetting, gearing, and the slide
  configuration for your class. A dyno tells you what those choices actually do.
- **Health checks.** A sealed engine still wears. A dyno catches a tired engine
  before it costs you a race weekend.
- **Curiosity.** The LO206 is a beautifully simple, well-documented engine —
  about 10 ft-lbs of torque and 8.8 HP, capped around 6,100 RPM. It's a perfect
  teacher.

It's small, cheap, predictable, and there are official factory dyno sheets to
check our numbers against. If you're going to build your first dyno, this is the
engine to build it around.

## The hydraulic brake approach

There are a few ways to build the "brake" part. Big commercial dynos often use
water brakes or eddy-current brakes. We're using a **hydraulic** brake, and it's
a genuinely elegant trick.

Here's the idea: couple the engine to a hydraulic pump. The harder you make it
to push fluid through that pump, the more the engine has to work to turn it. And
how do you control "how hard"? A **proportional valve** — basically an
adjustable restriction in the fluid path. Open the valve and the engine spins
freely; close it and the engine strains against the load. Modulate that valve in
real time and you can hold the engine at any RPM you like, or sweep it smoothly
across the whole range.

It's elegant because the *control* problem is clean: one actuator (the valve),
one main thing to measure (torque, via pressure or a load cell), and a tidy
feedback loop in between. That's a control-systems problem, and control-systems
problems are exactly the kind of thing you can practice in software before you
ever touch a wrench.

## The sim-first strategy

Which brings us to the part that makes this project a little unusual: **we are
building the entire control system in simulation before buying hardware.**

The plan is to write a Python model of the engine and the hydraulic load — one
that produces realistic RPM, torque, and pressure numbers — and have it talk to
the real control software (OpenPLC, running the kind of logic you'd find in
industrial automation) over the exact same protocol the real hardware will use:
Modbus. The controller won't know the difference. As far as it's concerned, it's
already running a dyno.

What does that de-risk?

- **The expensive mistakes.** The proportional valve is the priciest part of the
  build. We'll have the control logic working — PID tuning, safety limits, the
  whole loop — before we spend a dollar on it.
- **The dangerous mistakes.** Overspeed and over-pressure protection get tested
  against a simulator that we can deliberately push into failure, over and over,
  with zero risk to a real engine or to us.
- **The integration mistakes.** The fiddly business of which value lives in which
  register gets shaken out on the bench, not while an engine is screaming on a
  stand.

When the hardware finally arrives, the promise is that **only the I/O changes.**
The simulator gets unplugged and real sensors get plugged in. The control logic
doesn't move.

## What you'll learn following along

This is going to be equal parts mechanical engineering, control theory, and
software. By the end you'll have seen how to:

- model a physical system well enough to develop against it,
- speak an industrial protocol (Modbus) between a simulator and a real PLC,
- write and tune a PID loop with safety interlocks that actually matter,
- and make the clean jump from a simulated rig to a real one.

You don't need to be an expert in any of those. We'll build it up piece by piece.

## Next up

In the next chapter we start building the simulator: the engine model, the
LO206 torque curve, and the first Modbus conversation between our fake engine
and a real controller. We'll watch a PID loop hold a simulated engine at a
target RPM — the first real sign that this thing is going to work.
