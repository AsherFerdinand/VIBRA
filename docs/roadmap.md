# Development roadmap

The first release implements planar Euler–Bernoulli frames, static/modal solvers,
a cantilever workbench, analytical convergence, and a separate SDOF model.
Version 0.2 adds verified FEM harmonic response, proportional viscous damping,
complex phasor reports and an interactive harmonic workspace. It does
not attempt a general-purpose production CAE system.

Next milestones, in order:

1. **V3 — FEM transient dynamics:** initial-condition projection, forcing histories,
   verified time integration and modal superposition.
2. **V4 — Signal processing:** FFT amplitude conventions, windowing, filters and
   diagnostics verified against known signals.
3. **V5 — Automotive NVH studies:** documented illustrative models with clear
   assumptions and reproducible inputs.
4. **V6 — FEM scale and capabilities:** sparse assembly, distributed loads,
   nonzero supports, releases, shear-flexible elements and richer meshes.
5. **V7 — Independent CAE references:** reproducible comparisons, potentially with
   ANSYS Mechanical, supplementing analytical checks. No such comparison exists yet.
6. **V8 — Advanced interface:** persistent projects, result management and, if
   justified, FastAPI plus React/TypeScript. Keep numerical code independent.

Do not introduce complex 3D FEM before the added formulations have independent
verification. Experimental validation requires actual physical measurements and
is a separate activity from solver-to-solver comparison.
