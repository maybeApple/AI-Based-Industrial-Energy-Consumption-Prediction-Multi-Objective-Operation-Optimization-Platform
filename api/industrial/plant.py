"""Dynamic teaching plant: state and actuator memory, measured disturbances, no hardware."""
import numpy as np
from .data import INTERVAL_HOURS

STATE_NAMES = ['machine_load', 'machine_speed', 'power_factor', 'process_temperature', 'production_rate', 'energy_kwh']
COMMAND_NAMES = ['load_command', 'speed_command', 'power_factor_command']
INPUT_NAMES = STATE_NAMES + COMMAND_NAMES + ['ambient_temperature', 'material_factor']
COMMAND_LOW = np.array([.25, 600., .80])
COMMAND_HIGH = np.array([1., 1800., .99])
COMMAND_SPAN = COMMAND_HIGH - COMMAND_LOW
SLEW = np.array([.12, 180., .03])
STATE_LOW = np.array([.25, 600., .80, 15., 0., 0.])
STATE_HIGH = np.array([1., 1800., .99, 85., 60., 100.])


def initial_state():
    return np.array([.7, 1200., .9, 40., 21., 21.])


def plant_step(state, command, ambient, material, noise=None):
    """Only the simulator uses these equations; the controller rolls out its fitted ANN."""
    s = np.atleast_2d(np.asarray(state, dtype=float))
    u = np.atleast_2d(np.clip(command, COMMAND_LOW, COMMAND_HIGH))
    load = s[:, 0] + .50*(u[:, 0]-s[:, 0])
    speed = s[:, 1] + .35*(u[:, 1]-s[:, 1])
    pf = s[:, 2] + .60*(u[:, 2]-s[:, 2])
    temp = s[:, 3] + .12*(np.asarray(ambient) + 14*load**1.4 + 8*(speed/1800)**2 - s[:, 3])
    equilibrium = 45*load*(speed/1800)*np.asarray(material)*np.clip(1-.004*np.maximum(temp-40, 0), .75, 1)
    rate = .45*s[:, 4] + .55*equilibrium
    demand = INTERVAL_HOURS*(18+75*load**1.7+22*(speed/1800)**3+.4*rate+.04*(temp-35)**2)/pf
    energy = .20*s[:, 5] + .80*demand
    result = np.column_stack([load, speed, pf, temp, rate, energy])
    if noise is not None:
        result += np.atleast_2d(noise)*[.001, 1.5, .0004, .05, .05, .08]
    return np.clip(result, STATE_LOW, STATE_HIGH)


def input_frame(state, command, ambient, material):
    state, command = np.atleast_2d(state), np.atleast_2d(command)
    count = len(state)
    return np.column_stack([state, command, np.broadcast_to(ambient, count), np.broadcast_to(material, count)])


def transition_dataset(episodes=180, steps=50, seed=17):
    """Independent trajectories are held out whole, avoiding adjacent-transition leakage."""
    rng = np.random.default_rng(seed)
    inputs, outputs, ids = [], [], []
    for episode in range(episodes):
        state = np.array([rng.uniform(.3,.95), rng.uniform(650,1750), rng.uniform(.81,.98),
                          rng.uniform(25,65), rng.uniform(8,40), rng.uniform(8,40)])
        command = rng.uniform(COMMAND_LOW, COMMAND_HIGH)
        for step in range(steps):
            if step % 4 == 0:
                command = rng.uniform(COMMAND_LOW, COMMAND_HIGH)
            ambient, material = rng.uniform(20,38), rng.uniform(.7,1.2)
            x = input_frame(state, command, ambient, material)[0]
            next_state = plant_step(state, command, ambient, material, rng.normal(size=6))[0]
            inputs.append(x); outputs.append(next_state); ids.append(episode)
            state = next_state
    return np.asarray(inputs), np.asarray(outputs), np.asarray(ids)
