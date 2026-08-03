#!/usr/bin/env python3
"""
RID Black Hole visual — PC port of L:/Phone/blackholev3.py

3D collapsing cube driven by live CPU (Corsair) + GPU (NVML) metrics.
Auto stress: CPU all-core + GPU OpenCL/RTX burn when SN drops.
"""
from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib.black_hole_engine import launch_stressors, stop_stressors
from lib.gpu_black_hole_engine import GpuChannelEngine, sample_gpu_once
from lib.gpu_stress import launch_gpu_stress, stop_gpu_stress
from lib.rid_triad import DORMANCY_THRESHOLD, TriadSession, SensorPair

VERSION = "1.0.0-pc"
THRESHOLD = DORMANCY_THRESHOLD
STRESS_ON_S = 8.0
STRESS_OFF_S = 3.0


def sn_to_color(sn: float) -> tuple[int, int, int]:
    sn = max(0.0, min(1.0, sn))
    if sn < 0.25:
        t = sn / 0.25
        return int(255 * t), 0, 0
    if sn < 0.5:
        t = (sn - 0.25) / 0.25
        return 255, int(255 * t), 0
    if sn < 0.75:
        t = (sn - 0.5) / 0.25
        return 0, int(255 * (1 - t)), int(255 * t)
    t = (sn - 0.75) / 0.25
    return int(255 * t), int(255 * t), 255


def project(x, y, z, angle_x, angle_y, scale, cx, cy):
    cos_a, sin_a = math.cos(angle_y), math.sin(angle_y)
    x1 = x * cos_a - z * sin_a
    z1 = x * sin_a + z * cos_a
    cos_b, sin_b = math.cos(angle_x), math.sin(angle_x)
    y1 = y * cos_b - z1 * sin_b
    z2 = y * sin_b + z1 * cos_b
    if z2 + 5 <= 0:
        return None
    f = 300 / (z2 + 5)
    return int(x1 * f * scale + cx), int(y1 * f * scale + cy), z2


def console_run(seconds: float, auto_stress: bool, gpu_mode: str) -> int:
    session = TriadSession(pair=SensorPair.CPU_GPU)
    gpu_eng = GpuChannelEngine()
    cpu_procs: list = []
    gpu_procs: list = []
    stress_on = False
    stress_t = time.time()
    t0 = time.time()
    print(f"Black hole console v{VERSION} — {seconds:.0f}s (install pygame for 3D)")
    try:
        while time.time() - t0 < seconds:
            s = session.sample()
            g = sample_gpu_once(gpu_eng, 0)
            combined = (s.s_n + g.s_n) / 2.0
            if auto_stress:
                now = time.time()
                if stress_on and now - stress_t >= STRESS_ON_S:
                    stop_stressors(cpu_procs)
                    stop_gpu_stress(gpu_procs)
                    cpu_procs, gpu_procs = [], []
                    stress_on = False
                    stress_t = now
                elif not stress_on and now - stress_t >= STRESS_OFF_S:
                    cpu_procs = launch_stressors(None)
                    gpu_procs = launch_gpu_stress(gpu_mode)
                    stress_on = True
                    stress_t = now
            flag = "STRESS" if stress_on else "rest"
            print(
                f"t={s.t_s:5.1f}s CPU={s.a_c:.0f}C GPU={g.temp_c:.0f}C "
                f"S_n={combined:.3f} {flag} {g.gpu_name}"
            )
            time.sleep(1.0)
    finally:
        stop_stressors(cpu_procs)
        stop_gpu_stress(gpu_procs)
    return 0


def pygame_run(seconds: float, auto_stress: bool, gpu_mode: str, fullscreen: bool) -> int:
    import pygame

    session = TriadSession(pair=SensorPair.CPU_GPU)
    gpu_eng = GpuChannelEngine()
    cpu_procs: list = []
    gpu_procs: list = []
    stress_on = False
    stress_t = time.time()

    pygame.init()
    info = pygame.display.Info()
    w, h = (info.current_w, info.current_h) if fullscreen else (1280, 720)
    flags = pygame.FULLSCREEN if fullscreen else 0
    screen = pygame.display.set_mode((w, h), flags)
    pygame.display.set_caption(f"RID Black Hole PC v{VERSION}")
    font = pygame.font.Font(None, 28)
    clock = pygame.time.Clock()

    angle_x = angle_y = 0.0
    center_ema = 0.0
    first = True
    t0 = time.time()
    n, grid_scale, proj_scale = 3, 0.5, 8.0

    points = []
    for i in range(n):
        for j in range(n):
            for k in range(n):
                x = (i / (n - 1) - 0.5) * 2 * grid_scale
                y = (j / (n - 1) - 0.5) * 2 * grid_scale
                z = (k / (n - 1) - 0.5) * 2 * grid_scale
                di, dj, dk = abs(i - 1), abs(j - 1), abs(k - 1)
                tw = max(0, 1 - di) + max(0, 1 - dj) + max(0, 1 - dk)
                points.append((x, y, z, di, dj, dk, tw, i == 1 and j == 1 and k == 1))

    try:
        while time.time() - t0 < seconds:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return 0
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    return 0

            s = session.sample()
            g = sample_gpu_once(gpu_eng, 0)
            rsr, ltp, rle = s.runtime_rsr, s.runtime_ltp, s.runtime_rle
            combined = (s.s_n + g.s_n) / 2.0
            if first:
                center_ema = combined
                first = False
            else:
                center_ema = center_ema * 0.95 + combined * 0.05

            if auto_stress:
                now = time.time()
                if stress_on and now - stress_t >= STRESS_ON_S:
                    stop_stressors(cpu_procs)
                    stop_gpu_stress(gpu_procs)
                    cpu_procs, gpu_procs = [], []
                    stress_on = False
                    stress_t = now
                elif not stress_on and now - stress_t >= STRESS_OFF_S:
                    cpu_procs = launch_stressors(None)
                    gpu_procs = launch_gpu_stress(gpu_mode)
                    stress_on = True
                    stress_t = now

            screen.fill((0, 0, 0))
            cx, cy = w // 2, h // 2
            for x, y, z, di, dj, dk, tw, is_center in points:
                wr = max(0, 1 - di)
                wl = max(0, 1 - dj)
                we = max(0, 1 - dk)
                tot = wr + wl + we
                loc = (rsr * wr + ltp * wl + rle * we) / tot if tot > 0 else combined
                loc = center_ema if is_center else max(0.0, min(1.0, loc))
                p = project(x, y, z, angle_x, angle_y, proj_scale, cx, cy)
                if p:
                    color = sn_to_color(loc)
                    r = 18 if is_center else 6
                    pygame.draw.circle(screen, color, (p[0], p[1]), r)

            status = "STABLE" if combined >= THRESHOLD else "DORMANT"
            hud = [
                f"S_n: {combined:.3f} {status}",
                f"CPU {s.a_c:.0f}C  GPU {g.temp_c:.0f}C  {g.power_w:.0f}W  Util {g.util_pct:.0f}%",
                g.gpu_name,
                "STRESSING" if stress_on else "RESTING",
            ]
            for i, line in enumerate(hud):
                col = (255, 80, 80) if "STRESS" in line and stress_on else (220, 220, 220)
                screen.blit(font.render(line, True, col), (20, 20 + i * 28))

            pygame.display.flip()
            angle_x += 0.03
            angle_y += 0.06
            clock.tick(30)
    finally:
        stop_stressors(cpu_procs)
        stop_gpu_stress(gpu_procs)
        pygame.quit()
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Black hole visual (PC port blackholev3)")
    ap.add_argument("--seconds", type=float, default=180.0)
    ap.add_argument("--no-stress", action="store_true")
    ap.add_argument("--gpu-stress", default="rtx", choices=["normal", "extreme", "rtx"])
    ap.add_argument("--windowed", action="store_true")
    args = ap.parse_args(argv)
    auto = not args.no_stress
    try:
        import pygame  # noqa: F401
        return pygame_run(args.seconds, auto, args.gpu_stress, not args.windowed)
    except ImportError:
        return console_run(args.seconds, auto, args.gpu_stress)


if __name__ == "__main__":
    raise SystemExit(main())
