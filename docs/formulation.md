# Beam FEM formulation

VIBRA uses a prismatic, two-node Euler–Bernoulli planar frame element. The linear
model combines axial extension and in-plane bending. It assumes small strain,
small displacement, slender members, rigid joints and linear elastic isotropic
material properties. All model values use SI units. The bending axis is global z
when the member lies along global x. The rectangular section has A = bh and
I = bh³/12, with h in the plane of bending.

## Element interpolation and matrices

Local DOFs are d = [u₁, v₁, θ₁, u₂, v₂, θ₂]ᵀ. Positive θ is counterclockwise.
Axial displacement uses linear shape functions. Transverse displacement uses
cubic Hermite shape functions with ξ = x/L:

```
N₁ = 1 − 3ξ² + 2ξ³       N₂ = L(ξ − 2ξ² + ξ³)
N₃ = 3ξ² − 2ξ³           N₄ = L(−ξ² + ξ³)
v(x) = N₁v₁ + N₂θ₁ + N₃v₂ + N₄θ₂
```

The stiffness follows from the strain energy
½∫[EA(u′)² + EI(v″)²] dx. In the full local DOF ordering:

```
          [ EA/L      0          0      −EA/L      0          0    ]
          [ 0      12EI/L³    6EI/L²      0     −12EI/L³    6EI/L² ]
K_local = [ 0       6EI/L²    4EI/L       0      −6EI/L²    2EI/L  ]
          [−EA/L      0          0       EA/L      0          0    ]
          [ 0     −12EI/L³   −6EI/L²      0      12EI/L³   −6EI/L² ]
          [ 0       6EI/L²    2EI/L       0      −6EI/L²    4EI/L  ]
```

The consistent mass follows from ½∫ρA(u̇² + v̇²) dx using the same shape
functions. Its axial block for [u₁,u₂] is (ρAL/6)[[2,1],[1,2]]. Its bending
block for [v₁,θ₁,v₂,θ₂] is:

```
                   [156    22L     54    −13L ]
M_b = (ρAL/420) ×   [22L    4L²    13L    −3L² ]
                   [54     13L    156    −22L ]
                   [−13L  −3L²   −22L     4L² ]
```

Translation/rotation entries have kg, kg m and kg m² units as appropriate to
the associated generalized coordinates. Rotational DOF coupling comes from the
transverse interpolation; cross-sectional rotary inertia is **not** included.
No diagonal mass augmentation or regularization is used.

## Orientation and assembly

For c = (x₂−x₁)/L and s = (y₂−y₁)/L, the nodal transformation is
R = [[c,s,0],[−s,c,0],[0,0,1]]. With T = diag(R,R), d_local = T d_global,
K_global = TᵀK_local T and M_global = TᵀM_local T.

Global DOFs are ordered by ascending node identifier, then UX, UY, RZ. Elements
are assembled in ascending identifier order into dense NumPy matrices. A separate
assembly object exposes matrices, free/fixed indices and element maps, allowing a
future sparse backend without coupling it to the UI.

The model rejects duplicate identifiers, reversed duplicate members, invalid
references, self-connections, zero lengths, disconnected components and unused
nodes. A single connected frame is supported, including oriented members.

## Boundary conditions and static results

Only prescribed **zero** UX/UY/RZ values are currently supported. A fixed support
is all three constraints at a node; individual zero constraints can model rollers
and pins. Internal hinges/releases, elastic supports, nonzero imposed displacement,
contact and multipoint constraints are unsupported. No penalty stiffness is used.

Partitioning into free f and constrained c gives Kff uf = Ff with uc = 0.
The solve uses diagonal stiffness equilibration, Dii = 1/√Kff,ii. Positive
definiteness is checked on D Kff D with a dimensionless relative eigenvalue
threshold of 10⁻¹². This detects insufficient supports and unresolved mechanisms;
extreme slenderness or over-refined meshes can also trigger the conditioning guard.
The threshold is an explicit AnalysisConfig setting, not a correction to stiffness.

Reactions are (Ku−F)c; free reaction entries are zero. Local element resisting end
forces are q = K_local T d. These contain axial forces, shears and end moments.
With no distributed load, the internal diagrams along a member are
N(x) = −q₀, V(x) = q₁ and M(x) = −q₂ + q₁x. End actions and section forces thus
use different signs at the left end. The UI moment diagram is for the generated
straight chain; general frames expose per-member local end forces in the API.

## Modal analysis

The solver solves Kff φ = λ Mff φ using SciPy's symmetric generalized `eigh`
after the same equilibration. λ = ω², f = ω/(2π). Nonpositive eigenvalues are
errors, not clipped modes. The requested count must not exceed free DOFs.

Returned full vectors are mass-normalized: φᵀMφ = I, with zero constrained
components. Their translational components do not represent physical response
amplitude. Signs are arbitrary; the largest absolute component is made positive
for repeatable display. Repeated eigenvalues can still span different bases.

A mode's axial strain energy divided by total strain energy classifies it as
axial (>0.9), bending (<0.1), or coupled. This cleanly distinguishes modes of a
straight cantilever; general frames may have coupled behavior. Continuum bending
benchmarks must be compared with **bending** modes, not blindly with mode indices.
Plots use Hermite interpolation and explicit display magnification. Modal plots
scale peak nodal translation to a chosen fraction of member length.

## Analytical references

The standard virtual-work and consistent-mass formulation is described in K. J.
Bathe, *Finite Element Procedures*, and R. D. Cook et al., *Concepts and Applications
of Finite Element Analysis*. Cantilever roots satisfy cosh(β)cos(β) = −1. VIBRA
independently obtains roots using the stable equation cos(β) + sech(β) = 0.

Tip deflection and slope for transverse force F:
δ = FL³/(3EI), θ = FL²/(2EI).
Bending frequencies: ωₙ = βₙ²√(EI/(ρAL⁴)).
The first axial continuum frequency is √(E/ρ)/(4L).

This implementation does not use an external CAE result as numerical truth.
