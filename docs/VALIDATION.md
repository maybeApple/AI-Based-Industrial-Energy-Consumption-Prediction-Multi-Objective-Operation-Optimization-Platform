# Validation Record · V1.1

Date: 2026-10-06. Environment: Windows, Python 3.13.9, Node.js 24.14.0. Python package versions are recorded in requirements-lock.txt; frontend versions are recorded in package-lock.json.

## Backend

`python -m pytest -q`: **16 passed**.

Coverage includes health and historical pagination/filtering; prediction target isolation; extreme-energy anomaly detection; bounds, extra fields, invalid weights, non-finite inputs and search budgets; feasible decision bounds and objective constraints; three-dimensional Pareto non-dominance; independent recommendation-score recalculation; production/cost equation consistency; seed reproducibility; infeasible scenarios; real-data split boundaries and persistence comparison.

V1.1 also validates reference energy/cost/production consistency, elapsed time and timestamp metadata, and an infeasible reference under a feasible high-output scenario. A reference outside constraints must not be labeled feasible.

There is one upstream Starlette deprecation warning for the test client's httpx integration. It does not affect these assertions or the normal application request path.

## Frontend and browser

`npm run build`: passed. No dependencies were added for V1.1. The previous compatible dependency update reported zero npm audit vulnerabilities at the time it ran; no new audit claim is made for this iteration.

`python scripts/browser_smoke.py`: **passed**, browser_errors=[] using headless Microsoft Edge.

- English HTML language metadata and no CJK text in rendered pages, including error states.
- Overview data/model readiness and prediction with a 499 kWh observation flagged for review.
- Prediction inputs/results preserved across page navigation.
- Scenario preset values and weights; invalidation after changing constraints.
- Optimization completes correctly even after switching away and back.
- Three Pareto projections, point selection and return to recommendation.
- CSV download and JSON report content validation, including seed, full front and reference.
- Candidate sorting by descending production rate.
- Reference comparison rendering.
- No page-level horizontal overflow on all five pages at 390 px, including populated optimization results.
- Infeasible search response and zero-weight input error in English.
- History pagination, retained page selection and anomaly filtering.
- Measured-data benchmark page and explicit network-failure message.
- Direct `/#optimize` navigation.

Screenshots in `screenshots/` were regenerated in English. Desktop overview, Pareto and mobile optimization captures were inspected for layout.

## Model metrics (unchanged training artifacts)

| Workflow | MAE kWh | RMSE kWh | R² | Baseline MAE kWh |
|---|---:|---:|---:|---:|
| Synthetic operations | 0.544911 | 0.688912 | 0.990760 | 5.949622, training mean |
| Measured UCI steel | 4.277107 | 8.698103 | 0.923235 | 5.482202, persistence |

Synthetic test size: 900; nominal 90% interval test coverage: 0.894444. UCI raw rows: 35,040; feature-complete train/test sizes: 27,955/6,989. Training ends 2018-10-20 04:30; testing begins at 04:45.

These are not plant energy-savings experiments or proof of real-world control effectiveness. No concurrency load test, hardware connection, Linux/macOS verification, database integration or production deployment was performed.

## V1.2 neural-control validation (2026-10-07)

Backend suite: **27 passed** after adding dynamic neural-control tests. Neural network: 11–96–64–32–6, 9,638 parameters, 207 training epochs, 7,200 training and 1,800 independent-trajectory test transitions. ANN energy/production/temperature one-step MAE: 0.09085 kWh / 0.08841 units/h / 0.05039 °C. Same-test LightGBM energy/production MAE: 0.28319 kWh / 0.31597 units/h. Five-step recursive ANN energy/production/temperature MAE: 0.10021 / 0.10922 / 0.11704.

Default feedback run: tracking MAE 0.44627 versus fixed-command 7.15581 units/h; 97.22% of intervals within 10% of target; zero observed energy/temperature violations. Output totals differ between branches, so no equal-output savings claim is made. Same random seed reproduces the measured trace; the report's artifact hash records the trained model used.

`browser_neural.py`: passed with no page script errors. Covers direct control-page access, full feedback simulation, export content, measurement playback, navigation retention, single-step execution, changed setpoint, immediate disturbance, reset, predicted-infeasible reporting, English content and mobile layout after responsive charts settle. Desktop and mobile control screenshots were inspected. Existing browser acceptance also passes.

No real industrial hardware, formal stability proof, multi-user load test or plant calibration is included. See NEURAL-CONTROL.md for precise scope.

Multi-seed default-scenario evaluation (7, 42, 99): ANN-MPC tracking MAE was 0.40988, 0.44627 and 0.41059 units/h respectively; fixed-command MAE was 7.09539, 7.15581 and 7.08872. All three ANN runs had zero observed energy/temperature violations. This is a small simulation robustness check, not a general stability result. Exact summaries and the model hash are saved in artifacts/industrial/control_evaluation.json; regenerate with python -m scripts.evaluate_control.

## 3D Pareto and same-output benchmark

The production frontend build and 29 backend tests passed. The API tests cover exact output matching, adherence to the energy cap, repeatability, reference validation, and preserving the same Pareto front when only the reference changes. Headless Edge acceptance covers point selection by mouse and keyboard, rotation, zoom, view reset, English UI, mobile layout, and full CSV/JSON exports.

In the default balanced simulation, both reference and alternative deliver 21.00 units/hour. Modeled energy per 15 minutes changes from 20.66 to 18.86 kWh, and total modeled cost from 18.92 to 18.05 CU. These are estimates from the operating simulation. The real steel forecasting benchmark does not establish operational savings.
