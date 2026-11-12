# Model, Optimization and Architecture Design

## Operating data contract

Each row describes a 15-minute interval (0.25 hours). Historical timestamps are naive demonstration-factory local times, not a live plant clock.

| Field | Meaning | Bounds / units | Role |
|---|---|---|---|
| machine_load | Load ratio L | 0.25–1.0 | Decision |
| machine_speed | Speed S | 600–1800 rpm | Decision |
| temperature | Ambient temperature T | 20–45 °C | Fixed context, not furnace temperature |
| power_factor | Power factor PF | 0.80–0.99 | Decision, assuming compensation capability |
| production_rate | Throughput R | units/hour | Derived from L, S and T |
| energy_kwh | Interval energy E | kWh/15 minutes | Prediction target / observation |
| timestamp | Interval label | 15-minute spacing | History |
| machine_id | Demonstration machine | SIM-ROLL-01 | Synthetic equipment |

`FEATURES` defines a single feature order. Generation, prediction and optimization share `production()` and `operating_frame()` so production capacity cannot drift between workflows.

## Synthetic process and prediction

```text
R = 45 × L × (S / 1800) × [1 − 0.002 × |T − 32|]
E = 0.25 × [18 + 75 L^1.7 + 22(S/1800)^3 + 0.4R + 0.15(T−30)^2] / PF + epsilon
epsilon ~ Normal(0, 0.55²); energy clipped at zero
```

Load, speed, temperature and power factor are independently sampled. The observations carry chronological timestamps but do not reproduce real production scheduling or temporal dynamics. This is an educational generator, not a physically calibrated digital twin. Power-factor effects, temperature sensitivity, cost coefficients and capacity all need validation against real equipment.

LightGBM learns E_hat=f(L,S,R,T,PF). The first 70% of rows train the regressor. The next 15% calibrate a finite-sample 90% absolute-residual quantile. A symmetric prediction interval uses that radius, with its lower bound clipped at zero. The final 15% evaluate errors and interval coverage. Test data are not used for training or tuning.

Isolation Forest fits training features plus observed energy with contamination=0.025. Flag an anomaly candidate if the forest identifies an outlier, or if |observed E−E_hat| exceeds three times the calibration radius. The residual gate addresses the forest's possible insensitivity to a single extreme energy variable. It is a heuristic, not a fault probability or calibrated diagnostic test. The same rule is used for historical and single-point detection.

## Multi-objective operating optimization

Decision vector x=(L,S,PF). Ambient temperature, tariff p and interval length remain fixed. All objectives use minimization form:

```text
f1(x) = E_hat(x)                                 kWh/15 min
f2(x) = p E_hat(x) + 4(S/1800)^3 + 120(PF−0.80)^2 CU/15 min
f3(x) = −R(x)                                    units/hour
```

The second objective includes simulated wear and compensation costs, so it is not merely a constant multiple of energy. It is a fixed-scenario operating choice, not time-of-use scheduling. CU denotes illustrative currency units. No equipment is controlled.

Constraints use pymoo's G≤0 convention:

```text
R_min − R(x) ≤ 0
E_hat(x) − E_max ≤ 0
0.25 ≤ L ≤ 1
600 ≤ S ≤ 1800
0.80 ≤ PF ≤ 0.99
```

Minimum production prevents shutdown from becoming the trivial energy optimum. Production is derived rather than independently set. Fixing ambient temperature prevents free improvements by inventing a cooler environment. The energy cap constrains the prediction mean; actual consumption can exceed it. Robust optimization or upper-interval constraints are future extensions.

Default NSGA-II settings are population 80, 70 generations and seed 42. The returned solutions are approximate and non-dominated in three objectives. Tree predictions are piecewise constant, so clusters can occur. Neither finite-budget convergence nor global optimality is guaranteed. For research, compare seeds, search budgets and surrogate uncertainty.

## Recommendation, presets and reference comparison

Normalize each objective over the final front using (f−min)/(max−min), replacing zero spans with 1e-9. Normalize nonnegative preferences to sum to one. Recommend the candidate minimizing sqrt(sum(weight × normalized_objective²)). Weights rank the final front; they do not change the search objectives. Scores depend on the current front and are not comparable across separate scenarios. Ties use the first returned candidate.

Three frontend presets populate the same API contract:

| Preset | Minimum production | Energy limit | Preferences: energy/cost/output |
|---|---:|---:|---|
| Balanced production | 12 u/h | 50 kWh | 1 / 1 / 1 |
| Energy-conscious shift | 15 u/h | 30 kWh | 3 / 2 / 1 |
| High-output shift | 30 u/h | 45 kWh | 1 / 1 / 3 |

All presets initially use 32 °C and a tariff of 0.8 CU/kWh. Editing an input marks the scenario as custom and invalidates old results. Inputs are disabled while their search runs.

The reference point uses load 0.7, speed 1200 and PF 0.9 under the same temperature/tariff. It is evaluated through the same model and cost function as candidates, then marked feasible or outside current constraints. The comparison shows energy, total cost and production deltas together. It never asserts an equal-output comparison or measured savings.

Three chart projections help explore all objective pairs. Marker size encodes the remaining objective. Two-dimensional overlap does not imply dominance. A gold star marks the recommendation; a purple diamond marks another selection. Candidate rows can be sorted, selected and exported. JSON reports include scenario settings, complete results, the reference, current selection, recipe identifier, seed and elapsed time. The recipe identifier is not an artifact checksum.

## Measured UCI steel forecast

Target y_t is energy in interval t. Inputs are calendar hour/minute/weekday, y_(t−1), y_(t−4), y_(t−96), the mean of the preceding 96 intervals and previous lagging power factor. Rolling energy is shifted before aggregation. Target-interval energy, CO₂ and reactive power are excluded as potential target proxies.

Timestamps must be unique and exactly 15 minutes apart. After dropping the initial 96 rows without history, use a chronological 80/20 split. Previous observed test readings become available for subsequent predictions; this is rolling one-step evaluation, not a 48-hour open-loop forecast. The model is not retrained on the test set. Persistence baseline: y_hat_t=y_(t−1). The original CSV SHA-256 is stored in the metrics artifact.

The real dataset has no machine speed or production rate, so it does not validate the operating optimizer.

## Engineering and state management

FastAPI handles routing, schemas and lifecycle; the service combines predictions and history; data/models/optimizer modules implement the algorithms. React uses `/api`, and FastAPI serves the production build. There are no remote runtime fonts or hardware dependencies.

The React workspace provider retains prediction inputs/results, optimization inputs/results and history navigation when pages unmount. An in-flight optimization can finish after navigation and still update the shared workspace. Full reload starts a new session. Hash-based routes support direct links and browser navigation. Source data and trained models persist on disk; interactive runs are not written to a database.

## PostgreSQL and Django REST Framework extension

| Table | Fields | Constraints / indexes |
|---|---|---|
| machines | id, name, machine_type, site_id, status | Primary key |
| readings | id, machine_id, timestamp, interval_minutes, load, speed, temperature, power_factor, production_rate, energy_kwh, source | Unique(machine_id,timestamp), bounds, time index |
| model_versions | id, artifact_path, data_hash, feature_schema, train_end, metrics_json, created_at | Explicit model/data provenance |
| optimization_runs | id, machine_id, model_version_id, request_json, status, seed, started_at, finished_at | Task status index |
| pareto_solutions | id, run_id, variables_json, energy_kwh, cost, production_rate, score, recommended | Foreign key and recommendation integrity |

Introduce a repository layer to replace in-memory CSV reads. Use migrations. Algorithm modules do not need an ORM. If DRF is mandatory, replace Pydantic with serializers and routers with views while preserving the algorithm layer and frontend API contract. Long-running jobs need a queue, task status endpoints and versioned result persistence. Authentication, audits, hardware controls, concurrency limits and industrial safety/quality constraints remain outside this coursework prototype.

## V1.2 dynamic ANN and feedback control

The dedicated Neural Control workspace adds a three-hidden-layer dynamics model, simulated plant and receding-horizon MPC feedback loop. This is separate from the static operating optimizer above. The controller executes an action, uses the newly measured simulated state and solves again. Hard actuator/slew limits are enforced; energy and temperature feasibility are checked in prediction and observed violations are reported. Full equations, architecture, trajectory splits, tree-model comparison and control metrics are in [NEURAL-CONTROL.md](NEURAL-CONTROL.md).
