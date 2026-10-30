# Development roadmap

The first release implements planar Euler–Bernoulli frames, static/modal solvers,
a cantilever workbench, analytical convergence, and a separate SDOF model.
Version 0.2 adds verified FEM harmonic response, proportional viscous damping,
complex phasor reports and an interactive harmonic workspace.
Version 0.3 adds verified transient FEM, Newmark average acceleration, time histories,
consistent energy accounting, dynamic reactions and transient visualization.
Version 0.4 adds verified FFT/PSD, vibration metrics, validated CSV input and
FEM-linked signal diagnostics. Version 0.5 adds a reproducible force-driven
equivalent motor-interface support-rail investigation and design comparison. It does
not attempt a general-purpose production CAE system. Version 0.6 adds verified
concentrated motor mass/offset inertia and ground/relative spring-dampers, with a
bare/rigid/isolated installed-system study.

Version 0.7 reorganizes the application into three engineering experiences, with
a shared actual-model viewport, verified beam section stress contours and bounded
mode/complex-harmonic/transient animation.

Version 0.8 adds scenario-first Beginner workflows, deterministic result explanations,
a reproducible simulated spin recording and session-local Light/Dark presentation,
while retaining the complete Advanced workbench and all numerical algorithms.

Next milestones, in order:

1. **Interpretation and measurements:** student feedback on the three-experience workbench,
   controlled measurement/FRF ingestion and mode tracking; independently verify
   prescribed base motion and chassis force paths before installed-system comparisons.
2. **V6 — FEM scale and capabilities:** sparse assembly, distributed loads,
   nonzero supports, releases, shear-flexible elements and richer meshes.
3. **V7 — Independent CAE references:** reproducible comparisons, potentially with
   ANSYS Mechanical, supplementing analytical checks. No such comparison exists yet.
4. **V8 — Advanced interface:** persistent projects, result management and, if
   justified, FastAPI plus React/TypeScript. Keep numerical code independent.

Do not introduce complex 3D FEM before the added formulations have independent
verification. Experimental validation requires actual physical measurements and
is a separate activity from solver-to-solver comparison.

Signal extensions should add verified Welch PSD, cross spectra/FRF estimation,
anti-alias/resampling choices and calibrated measurement ingestion before claiming
measured modal identification or automated health grading.
