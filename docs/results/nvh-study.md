# Automotive NVH study — equivalent motor-interface support rail

## Objective and assumptions

Investigate two bare slender rails under prescribed forces. This is not a production bracket or installed motor/vehicle model.

- Equivalent straight cantilever support rail, not a solid/shell or production bracket.
- Fixed root approximates a rigid attachment; no bolts, contact or mount/base compliance.
- Linear elastic in-plane Euler–Bernoulli frame; no shear deformation or rotary section inertia.
- Bare rail mass only; motor inertia/rigid-body coupling and vehicle structure omitted.
- All interface forces are illustrative assumptions, not measured motor loads.
- Dynamics perturb static equilibrium; linear superposition without stress stiffening.
- Same Rayleigh coefficients across designs; modal damping ratios may change with frequency.
- Harmonic force amplitude is peak, constant over frequency; order frequency = order*rpm/60.
- Pulse and harmonic analyses are separate load cases, not a single operating event.
- Finite-record PSD peaks are reference comparisons, not experimental modal identification.
- No strength/fatigue, acoustic, experimental, ANSYS or vehicle-performance claims.

## Inputs (SI)

| Input | Baseline A | Modified B |
| --- | --- | --- |
| Length [m] | 0.45 | 0.45 |
| Section width [m] | 0.025 | 0.025 |
| Bending depth [m] | 0.012 | 0.015 |
| Young modulus [Pa] | 2.1e+11 | 2.1e+11 |
| Density [kg/m³] | 7850 | 7850 |

Both use 8 frame elements; fixed root ux=uy=rz=0 and free tip.
Static tip force -200 N; dynamic peak force 2 N.
Excitation x/L=1; monitor x/L=1.
Order 2 × 1800 rpm / 60 = 60 Hz; rotation alone is 30 Hz.
Rayleigh alpha=4 1/s, beta=8e-05 s.
Pulse -20 N half-sine, width 0.01 s; duration 0.4 s, dt=0.0001 s.

## Engineering comparison

| Quantity | Baseline A | Modified B |
| --- | --- | --- |
| Rail mass [kg] | 1.05975 | 1.3246875 |
| Maximum static translation [mm] | 8.03571429 | 4.11428571 |
| First natural frequency [Hz] | 49.5121976 | 61.890247 |
| Harmonic amplitude at 60 Hz [mm] | 0.163288507 | 0.553351211 |
| Operating phase [deg] | -174.31427 | -33.6429174 |
| Sampled harmonic peak [mm] | 2.05368144 | 0.959481342 |
| Sampled peak frequency [Hz] | 49.6 | 62 |
| Transient monitored peak displacement [mm] | 1.18422513 | 0.664105346 |
| Transient peak velocity [m/s] | 0.354352534 | 0.248439334 |
| Transient peak acceleration [m/s²] | 113.320276 | 91.8311051 |
| Post-pulse displacement RMS [mm] | 0.372281039 | 0.170205896 |
| Post-pulse acceleration RMS [m/s²] | 36.015998 | 25.7508687 |
| Maximum absolute end moment [N m] | 90 | 90 |
| Relative energy balance residual | 5.39139842e-13 | 5.16343176e-13 |

### Baseline A

Root [Fx,Fy,Mz] = (0.0, 200.00000000004002, 90.0000000000012) N/N m; equilibrium residual = (0.0, 4.001776687800884e-11, 1.1937117960769683e-12) N/N m.
JSON contains local [N1,V1,M1,N2,V2,M2] end actions. Section moment M(x)=-M1+V1*x differs from support-reaction sign.

| Mode | Frequency [Hz] | Family |
| --- | --- | --- |
| 1 | 49.5121976 | bending |
| 2 | 310.31181 | bending |
| 3 | 869.341031 | bending |
| 4 | 1706.33977 | bending |
| 5 | 2830.68135 | bending |
| 6 | 2878.05923 | axial |

Signal fs=10000 Hz, df=2.63088661 Hz, N=3801, span=0.38 s.
Displacement/acceleration dominant bins: 49.98684556695606 / 49.98684556695606 Hz.
Finite duration, damping and leakage affect peaks; these are not measured modal IDs.
Source warnings: Not all FEM modes have 20 steps/cycle; refine dt for the response band of interest.

### Deeper section B

Root [Fx,Fy,Mz] = (0.0, 200.00000000025284, 90.00000000008876) N/N m; equilibrium residual = (0.0, 2.5283952709287405e-10, 8.876099855115172e-11) N/N m.
JSON contains local [N1,V1,M1,N2,V2,M2] end actions. Section moment M(x)=-M1+V1*x differs from support-reaction sign.

| Mode | Frequency [Hz] | Family |
| --- | --- | --- |
| 1 | 61.890247 | bending |
| 2 | 387.889762 | bending |
| 3 | 1086.67629 | bending |
| 4 | 2132.92471 | bending |
| 5 | 2878.05923 | axial |
| 6 | 3538.35169 | bending |

Signal fs=10000 Hz, df=2.63088661 Hz, N=3801, span=0.38 s.
Displacement/acceleration dominant bins: 63.141278610891874 / 63.141278610891874 Hz.
Finite duration, damping and leakage affect peaks; these are not measured modal IDs.
Source warnings: Not all FEM modes have 20 steps/cycle; refine dt for the response band of interest.

## Controlled one-at-a-time variations

| Input | Factor | f1 ratio | Static tip ratio | Mass ratio |
| --- | --- | --- | --- | --- |
| length | 0.9 | 1.234568 | 0.729 | 0.9 |
| length | 1.1 | 0.8264463 | 1.331 | 1.1 |
| width | 0.9 | 1 | 1.111111 | 0.9 |
| width | 1.1 | 1 | 0.9090909 | 1.1 |
| height | 0.9 | 0.9 | 1.371742 | 0.9 |
| height | 1.1 | 1.1 | 0.7513148 | 1.1 |
| young_modulus | 0.9 | 0.9486833 | 1.111111 | 1 |
| young_modulus | 1.1 | 1.048809 | 0.9090909 | 1 |
| density | 0.9 | 1.054093 | 1 | 0.9 |
| density | 1.1 | 0.9534626 | 1 | 1.1 |

Rectangular bending laws: f1 ∝ h/L²*sqrt(E/rho), static tip deflection ∝ L³/(E*b*h³), mass ∝ rho*b*h*L. Width scales stiffness and mass equally, leaving ideal bending frequencies unchanged.

## Harmonic sensitivities

| Design | Damping factor | Force x/L | Monitor x/L | E factor | Operating [mm] | Sampled max [mm] |
| --- | --- | --- | --- | --- | --- | --- |
| baseline | 0.5 | 1 | 1 | 1 | 0.1638621 | 4.054478 |
| baseline | 1 | 1 | 1 | 1 | 0.1632885 | 2.053681 |
| baseline | 2 | 1 | 1 | 1 | 0.1610539 | 1.030317 |
| baseline | 1 | 0.5 | 1 | 1 | 0.05767368 | 0.6974239 |
| baseline | 1 | 1 | 0.5 | 1 | 0.05767368 | 0.6974239 |
| baseline | 1 | 1 | 1 | 0.9 | 0.1341206 | 2.297185 |
| baseline | 1 | 1 | 1 | 1.1 | 0.2076628 | 1.841168 |
| modified | 0.5 | 1 | 1 | 1 | 0.6310002 | 1.898301 |
| modified | 1 | 1 | 1 | 1 | 0.5533512 | 0.9594813 |
| modified | 2 | 1 | 1 | 1 | 0.3989701 | 0.4817774 |
| modified | 1 | 0.5 | 1 | 1 | 0.1869103 | 0.3258272 |
| modified | 1 | 1 | 0.5 | 1 | 0.1869103 | 0.3258272 |
| modified | 1 | 1 | 1 | 0.9 | 0.7324041 | 1.095064 |
| modified | 1 | 1 | 1 | 1.1 | 0.2418722 | 0.8543862 |

## Convergence and verification

Differences compare full monitored histories at common timestamps with computed fine references, not exact transient truth. Reference-row zero is by construction. Peak values use each run's full time grid.

| Design | Study | Elements | dt [s] | Relative u diff | Relative v diff | Relative a diff |
| --- | --- | --- | --- | --- | --- | --- |
| Baseline A | time | 8 | 0.0001 | 0.001516093 | 0.001575429 | 0.01007987 |
| Baseline A | time | 8 | 5e-05 | 0.0003032488 | 0.000315117 | 0.001201138 |
| Baseline A | time | 8 | 2.5e-05 | 0 | 0 | 0 |
| Baseline A | mesh | 4 | 2.5e-05 | 0.00065358 | 0.0006796658 | 0.001541486 |
| Baseline A | mesh | 8 | 2.5e-05 | 3.916542e-05 | 4.072825e-05 | 0.0001267496 |
| Baseline A | mesh | 16 | 2.5e-05 | 0 | 0 | 0 |
| Deeper section B | time | 8 | 0.0001 | 0.002140408 | 0.002225941 | 0.008968457 |
| Deeper section B | time | 8 | 5e-05 | 0.0004281323 | 0.0004452325 | 0.001196927 |
| Deeper section B | time | 8 | 2.5e-05 | 0 | 0 | 0 |
| Deeper section B | mesh | 4 | 2.5e-05 | 0.0005904092 | 0.0006144082 | 0.000893358 |
| Deeper section B | mesh | 8 | 2.5e-05 | 3.538031e-05 | 3.681751e-05 | 8.754373e-05 |
| Deeper section B | mesh | 16 | 2.5e-05 | 0 | 0 | 0 |

- static_force_moment_equilibrium: PASS.
- static_analytical_cantilever: PASS.
- first_modal_analytical_cantilever: PASS.
- controlled_frequency_scaling: PASS.
- controlled_static_scaling: PASS.
- transient_energy_balance: PASS.
- base_step_monitored_displacement_difference_below_one_percent: PASS.
- selected_mesh_monitored_displacement_difference_below_one_percent: PASS.
- base_step_acceleration_difference_below_five_percent: PASS.
- selected_mesh_acceleration_difference_below_one_percent: PASS.

## Engineering conclusions

B relative to A: mass +25.00%, maximum static displacement -48.80%, first natural frequency +25.00%, harmonic displacement at 60 Hz +238.88%. Higher stiffness can move resonance toward an operating order while reducing static deformation. These load-specific tradeoffs do not establish a universally superior design.

These results concern structural response, not strength, fatigue, sound, production suitability or validated vehicle performance. Motor inertia and mount compliance are absent. Dynamics perturb a statically loaded linear equilibrium; no geometric/prestress effects are included.

Figures and JSON are generated by the reproducible example. No experimental validation or ANSYS correlation is claimed.
