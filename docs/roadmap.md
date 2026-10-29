# Development roadmap

The first release implements planar Euler–Bernoulli frames, static/modal solvers,
a cantilever workbench, analytical convergence, and a separate SDOF model. It does
not attempt a general-purpose production CAE system.

Next milestones, in order:

1. **V2 — FEM harmonic response:** proportional damping, complex dynamic stiffness,
   frequency-response functions, and independent multi-DOF benchmarks. SDOF harmonic
   excitation exists now; beam harmonic response does not.
2. **V3 — FEM transient dynamics:** initial-condition projection, forcing histories,
   verified time integration and modal superposition.
3. **V4 — Signal processing:** FFT amplitude conventions, windowing, filters and
   diagnostics verified against known signals.
4. **V5 — Automotive NVH studies:** documented illustrative models with clear
   assumptions and reproducible inputs.
5. **V6 — FEM scale and capabilities:** sparse assembly, distributed loads,
   nonzero supports, releases, shear-flexible elements and richer meshes.
6. **V7 — Independent CAE references:** reproducible comparisons, potentially with
   ANSYS Mechanical, supplementing analytical checks. No such comparison exists yet.
7. **V8 — Advanced interface:** persistent projects, result management and, if
   justified, FastAPI plus React/TypeScript. Keep numerical code independent.

Do not introduce complex 3D FEM before the added formulations have independent
verification. Experimental validation requires actual physical measurements and
is a separate activity from solver-to-solver comparison.
