# Conway + stability triad (PRT)

## Three things to compare (stability)

Master RID is not one number only. Training compares **three channels**:

| Channel | Role |
| ------- | ---- |
| **RSR** | Identity / continuity |
| **LTP** | Load / structure |
| **RLE** | Entropy / headroom |

`Master S_n = geom_mean(RSR, LTP, RLE)` — same math as AIOS plant.

She must **predict all three before the act**, then we measure all three after settle and score each. REWARD only if **all three** are within tolerance. S_n-alone predictions cannot get full REWARD.

## Pattern frame (help her learn)

We were punishing her for failing to invent the plant from raw floats. PRT now injects an **action-conditioned pattern frame** (`lib/prt_pattern_frame.py`):

- normalized RSR/LTP/RLE/S_n (+ GPU VRAM free, package−coolant headroom)
- empirical **act deltas** from recent cycles (fallback curriculum: observe≈hold, speak≈RLE dip, life≈mild load)
- `act_prior_after` scaffold — start here, refine
- if model output is incomplete/mush, **fill missing channels from act prior** (marked `prior_filled`) — representation assist, still scored against plant
- life `live_cells` prior uses **per-pattern survival** (empirical from cycles: glider/blinker hold, random/dense decay, pulsar grows)

**Loop internalization signal:** life cycles where stability triad label and live_cells task label both REWARD (consequence + plant). Tracked in batch evidence as `life_loop_convergence`.

**Scaffold fade:** see `PRT_SCAFFOLD_FADE.md` — Phase 2 partial blanks so she owns the container, not just the content.

This is representation help, not grade inflation.

## Plus the task (life)

`act=life` adds a fourth countable: `live_cells` after Conway generations (CPU pressure). Overall REWARD = triad REWARD **and** live_cells REWARD.

## Cycle

1. Observe triad (rsr/ltp/rle + S_n)  
2. (life) show seeded board  
3. Predict triad JSON (+ live_cells if life)  
4. Act (observe / speak / life)  
5. Measure triad (+ live_cells)  
6. Score channels → combined label  

## Commands

```powershell
$PY = "L:\Continue\.venv\Scripts\python.exe"
& $PY L:\Continue\Viv\foundation\prt_main.py cycle --act life
& $PY L:\Continue\Viv\foundation\prt_main.py quick
& $PY L:\Continue\Viv\foundation\prt_main.py night start
```
