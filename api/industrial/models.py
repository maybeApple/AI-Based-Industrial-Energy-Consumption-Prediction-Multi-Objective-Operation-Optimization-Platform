import json
import hashlib
import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.ensemble import IsolationForest
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from .data import ARTIFACTS, DATA, FEATURES, generate_demo

VERSION = 1


def metrics(y, pred):
    return {'mae_kwh': float(mean_absolute_error(y, pred)),
            'rmse_kwh': float(np.sqrt(mean_squared_error(y, pred))),
            'r2': float(r2_score(y, pred))}


def regressor():
    return LGBMRegressor(n_estimators=230, learning_rate=.055, num_leaves=31,
                         random_state=42, n_jobs=2, verbosity=-1)


def train_operations():
    df = generate_demo()
    # Contiguous train/calibration/test split: no future test rows used in fitting.
    train, cal, test = np.split(np.arange(len(df)), [int(len(df)*.7), int(len(df)*.85)])
    model = regressor().fit(df.iloc[train][FEATURES], df.iloc[train].energy_kwh)
    error = abs(df.iloc[cal].energy_kwh.to_numpy() - model.predict(df.iloc[cal][FEATURES]))
    radius = float(np.quantile(error, min(1, np.ceil((len(error)+1)*.9)/len(error)), method='higher'))
    anomaly = IsolationForest(n_estimators=150, contamination=.025, random_state=42, n_jobs=2)
    anomaly.fit(df.iloc[train][FEATURES + ['energy_kwh']])
    pred = model.predict(df.iloc[test][FEATURES])
    report = {**metrics(df.iloc[test].energy_kwh, pred), 'test_rows': len(test),
              'interval_coverage': float(np.mean(abs(df.iloc[test].energy_kwh - pred) <= radius)),
              'baseline_mae_kwh': float(mean_absolute_error(df.iloc[test].energy_kwh, np.full(len(test), df.iloc[train].energy_kwh.mean()))),
              'split': 'chronological 70% train / 15% calibration / 15% test',
              'source': 'synthetic_operations', 'features': FEATURES,
              'train_rows': len(train), 'calibration_rows': len(cal),
              'training_end': str(df.iloc[train[-1]].timestamp),
              'test_start': str(df.iloc[test[0]].timestamp),
              'anomaly_note': 'Unsupervised outlier flag; not validated fault diagnosis.'}
    bundle = {'version': VERSION, 'model': model, 'anomaly': anomaly, 'radius': radius, 'metrics': report}
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, ARTIFACTS / 'operations.joblib')
    (ARTIFACTS / 'operations_metrics.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return bundle, df


def load_operations():
    path = ARTIFACTS / 'operations.joblib'
    if path.exists() and (DATA / 'operations_demo.csv').exists():
        bundle = joblib.load(path)
        if bundle.get('version') == VERSION:
            return bundle, pd.read_csv(DATA / 'operations_demo.csv')
    return train_operations()


def train_steel(path):
    """Next-interval one-step forecast using only values available before target t."""
    df = pd.read_csv(path)
    df['timestamp'] = pd.to_datetime(df['date'], dayfirst=True)
    df = df.sort_values('timestamp').reset_index(drop=True)
    if df.timestamp.duplicated().any() or not df.timestamp.diff().dropna().eq(pd.Timedelta(minutes=15)).all():
        raise ValueError('Steel dataset must have unique, contiguous 15-minute timestamps')
    y = pd.to_numeric(df['Usage_kWh'], errors='raise')
    x = pd.DataFrame({'hour': df.timestamp.dt.hour, 'minute': df.timestamp.dt.minute,
                       'weekday': df.timestamp.dt.dayofweek,
                       'lag_1': y.shift(1), 'lag_4': y.shift(4), 'lag_96': y.shift(96),
                       'rolling_96': y.shift(1).rolling(96).mean(),
                       'power_factor_previous': df['Lagging_Current_Power_Factor'].shift(1)/100})
    valid = x.notna().all(axis=1) & y.notna()
    x, y, stamps = x[valid], y[valid], df.timestamp[valid]
    cut = int(len(x)*.8)
    model = regressor().fit(x.iloc[:cut], y.iloc[:cut])
    pred = np.maximum(0, model.predict(x.iloc[cut:]))
    report = {**metrics(y.iloc[cut:], pred), 'source': 'UCI Steel Industry Energy Consumption',
              'rows': len(df), 'train_rows': cut, 'test_rows': len(x)-cut,
              'split': 'chronological 80% train / 20% test; rolling one-step evaluation',
              'features': list(x.columns), 'horizon_minutes': 15,
              'baseline_mae_kwh': float(mean_absolute_error(y.iloc[cut:], x.iloc[cut:].lag_1)),
              'training_end': str(stamps.iloc[cut-1]), 'test_start': str(stamps.iloc[cut]),
              'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
              'note': 'Previous observed readings update each step; not a 24-hour open-loop forecast.'}
    preview = pd.DataFrame({'timestamp': stamps.iloc[cut:].astype(str), 'actual': y.iloc[cut:], 'forecast': pred}).tail(192)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    joblib.dump({'model': model, 'metrics': report}, ARTIFACTS / 'steel.joblib')
    (ARTIFACTS / 'steel_metrics.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    preview.to_csv(DATA / 'steel_test_preview.csv', index=False)
    return report
