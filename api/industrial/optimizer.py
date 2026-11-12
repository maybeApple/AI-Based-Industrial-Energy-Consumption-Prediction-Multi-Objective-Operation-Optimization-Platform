import numpy as np
from time import perf_counter
from datetime import datetime, timezone
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.core.problem import Problem
from pymoo.optimize import minimize
from .data import LOW, HIGH, operating_frame, production, INTERVAL_HOURS


def evaluate(model, x, temperature, tariff):
    frame = operating_frame(x, temperature)
    energy = np.maximum(0, model.predict(frame))
    # Demonstration equipment wear and power-factor compensation costs per interval.
    wear = 4 * (frame.machine_speed.to_numpy()/1800)**3
    correction = 120 * (frame.power_factor.to_numpy()-.80)**2
    cost = energy * tariff + wear + correction
    objectives = np.column_stack([energy, cost, -frame.production_rate.to_numpy()])
    return objectives, frame, wear, correction


class IndustrialProblem(Problem):
    def __init__(self, model, request):
        super().__init__(n_var=3, n_obj=3, n_ieq_constr=2, xl=LOW, xu=HIGH)
        self.model, self.request = model, request

    def _evaluate(self, x, out, *args, **kwargs):
        r = self.request
        f, _, _, _ = evaluate(self.model, x, r.temperature, r.tariff)
        out['F'] = f
        out['G'] = np.column_stack([r.min_production_rate + f[:, 2], f[:, 0] - r.max_energy_kwh])


def operating_metrics(frame, f, wear, correction, tariff, index):
    row = frame.iloc[index]
    return {**{key: float(value) for key, value in row.items()},
            'energy_kwh': float(f[index, 0]), 'cost': float(f[index, 1]),
            'electricity_cost': float(f[index, 0]*tariff),
            'wear_cost': float(wear[index]), 'correction_cost': float(correction[index]),
            'units_per_interval': float(row.production_rate*INTERVAL_HOURS)}


def same_output_benchmark(model, request, reference, reference_settings):
    target = reference['production_rate']
    if target < request.min_production_rate:
        return {'status': 'reference_below_minimum', 'target_production_rate': target}
    if reference['energy_kwh'] > request.max_energy_kwh:
        return {'status': 'reference_above_energy_limit', 'target_production_rate': target}

    speeds, factors = np.meshgrid(
        np.unique(np.r_[np.linspace(LOW[1], HIGH[1], 81), reference_settings[1]]),
        np.unique(np.r_[np.linspace(LOW[2], HIGH[2], 41), reference_settings[2]]))
    speed, factor = speeds.ravel(), factors.ravel()
    # At fixed temperature and speed, the simulated production equation is linear in load.
    load = target / production(1, speed, request.temperature)
    in_bounds = (load >= LOW[0]) & (load <= HIGH[0])
    settings = np.vstack([reference_settings, np.column_stack(
        [load[in_bounds], speed[in_bounds], factor[in_bounds]])])
    f, frame, wear, correction = evaluate(model, settings, request.temperature, request.tariff)
    feasible = ((f[:, 0] <= request.max_energy_kwh)
                & np.isclose(-f[:, 2], target, rtol=0, atol=1e-8))
    best = int(np.argmin(np.where(feasible, f[:, 1], np.inf)))
    return {'status': 'ok', 'target_production_rate': target,
            'candidate': operating_metrics(frame, f, wear, correction, request.tariff, best),
            'evaluated_points': len(settings), 'feasible_points': int(feasible.sum()),
            'method': 'Lowest modeled total cost on a fixed-output speed and power-factor grid, including the reference'}


def optimize(model, request):
    started = perf_counter()
    result = minimize(IndustrialProblem(model, request), NSGA2(pop_size=request.population),
                      ('n_gen', request.generations), seed=request.seed, verbose=False)
    if result.X is None:
        return {'status': 'no_feasible_solution', 'message': 'No feasible solution found in this search. Reduce the production requirement or increase the energy limit.', 'pareto': [], 'recommended': None}
    f, frame, wear, correction = evaluate(model, result.X, request.temperature, request.tariff)
    weights = np.asarray(request.weights) / sum(request.weights)
    normalized = (f - f.min(axis=0)) / np.maximum(np.ptp(f, axis=0), 1e-9)
    scores = np.sqrt((weights * normalized**2).sum(axis=1))
    points = [{'id': i, **operating_metrics(frame, f, wear, correction, request.tariff, i),
               'score': float(scores[i])} for i in range(len(frame))]
    baseline = request.reference
    reference_settings = [baseline.machine_load, baseline.machine_speed, baseline.power_factor]
    rf, rframe, rwear, rcorrection = evaluate(model, reference_settings, request.temperature, request.tariff)
    reference = operating_metrics(rframe, rf, rwear, rcorrection, request.tariff, 0)
    reference['feasible'] = (reference['production_rate'] >= request.min_production_rate
                             and reference['energy_kwh'] <= request.max_energy_kwh)
    return {'status': 'ok', 'pareto': points, 'recommended': points[int(np.argmin(scores))],
            'reference': reference,
            'same_output_benchmark': same_output_benchmark(model, request, reference, reference_settings),
            'elapsed_seconds': round(perf_counter()-started, 3),
            'created_at': datetime.now(timezone.utc).isoformat(),
            'model_version': 'synthetic-operations-v1',
            'source': 'synthetic_operations', 'interval_minutes': 15,
            'recommendation_method': 'Minimum weighted distance to normalized ideal point within this approximate Pareto set',
            'request': request.model_dump(), 'algorithm': 'pymoo NSGA-II'}
