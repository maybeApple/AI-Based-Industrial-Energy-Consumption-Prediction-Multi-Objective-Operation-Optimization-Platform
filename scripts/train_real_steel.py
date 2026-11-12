"""Train and compare real-data forecasters without replacing the served model.

Run from the project root: python -m scripts.train_real_steel --output <directory>
"""
import argparse
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor

from api.industrial.data import DATA
from api.industrial.models import metrics, regressor

SOURCE = 'https://archive.ics.uci.edu/dataset/851/steel+industry+energy+consumption'
LEGACY = ['hour', 'minute', 'weekday', 'lag_1', 'lag_4', 'lag_96', 'rolling_96',
          'power_factor_previous']


def make_features(data):
    stamps = data.timestamp
    energy = pd.to_numeric(data['Usage_kWh'], errors='raise')
    past = energy.shift(1)
    x = pd.DataFrame({'hour': stamps.dt.hour, 'minute': stamps.dt.minute,
                      'weekday': stamps.dt.dayofweek})
    for lag in (1, 2, 3, 4, 8, 16, 96):
        x[f'lag_{lag}'] = energy.shift(lag)
    for window in (4, 8, 16, 96):
        history = past.rolling(window)
        x[f'rolling_{window}'] = history.mean()
        x[f'rolling_std_{window}'] = history.std()
    for label, column in {
        'power_factor': 'Lagging_Current_Power_Factor',
        'leading_pf': 'Leading_Current_Power_Factor',
        'lagging_reactive': 'Lagging_Current_Reactive.Power_kVarh',
        'leading_reactive': 'Leading_Current_Reactive_Power_kVarh',
    }.items():
        telemetry = pd.to_numeric(data[column], errors='raise')
        x[f'{label}_previous'] = telemetry.shift(1) / (100 if label in ('power_factor', 'leading_pf') else 1)
        x[f'{label}_change'] = telemetry.shift(1) - telemetry.shift(2)
    return x, energy


def model_for(objective):
    return LGBMRegressor(objective=objective, n_estimators=230, learning_rate=.055,
                         num_leaves=31, random_state=42, n_jobs=2, verbosity=-1)


def forecast(model, frame, features, model_weight):
    predicted = model.predict(frame[features]) if model_weight else frame.lag_1.to_numpy()
    return np.maximum(0, model_weight*predicted + (1-model_weight)*frame.lag_1.to_numpy())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=DATA / 'Steel_industry_data.csv')
    parser.add_argument('--output', type=Path, default=DATA.parents[1] / 'runtime' / 'real-steel-training')
    args = parser.parse_args()
    data = pd.read_csv(args.data)
    data['timestamp'] = pd.to_datetime(data['date'], format='%d/%m/%Y %H:%M')
    data = data.sort_values('timestamp').reset_index(drop=True)
    if not data.timestamp.diff().dropna().eq(pd.Timedelta(minutes=15)).all():
        raise ValueError('Expected unique, contiguous 15-minute observations.')

    # Probe forecast-time causality: changing a reading at t must not change any
    # predictors at or before t, and it must change the energy lag at t+1.
    x, y = make_features(data)
    probe = 192
    altered = data.copy()
    altered.loc[probe, ['Usage_kWh', 'Lagging_Current_Power_Factor']] += 10
    altered_x, _ = make_features(altered)
    pd.testing.assert_frame_equal(x.iloc[:probe+1], altered_x.iloc[:probe+1])
    assert altered_x.loc[probe+1, 'lag_1'] != x.loc[probe+1, 'lag_1']
    valid = x.notna().all(axis=1) & y.notna()
    stamps, x, y = data.timestamp[valid], x[valid], y[valid]
    val_at, test_at = int(len(x)*.70), int(len(x)*.80)
    validation = x.iloc[val_at:test_at]
    valid_y = y.iloc[val_at:test_at]
    recent = [key for key in x.columns if key not in ('hour', 'minute', 'weekday')]
    feature_sets = {'recent': recent, 'recent_and_calendar': list(x.columns)}
    validation_results = [{'inputs': 'persistence', 'objective': None, 'model_weight': 0,
                           **metrics(valid_y, validation.lag_1)}]
    legacy_val = regressor().fit(x.iloc[:val_at][LEGACY], y.iloc[:val_at])
    for label, features in feature_sets.items():
        for objective in ('regression', 'regression_l1'):
            model = model_for(objective).fit(x.iloc[:val_at][features], y.iloc[:val_at])
            for weight in (1., .75, .5):
                prediction = forecast(model, validation, features, weight)
                validation_results.append({'inputs': label, 'objective': objective, 'model_weight': weight,
                                           **metrics(valid_y, prediction)})
    selected = min(validation_results, key=lambda row: row['mae_kwh'])
    weight = selected['model_weight']
    features = feature_sets.get(selected['inputs'], ['lag_1'])
    selected_model = (model_for(selected['objective']).fit(x.iloc[:test_at][features], y.iloc[:test_at])
                      if weight else None)
    legacy = regressor().fit(x.iloc[:test_at][LEGACY], y.iloc[:test_at])
    test = x.iloc[test_at:]
    actual = y.iloc[test_at:].to_numpy()
    pred = forecast(selected_model, test, features, weight)
    legacy_pred = forecast(legacy, test, LEGACY, 1)
    persistence = test.lag_1.to_numpy()

    def compare(rows):
        return {label: {**metrics(actual[rows], values[rows]),
                        'max_absolute_error_kwh': float(np.max(np.abs(actual[rows] - values[rows])))}
                for label, values in {'selected': pred, 'legacy_lightgbm': legacy_pred,
                                      'persistence': persistence}.items()}

    report = {
        'source': SOURCE, 'license': 'CC BY 4.0', 'horizon_minutes': 15, 'raw_rows': len(data),
        'source_sha256': hashlib.sha256(args.data.read_bytes()).hexdigest(),
        'split': {'initial_training_rows': val_at, 'validation_rows': test_at-val_at,
                  'refit_rows': test_at, 'test_rows': len(test), 'validation_start': str(stamps.iloc[val_at]),
                  'training_end': str(stamps.iloc[test_at-1]), 'test_start': str(stamps.iloc[test_at]),
                  'test_end': str(stamps.iloc[-1])},
        'model_selection': 'Lowest validation MAE, then refit on all pre-test records.',
        'selected_recipe': selected, 'features': features,
        'legacy_validation': metrics(valid_y, forecast(legacy_val, validation, LEGACY, 1)),
        'validation_candidates': validation_results,
        'test': compare(slice(None)), 'final_48h_diagnostic': compare(slice(-192, None)),
        'maximum_legacy_overprediction': {
            'timestamp': str(stamps.iloc[test_at+int(np.argmax(legacy_pred-actual))]),
        },
        'notes': ['Only the clock is known for the target interval; all metered inputs are lagged.',
                  'One-step replay: newly observed values are available for the next forecast.',
                  'The project has previously inspected this test period. It is a retrospective benchmark, not independent site validation.',
                  'The last 48 hours are a diagnostic slice, not a model selection set.',
                  'This observational dataset does not validate operating interventions or control.'],
    }
    preview = pd.DataFrame({'timestamp': stamps.iloc[test_at:].astype(str), 'actual_kwh': actual,
                            'selected_kwh': pred, 'legacy_kwh': legacy_pred, 'persistence_kwh': persistence})
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    preview.to_csv(args.output / 'test_predictions.csv', index=False)
    joblib.dump({'model': selected_model, 'features': features, 'model_weight': weight, 'report': report},
                args.output / 'real_steel_forecaster.joblib')
    print(json.dumps({key: report[key] for key in ['split', 'selected_recipe', 'test', 'final_48h_diagnostic']},
                     indent=2))


if __name__ == '__main__':
    main()
