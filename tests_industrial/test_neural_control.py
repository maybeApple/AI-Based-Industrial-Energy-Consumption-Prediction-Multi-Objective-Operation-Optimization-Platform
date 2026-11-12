import numpy as np
import pytest
from fastapi.testclient import TestClient
from api.industrial_app import app
from api.industrial.plant import SLEW, COMMAND_LOW, COMMAND_HIGH, STATE_NAMES
from api.industrial.control import choose_action
from api.industrial.schemas import ControlSettings


@pytest.fixture(scope='module')
def client():
    with TestClient(app) as c:
        yield c


def test_trained_deep_network_and_independent_test_trajectories(client):
    model = client.get('/api/control/model').json()
    m = model['metrics']
    assert model['ready'] and len(model['model_sha256']) == 64
    assert m['architecture'] == [11,96,64,32,6] and m['hidden_layers'] == 3
    assert m['parameter_count'] == 9638
    assert m['train_episode_max'] < m['test_episode_min']
    for key in STATE_NAMES:
        assert m['mae'][key] < m['persistence_mae'][key]
    assert m['lightgbm_comparison_mae']['energy_kwh'] > 0
    assert m['rollout_windows'] == 1656
    assert [r['horizon'] for r in m['recursive_test_rollout']] == [1,2,3,4,5]
    assert m['recursive_test_rollout'][-1]['energy_mae_kwh'] < .5


def test_feedback_tracking_slew_bounds_and_reproducibility(client):
    run = client.post('/api/control/run',json={}).json()
    assert run['status'] == 'ok' and len(run['rows']) == 36
    assert run['summary']['tracking_mae'] < run['baseline_summary']['tracking_mae']*.5
    assert run['summary']['energy_violations'] == run['summary']['temperature_violations'] == 0
    assert run['summary']['total_units'] == pytest.approx(sum(r['production_rate']*.25 for r in run['rows']))
    previous = np.array([.7,1200,.9])
    for row in run['rows']:
        action = np.array([row['load_command'],row['speed_command'],row['power_factor_command']])
        assert np.all(action >= COMMAND_LOW) and np.all(action <= COMMAND_HIGH)
        assert np.all(abs(action-previous) <= SLEW+1e-8)
        previous = action
    assert run['rows'][9]['target'] == 22 and run['rows'][10]['target'] == 28
    assert run['rows'][19]['material_factor'] == 1 and run['rows'][20]['material_factor'] == .82
    again = client.post('/api/control/run',json={}).json()
    assert run['rows'] == again['rows']


def test_controller_uses_ann_and_not_simulator_as_internal_model():
    class CountingModel:
        def __init__(self):
            self.calls = 0
        def predict(self,x):
            self.calls += 1
            state = x[:,:6].copy()
            state[:,4] += .1*(x[:,6]-.7)
            return state
    model = CountingModel()
    settings = ControlSettings(horizon=3,samples=32,iterations=2)
    context = {'target':28,'ambient':30,'material':1,'tariff':.8}
    choose_action(model,np.array([.7,1200,.9,40,21,21]),np.array([.7,1200,.9]),context,settings,np.random.default_rng(42))
    assert model.calls == settings.horizon*settings.iterations


def test_single_step_measured_state_feedback_and_disturbance_response(client):
    payload = {'target':28,'samples':64}
    first = client.post('/api/control/step',json=payload).json()
    assert first['measured_next_state'] != first['predicted_next_state']
    second = client.post('/api/control/step',json={**payload,'state':first['measured_next_state'],'previous_command':first['action']}).json()
    assert second['measured_next_state'] != first['measured_next_state']
    disturbed = client.post('/api/control/step',json={**payload,'material_factor':.7}).json()
    assert disturbed['action'] != first['action']


def test_infeasible_limits_reported_not_hidden(client):
    run = client.post('/api/control/run',json={'max_energy_kwh':5,'max_temperature':35,'samples':32,'steps':12,'target_step':4,'disturbance_step':8,'horizon':2,'iterations':2}).json()
    assert run['summary']['predicted_infeasible_steps'] > 0
    assert run['summary']['energy_violations'] > 0
    assert run['summary']['temperature_violations'] > 0


@pytest.mark.parametrize('endpoint,payload',[
    ('run',{'steps':12,'target_step':12}),('run',{'target':99}),
    ('run',{'steps':72,'horizon':8,'samples':256,'iterations':5}),
    ('step',{'state':[.7,1200,.9,40,21]}),('step',{'state':[.7,1200,.9,40,21,'NaN']}),
    ('step',{'previous_command':[1.5,1200,.9]}),
])
def test_invalid_control_requests(client,endpoint,payload):
    assert client.post('/api/control/'+endpoint,json=payload).status_code == 422
