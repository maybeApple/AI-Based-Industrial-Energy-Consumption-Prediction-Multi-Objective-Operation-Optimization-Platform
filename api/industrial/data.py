"""Reproducible synthetic operations, never inferred from the energy target."""
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'data' / 'industrial'
ARTIFACTS = ROOT / 'artifacts' / 'industrial'
FEATURES = ['machine_load', 'machine_speed', 'production_rate', 'temperature', 'power_factor']
LOW = [0.25, 600.0, 0.80]
HIGH = [1.0, 1800.0, 0.99]
INTERVAL_HOURS = 0.25


def production(load, speed, temperature):
    """Demonstration capacity equation, units/hour. Not a measured steel process."""
    return 45 * np.asarray(load) * (np.asarray(speed) / 1800) * (1 - 0.002 * abs(np.asarray(temperature) - 32))


def operating_frame(x, temperature):
    x = np.atleast_2d(x)
    return pd.DataFrame({
        'machine_load': x[:, 0], 'machine_speed': x[:, 1],
        'production_rate': production(x[:, 0], x[:, 1], temperature),
        'temperature': temperature, 'power_factor': x[:, 2],
    })[FEATURES]


def generate_demo(rows=6000, seed=42):
    rng = np.random.default_rng(seed)
    load = rng.uniform(.25, 1, rows)
    speed = rng.uniform(600, 1800, rows)
    temp = rng.uniform(20, 45, rows)
    pf = rng.uniform(.80, .99, rows)
    rate = production(load, speed, temp)
    energy = (18 + 75 * load**1.7 + 22 * (speed / 1800)**3 + .4 * rate + .15 * (temp - 30)**2) / pf * INTERVAL_HOURS
    energy = np.maximum(0, energy + rng.normal(0, .55, rows))
    frame = pd.DataFrame({'timestamp': pd.date_range('2025-01-01', periods=rows, freq='15min'),
        'machine_load': load, 'machine_speed': speed, 'production_rate': rate,
        'temperature': temp, 'power_factor': pf, 'energy_kwh': energy,
        'machine_id': 'SIM-ROLL-01', 'source': 'synthetic_operations'})
    DATA.mkdir(parents=True, exist_ok=True)
    frame.to_csv(DATA / 'operations_demo.csv', index=False)
    return frame
