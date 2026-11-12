# Deep ANN-Based Closed-Loop Control · V1.2

## What is implemented

V1.2 controls a **dynamic simulated process** through a trained deep artificial neural network and a receding-horizon model predictive controller. Open `http://127.0.0.1:8000/#control`.

The complete loop is:

```text
Measured state + current disturbances + candidate commands
                         ↓
           Trained deep ANN predicts next states
                         ↓
       MPC evaluates bounded future command sequences
                         ↓
             Execute only the first selected command
                         ↓
       Dynamic simulator returns the actual next state
                         ↓
             Use that measurement in the next solve
```

This is ANN-model-based feedback control. The neural network is the prediction model, while MPC selects actions. It is not a directly learned neural policy or reinforcement-learning agent. The existing LightGBM forecasting, anomaly detection and NSGA-II Pareto tools remain separate application modules.

## Neural network

Architecture: **11 → 96 → 64 → 32 → 6**, with three fully connected ReLU hidden layers, linear regression outputs, Adam training and 9,638 learned parameters. Implemented with the existing scikit-learn MLPRegressor runtime; no additional neural framework, GPU or cloud API is needed.

Inputs:

- Current measured load, speed, power factor, process temperature, production rate and interval energy (6).
- Candidate load, speed and power-factor commands (3).
- Measured ambient temperature and material factor (2).

Outputs: the next values of the six measured state variables. Current energy is a past observation when predicting **next** interval energy, not the target observation itself. The static same-interval LightGBM model still excludes observed target energy from its features.

Input and output standardization are fitted on the training trajectories. The target transformer is inverted before physical scoring. Broad physical state ranges clip impossible predictions; the user-configured process limits are not used as prediction clipping bounds.

## Training and evaluation

`plant.transition_dataset()` creates 180 independent trajectories, each 50 intervals long: 9,000 transitions. The first 144 trajectories (7,200 transitions) train the model; the final 36 (1,800 transitions) are held out whole. Internal early stopping uses 12% of the training transitions. Recorded test trajectories are never used for model fitting or early stopping. Dataset seed: 17; network seed: 42.

The generator includes different initial conditions, actuator lag, thermal memory, production memory, energy memory, changing commands, ambient/material variation and small process noise. The values are generated independently from the UCI steel dataset.

Held-out one-step errors:

| Output MAE | Deep ANN | LightGBM on the same split | Persistence |
|---|---:|---:|---:|
| Interval energy, kWh | 0.09085 | 0.28319 | 1.80851 |
| Production rate, units/h | 0.08841 | 0.31597 | 2.37154 |
| Process temperature, °C | 0.05039 | 0.10636 | 0.70985 |

These values measure identification of the synthetic process, not field accuracy. The LightGBM comparison is a multi-output tree benchmark using the same training/test trajectories; it is not substituted inside the ANN controller.

Recursive rollout validation uses 1,656 overlapping windows from held-out trajectories. The ANN feeds its own predicted state into the next prediction for five intervals, using the held-out recorded command and exogenous-input sequence. No measured state is injected inside a window. At five steps, MAE is 0.10021 kWh for energy, 0.10922 units/h for production and 0.11704 °C for temperature. These windows are overlapping diagnostics, not 1,656 independent experiments.

Training commands:

```powershell
.\.venv\Scripts\python.exe -m scripts.train_neural
```

The standard `scripts.prepare_industrial` and `setup.ps1` also train this network. Restart the API after retraining. Files:

- `data/industrial/dynamic_transitions.csv`: training/test trajectory data.
- `artifacts/industrial/neural_dynamics.joblib`: network, scalers, version and report.
- `artifacts/industrial/neural_metrics.json`: validation metrics, loss curve and data hash.
- `artifacts/industrial/control_default_run.json`: reference default closed-loop experiment.

Missing ANN artifacts are trained locally on startup. Control reports include the actual model-file SHA-256.

## Dynamic simulated plant

One interval equals 15 minutes. States are load L, speed S, PF, process temperature T, production R and energy E. Commands are uL, uS and uPF. Ambient A and material factor M are measured external inputs.

```text
L_next  = L + 0.50 (uL − L)
S_next  = S + 0.35 (uS − S)
PF_next = PF + 0.60 (uPF − PF)
T_next  = T + 0.12 [A + 14 L_next^1.4 + 8(S_next/1800)^2 − T]
R_equilibrium = 45 L_next (S_next/1800) M × clip(1 − 0.004 max(T_next−40,0), 0.75, 1)
R_next = 0.45 R + 0.55 R_equilibrium
E_demand = 0.25 [18 + 75 L_next^1.7 + 22(S_next/1800)^3 + 0.4 R_next + 0.04(T_next−35)^2] / PF_next
E_next = 0.20 E + 0.80 E_demand
```

Small seeded process noise is included in batch experiments. Interactive single steps use deterministic plant transitions for clarity. Broad physical bounds are applied in the plant. This is an educational process with abstract units; it is not calibrated to steel production or equipment thermodynamics.

Only the simulator calls these equations during execution. `choose_action()` rolls out the **trained ANN** when selecting commands. In particular, the controller does not optimize using the known simulator equations and merely display neural predictions afterward.

## MPC algorithm and limits

Default horizon: 5 intervals. Default search: 128 candidates × 3 cross-entropy rounds. Candidate sequences are sampled, projected into command/slew bounds, recursively evaluated through the ANN and refined using the best-performing candidates. The prior winning sequence is shifted as a warm start.

Per-step objective includes:

- Squared normalized production tracking error, weight 25.
- Additional shortage penalty, weight 30.
- Predicted energy and illustrative electricity/wear/compensation cost.
- Command-change penalty.
- Strong squared penalties for predicted energy and temperature limit violations.

When any candidate satisfies predicted limits over the entire horizon, choose the best such candidate. Otherwise choose the lowest total-penalty candidate and explicitly report that no feasible predicted horizon was found. This is a finite-budget sampling search, not proof of optimality or infeasibility.

Hard command bounds:

| Command | Bounds | Maximum change per interval |
|---|---|---|
| Load | 0.25–1.0 | 0.12 |
| Speed | 600–1800 rpm | 180 rpm |
| Power factor | 0.80–0.99 | 0.03 |

Energy and temperature constraints act on predictions and can be violated by the actual simulated plant. Observed violations are counted, including initial transients. No formal stability guarantee or safety certificate is claimed. Search budgets and request bounds are validated by the API.

## Experiment and interactive operation

**Closed-loop experiment:** an accelerated, fully executed feedback run, with charts and playback of measured states. Playback is presentation of an already completed run; it does not execute the control algorithm again.

Default experiment: 36 intervals. Target is 22 units/h initially and changes to 28 after interval 10. After interval 20, material factor becomes 0.82, ambient rises by 3 °C and tariff rises by 35%. The controller sees the new target and disturbance only when they occur and holds current external inputs constant inside its prediction horizon.

The fixed-command comparison uses the same initial state, disturbance sequence and process-noise sequence. Its commands remain at load 0.7, speed 1200 rpm and PF 0.9. Both branches are simulated independently and actually execute their own commands.

Default result, seed 42:

| Metric | ANN MPC | Fixed commands |
|---|---:|---:|
| Tracking MAE, units/h | 0.44627 | 7.15581 |
| Time within 10% of target | 97.22% | 27.78% |
| Output, units | 233.07187 | 172.59767 |
| Energy, kWh | 895.73350 | 753.91138 |
| Energy / temperature violations | 0 / 0 | 0 / 0 |

The controller produces more output and consumes more total energy. These are tracking results; they must not be presented as an equal-output energy-savings experiment.

**Interactive control:** the user changes the setpoint, optionally applies a disturbance, and clicks `Advance one control step`. The server predicts actions through the ANN, executes the first move in the dynamic plant and returns a measured state. The browser submits that measurement and the applied command for the following step. Reset returns to the common initial condition. Inputs and results survive page changes in the current browser session.

## API

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/control/model` | Architecture, errors, training report and artifact hash |
| POST | `/api/control/run` | Full accelerated closed-loop experiment and comparison |
| POST | `/api/control/step` | One closed-loop action, prediction and plant measurement |

Default full experiment request: `{}`. Example single step:

```json
{"state":[0.7,1200,0.9,40,21,21],"previous_command":[0.7,1200,0.9],"target":28,"ambient":30,"material_factor":1,"tariff":0.8}
```

The response includes `action`, `predicted_next_state` and `measured_next_state`. Submit the latter two relevant feedback values (measured state and applied action) to the next request. Endpoints are stateless and control only the simulator. No hardware is connected.

## Verification and references

Backend tests verify ANN architecture/independent holdout data, actual feedback progression, ANN use during search, actuator/slew bounds, default tracking improvement, seeded reproducibility, disturbance-sensitive actions, infeasible limit reporting and request validation. Browser checks cover both modes, parameter changes, exports, page-state retention, playback, reset, English content and mobile layouts.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/browser_smoke.py
.\.venv\Scripts\python.exe scripts/browser_neural.py
```

Official references: [scikit-learn MLPRegressor](https://scikit-learn.org/stable/modules/generated/sklearn.neural_network.MLPRegressor.html), [MathWorks introduction to model predictive control](https://www.mathworks.com/help/mpc/gs/what-is-mpc.html). This application implements its own sampling controller; it does not depend on MATLAB.
