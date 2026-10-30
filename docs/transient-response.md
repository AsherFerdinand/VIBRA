# Verified transient FEM dynamics — VIBRA 0.3.0

## Scope and equation

The transient solver integrates **M ü + C u̇ + K u = F(t)** using the existing
2D Euler–Bernoulli consistent mass, stiffness, DOF map and exact zero-constraint
elimination. Materials are linear elastic, strains/displacements are small and
joints rigid. Only stable supported connected frames are currently accepted;
free-free rigid-body dynamics and moving supports are not implemented.

C = αM + β_R K uses the same validated undamped, mass-, stiffness-proportional and
Rayleigh models as harmonic analysis. α has units s⁻¹, β_R has units s. Both are
nonnegative; modal ζn = α/(2ωn) + β_R ωn/2. These are assumed viscous coefficients,
not experimentally identified material properties. **β_R is not the Newmark
parameter β_N.** See [harmonic damping theory](harmonic-response.md).

Only `TransientConfig.loads` supplies transient forcing. `FrameModel.loads`
remains static-only, explicitly unused in transient reports. Axial/transverse
forces use N, moments N m, displacement m, rotation rad, time s, velocity m/s or
rad/s, acceleration m/s² or rad/s², energy J.

## Average-acceleration Newmark method

The implementation fixes **β_N = 1/4, γ_N = 1/2**. For a uniform step h:

```
u_predict = u_n + h v_n + (h²/4) a_n
v_predict = v_n + (h/2) a_n
A = M + (h/2) C + (h²/4) K
A a_(n+1) = F_(n+1) − C v_predict − K u_predict
u_(n+1) = u_predict + (h²/4) a_(n+1)
v_(n+1) = v_predict + (h/2) a_(n+1)
```

The reduced matrices use the existing diagonal stiffness equilibration. Mass and
A are additionally diagonally equilibrated before Cholesky factorization. LAPACK
`dpocon` estimates reciprocal 1-norm condition; the default threshold is 10⁻¹²
(configurable from 10⁻¹⁵ to below 10⁻³). Both factorizations are reused. There is
no mass lumping, penalty constraint, stiffness shift or artificial regularization.
Singular, non-positive-definite or excessively ill-conditioned matrices are errors.

Initial displacement and velocity are sparse explicit nodal DOF values; unspecified
entries are zero. Unknown/duplicate DOFs, nonfinite inputs and nonzero initial
values on constrained DOFs are rejected. Initial acceleration is computed from
**Mff a₀ = Ff(0⁺) − Cff v₀ − Kff u₀**. It is not arbitrarily set to zero.

Average acceleration is unconditionally stable for this linear positive-definite
problem. It is second-order accurate for sufficiently resolved smooth intervals,
with **no numerical damping**. Stability and excellent energy balance do not imply
correct phase. For undamped SDOF, numerical angular frequency is
ω_num = (2/h) atan(ωh/2). Coarse steps retain energy but accumulate phase error.
Resolve the response band, load shape and initial modal content, then check time
convergence. Warnings identify fewer than 20 steps/cycle and short pulses; 20 is
an advisory resolution criterion, not a universal error bound.

## Time grid and force conventions

`TimeGrid(duration=T, time_step=h)` requires T/h to be an integer, within 10⁻⁹
absolute tolerance on the interval count. It creates an inclusive uniform grid
from zero through T; h_actual = T/N differs from requested h only by accepted
floating-point rounding. No shortened final interval is silently inserted.
There are at most 50000 intervals, 600 global DOFs and 2000000 time×global-DOF
values per run. Limits keep the retained dense histories and factorization modest.

All force onset/pulse-end events **inside** [0,T] must align to this grid within
10⁻⁸ of an interval count. Events outside the run are allowed. Loads superpose
linearly at any selected nodal UX/UY/RZ coordinate; amplitudes are signed.

| Force | Definition |
| --- | --- |
| `StepForce` | A for t ≥ start, zero before |
| `HarmonicForce` | A cos(2πf(t−start)+φ) for t ≥ start, zero before; φ in degrees |
| `PulseForce`, rectangular | A for start ≤ t < end, zero otherwise |
| `PulseForce`, half-sine | A sin(π(t−start)/(end−start)) inside the pulse, exactly zero at/outside its endpoints |
| `SampledForce` | Continuous piecewise-linear interpolation of time/value pairs, no extrapolation |

Sampled inputs must start at t=0, strictly increase, have matching finite time/value
lengths and cover the entire simulation. Their last time may exceed T. Knots need
not align to the integration grid; off-grid knots trigger a convergence warning.
They represent a linear interpolant, not zero-order hold. Nonzero harmonic
forcing must lie below the grid Nyquist frequency. Half-sine pulses or sampled
features completely missed by the grid are rejected rather than silently yielding
zero loading; partially resolved histories still require a convergence study. At most 10001 pairs per
history, 50000 pairs total and 32 simultaneous load histories are supported.
Finite pulses are not Dirac impulses; no instantaneous velocity change is modeled.

### Force jumps

A finite force jump changes acceleration, while **u and v stay continuous**. The
integrator uses F(t_n⁺) at interval start and F(t_(n+1)⁻) at interval end. At a jump:

**M Δa = F(t⁺) − F(t⁻)**.

The mass factorization updates acceleration before the next interval. Returned
acceleration and support reactions use right-hand limits. Right/left force
histories are both exposed, including the final timestamp. This avoids smearing
an endpoint jump backward into the previous interval or moving a load onset
half a step early. At t=0 the prescribed initial state and F(0⁺) define the IVP;
no pre-simulation loading history is inferred.

## Energy accounting and support reactions

Kinetic energy T = ½vᵀMv, elastic strain energy V = ½uᵀKu and mechanical energy
E = T+V use the same consistent matrices as the solve. No rotary inertia beyond
that implicit in transverse Hermite interpolation is added.

The work/dissipation quadratures are chosen consistently with average acceleration:

```
v_avg = (v_n + v_(n+1))/2
F_avg = (F(t_n⁺) + F(t_(n+1)⁻))/2
ΔD = h v_avgᵀ C v_avg
ΔW = F_avgᵀ (u_(n+1) − u_n)
R_E(t) = E(t) − E(0) + D(t) − W(t)
```

These are discrete approximations to ∫vᵀCv dt and ∫Fᵀv dt, **not exact continuous
integrals**. In particular, ΔD is not endpoint trapezoidal power quadrature.
The Newmark kinematic identities and interval-averaged equilibrium imply ΔE+ΔD=ΔW
up to floating-point solve error. Finite force jumps do no instantaneous work
because u and v do not jump. Negative external work is physically allowed;
negative kinetic/strain energy or damping increments are rejected.

The reported relative energy residual is max|R_E| divided by the maximum of E,
cumulative D and |W| over the full grid. It is zero for an identically zero case.
The solver rejects nonfinite histories, excessive equilibrium backward error
(default 10⁻⁹), or relative energy residual above the default 10⁻⁶. Energy
residuals much smaller than this guard are demonstrated by independent benchmarks.
A small residual only checks algebraic/discrete consistency, not time or mesh accuracy.

The free-DOF equilibrium backward error at each sample divides
‖Ma+Cv+Ku−F‖∞ by ‖M‖∞‖a‖∞+‖C‖∞‖v‖∞+‖K‖∞‖u‖∞+‖F‖∞ in the equilibrated
coordinates. A zero denominator for an exact zero solution gives zero error.

Dynamic support reactions are **(Ma+Cv+Ku−F)c**, using the full assembled matrices
and right-hand acceleration/force. They include M_cf a_f and C_cf v_f coupling,
not just elastic forces. Supported u/v/a are exactly zero. These fixed supports
perform zero work; moving/nonzero supports would require additional terms and
are unsupported. `reactions[:,j]` follows `constrained_indices[j]`; global indices
follow ascending node IDs and then UX/UY/RZ.

## Python API and workbench

```python
from vibra.core.dynamic_models import Damping, ResponseDOF
from vibra.core.mesh import cantilever
from vibra.dynamics.forcing import PulseForce
from vibra.solvers.transient import TimeGrid, TransientConfig, solve_transient
from vibra.verification.benchmarks import steel_case

g, material, rectangle = steel_case()
model = cantilever(g, material, rectangle.section(), 16, tip_force=0)
config = TransientConfig(
    grid=TimeGrid(duration=1, time_step=0.0005),
    damping=Damping(kind="rayleigh", alpha=2, beta=2e-5),
    loads=(PulseForce(node=16, amplitude=1, end_time=0.04),),
    responses=(ResponseDOF(node=16), ResponseDOF(node=8)),
)
result = solve_transient(model, config)
```

Full displacement/velocity/acceleration arrays have shape [time, global DOF].
Selected `response_displacement`, `response_velocity`, `response_acceleration`
retain the supplied response-DOF order. Force arrays are full global histories;
reactions retain only support columns. `InitialValue` can specify each initial
coordinate explicitly. Zero initial state and no loads give exact zero response.

In Streamlit select **Transient response**. Define geometry, material, mesh,
damping, load history, time grid and response nodes/DOFs. Optional nonzero initial
tip displacement/velocity initializes the whole cantilever with the static tip-load
profile, including consistent slopes; this is clearly labeled and differs from
setting only the tip node in the Python API.

Plots show displacement, velocity, acceleration, mechanical energy, cumulative
work/dissipation and balance. A time slider inspects actual solved deformations.
Magnification is explicit and metrics retain physical units. Optional animation
uses up to 60 actual FEM timestamps; playback speed is illustrative and can
undersample high frequencies. It is not a separate simulation or interpolated mock.
Plots display at most 2001 actual samples, while diagnostics/integrals use all steps.

## Bounded engineering reports

`vibra.io.transient_report.transient_report(model, config, result, max_samples=1001)`
exports full model/configuration, original exact load definitions, selected
response histories, sampled right/left forcing, support reactions, energy histories,
full-grid numerical diagnostics, warnings and assumptions. It does not duplicate
all global field arrays. Output includes endpoint-preserving uniform index selection
and explicit exported indices, actual integration step and full/exported counts.

Output is limited to 250000 scalar history values, max_samples in [2,5001] and
25 MB JSON. Channel count can reduce the actual sample count. Original sampled
forcing is retained exactly for reproducibility. Output decimation never changes
integration or recomputes energy on a coarse grid; it can miss extrema, so use the
full Python result for detailed studies. These safeguards avoid unnecessarily
large browser downloads while preserving complete inputs and full-grid diagnostics.

## Independent verification

Run `uv run pytest` and `uv run vibra-verify-transient`. The CLI writes
`artifacts/transient-verification.json` and exits nonzero if any benchmark fails.
The committed [reference report](results/transient-verification.json) records
actual inputs/errors, separate series/time/spatial convergence and check outcomes.

- One free transverse DOF in a guided beam provides independently known
  m = 156ρAL/420, k = 12EI/L³, without reading reference values out of assembled K/M.
  Exact undamped/damped free responses and forced cosine response exercise initial
  acceleration, displacement/velocity/acceleration and damping.
- Delayed steps and rectangular pulses are compared with closed-form step-response
  superposition. Half-sine pulses have an independent continuous SDOF solution.
  Sampled forcing is also checked against tight-tolerance SciPy DOP853 integration
  of its continuous piecewise-linear interpolant.
- Constant load with equilibrium initial displacement stays static; zero force/state
  remains zero. Tests recover the initial support inertial shear 54/156 of the
  guided-beam tip force, independently confirming consistent-mass support coupling.
- A uniform continuous cantilever under a 1 N, 40 ms half-sine tip pulse supplies
  the spatial benchmark. Exact roots satisfy cosh(β)cos(β) = −1. Eigenfunctions
  normalized to unit tip displacement have modal mass ρAL/4; closed-form scalar
  pulse responses are summed over 128 continuum bending modes. No FEM matrices
  or FEM eigenvectors enter this reference. A 96/128-mode comparison estimates
  series truncation separately (about 1.58×10⁻⁸ of peak response).

The normalization and modal expansion are standard continuous Euler–Bernoulli
beam results; see R. D. Blevins, *Formulas for Natural Frequency and Mode Shape*,
and L. Meirovitch, *Fundamentals of Vibrations*. The time integration formulation
is the average-acceleration Newmark scheme, also described in K. J. Bathe,
*Finite Element Procedures*.

Acceptance criteria distinguish accuracy and algebraic consistency:

| Check | Criterion |
| --- | --- |
| Free SDOF final refinement, h=62.5 μs over 0.2 s | max displacement error / reference peak <5×10⁻⁴ |
| Time-step halving | successive error ratio between 3.5 and 4.5 |
| Damped SDOF, h=100 μs | max displacement error / initial amplitude <10⁻³ |
| Forced SDOF, h=100 μs | max displacement error / reference peak <10⁻³ |
| Benchmark energy balance | relative residual <10⁻⁹ |
| Static initial equilibrium | relative displacement drift <10⁻¹⁰ |
| Continuous-series 96/128-mode difference | relative peak-normalized difference <10⁻⁷ |
| FEM spatial convergence, h=10 μs, T=0.12 s | errors decrease for 2/4/8 elements; final <0.002 |
| Initial constraints and zero state | exactly zero |

At h=100 μs, the benchmark damped/free and forced displacement errors are
approximately 3.64×10⁻⁴ and 1.97×10⁻⁴, respectively. Undamped energy residuals
are near machine precision while the deliberately coarse h=1 ms response has
about 7.9% displacement error over 0.2 s: energy conservation alone is insufficient.
FEM peak-normalized errors decrease from 0.00610 to 0.000647 to 0.0000530 over
2/4/8 elements. More stringent unit comparisons use finer time steps rather than
relaxing numerical assertions near displacement zero crossings.

## Reproducible pulse-decay example

Run `uv run python examples/transient_cantilever.py` to write standalone response,
energy and actual deformation-animation HTML plus a bounded JSON report under
`artifacts/transient-cantilever/`. Regenerate the figure and verification report
with `uv run python scripts/generate_transient_portfolio.py`.

The unchanged steel geometry is 1 m × 20 mm × 20 mm, E=210 GPa, ρ=7850 kg/m³.
With 16 elements, h=0.5 ms, α=2 s⁻¹, β_R=20 μs, and a 1 N half-sine tip pulse
lasting 40 ms, peak tip displacement is approximately **0.199 mm**. At 1 s,
mechanical energy is about **11.9%** of its pulse-end value. The relative discrete
energy-balance residual is approximately **4.6×10⁻¹²**. These are actual solver
outputs, not experimental data or an independent accuracy certification of every
mode in this illustrative mesh/time grid.

![Executed cantilever pulse and energy histories](results/transient-response.svg)

No experimental validation or ANSYS correlation has been performed. Next: verified
FFT/signal diagnostics, followed by richer loads, sparse dynamics and broader NVH cases.
