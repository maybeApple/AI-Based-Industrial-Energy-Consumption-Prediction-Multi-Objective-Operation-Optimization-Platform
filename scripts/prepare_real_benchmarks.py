"""Publish measured forecast comparisons from the steel run and the optional SCADA archive."""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import joblib
import numpy as np
import pandas as pd

from api.industrial.data import ARTIFACTS
from api.industrial.models import metrics
from scripts.train_real_steel import model_for, forecast

SCADA_URL = 'https://doi.org/10.5281/zenodo.19180972'
SCADA_ARCHIVE_MD5 = 'acc03fa5cb4b9c54a426440fffe49e74'
ASSET = 'comp_a'
WINDOWS_48_HOURS = 192
INTERVAL = '15min'


def scores(actual, predicted):
    return {**metrics(actual, predicted),
            'max_absolute_error_kwh': float(np.abs(actual - predicted).max())}


def model_comparison(key, label, test, preview):
    return {'key': key, 'label': label, 'test': test, 'preview': preview}


def preview_records(frame):
    return json.loads(frame.to_json(orient='records', double_precision=12))


def display_window(key, label, frame):
    scored = frame.dropna()
    return {'key': key, 'label': label, 'scored_rows': len(scored), 'history': preview_records(frame),
            'mae': {column: float(np.abs(scored.actual - scored[column]).mean()) if len(scored) else None
                    for column in frame.columns if column not in ('timestamp', 'actual')}}


def steel_benchmark(steel_run):
    report = json.loads((steel_run / 'report.json').read_text(encoding='utf-8'))
    data = pd.read_csv(steel_run / 'test_predictions.csv').rename(columns={
        'actual_kwh': 'actual', 'selected_kwh': 'forecast', 'legacy_kwh': 'legacy',
        'persistence_kwh': 'persistence',
    })
    split = report['split']
    if len(data) != split['test_rows'] or data.timestamp.iloc[0] != split['test_start']:
        raise ValueError('Steel predictions do not match the reported test period.')
    recipe = report['selected_recipe']
    weight = recipe['model_weight']
    forecast_label = 'Retrained LightGBM' if weight == 1 else 'Retrained LightGBM blend' if weight else 'Validation-selected persistence'
    models = [(forecast_label, 'forecast', 'selected'), ('Last-reading baseline', 'persistence', 'persistence'),
              ('Previous LightGBM', 'legacy', 'legacy_lightgbm')]
    return {
        'id': 'steel', 'label': 'Steel plant · UCI', 'chart_title': 'Measured steel energy / one-step forecast',
        'source_url': report['source'], 'source_label': 'UCI Steel Industry Energy Consumption',
        'attribution': 'V E, S., Shin, C., & Cho, Y. (2021) · CC BY 4.0 · DOI: 10.24432/C52G8C',
        'asset_scope': 'South Korean steel plant', 'time_zone': 'Source local time',
        'source_rows': report['raw_rows'], 'test_rows': split['test_rows'],
        'training_end': split['training_end'], 'test_start': split['test_start'],
        'models': [model_comparison(key, name, report['test'][method], report['final_48h_diagnostic'][method])
                   for name, key, method in models],
        'default_window': 'final',
        'windows': [display_window('first', 'First 48 test hours', data.head(WINDOWS_48_HOURS)),
                    display_window('final', 'Final 48 test hours', data.tail(WINDOWS_48_HOURS))],
        'notes': ['The retrained model uses calendar signals and lagged energy and electrical telemetry. Target-interval meter readings are excluded.',
                  'The test period was inspected in earlier project work. This is a retrospective comparison, not validation at a new site.'],
    }


def load_scada_compressor(archive):
    with archive.open('rb') as source:
        if hashlib.file_digest(source, 'md5').hexdigest() != SCADA_ARCHIVE_MD5:
            raise ValueError('Archive checksum does not match the cited Zenodo release.')
    columns = ['AssetId', 'Phase', 'window_start_utc', 'Energy_kWh_15m', 'IsReliableWindow']
    with ZipFile(archive) as zip_file:
        parts = sorted(name for name in zip_file.namelist()
                       if f'/data_csv/asset_id={ASSET}/' in name and name.endswith('.csv'))
        if not parts:
            raise ValueError('The cited compressor CSV partitions are missing.')
        samples = []
        for name in parts:
            with zip_file.open(name) as member:
                raw = pd.read_csv(member, usecols=columns)
            samples.append(raw.loc[(raw.AssetId == ASSET) & (raw.Phase == 'ALL')])
    data = pd.concat(samples, ignore_index=True)
    stamps = pd.DatetimeIndex(pd.to_datetime(data.window_start_utc, utc=True))
    if stamps.empty or stamps.has_duplicates or not (stamps.floor(INTERVAL) == stamps).all():
        raise ValueError('The asset must have unique 15-minute UTC windows.')
    energy = pd.to_numeric(data.Energy_kWh_15m, errors='raise')
    reliable = data.IsReliableWindow.eq(1) & np.isfinite(energy) & energy.ge(0)
    observed = pd.Series(energy.where(reliable).to_numpy(), index=stamps).sort_index()
    grid = pd.date_range(observed.index.min(), observed.index.max(), freq=INTERVAL)
    return observed.reindex(grid), len(data), int(reliable.sum())


def scada_features(energy):
    local = energy.index.tz_convert('Europe/Dublin')
    inputs = pd.DataFrame({'hour': local.hour, 'minute': local.minute,
                           'weekday': local.dayofweek}, index=energy.index)
    for lag in (1, 2, 3, 4, 8, 16, 96):
        inputs[f'lag_{lag}'] = energy.shift(lag)
    past = energy.shift(1)
    for width in (4, 8, 16):
        window = past.rolling(width)
        inputs[f'mean_{width}'] = window.mean()
        inputs[f'std_{width}'] = window.std()
    return inputs


def scada_benchmark(archive, model_dir):
    energy, source_rows, reliable_rows = load_scada_compressor(archive)
    inputs = scada_features(energy)
    # Keep a regular grid so lags cannot silently jump over a bad interval.
    # All methods are scored on the same targets with both baselines available.
    eligible = energy.notna() & inputs.lag_1.notna() & inputs.lag_96.notna()
    val_start, test_start = inputs.index[[int(len(inputs)*.7), int(len(inputs)*.8)]]
    train = eligible & (inputs.index < val_start)
    val = eligible & (inputs.index >= val_start) & (inputs.index < test_start)
    refit = train | val
    test = eligible & (inputs.index >= test_start)
    if min(train.sum(), val.sum(), test.sum()) < 200:
        raise ValueError('The compressor has insufficient eligible history in a chronological split.')
    features = list(inputs.columns)
    candidates = []
    for objective in ('regression', 'regression_l1'):
        model = model_for(objective).fit(inputs.loc[train], energy.loc[train])
        for weight in (1., .75, .5):
            predictions = forecast(model, inputs.loc[val], features, weight)
            candidates.append({'objective': objective, 'model_weight': weight,
                               **scores(energy.loc[val].to_numpy(), predictions)})
    selected = min(candidates, key=lambda row: row['mae_kwh'])
    weight = selected['model_weight']
    model = model_for(selected['objective']).fit(inputs.loc[refit], energy.loc[refit])
    predictions = pd.DataFrame({'actual': energy.loc[test],
                                'forecast': forecast(model, inputs.loc[test], features, weight),
                                'persistence': inputs.loc[test, 'lag_1'], 'daily': inputs.loc[test, 'lag_96']})
    test_grid = inputs.index[inputs.index >= test_start]
    preview = predictions.reindex(test_grid[-WINDOWS_48_HOURS:])
    scored = preview.dropna()
    items = [('forecast', 'LightGBM' if weight == 1 else 'LightGBM blend'),
             ('persistence', 'Last-reading baseline'), ('daily', 'Prior-day baseline')]
    comparison = [model_comparison(key, label,
                                   scores(predictions.actual.to_numpy(), predictions[key].to_numpy()),
                                   scores(scored.actual.to_numpy(), scored[key].to_numpy()) if not scored.empty else None)
                  for key, label in items]
    report = {'asset_id': ASSET, 'source': SCADA_URL, 'source_archive_md5': SCADA_ARCHIVE_MD5,
              'source_rows': source_rows, 'reliable_rows': reliable_rows, 'regular_grid_rows': len(inputs),
              'validation_start': str(val_start), 'test_split_boundary': str(test_start),
              'train_rows': int(train.sum()), 'validation_rows': int(val.sum()), 'refit_rows': int(refit.sum()),
              'test_rows': int(test.sum()), 'test_grid_rows': int((inputs.index >= test_start).sum()),
              'selected_recipe': selected, 'validation_candidates': candidates,
              'validation_baselines': {key: scores(energy.loc[val].to_numpy(), inputs.loc[val, lag].to_numpy())
                                       for key, lag in [('persistence', 'lag_1'), ('daily', 'lag_96')]},
              'models': comparison}
    model_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump({'model': model, 'features': features, 'model_weight': weight, 'report': report},
                model_dir / 'scada-compressor.joblib')
    (model_dir / 'scada-compressor-report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    def to_display(key, label, frame):
        return display_window(key, label, frame.assign(
            timestamp=frame.index.strftime('%Y-%m-%d %H:%M:%S')).reset_index(drop=True))

    return {
        'id': 'scada-compressor', 'label': 'Air compressor · Irish manufacturing site',
        'chart_title': 'Measured air compressor energy / one-step forecast', 'source_url': SCADA_URL,
        'source_label': 'Industrial Asset-Level Electrical Energy Dataset',
        'attribution': 'Flynn, Murphy, Walsh & Riordan (2026) · CC BY 4.0 · DOI: 10.5281/zenodo.19180972',
        'asset_scope': 'SCADA air compressor (comp_a)', 'time_zone': 'UTC', 'source_rows': source_rows,
        'test_rows': int(test.sum()), 'training_end': inputs.index[refit][-1].strftime('%Y-%m-%d %H:%M:%S'),
        'test_start': predictions.index[0].strftime('%Y-%m-%d %H:%M:%S'), 'models': comparison,
        'default_window': 'first',
        'windows': [to_display('first', 'First 48 test hours', predictions.reindex(test_grid[:WINDOWS_48_HOURS])),
                    to_display('final', 'Final 48 test hours', preview)],
        'notes': [f'One compressor, using the published ALL-phase meter series. {reliable_rows:,} of {source_rows:,} source readings pass the published reliability flag and numeric checks.',
                  f'{int(test.sum()):,} of {report["test_grid_rows"]:,} test-period intervals are scored. All methods use the same targets and require valid previous-interval and previous-day readings. Unscored intervals appear as gaps.',
                  'The models were trained separately from the steel plant. This benchmark contains metered energy, not compressor commands, pressure targets or output.'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--steel-run', type=Path, required=True)
    parser.add_argument('--scada-zip', type=Path)
    parser.add_argument('--output', type=Path, default=ARTIFACTS / 'real_benchmarks')
    parser.add_argument('--model-dir', type=Path, default=ARTIFACTS / 'real_forecasters')
    args = parser.parse_args()
    benchmark = steel_benchmark(args.steel_run)
    args.output.mkdir(parents=True, exist_ok=True)
    args.model_dir.mkdir(parents=True, exist_ok=True)
    # Copy the reproducible steel run outputs into the project handoff.
    for source_name, target_name in [('real_steel_forecaster.joblib', 'steel.joblib'),
                                     ('report.json', 'steel-report.json')]:
        (args.model_dir / target_name).write_bytes((args.steel_run / source_name).read_bytes())
    benchmarks = [benchmark]
    if args.scada_zip:
        benchmarks.append(scada_benchmark(args.scada_zip, args.model_dir))
    for item in benchmarks:
        (args.output / (item['id'] + '.json')).write_text(
            json.dumps(item, ensure_ascii=False, allow_nan=False, separators=(',', ':')) + '\n', encoding='utf-8')
        print(json.dumps({'id': item['id'], 'source_rows': item['source_rows'], 'test_rows': item['test_rows'],
                          'windows': [{key: window[key] for key in ('key', 'scored_rows', 'mae')}
                                      for window in item['windows']], 'models': item['models']}))


if __name__ == '__main__':
    main()
