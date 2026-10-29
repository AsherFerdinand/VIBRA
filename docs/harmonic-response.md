# Verified FEM harmonic response (VIBRA 0.2)

## Equation, convention and forcing

Starting from M ü + C u̇ + K u = F(t), define peak phasors by
u(t) = Re(U exp(jωt)) and F(t) = Re(F exp(jωt)). Then

**(K + jωC − ω²M) U = F**, with ω = 2πf.

A harmonic load has a node, UX/UY/RZ DOF, nonnegative peak amplitude, and phase in
degrees. UX/UY amplitudes are forces [N], RZ amplitudes are moments [N m].
Multiple loads add coherently as a exp(jφ); they are not added as magnitudes.
Phase 180° reverses a load. These are peak amplitudes, **not RMS**. The load phasor
is constant over a sweep. Frequency-dependent load spectra require separate cases.

Only `HarmonicConfig.loads` is applied. `FrameModel.loads` remains static loading
and is explicitly recorded as unused in harmonic reports; there is no prestress.
Loads applied at supported DOFs are carried by those supports, with zero prescribed
motion. They do not constitute base excitation. Unsupported/unconstrained models
are rejected through the same stability check as static and modal analysis.

The existing element stiffness, consistent mass, global assembly, deterministic
DOF map and exact zero-constraint elimination are reused. No modal truncation,
penalty constraint or artificial damping/mass/stiffness shift is applied.
At each sample, a direct complex LU solves the reduced dynamic system.

## Damping inputs

The validated `Damping` model represents C = αM + βK:

| Kind | Coefficients | Physical/model interpretation |
| --- | --- | --- |
| `undamped` | α = β = 0 | Ideal model; steady-state response is not uniquely finite at a pole |
| `mass` | α ≥ 0 [1/s], β = 0 | Viscous drag proportional to mass; strongly weights low modal frequencies |
| `stiffness` | α = 0, β ≥ 0 [s] | Viscous damping proportional to elastic stiffness; weights high frequencies |
| `rayleigh` | α, β ≥ 0 | Sum of mass- and stiffness-proportional viscous damping |

Inactive coefficients must be zero; contradictory input is rejected rather than
ignored. Negative/nonfinite coefficients are rejected. Zero coefficients are
allowed for any kind, so the reported modal damping ratios are the definitive
measure of damping, regardless of the chosen label.

For mass-normalized undamped mode n:

**ζn = α/(2ωn) + βωn/2**.

This is proportional viscous damping; β does not represent frequency-independent
hysteretic loss. It does not capture arbitrary joint damping or nonproportional
measured damping matrices. Coefficients are user assumptions, not identified
material constants. A Rayleigh fit over one band can overdamp other bands.
Increasing damping lowers the measured example's response at its first natural
frequency; it need not monotonically reduce every response near an antiresonance.

## Numerical diagnostics and failure behavior

The reduced matrices use the existing diagonal scale Dii = 1/√Kff,ii. Define
A = D(Kff + jωCff − ω²Mff)D, b = D Ff; solve Ay = b and recover Uf = Dy.
A single LU factorization is reused for the solve and LAPACK `zgecon` inverse
1-norm condition estimation. Let

S = ‖DKffD‖₁ + ω²‖DMffD‖₁ + ω‖DCffD‖₁.

The reported adjusted reciprocal condition is

**r = rcond(A) ‖A‖₁ / S ≈ 1/(‖A⁻¹‖₁ S)**.

S compares the dynamic matrix with its uncancelled physical terms. This matters
for a scalar resonance: raw cond(A) is always 1 for a nonzero scalar, even if
k−mω² nearly cancels. The adjusted estimate detects that loss of relative
impedance as well as multivariable ill-conditioning. It is an estimate after
mixed-unit equilibration, not a coordinate-invariant condition number.

The default r threshold is 10⁻¹² (configurable from 10⁻¹⁵ to below 10⁻³). The
existing constrained stiffness threshold remains 10⁻¹². Too fine a mesh or
extreme geometry can also trigger these guards. Check the model and resolution
before changing tolerances. The solver never regularizes a rejected system.

The normalized backward error is
‖Ay−b‖₁ / (‖A‖₁‖y‖₁ + ‖b‖₁), with zero for an exact zero-load solution.
It must not exceed the configured default 10⁻⁹. Nonfinite matrices, loads,
solutions or amplitudes are rejected. A failed frequency aborts the **whole** sweep
and reports that frequency; no partial sweep is returned as valid. Zero load does
not bypass uniqueness/conditioning checks at an undamped pole.

These diagnostics verify an algebraic solution. They do not establish spatial
mesh accuracy, frequency resolution or suitability of linear beam theory.

## Inputs, results and workbench

`FrequencySweep(start_hz, stop_hz, points)` produces an inclusive uniform grid.
`HarmonicConfig.frequencies_hz` also accepts an explicit strictly increasing,
nonnegative sequence (including a single frequency). DC, f = 0, is supported.

```python
from vibra.core.mesh import cantilever
from vibra.io.harmonic_report import harmonic_report
from vibra.solvers.harmonic import (
    Damping,
    FrequencySweep,
    HarmonicConfig,
    HarmonicLoad,
    ResponseDOF,
    solve_harmonic,
)
from vibra.verification.benchmarks import steel_case

g, material, rectangle = steel_case()
model = cantilever(g, material, rectangle.section(), 16, tip_force=0)
config = HarmonicConfig(
    frequencies_hz=FrequencySweep(stop_hz=60, points=1001).frequencies(),
    damping=Damping(kind="rayleigh", alpha=2, beta=2e-5),
    loads=(HarmonicLoad(node=16, amplitude=1, phase_degrees=0),),
    responses=(ResponseDOF(node=16), ResponseDOF(node=8)),
)
result = solve_harmonic(model, config)
report_json = harmonic_report(model, config, result)
```

`displacement` has shape [frequencies, full global DOFs], including exactly zero
supported entries. `response_amplitude`, `phase_radians` and `phase_defined` have
shape [frequencies, selected response DOFs]. Translational values use m, rotation
uses rad. Phases are wrapped to [−π,π] and refer to the common global cosine
reference, not automatically to one particular load. For response less than or
equal to 10⁻¹² of that channel's maximum amplitude, phase is marked undefined;
the stored phase zero is only a placeholder. Plots leave gaps there.

All undamped natural frequencies and corresponding proportional modal damping
ratios are returned, not just visibly excited modes. `peaks` identifies strictly
interior local maxima of each sampled amplitude curve. `sampled_maxima` separately
records the greatest sample of each nonzero channel and flags sweep boundaries.
Neither field identifies exact poles. Narrow peaks can be missed or underestimated;
refine frequency spacing and compare meshes before interpreting a peak value.
An undamped curve connecting finite samples does not imply bounded resonance.

In Streamlit select **Harmonic response**, define geometry/material/mesh,
excitation node/DOF/amplitude/phase, sweep and damping, and one or more response
nodes/DOFs. UX/UY amplitude traces use the translation axis; RZ uses the rotation
axis. Natural frequencies are dotted lines and sampled peaks are diamond markers.
All listed natural frequencies are undamped markers, not promised response peaks.

The selected-frequency deformation is **Re(U exp(jθ))**, interpolated with the
existing beam Hermite shape functions. Change θ to inspect the cycle. The amplitude
and phase metrics are physical phasor results; the displayed geometry is magnified
by an explicit scale. It is never constructed by treating |U| as a signed shape.

## Report schema

`harmonic_report(model, config, result)` extends the existing JSON envelope with:

- Full mesh/material/support data, load and response DOFs, actual frequency samples,
  damping coefficients and solver tolerances; static load precedence is explicit.
- Full complex global U and load phasor, encoded as same-shaped `real` and `imag`
  arrays; selected amplitudes/phases and phase-validity masks.
- Undamped natural frequencies, modal damping ratios, sampled peak information,
  per-frequency condition and residual diagnostics.
- Phasor/units conventions, solver verification scope, assumptions and limitations.

The JSON envelope remains schema 1.0; existing real-only reports keep their shape.
The harmonic result introduces named complex encodings; it does not put complex
literals or NaNs into JSON. Runtime residual metadata is separate from the
independent benchmark report and does not certify a user model experimentally.

## Independent verification and reproducible plots

Run `uv run vibra-verify-harmonic`, `uv run pytest` and
`uv run python examples/harmonic_cantilever.py`.
Regenerate the committed figures/report with
`uv run python scripts/generate_harmonic_portfolio.py`.

The SDOF receptance is independently evaluated as 1/(k−mω²+jcω), including
−90° phase at the damped natural frequency. The FEM test fixture has one free
transverse DOF and known k = 12EI/L³ and m = 156ρAL/420; it does not read its
reference coefficients out of assembled matrices. Tests cover all damping kinds,
several load phases, multiple response DOFs, coherent superposition, reciprocity,
full modal-superposition equivalence, support elimination and failure cases.

A second independent benchmark solves the *continuous* uniform Euler–Bernoulli
cantilever boundary-value problem. Let EI* = EI(1+jωβ),
q⁴ = ρA(ω²−jωα)/EI*, z = qL. With y(0)=y′(0)=0, y″(L)=0 and
−EI* y‴(L)=F, the tip compliance is

**H = [cosh(z)sin(z) − sinh(z)cos(z)] / [EI* q³ (1+cosh(z)cos(z))]**.

At DC use L³/(3EI). This formula does not use FEM matrices or modal sums. It is
used for the first few bending modes; very large hyperbolic arguments and
catastrophic small-argument cancellation limit its numerical evaluation.

The steel case is unchanged: 1 m length, 20 × 20 mm section, E = 210 GPa,
ρ = 7850 kg/m³, fixed root, now a **1 N peak** tip force. Rayleigh coefficients
are α = 2 s⁻¹ and β = 2×10⁻⁵ s. The first continuum natural frequency is
16.71033189 Hz. At 32 elements, the largest complex compliance error over five
samples at 0.1/0.7/0.95/1.05/1.5 times that frequency is about **1.90×10⁻⁷**.
The phase error over those samples is about **3.28×10⁻⁸ rad**.

| Elements | Maximum relative complex compliance error |
| ---: | ---: |
| 2 | 1.1367×10⁻² |
| 4 | 7.6156×10⁻⁴ |
| 8 | 4.8459×10⁻⁵ |
| 16 | 3.0424×10⁻⁶ |
| 32 | 1.8949×10⁻⁷ |

Acceptance criteria: SDOF complex and phase error <10⁻¹⁰; DC static error
<10⁻⁸; low-frequency complex static error at f/f₁=0.001 <10⁻⁴; monotonically
decreasing continuum error over these five meshes with 32-element error <10⁻⁵;
first sampled peak within 0.1% of continuum f₁; decreasing first-natural-frequency
response for α = 0.5, 2, 8 s⁻¹. Phase comparisons use a wrapped complex ratio,
so ±π branch choices do not create false failures. These thresholds distinguish
floating-point algebra, discretization and finite frequency resolution.

![Executed FEM and continuous beam harmonic responses](results/harmonic-response.svg)

The figure compares actual undamped and Rayleigh FEM solves with the independent
Rayleigh continuum curve. The finite sampled undamped maximum is **not** a finite
physical resonance amplitude. Full metrics, inputs and check outcomes are recorded
in [harmonic-verification.json](results/harmonic-verification.json).

No experimental validation or ANSYS correlation has been performed.
