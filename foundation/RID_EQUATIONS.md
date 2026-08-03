# RID Equation Set — Canonical vs Proposed

**Status:** Doctrine reference (2026-07-26)  
**Bedrock:** `L:/Continue/Viv/foundation/`  
**Theory source (read-only):** `L:/Phone/` (`ridplot.py`, `ridv14.py`)  
**Runtime:** `lib/rid_triad.py`, `lib/master_rid.py`, `rid_main.py`

This document separates **already-implemented RID mathematics** from **proposed CPU↔GPU electrical and routing equations**. Proposed sections are not plant law until coded, evidenced, and gated.

**Unresolved by design:** watts, volts, and amps are **not** permanently assigned one-to-one to RSR, LTP, and RLE. The cleaner formulation treats them as the three inputs of an independent electrical subsystem whose \(S_{\text{electrical}}\) then participates in the RID hierarchy.

---

## Part A — Canonical RID (implemented)

### A.1 Dual-sensor plant equations

For two plant measurements \(A\) and \(B\) (e.g. paired temperatures):

\[
LTP=\frac{A+B}{2}
\]

Midpoint / coupled layer state.

\[
RSR=A\times B
\]

Coupled product (continuity / reconstruction stability on the raw plant pair).

\[
RLE=
A B-
\left(\frac{A+B}{2}\right)^2
\]

Gap / spread-energy term (as in the RID briefing and `L:/Phone/ridplot.py`).

\[
RLE_{\text{rate}}=\frac{d(RLE)}{dt}
\]

Rate of RLE change — early warning channel.

### A.2 Runtime channels (normalized)

Live control uses **normalized** RSR, LTP, and RLE in \([0,1]\) (load stability, thermal headroom, memory/RAM headroom). Raw dual-sensor formulas and runtime channels share names but are not the same numeric scale — always check which layer you are reading.

### A.3 Subsystem stability

For subsystem \(k\):

\[
S_k=
\sqrt[3]{
RSR_k\,
LTP_k\,
RLE_k
}
\]

Implemented as `sn_from_channels` in `lib/master_rid.py`.

Current subsystems include (names as wired today):

| \(k\) (doctrine) | Runtime name (approx.) |
|------------------|-------------------------|
| CPU | `cpu_automaton` |
| GPU | `gpu` |
| coolant | `coolant_loop` |
| piston | `piston` |

Near \(1\) means highly stable **for current activity**, not necessarily idle.

### A.4 Master \(S_n\)

For \(N\) **available** subsystems:

\[
Master\_S_n
=
\left(
\prod_{k=1}^{N}S_k
\right)^{1/N}
\]

Geometric mean of available subsystem scores (`_geom_mean` in `lib/master_rid.py`). Unavailable subsystems are omitted rather than forced to zero when the plant marks them unavailable.

### A.5 Dormancy gate

\[
S_n < T_{\text{dormant}} \Rightarrow \text{DORMANT}
\]

\[
S_n \ge T_{\text{dormant}} \Rightarrow \text{ACTIVE}
\]

Thresholds are **calibrated, not universal**:

| Context | Typical floor | Note |
|---------|---------------|------|
| Host / Law-5 security | \(\approx 0.37\) | Cold-start / security dormancy |
| Broader Architect alignment | \(0.45\) | Default plant doctrine in `RID.md` |

Do not conflate Law-5 security dormancy with judge Vixi floors or AIFL speech gates.

### A.6 Predictive / PRT loop (existing control idea)

\[
F_\theta(x_t,a_t,c_t)
\rightarrow
\left(
\widehat{RSR}_{t+\Delta},
\widehat{LTP}_{t+\Delta},
\widehat{RLE}_{t+\Delta},
\widehat{O}_{t+\Delta}
\right)
\]

- \(x_t\): plant state  
- \(a_t\): proposed action  
- \(c_t\): language / memory / task context  
- hats: predicted futures; sensors grade actual outcomes  

This is the SEE → COMMIT → ACT → GRADE spine (PRT), not a claim that a full learned \(F_\theta\) is already the live authority.

---

## Part B — Proposed electrical + routing (not yet RID law)

Sections below are **proposed**. They must not be confused with Part A. Implementation requires telemetry sources, fail-closed handling, evidence captures, and an explicit experiment flag.

### B.1 Basic electrical identities (bridge only)

\[
P = VI,\qquad
I = \frac{V}{R},\qquad
R = \frac{V}{I}
\]

These identities motivate coupling ratios. They are **not** the RID stability formula.

### B.2 CPU↔GPU normalized ratios

For watts, volts, or amps:

\[
r_X =
\frac{\min(X_{\text{CPU}},X_{\text{GPU}})}
{\max(X_{\text{CPU}},X_{\text{GPU}})}
\qquad
X\in\{W,V,I\}
\]

Dimensionless in \([0,1]\): \(1\) = equal; near \(0\) = imbalance; \(0\) = required side failed.

Safe piecewise form:

\[
r_X =
\begin{cases}
\dfrac{\min(X_{\text{CPU}},X_{\text{GPU}})}
{\max(X_{\text{CPU}},X_{\text{GPU}})},&
\max(X_{\text{CPU}},X_{\text{GPU}})>0
\\[8pt]
1,&\text{both intentionally inactive}
\\
0,&\text{required component reading failed}
\end{cases}
\]

Example — **Ohm-consistent** (same rail \(V\), \(W=VI\)):

\[
V_{\text{CPU}}=V_{\text{GPU}}=12,\quad
I_{\text{CPU}}=2,\ I_{\text{GPU}}=4
\Rightarrow
W_{\text{CPU}}=24,\ W_{\text{GPU}}=48
\]

\[
r_V=1,\quad r_I=\tfrac{2}{4}=0.5,\quad r_W=\tfrac{24}{48}=0.5
\]

Then \(r_W=r_I\) as required by \(P=VI\) at shared voltage.

Example — **mixed sensor domains** (illustrative only; package watts ≠ rail \(VI\)):

\[
r_W=\frac{65}{120}\approx0.542,\quad
r_I=\frac{2}{4}=0.5,\quad
r_V=\frac{12}{12}=1
\]

Do not treat the mixed-domain numbers as one Ohm-consistent circuit.

### B.3 Raw electrical coupling product

\[
C_{\text{electrical}}=r_W\,r_V\,r_I
\]

Any zero factor zeros the product.

Ohm-consistent example: \(C=0.5\times1\times0.5=0.25\).

Mixed-domain illustrative: \(0.542\times1\times0.5\approx0.271\).

### B.4 Electrical subsystem stability (proposed)

\[
S_{\text{electrical}}
=
\sqrt[3]{r_W\,r_V\,r_I}
=
\sqrt[3]{C_{\text{electrical}}}
\]

Geometric mean keeps the score on a comparable scale to the inputs.

Ohm-consistent: \(\sqrt[3]{0.25}\approx0.630\). Mixed-domain illustrative: \(\sqrt[3]{0.271}\approx0.647\).

**Dependence (same pattern as RID):** if \(P=VI\) holds exactly on each side, \(\{W,V,I\}\) are not three free physical axes — parallel to \(RLE=RSR-LTP^2\). The triad remains valid as **three observed meter channels**, not three independent degrees of freedom.

**Role:** \(S_{\text{electrical}}\) is a **candidate new subsystem** in the Master hierarchy — not a remapping of W/V/I onto RSR/LTP/RLE.

### B.5 Active-set Master \(S_n\) (proposed refinement)

\[
Master\_S_n(t)
=
\left(
\prod_{k\in A(t)}
S_k
\right)^{1/|A(t)|}
\]

\(A(t)\) = components required for the current task.

- CPU-only: \(A(t)=\{\text{CPU},\text{coolant},\text{memory}\}\)  
- Transformer inference: \(A(t)=\{\text{CPU},\text{GPU},\text{coolant},\text{memory},\text{electrical}\}\)  

**Locked inactive rule:** intentionally inactive / sleeping components are **excluded from \(A(t)\)**.  
Never feed Master by setting \(r_X=1\) (or \(S=1\)) for sleepers — that inflates Master (demo: \(0.50,0.80,1.00\to0.737\) vs exclude electrical \(\to0.632\)).  
The piecewise \(r_X=1\) “both intentionally inactive” case is only a **local placeholder** for the ratio helper when `required=False`; it is not Master fuel.

### B.6 Weighted Master \(S_n\) (proposed)

\[
Master\_S_n(t)
=
\left(
\prod_{k\in A(t)}S_k^{w_k}
\right)^{
\frac{1}{\sum_{k\in A(t)}w_k}
}
\]

Weights \(w_k\) raise critical components (e.g. CPU mind, coolant) over optional voice lanes.

### B.7 Measurement efficiency (proposed)

\[
\eta_{\text{measurement}}
=
\frac{\Delta\text{Prediction Accuracy}}{\text{Measurement Cost}}
\]

Objective: maximize useful prediction accuracy per total measurement cost — not perfect sensing.

### B.8 Net value of a sensor (proposed)

\[
V_j=\Delta A_j-C_j
\]

Sensor \(j\) is useful when \(V_j>0\).

### B.9 GPU invocation value (proposed)

\[
G_{\text{GPU}}
=
\frac{
\text{Expected capability or accuracy gain}
}{
\text{Incremental joules}
+
\text{latency}
+
\text{stability cost}
}
\]

High \(G_{\text{GPU}}\) → wake transformer; low → remain CPU-only.

### B.10 CPU-versus-GPU routing (proposed)

\[
i^*
=
\arg\max_{i\in\{\text{CPU},\text{GPU}\}}
\frac{
\text{Expected useful work}_i
}{
\max(\varepsilon,\ \Delta S_{n,i}^{\text{pred}})
}
\]

Where \(\varepsilon>0\) is a denominator floor (default \(\varepsilon=10^{-6}\) in pure-math helpers).

Defined edge cases (document-only until predictors exist):

| Predicted \(\Delta S_{n,i}\) | Behavior |
|-----------------------------|----------|
| \(\gt \varepsilon\) | Use formula above |
| \(0 < \Delta S_n \le \varepsilon\) | Clamp denominator to \(\varepsilon\) |
| \(\le 0\) (neutral or stability-improving) | Treat as preferable vs positive-loss lanes; score as \(+\infty\) for ranking among finite-loss options, or pick max work among \(\Delta S_n\le 0\) |

Choose the lane with the most useful work per unit predicted stability loss (liquid-cooled CPU may win even at high watts if predicted \(\Delta S_n\) is smaller than the air-cooled GPU). **No live router in this gate** — predictors are not wired.

### B.11 Proposed hierarchy

\[
\text{Telemetry}
\rightarrow
r_W,r_V,r_I
\rightarrow
S_{\text{electrical}}
\rightarrow
S_{\text{CPU}},S_{\text{GPU}},S_{\text{other}}
\rightarrow
Master\_S_n
\rightarrow
\text{predict}
\rightarrow
\text{route}
\rightarrow
\text{act}
\rightarrow
\text{measure}
\]

### B.12 Sensor inventory (this host / foundation)

| Channel | Foundation source | Status |
|---------|-------------------|--------|
| GPU package watts \(W_{\text{GPU}}\) | `lib/gpu_plant.py` NVML `power_w` (+ HWiNFO cross-check) | **Wired** |
| CPU package watts \(W_{\text{CPU}}\) | HWiNFO `CPU Package Power [W]` | **Wired** |
| CPU / GPU volts \(V\) | HWiNFO `Vcore` / `GPU Core Voltage` | **Wired** |
| CPU amps \(I_{\text{CPU}}\) | HWiNFO `VR VCC Current (SVID IOUT)` | **Wired** |
| GPU amps \(I_{\text{GPU}}\) | No native `[A]`; Ohm sum of measured PCIe+8-pin \(P/V\) | **Software-reconstructed (non-independent)** |

Incomplete triad ⇒ electrical subsystem `available=false` and \(S_{\text{electrical}}=\texttt{null}\). Never invent \(V\) from assumed 12 V rails. Never present \(I=W/V\) as an **independent** live axis.

**Software-best GPU amps (locked):** when no native GPU `[A]` sensor exists, observe may reconstruct \(I_{\text{GPU}}\) as the sum of \(P/V\) over *simultaneously measured* same-rail HWiNFO board-input pairs (PCIe +12V and 8-pin). That value is stamped `software_ohm_from_measured_hwinfo_rails` and fails `reject_derived_live_axes` for independence — it may enter observe/shadow \(S_{\text{electrical}}\) as a dependent meter channel (same pattern as RLE identity), never as a free physical axis, and never into Master authority without B.14 evidence.

### B.13 Admission semantics (locked)

The observe gate preserves the boundary between a **valid theory** and **available instrumentation**:

\[
\text{missing measurement} \neq 0
\]

\[
\text{missing measurement} \neq \text{estimated measurement}
\]

When CPU watts or voltage/current channels are unavailable, electrical correctly returns:

\[
available=false,\qquad S_{\text{electrical}}=\texttt{null}
\]

It is excluded from the active Master geometric mean rather than inserted as zero, one, or a fabricated estimate. That preserves four distinct states:

| State | Meaning |
|-------|---------|
| Unavailable measurement | Channel not instrumented / incomplete triad — withhold admission |
| Intentionally inactive | Component not in \(A(t)\) — exclude, do not score as healthy |
| Measured healthy | Real meters present; ratio/product/S computed |
| Measured failed | Required meter present but failed → \(r_X=0\) (not “missing”) |

Present system state (evidence-governed):

\[
\boxed{
\text{implemented}
+
\text{incomplete instrumentation}
+
\text{admission withheld}
}
\]

Software is no longer the limiting factor. The remaining limitation is **observability**.

Until real CPU \(W\) and valid \(V/I\) channels exist:

\[
S_{\text{electrical}}=\texttt{null}
\qquad\Rightarrow\qquad
\text{electrical}\notin A(t)
\]

for the Master geometric mean.

### B.14 Authority promotion ladder (locked)

Once meters are wired, electrical earns Master participation only through:

\[
\text{observe}
\rightarrow
\text{validate}
\rightarrow
\text{calibrate}
\rightarrow
\text{shadow-run}
\rightarrow
\text{compare against current Master}
\rightarrow
\text{grant authority only after evidence}
\]

Honesty contract (non-negotiable):

- no synthetic fills  
- no zero substitution for missing meters  
- no neutral-value masking (\(r_X=1\) / \(S=1\) for incomplete)  
- no early Master participation  

The electrical lane earns authority only after physical measurements are complete and its behavior is proven stable against the current Master.

### B.15 Four explicit lane states (locked) — prediction branch CLOSED

Decisive evidence (2026-07-27, corpus `rid_electrical_decisive_v1_15`) produced
**negative** \(\Delta_{\text{info}}\) on whole-session holdouts. The Master /
prediction / routing branch is closed:

\[
\boxed{\texttt{rejected\_operational\_use}}
\qquad
\text{rails: }
\boxed{\texttt{observe\_only\_diagnostics}}
\]

\[
\text{unimplemented}
\rightarrow
\text{implemented but unavailable}
\rightarrow
\text{measured in shadow}
\rightarrow
\textbf{rejected operational use}
\quad(\text{not admitted})
\]

| State | Claim | Master |
|-------|-------|--------|
| Unimplemented | No electrical code/path | \(\notin A(t)\) |
| Implemented but unavailable | Code present; meters incomplete → \(S=\texttt{null}\) | \(\notin A(t)\) |
| Measured in shadow | Historical shadow/A/B phase | \(\notin A(t)\) |
| **Rejected operational use (current)** | Decisive negative \(\Delta_{\text{info}}\); prediction closed | \(\notin A(t)\); no weight; no routing |
| Admitted to Master | **Not reached**; reopen only under material-change conditions | — |

**Rails may still observe** (diagnostics only): board power distribution, voltage
anomalies, Ohm-stamped derived current, missing/stale sensors, unusual
PCIe-vs-8-pin behavior, forensic state during crash/throttle.  
**Do not** describe that telemetry as predictive.

Authority scaffolds (canary \(w_e\), advisory \(Q_i\), admission gate) remain
in-tree as evidence of what was examined; all apply/write paths **fail closed**
(`lib/rid_electrical_policy.py`).

**Reopen prediction only when** something material changes *before* new data:
independent hardware current meters; substantially different sensors; new CPU
power instrumentation; different hardware; different prediction target; new
physical hypothesis. **Not** by collecting more sessions of the same construction.

**Productive next electrical experiment (separate):** predict direct electrical
outcomes \(E_{\text{action}}=\int P\,dt\), peak board power, or overload risk —
not Master \(S_n\).

**Started:** `rid_electrical_outcomes_v1` / `rid_electrical_action_ledger_v1` /
`rid_electrical_ledger_campaign_v1` — validated energy, per-action ledger, then
**controlled one-factor campaign** with \(CV_E/CV_P\) gates. Learning admission
**withheld**; predictor blocked until signatures are repeatable. Accounting only;
\(\notin A(t)\).

**Return plant focus to proven channels:** thermal gradients, coolant, load,
VRAM headroom, transition rates, existing RID subsystem states.

Authoritative artifacts:
`artifacts/auto/rid_electrical/{decisive_evidence_latest,role_decision_latest,corpus_freeze_manifest,prediction_postmortem_latest,CLOSED_PREDICTION_BRANCH}.*`

---

### B.15b Historical info-gain gate (archival)

The following gate governed the closed experiment and remains documented for
replay. It does **not** reopen the lane.

\[
\Delta_{\text{info}}
=
MAE_{\text{baseline}}
-
MAE_{\text{baseline+electrical}}
\]

| Outcome (historical) | Disposition |
|---------|------------------|
| Positive multi-session clean \(\Delta_{\text{info}}\) | Would have supported admission review |
| No prediction gain, useful rails | Permanent diagnostic observer |
| **Negative / unstable (observed)** | **`rejected_operational_use`** |

\(I_{\text{GPU}}\) remains derived (`software_ohm_from_measured_hwinfo_rails`), not an independent axis.


---

## Implementation gate (observe-only diagnostics)

1. Flag: `rid_electrical_observe_v1` (diagnostics only; **not** Master / prediction / routing).  
2. Policy: `lib/rid_electrical_policy.py` — `rejected_operational_use`.  
3. Code retained: `lib/rid_electrical.py`, tests, shadow/ablation/canary/advisory scaffolds (disabled).  
4. Keep Part A Master rollup unchanged.  
5. Incomplete channels fail closed (`available=false`).  
6. Accidental Master electrical write → fail closed.

Commands:

```powershell
L:\Continue\.venv\Scripts\python.exe scripts\test_rid_electrical.py
L:\Continue\.venv\Scripts\python.exe scripts\rid_electrical_observe.py --once
L:\Continue\.venv\Scripts\python.exe scripts\rid_electrical_close_prediction_branch.py
L:\Continue\.venv\Scripts\python.exe scripts\rid_electrical_master_canary.py --apply
L:\Continue\.venv\Scripts\python.exe scripts\rid_electrical_advisory_route.py --once
```

Do **not** run new decisive/admission campaigns for Master prediction on the same meters.

---

## Related docs

| Doc | Role |
|-----|------|
| `RID.md` | Living RID pillar overview |
| `AIOS_ALPHA_MANUAL.md` | Operator \(S_n\) / dormancy notes |
| `AIFL.md` | Learning loop (consumes plant; does not redefine RID math) |
| `L:/Phone/ridplot.py` | Canonical dual-sensor arithmetic source |

---

## Verification verdict (2026-07-26)

Checked algebraically against `L:/Phone/ridplot.py` and `lib/master_rid.py`. Numerics reproduced with `L:/Continue/.venv/Scripts/python.exe`. Contracts locked in `scripts/test_rid_electrical.py`.

### Correct (keep)

| Claim | Verdict |
|-------|---------|
| \(P=VI\), \(I=V/R\), \(R=V/I\) | True electrical identities (bridge only). |
| Dual-sensor LTP / RSR / RLE definitions | Match Phone RID. Identity holds: \(RLE=-(A-B)^2/4\). |
| \(S_k=(RSR\cdot LTP\cdot RLE)^{1/3}\) (normalized channels) | Matches `sn_from_channels`. |
| \(C_{\text{electrical}}=r_Wr_Vr_I\) and \(S_{\text{electrical}}=C^{1/3}\) | Algebraically consistent. |
| \(r_X=\min/\max\) with fail-closed \(0/0\) cases | Sound dimensionless coupling ratio. |
| Master as geometric mean of subsystem \(S_k\) | Matches runtime `_geom_mean`. |
| Weighted geom-mean formula | Correct. |
| Active set \(A(t)\) excluding sleeping GPU | Locked: exclude sleepers; never Master-inflate with \(S=1\). |
| Keeping W/V/I **off** the RSR/LTP/RLE axes | Correct — parallel subsystem is the clean design. |

### Locked polish rules

1. Prefer Ohm-consistent fixtures when demonstrating \(P=VI\); label mixed-domain package-vs-rail numbers explicitly.  
2. Observed channels may be dependent under exact \(P=VI\) — still valid as meters.  
3. Inactive ⇒ exclude from \(A(t)\); never inactive ⇒ \(S=1\) inside Master.  
4. Routing denominator uses \(\varepsilon\) floor; \(\Delta S_n\le 0\) is a defined edge (no live router yet).  
5. Runtime Master today: `cpu_automaton`, `piston`, `gpu`, `coolant_loop` only — observe gate does not change this.

### Bottom line

**Canonical RID math: correct.**  
**Electrical coupling + geometric-mean subsystem: coherent — keep.**  
**Observe gate:** compute what real meters allow; fail closed when the triad is incomplete; Master authority unchanged.
