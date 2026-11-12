import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from api.industrial_app import app
from api.industrial.data import production


@pytest.fixture(scope='module')
def client():
    with TestClient(app) as c:
        yield c


def test_summary_history_and_anomaly_filter(client):
    assert client.get('/api/health').json()['status'] == 'ok'
    summary = client.get('/api/summary').json()
    assert summary['rows'] == 6000
    assert summary['metrics']['mae_kwh'] < summary['metrics']['baseline_mae_kwh']
    first = client.get('/api/history?limit=48').json()
    second = client.get('/api/history?limit=48&offset=48').json()
    assert len(first['rows']) == len(second['rows']) == 48
    assert second['rows'][-1]['timestamp'] < first['rows'][0]['timestamp']
    filtered = client.get('/api/history?anomalies_only=true').json()
    assert filtered['rows'] and all(r['anomaly'] for r in filtered['rows'])
    assert client.get('/api/history?limit=10000').status_code == 422


def test_prediction_target_not_used_as_input(client):
    base = client.post('/api/predict', json={}).json()
    outlier = client.post('/api/predict', json={'energy_kwh': 499}).json()
    assert base['predicted_energy_kwh'] == outlier['predicted_energy_kwh']
    assert base['anomaly'] is None and outlier['anomaly'] is True
    assert 0 <= base['lower_kwh'] < base['predicted_energy_kwh'] < base['upper_kwh']
    assert base['operating_point']['production_rate'] == pytest.approx(production(.7, 1200, 32))


@pytest.mark.parametrize('path,payload', [
    ('predict', {'machine_load': 2}), ('predict', {'power_factor': .4}),
    ('predict', {'machine_speed': 500}), ('predict', {'production_rate': 999}),
    ('optimize', {'weights': [0, 0, 0]}), ('optimize', {'weights': [-1, 1, 1]}),
    ('optimize', {'weights': [1, 2]}), ('optimize', {'generations': 10000}),
    ('optimize', {'tariff': 0}), ('predict', {'temperature': 'NaN'}),
    ('optimize', {'reference': {'machine_speed': 1900}}),
])
def test_invalid_inputs(client, path, payload):
    assert client.post('/api/'+path, json=payload).status_code == 422


def test_pareto_constraints_nondominance_recommendation_and_reproducibility(client):
    request = {'population': 48, 'generations': 30, 'min_production_rate': 15, 'max_energy_kwh': 40,
               'temperature': 30, 'tariff': .75, 'weights': [2, 1, 3]}
    response = client.post('/api/optimize', json=request)
    assert response.status_code == 200
    result = response.json()
    assert result['status'] == 'ok' and len(result['pareto']) > 5
    points = result['pareto']
    f = np.array([[p['energy_kwh'], p['cost'], -p['production_rate']] for p in points])
    for p, candidate in zip(points, f):
        assert .25 <= p['machine_load'] <= 1
        assert 600 <= p['machine_speed'] <= 1800
        assert .8 <= p['power_factor'] <= .99
        assert p['production_rate'] >= 15 - 1e-8
        assert p['energy_kwh'] <= 40 + 1e-8
        assert p['production_rate'] == pytest.approx(production(p['machine_load'], p['machine_speed'], 30))
        assert p['cost'] == pytest.approx(p['electricity_cost']+p['wear_cost']+p['correction_cost'])
        assert not np.any(np.all(f <= candidate, axis=1) & np.any(f < candidate, axis=1))
    scores = np.sqrt((np.array([2, 1, 3])/6 * ((f-f.min(axis=0))/np.maximum(np.ptp(f, axis=0), 1e-9))**2).sum(axis=1))
    assert result['recommended']['id'] == int(np.argmin(scores))
    reference = result['reference']
    assert reference['production_rate'] == pytest.approx(production(.7, 1200, 30))
    assert reference['cost'] == pytest.approx(reference['electricity_cost'] + reference['wear_cost'] + reference['correction_cost'])
    assert reference['electricity_cost'] == pytest.approx(reference['energy_kwh']*.75)
    assert reference['feasible'] == (reference['production_rate'] >= 15 and reference['energy_kwh'] <= 40)
    benchmark = result['same_output_benchmark']
    alternative = benchmark['candidate']
    assert benchmark['status'] == 'ok'
    assert benchmark['target_production_rate'] == reference['production_rate']
    assert alternative['production_rate'] == pytest.approx(reference['production_rate'], abs=1e-8)
    assert alternative['units_per_interval'] == pytest.approx(reference['units_per_interval'], abs=1e-8)
    assert alternative['energy_kwh'] <= request['max_energy_kwh']
    assert alternative['cost'] <= reference['cost']
    assert benchmark['evaluated_points'] >= benchmark['feasible_points'] > 1
    assert result['elapsed_seconds'] >= 0 and result['created_at'].endswith('+00:00')
    again = client.post('/api/optimize', json=request).json()
    assert again['recommended'] == result['recommended']
    assert again['same_output_benchmark'] == benchmark


def test_infeasible_constraints(client):
    r = client.post('/api/optimize', json={'min_production_rate': 45, 'temperature': 45, 'max_energy_kwh': 1, 'population': 40, 'generations': 20}).json()
    assert r['status'] == 'no_feasible_solution'
    assert r['pareto'] == [] and r['recommended'] is None
    assert 'No feasible solution' in r['message']


def test_reference_not_claimed_feasible_for_high_output(client):
    response = client.post('/api/optimize', json={'min_production_rate': 30, 'population': 40, 'generations': 20}).json()
    assert response['status'] == 'ok'
    assert response['reference']['feasible'] is False
    assert response['same_output_benchmark']['status'] == 'reference_below_minimum'
    assert 'candidate' not in response['same_output_benchmark']
    assert all(p['production_rate'] >= 30 for p in response['pareto'])


def test_custom_reference_enables_high_output_benchmark_without_changing_front(client):
    request = {'min_production_rate': 30, 'population': 40, 'generations': 20}
    original = client.post('/api/optimize', json=request).json()
    custom = {'machine_load': .9, 'machine_speed': 1500, 'power_factor': .90}
    result = client.post('/api/optimize', json={**request, 'reference': custom}).json()
    assert result['pareto'] == original['pareto']
    assert result['reference']['feasible']
    assert result['request']['reference'] == custom
    assert result['same_output_benchmark']['candidate']['production_rate'] == pytest.approx(33.75, abs=1e-8)


def test_real_steel_benchmark_if_prepared(client):
    data = client.get('/api/steel').json()
    if not data['available']:
        pytest.skip('Optional UCI dataset not downloaded')
    m = data['metrics']
    assert m['rows'] == 35040 and m['horizon_minutes'] == 15
    assert m['training_end'] < m['test_start']
    assert m['mae_kwh'] < m['baseline_mae_kwh']
    assert len(data['history']) == 192
    assert not any('CO2' in f or 'Usage_kWh' in f for f in m['features'])


def test_measured_benchmarks_have_comparable_clock_aligned_windows(client):
    response = client.get('/api/real-benchmarks')
    assert response.status_code == 200
    benchmarks = response.json()['benchmarks']
    if not benchmarks:
        pytest.skip('Optional measured forecast artifacts not prepared')
    assert len({item['id'] for item in benchmarks}) == len(benchmarks)
    for item in benchmarks:
        assert pd.Timestamp(item['training_end']) < pd.Timestamp(item['test_start'])
        methods = {model['key'] for model in item['models']}
        assert {'forecast', 'persistence'} <= methods
        assert {window['key'] for window in item['windows']} == {'first', 'final'}
        for window in item['windows']:
            rows = pd.DataFrame(window['history'])
            assert len(rows) == 192
            assert pd.to_datetime(rows.timestamp).diff().dropna().eq(pd.Timedelta(minutes=15)).all()
            assert rows.dropna().shape[0] == window['scored_rows']
            for key in methods:
                expected = (rows.actual - rows[key]).abs().mean()
                if window['scored_rows']:
                    assert window['mae'][key] == pytest.approx(expected, abs=1e-10)
                else:
                    assert window['mae'][key] is None


def test_scada_lag_stays_missing_at_a_gap_and_does_not_use_target_readings():
    from scripts.prepare_real_benchmarks import scada_features

    stamps = pd.date_range('2025-11-01', periods=120, freq='15min', tz='UTC')
    values = pd.Series(np.arange(120, dtype=float), index=stamps)
    values.iloc[97] = np.nan
    original = scada_features(values)
    assert np.isnan(original.iloc[98]['lag_1'])
    assert original.iloc[98]['lag_2'] == values.iloc[96]
    assert original.iloc[98]['lag_96'] == values.iloc[2]
    assert np.isnan(original.iloc[98]['mean_4'])
    modified = values.copy()
    modified.iloc[99] = 2000.
    changed = scada_features(modified)
    pd.testing.assert_frame_equal(changed.iloc[:100], original.iloc[:100])
    assert changed.iloc[100]['lag_1'] == 2000.
