#!/usr/bin/env python3
"""
RID 3D cube — PC port of L:/Phone/ridtessv1.py

27-vertex rotating cube colored by local S_n from live PC telemetry.
Requires pygame. Falls back to console mode if pygame missing.
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

from lib.rid_triad import DORMANCY_THRESHOLD, TriadSession, runtime_channels

VERSION = "1.0.0-pc"


def sn_color(sn: float) -> tuple[int, int, int]:
    if sn < 0.5:
        return 255, int(sn * 2 * 255), 0
    return int((1 - sn) * 2 * 255), 255, 0


def project(
    x: float, y: float, z: float,
    angle_x: float, angle_y: float, scale: float, cx: int, cy: int,
) -> tuple[int, int] | None:
    cos_a, sin_a = math.cos(angle_y), math.sin(angle_y)
    x1 = x * cos_a - z * sin_a
    z1 = x * sin_a + z * cos_a
    cos_b, sin_b = math.cos(angle_x), math.sin(angle_x)
    y1 = y * cos_b - z1 * sin_b
    z2 = y * sin_b + z1 * cos_b
    if z2 + 5 <= 0:
        return None
    f = 300 / (z2 + 5)
    return int(x1 * f * scale + cx), int(y1 * f * scale + cy)


def console_run(duration: float, interval: float) -> int:
    session = TriadSession()
    sn_log: list[float] = []
    t0 = time.time()
    print(f"RID cube console mode (install pygame for 3D) — {duration:.0f}s")
    print(f"{'t':>6s} {'RSR':>6s} {'LTP':>6s} {'RLE':>6s} {'S_n':>6s} {'status':>8s}")
    while time.time() - t0 < duration:
        s = session.sample()
        sn_log.append(s.s_n)
        print(
            f"{s.t_s:6.1f} {s.runtime_rsr:6.3f} {s.runtime_ltp:6.3f} "
            f"{s.runtime_rle:6.3f} {s.s_n:6.3f} {s.status:>8s}"
        )
        time.sleep(interval)
    if sn_log:
        print(f"\nAvg S_n: {sum(sn_log)/len(sn_log):.3f}  Min: {min(sn_log):.3f}  "
              f"Dormancy beats: {sum(1 for x in sn_log if x < DORMANCY_THRESHOLD)}")
    return 0


def pygame_run(duration: float) -> int:
    import pygame

    session = TriadSession()
    pygame.init()
    info = pygame.display.Info()
    w, h = min(info.current_w, 1280), min(info.current_h, 720)
    screen = pygame.display.set_mode((w, h))
    pygame.display.set_caption(f"RID Cube PC v{VERSION}")
    clock = pygame.time.Clock()
    font = pygame.font.Font(None, 30)

    angle_x, angle_y = 0.0, 0.0
    start = time.time()
    sn_log: list[float] = []
    n, grid_scale, proj_scale = 3, 0.5, 10

    while time.time() - start < duration:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return 0

        s = session.sample()
        rsr, ltp, rle, sn = s.runtime_rsr, s.runtime_ltp, s.runtime_rle, s.s_n
        sn_log.append(sn)

        screen.fill((5, 5, 15))
        cx, cy = w // 2, h // 2
        points_3d: list[tuple[float, float, float, float]] = []

        for i in range(n):
            for j in range(n):
                for k in range(n):
                    x = (i / (n - 1) - 0.5) * 2 * grid_scale
                    y = (j / (n - 1) - 0.5) * 2 * grid_scale
                    z = (k / (n - 1) - 0.5) * 2 * grid_scale
                    di, dj, dk = abs(i - 1), abs(j - 1), abs(k - 1)
                    wr = max(0, 1 - di)
                    wl = max(0, 1 - dj)
                    we = max(0, 1 - dk)
                    tw = wr + wl + we
                    local = (rsr * wr + ltp * wl + rle * we) / tw if tw > 0 else sn
                    local = max(0.0, min(1.0, local))
                    points_3d.append((x, y, z, local))

        proj = []
        for x, y, z, loc in points_3d:
            p = project(x, y, z, angle_x, angle_y, proj_scale, cx, cy)
            proj.append((p, loc) if p else None)

        for idx, (x, y, z, _loc) in enumerate(points_3d):
            i = idx // (n * n)
            j = (idx // n) % n
            k = idx % n
            for di, dj, dk in ((1, 0, 0), (0, 1, 0), (0, 0, 1)):
                ni, nj, nk = i + di, j + dj, k + dk
                if ni < n and nj < n and nk < n:
                    nidx = ni * n * n + nj * n + nk
                    if proj[idx] and proj[nidx]:
                        pygame.draw.line(
                            screen, (60, 60, 60),
                            proj[idx][0], proj[nidx][0], 1,
                        )

        center_sn = sn
        for idx, item in enumerate(proj):
            if not item:
                continue
            (px, py), loc = item
            color = sn_color(loc)
            radius = 10 if idx == 13 else 4
            pygame.draw.circle(screen, color, (px, py), radius)

        hud1 = font.render(
            f"S_n: {center_sn:.3f} {'STABLE' if center_sn >= DORMANCY_THRESHOLD else 'DORMANT'}",
            True, (255, 255, 255),
        )
        hud2 = font.render(
            f"A={s.a_c:.1f}°C B={s.b_c:.1f}°C  load={s.cpu_load_pct:.0f}%",
            True, (200, 200, 200),
        )
        screen.blit(hud1, (20, 20))
        screen.blit(hud2, (20, 55))
        pygame.display.flip()
        angle_y += 0.02
        angle_x += 0.01
        clock.tick(20)

    if sn_log:
        print(f"=== RID Cube PC complete — {len(sn_log)} samples ===")
        print(f"Avg S_n: {sum(sn_log)/len(sn_log):.3f}  Min: {min(sn_log):.3f}")
    pygame.quit()
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="RID 3D cube (PC port of Phone/ridtessv1.py)")
    ap.add_argument("--seconds", type=float, default=120.0)
    ap.add_argument("--interval", type=float, default=1.0, help="Console mode sample interval")
    args = ap.parse_args(argv)
    try:
        import pygame  # noqa: F401
        return pygame_run(args.seconds)
    except ImportError:
        return console_run(args.seconds, args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
