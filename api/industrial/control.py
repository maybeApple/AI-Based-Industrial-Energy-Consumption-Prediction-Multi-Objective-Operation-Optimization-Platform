"""ANN model predictive control: predict, choose, execute first move, measure, repeat."""
from datetime import datetime, timezone
from time import perf_counter
import numpy as np
from threadpoolctl import threadpool_limits
from .plant import (COMMAND_LOW, COMMAND_HIGH, COMMAND_SPAN, SLEW, STATE_NAMES,
                    COMMAND_NAMES, initial_state, input_frame, plant_step)
from .data import INTERVAL_HOURS


def cost_components(states, commands, tariff):
    energy = states[...,5]
    wear = 4*(commands[...,1]/1800)**3
    compensation = 120*(commands[...,2]-.80)**2
    return energy*tariff + wear + compensation


def project_sequence(sequences, previous):
    """Apply both actuator bounds and per-interval slew limits to every candidate."""
    result = np.asarray(sequences).copy()
    last = np.broadcast_to(previous, (len(result),3)).copy()
    for j in range(result.shape[1]):
        result[:,j] = np.clip(result[:,j], np.maximum(COMMAND_LOW,last-SLEW), np.minimum(COMMAND_HIGH,last+SLEW))
        last = result[:,j]
    return result


def choose_action(model, state, previous, context, settings, rng, warm_plan=None):
    """Cross-entropy shooting MPC. Search calls only the trained ANN, never plant_step."""
    count, horizon = settings.samples, settings.horizon
    mean = np.tile(previous, (horizon,1)) if warm_plan is None else np.vstack([warm_plan[1:], warm_plan[-1]])
    std = np.tile(COMMAND_SPAN*.35, (horizon,1))
    best = None
    for _ in range(settings.iterations):
        candidates = rng.normal(mean, std, size=(count,horizon,3))
        candidates[0] = mean
        candidates[1] = previous
        candidates = project_sequence(candidates,previous)
        states = np.tile(state, (count,1))
        losses = np.zeros(count)
        feasible = np.ones(count,dtype=bool)
        last = np.tile(previous, (count,1))
        first_predictions = None
        for j in range(horizon):
            states = model.predict(input_frame(states,candidates[:,j],context['ambient'],context['material']))
            if j == 0:
                first_predictions = states.copy()
            error = (states[:,4]-context['target'])/context['target']
            shortage = np.maximum(-error,0)
            energy_excess = np.maximum(states[:,5]-settings.max_energy_kwh,0)/settings.max_energy_kwh
            heat_excess = np.maximum(states[:,3]-settings.max_temperature,0)/10
            losses += (25*error**2 + 30*shortage**2 + settings.energy_weight*states[:,5]/40
                       + .2*cost_components(states,candidates[:,j],context['tariff'])/40
                       + .025*np.sum(((candidates[:,j]-last)/SLEW)**2,axis=1)
                       + 1000*(energy_excess**2+heat_excess**2))
            feasible &= (states[:,5] <= settings.max_energy_kwh) & (states[:,3] <= settings.max_temperature)
            last = candidates[:,j]
        order = np.argsort(losses)
        elite = candidates[order[:max(8,count//8)]]
        mean = elite.mean(axis=0)
        std = np.maximum(elite.std(axis=0), COMMAND_SPAN*.015)
        valid = np.flatnonzero(feasible)
        idx = int(valid[np.argmin(losses[valid])]) if len(valid) else int(order[0])
        contender = (float(losses[idx]), candidates[idx].copy(), first_predictions[idx].copy(), bool(feasible[idx]))
        if best is None or (contender[3] and not best[3]) or (contender[3] == best[3] and contender[0] < best[0]):
            best = contender
    return {'action': best[1][0], 'plan': best[1], 'predicted_next_state': best[2],
            'predicted_horizon_feasible': best[3], 'objective': best[0]}


def context_at(step, settings):
    """Setpoint changes and material/ambient disturbances are revealed at their step."""
    disturbed = settings.disturbance_enabled and step >= settings.disturbance_step
    return {'target': settings.target_after if step >= settings.target_step else settings.target,
            'ambient': settings.ambient + (3 if disturbed else 0),
            'material': settings.material_factor if disturbed else 1.,
            'tariff': settings.tariff*(1.35 if disturbed else 1.), 'disturbance_active': disturbed}


def measure_row(step, state, command, context, predicted=None, feasible=True):
    row = {'step': step+1, 'minutes': (step+1)*15,
           **{name:float(v) for name,v in zip(STATE_NAMES,state)},
           **{name:float(v) for name,v in zip(COMMAND_NAMES,command)},
           'target': context['target'], 'ambient_temperature': context['ambient'],
           'material_factor': context['material'], 'tariff': context['tariff'],
           'disturbance_active': bool(context['disturbance_active']),
           'cost': float(cost_components(state,command,context['tariff'])),
           'predicted_horizon_feasible': bool(feasible)}
    if predicted is not None:
        row['predicted_production_rate'] = float(predicted[4])
        row['predicted_energy_kwh'] = float(predicted[5])
    return row


def control_summary(rows, settings):
    return {'tracking_mae': float(np.mean([abs(r['production_rate']-r['target']) for r in rows])),
            'total_energy_kwh': float(sum(r['energy_kwh'] for r in rows)),
            'total_units': float(sum(r['production_rate']*INTERVAL_HOURS for r in rows)),
            'total_cost': float(sum(r['cost'] for r in rows)),
            'energy_violations': int(sum(r['energy_kwh'] > settings.max_energy_kwh for r in rows)),
            'temperature_violations': int(sum(r['process_temperature'] > settings.max_temperature for r in rows)),
            'max_process_temperature': float(max(r['process_temperature'] for r in rows)),
            'within_10_percent_target': float(np.mean([abs(r['production_rate']-r['target']) <= .1*r['target'] for r in rows])),
            'predicted_infeasible_steps': int(sum(not r['predicted_horizon_feasible'] for r in rows))}


def run_control(model, settings):
    started = perf_counter()
    rng = np.random.default_rng(settings.seed)
    noises = np.random.default_rng(settings.seed+1).normal(size=(settings.steps,6))
    state = initial_state(); baseline = state.copy(); previous = state[:3].copy()
    fixed = previous.copy(); warm = None; rows = []; baseline_rows = []
    with threadpool_limits(limits=2):
        for step in range(settings.steps):
            context = context_at(step,settings)
            choice = choose_action(model,state,previous,context,settings,rng,warm)
            action = choice['action']
            measured = plant_step(state,action,context['ambient'],context['material'],noises[step])[0]
            baseline = plant_step(baseline,fixed,context['ambient'],context['material'],noises[step])[0]
            rows.append(measure_row(step,measured,action,context,choice['predicted_next_state'],choice['predicted_horizon_feasible']))
            baseline_rows.append(measure_row(step,baseline,fixed,context))
            # Actual plant measurement closes the loop. ANN predictions are not reused as observations.
            state = measured; previous = action; warm = choice['plan']
    return {'status':'ok', 'controller':'ANN-based receding-horizon MPC', 'source':'synthetic_dynamic_plant',
            'rows':rows, 'baseline_rows':baseline_rows, 'summary':control_summary(rows,settings),
            'baseline_summary':control_summary(baseline_rows,settings), 'settings':settings.model_dump(),
            'initial_state': dict(zip(STATE_NAMES,initial_state().tolist())),
            'model_sha256':model.artifact_hash, 'architecture':model.report['architecture'],
            'elapsed_seconds':round(perf_counter()-started,3), 'created_at':datetime.now(timezone.utc).isoformat(),
            'baseline':'Fixed commands: 70% load, 1200 rpm, power factor 0.90; same initial state and disturbances',
            'note':'Accelerated simulation with measured feedback at each step. No hardware, no real-plant validation or stability guarantee.'}


def advance_control(model, request):
    context = {'target':request.target,'ambient':request.ambient,'material':request.material_factor,
               'tariff':request.tariff,'disturbance_active':request.material_factor != 1}
    with threadpool_limits(limits=2):
        choice = choose_action(model,np.array(request.state),np.array(request.previous_command),
                               context,request,np.random.default_rng(request.seed))
    measured = plant_step(request.state,choice['action'],request.ambient,request.material_factor)[0]
    return {'action':choice['action'].tolist(), 'predicted_next_state':choice['predicted_next_state'].tolist(),
            'measured_next_state':measured.tolist(), 'predicted_horizon_feasible':choice['predicted_horizon_feasible'],
            'row':measure_row(0,measured,choice['action'],context,choice['predicted_next_state'],choice['predicted_horizon_feasible']),
            'source':'synthetic_dynamic_plant'}
