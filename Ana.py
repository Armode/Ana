#!/usr/bin/env python3
"""
Ana v1 primitive — export-ready simulation (circular layout + legend + step mode)

Features (locked in):
- 6-tile ring A–B–C–D–E–F–A
- Single baton token: exactly one S=0
- Baton moves CW/CCW, reverses on failed ACT geometry
- Escalation: after K fails → PARK for H steps and flip buf(C)
- Task triggers on ARRIVE_C:
  - Jump once (D=1 → D=0)
  - Then ACT attempts (D=0)
- Strict boundary test on BOTH sides of C, but uses effective value:
  - eff(X) = buf[X] if S[X]==0 else S[X]
- Mirror ACT success: latch shadows on neighbors of C (B and D) with decay
- Hesitation accumulation at C on failed ACT attempt, capped at Emax=6
  - Reset E(C)=0 on ACT success

Run:
  python ana_v1.py
  python ana_v1.py --steps 120 --mode step
  python ana_v1.py --mode sleep --delay 0.4
"""

from dataclasses import dataclass
from typing import List
import argparse
import time

TILES = ["A", "B", "C", "D", "E", "F"]
IDX = {t: i for i, t in enumerate(TILES)}
N = len(TILES)

def left(i: int) -> int:
    return (i - 1) % N

def right(i: int) -> int:
    return (i + 1) % N

def domain_sign(i: int) -> int:
    # Fixed segmentation domains for release behavior
    return +1 if i in (IDX["A"], IDX["B"], IDX["C"]) else -1

def s_char(v: int) -> str:
    return {+1: "+", 0: "0", -1: "-"}[v]

def halo_char(e: int) -> str:
    # Visual intensity: capped at 6 but displayed as 0,1,2,3+
    if e <= 0: return " "
    if e == 1: return "·"
    if e == 2: return "o"
    return "*"

def eff(S: List[int], buf: List[int], i: int) -> int:
    # Effective value for boundary checks: token uses buffered phase sign
    return buf[i] if S[i] == 0 else S[i]

def boundary_strict_effective(S: List[int], buf: List[int], i: int) -> bool:
    # Strict boundary: neighbor effective sum == 0
    return eff(S, buf, left(i)) + eff(S, buf, right(i)) == 0

@dataclass
class Task:
    P: int = 1          # task active
    D: int = 1          # jump flag (1=jump next ARRIVE_C, 0=act next ARRIVE_C)
    TTL: int = 3        # successful ACTs remaining
    FAILCOUNT: int = 0
    DIR: str = "CW"
    K: int = 3          # failures to escalate
    H: int = 2          # park duration
    PARK: int = 0       # remaining parked ticks

def step_baton(pos: int, direction: str) -> int:
    return right(pos) if direction == "CW" else left(pos)

def print_legend(Emax: int) -> None:
    print("LEGEND")
    print(" Tile:Xh[bY]  -> X=state (+,0,-), h=shadow, bY=buffer sign")
    print(f" Shadow levels: ' ' = 0 (none), '·' = 1, 'o' = 2, '*' = 3..{Emax}")
    print(" Baton marker: B/^ above tile holding the baton (state 0)")
    print(" DIR= direction of baton travel")
    print(" Occurrence: ARRIVE_C when baton enters C")
    print(" Task: jump once, then act on next ARRIVE_C; repeat via TTL")
    print(" ACT success: mirror pulse -> latch shadows on B & D (neighbors of C)")
    print(" ACT fail: hesitation accumulates at C (cap), reverse DIR; after K fails -> PARK H steps and flip buf(C)")
    print("-" * 72)

def render_circle(S: List[int], E: List[int], buf: List[int], baton_pos: int, direction: str) -> str:
    # Rough ASCII circle layout
    layout = {
        0: (2, 6),   # A
        1: (0, 10),  # B
        2: (2, 14),  # C
        3: (6, 14),  # D
        4: (8, 10),  # E
        5: (6, 6),   # F
    }
    canvas = [[" "] * 28 for _ in range(13)]

    for i, (r, c) in layout.items():
        tile = TILES[i]
        s = s_char(S[i])
        h = halo_char(E[i])
        b = s_char(buf[i])
        mark = f"{tile}:{s}{h}[b{b}]"
        for j, ch in enumerate(mark):
            canvas[r][c + j] = ch

    # Baton marker above the current baton holder
    br, bc = layout[baton_pos]
    canvas[max(br - 2, 0)][bc + 1] = "B"
    canvas[max(br - 1, 0)][bc + 1] = "^"

    # Direction label
    label = f"DIR={direction}"
    for j, ch in enumerate(label):
        canvas[11][j] = ch

    return "\n".join("".join(row) for row in canvas)

def simulate(
    steps: int = 80,
    mode: str = "step",        # "step" | "sleep" | "fast"
    delay: float = 0.4,        # used if mode == "sleep"
    Hshadow: int = 3,
    Emax: int = 6,
    TTL: int = 3,
) -> None:
    # Committed states
    S = [+1, +1, +1, -1, -1, -1]
    # Shadow timers (latch + decay)
    E = [0] * N
    # Buffered phase signs
    buf = [domain_sign(i) for i in range(N)]

    # Start baton at A
    baton_pos = IDX["A"]
    S[baton_pos] = 0

    task = Task(TTL=TTL)

    print_legend(Emax)
    print(render_circle(S, E, buf, baton_pos, task.DIR))
    print("=" * 72)

    for t in range(1, steps + 1):
        # pacing
        if mode == "step":
            input(f"\nPress Enter for t={t}...")
        elif mode == "sleep":
            time.sleep(delay)

        # 1) decay shadows
        for i in range(N):
            if E[i] > 0:
                E[i] -= 1

        # 2) parking
        if task.PARK > 0:
            task.PARK -= 1
            print(f"\nt={t:02d} (PARK)")
            print(render_circle(S, E, buf, baton_pos, task.DIR))
            continue

        # 3) move baton (atomic swap)
        old = baton_pos
        new = step_baton(baton_pos, task.DIR)

        S[old] = domain_sign(old)  # release
        baton_pos = new
        prev = S[baton_pos]
        S[baton_pos] = 0           # acquire

        events = []
        arrive_c = (baton_pos == IDX["C"] and prev in (+1, -1))

        if arrive_c and task.P == 1:
            events.append("ARRIVE_C")

            if task.D == 1:
                # Jump occurrence
                task.D = 0
                events.append("JUMP")
            else:
                # ACT attempt
                L, R = left(baton_pos), right(baton_pos)  # B, D
                lb = boundary_strict_effective(S, buf, L)
                rb = boundary_strict_effective(S, buf, R)
                events.append(f"b(B)={lb} b(D)={rb}")

                if lb and rb:
                    # ACT success: mirror pulse -> latch neighbor shadows
                    E[L] = max(E[L], Hshadow)
                    E[R] = max(E[R], Hshadow)

                    # Reset hesitation at C on success
                    E[IDX["C"]] = 0

                    task.FAILCOUNT = 0
                    task.TTL -= 1
                    events.append("ACT✓ MIRROR")
                    events.append(f"TTL→{task.TTL}")

                    # Re-arm immediately if repeats remain
                    if task.TTL > 0:
                        task.D = 1
                        events.append("RE-ARM")
                    else:
                        task.P = 0
                        task.D = 0
                        events.append("DONE")
                else:
                    # Hesitation accumulates at C (cap at Emax), and reversals/escalation
                    E[IDX["C"]] = min(E[IDX["C"]] + 1, Emax)
                    events.append(f"HESITATE E(C)={E[IDX['C']]}")

                    task.DIR = "CCW" if task.DIR == "CW" else "CW"
                    task.FAILCOUNT += 1
                    events.append(f"REV DIR→{task.DIR}")
                    events.append(f"FAIL→{task.FAILCOUNT}")

                    if task.FAILCOUNT >= task.K:
                        task.PARK = task.H
                        task.FAILCOUNT = 0
                        buf[IDX["C"]] *= -1
                        events.append(f"ESCALATE PARK={task.H} buf(C)→{s_char(buf[IDX['C']])}")

        header = f"\nt={t:02d}"
        if events:
            header += " | " + ", ".join(events)
        print(header)
        print(render_circle(S, E, buf, baton_pos, task.DIR))

def main():
    parser = argparse.ArgumentParser(description="Ana v1 primitive simulation (export-ready).")
    parser.add_argument("--steps", type=int, default=80, help="Number of ticks to simulate.")
    parser.add_argument("--mode", choices=["step", "sleep", "fast"], default="step",
                        help="Pacing mode: step=press Enter, sleep=delay per tick, fast=no delay.")
    parser.add_argument("--delay", type=float, default=0.4, help="Seconds per tick for --mode sleep.")
    parser.add_argument("--hshadow", type=int, default=3, help="Shadow latch level on mirror success.")
    parser.add_argument("--emax", type=int, default=6, help="Hesitation shadow cap (and overall shadow cap).")
    parser.add_argument("--ttl", type=int, default=3, help="Number of successful ACT/MIRROR events to perform.")
    args = parser.parse_args()

    simulate(
        steps=args.steps,
        mode=args.mode,
        delay=args.delay,
        Hshadow=args.hshadow,
        Emax=args.emax,
        TTL=args.ttl,
    )

if __name__ == "__main__":
    main()
