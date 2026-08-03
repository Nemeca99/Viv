"""Bounded Conway Game of Life plant — CPU pressure task for Viv PRT.

Pure B3/S23 (wrap edges). No pygame, no network, no RID inject in v0 —
the task outcome (live cell count) is a clean secondary teacher alongside
hardware Master S_n.

Caps are hard: oversized requests clamp, never spawn shells.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any, Literal

import numpy as np

PatternName = Literal["random", "glider", "blinker", "pulsar_seed", "dense"]

# Hard safety caps (base-model act allowlist)
MAX_ROWS = 96
MAX_COLS = 96
MAX_GENERATIONS = 80
DEFAULT_ROWS = 48
DEFAULT_COLS = 48
DEFAULT_GENERATIONS = 24
DEFAULT_DENSITY = 0.35


@dataclass
class LifeSnapshot:
    live_cells: int
    density: float
    rows: int
    cols: int
    generation: int
    pattern: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _neighbors(grid: np.ndarray) -> np.ndarray:
    """Toroidal neighbor counts without scipy."""
    g = grid.astype(np.uint8)
    return (
        np.roll(np.roll(g, 1, 0), 1, 1)
        + np.roll(g, 1, 0)
        + np.roll(np.roll(g, 1, 0), -1, 1)
        + np.roll(g, 1, 1)
        + np.roll(g, -1, 1)
        + np.roll(np.roll(g, -1, 0), 1, 1)
        + np.roll(g, -1, 0)
        + np.roll(np.roll(g, -1, 0), -1, 1)
    )


def step_once(grid: np.ndarray) -> np.ndarray:
    n = _neighbors(grid)
    survive = (grid == 1) & ((n == 2) | (n == 3))
    birth = (grid == 0) & (n == 3)
    return (survive | birth).astype(np.uint8)


def _snapshot(grid: np.ndarray, *, generation: int, pattern: str) -> LifeSnapshot:
    live = int(grid.sum())
    rows, cols = grid.shape
    den = float(live) / float(max(1, rows * cols))
    return LifeSnapshot(
        live_cells=live,
        density=round(den, 6),
        rows=int(rows),
        cols=int(cols),
        generation=int(generation),
        pattern=pattern,
    )


def seed_grid(
    *,
    rows: int = DEFAULT_ROWS,
    cols: int = DEFAULT_COLS,
    pattern: PatternName = "random",
    density: float = DEFAULT_DENSITY,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    rows = int(max(8, min(MAX_ROWS, rows)))
    cols = int(max(8, min(MAX_COLS, cols)))
    density = float(max(0.05, min(0.85, density)))
    rng = rng or np.random.default_rng()
    grid = np.zeros((rows, cols), dtype=np.uint8)

    if pattern == "dense":
        density = max(density, 0.55)
        grid = (rng.random((rows, cols)) < density).astype(np.uint8)
    elif pattern == "glider":
        # Classic glider mid-left
        y, x = rows // 3, cols // 4
        cells = ((0, 1), (1, 2), (2, 0), (2, 1), (2, 2))
        for dy, dx in cells:
            grid[(y + dy) % rows, (x + dx) % cols] = 1
    elif pattern == "blinker":
        y, x = rows // 2, cols // 2
        for dx in (-1, 0, 1):
            grid[y, (x + dx) % cols] = 1
    elif pattern == "pulsar_seed":
        # Small 3x3 box cluster — not full pulsar, still structured
        y, x = rows // 2, cols // 2
        for dy in range(-1, 2):
            for dx in range(-1, 2):
                if dy == 0 and dx == 0:
                    continue
                grid[(y + dy) % rows, (x + dx) % cols] = 1
    else:
        grid = (rng.random((rows, cols)) < density).astype(np.uint8)
    return grid


def run_life(
    *,
    generations: int = DEFAULT_GENERATIONS,
    rows: int = DEFAULT_ROWS,
    cols: int = DEFAULT_COLS,
    pattern: PatternName = "random",
    density: float = DEFAULT_DENSITY,
    seed: int | None = None,
) -> dict[str, Any]:
    """Run N generations; returns before/after snapshots + wall time (CPU load)."""
    generations = int(max(1, min(MAX_GENERATIONS, generations)))
    rng = np.random.default_rng(seed)
    grid = seed_grid(rows=rows, cols=cols, pattern=pattern, density=density, rng=rng)
    before = _snapshot(grid, generation=0, pattern=pattern)
    t0 = time.perf_counter()
    for g in range(1, generations + 1):
        grid = step_once(grid)
    elapsed = time.perf_counter() - t0
    after = _snapshot(grid, generation=generations, pattern=pattern)
    return {
        "ok": True,
        "act": "life",
        "domain": "conway_b3s23",
        "generations": generations,
        "seed": seed,
        "elapsed_s": round(elapsed, 4),
        "before": before.to_dict(),
        "after": after.to_dict(),
        "delta_live": int(after.live_cells - before.live_cells),
        "caps": {
            "max_rows": MAX_ROWS,
            "max_cols": MAX_COLS,
            "max_generations": MAX_GENERATIONS,
        },
    }


def peek_before(
    *,
    rows: int = DEFAULT_ROWS,
    cols: int = DEFAULT_COLS,
    pattern: PatternName = "random",
    density: float = DEFAULT_DENSITY,
    seed: int | None = None,
) -> dict[str, Any]:
    """Seed-only snapshot for predict-before-act (no evolution)."""
    rng = np.random.default_rng(seed)
    grid = seed_grid(rows=rows, cols=cols, pattern=pattern, density=density, rng=rng)
    return _snapshot(grid, generation=0, pattern=pattern).to_dict()


def pick_pressure_pattern(round_i: int = 0) -> PatternName:
    """Rotate patterns so curriculum isn't one mushy random density."""
    choices: list[PatternName] = ["glider", "blinker", "pulsar_seed", "random", "dense"]
    return choices[int(round_i) % len(choices)]
