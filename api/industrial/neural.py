"""Three-hidden-layer artificial neural network identifies the dynamic simulator."""
import hashlib
import json
from time import perf_counter
import joblib
import numpy as np
import pandas as pd
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.multioutput import MultiOutputRegressor
from lightgbm import LGBMRegressor
from threadpoolctl import threadpool_limits
from .data import ARTIFACTS, DATA
from .plant import INPUT_NAMES, STATE_NAMES, STATE_LOW, STATE_HIGH, transition_dataset

NEURAL_VERSION = 1


class NeuralDynamics:
    def __init__(self, network, input_scaler, target_scaler, report, artifact_hash=None):
        self.network, self.input_scaler, self.target_scaler = network, input_scaler, target_scaler
        self.report, self.artifact_hash = report, artifact_hash

    def predict(self, x):
        prediction = self.target_scaler.inverse_transform(self.network.predict(self.input_scaler.transform(x)))
        return np.clip(prediction, STATE_LOW, STATE_HIGH)


def train_neural():
    started = perf_counter()
    x, y, episode = transition_dataset()
    train, test = episode < 144, episode >= 144
    sx, sy = StandardScaler().fit(x[train]), StandardScaler().fit(y[train])
    network = MLPRegressor(hidden_layer_sizes=(96,64,32), activation='relu', solver='adam',
        batch_size=256, learning_rate_init=.002, max_iter=250, early_stopping=True,
        validation_fraction=.12, n_iter_no_change=20, tol=1e-5, random_state=42)
    with threadpool_limits(limits=2):
        network.fit(sx.transform(x[train]), sy.transform(y[train]))
        pred = sy.inverse_transform(network.predict(sx.transform(x[test])))
    report = {'source': 'synthetic_dynamic_plant', 'architecture': [len(INPUT_NAMES),96,64,32,len(STATE_NAMES)],
        'hidden_layers': 3, 'activation': 'ReLU', 'optimizer': 'Adam', 'backend': 'scikit-learn MLPRegressor',
        'epochs': int(network.n_iter_), 'parameter_count': int(sum(w.size for w in network.coefs_)+sum(b.size for b in network.intercepts_)),
        'train_rows': int(train.sum()), 'test_rows': int(test.sum()), 'episodes': 180,
        'split': '144 independent training trajectories / 36 held-out test trajectories; 12% internal training validation',
        'train_episode_max': 143, 'test_episode_min': 144,
        'mae': {name: float(mean_absolute_error(y[test,i], pred[:,i])) for i,name in enumerate(STATE_NAMES)},
        'persistence_mae': {name: float(mean_absolute_error(y[test,i], x[test,i])) for i,name in enumerate(STATE_NAMES)},
        'r2': {name: float(r2_score(y[test,i], pred[:,i])) for i,name in enumerate(STATE_NAMES)},
        'input_names': INPUT_NAMES, 'output_names': STATE_NAMES,
        'loss_curve': [float(v) for v in network.loss_curve_], 'training_seconds': round(perf_counter()-started,2),
        'note': 'Simulation identification. No real plant validation or stability guarantee.'}
    # Recursive held-out rollout: no measured state is injected inside the prediction horizon.
    starts = np.array([e*50+j for e in range(144,180) for j in range(46)])
    recursive = x[starts,:6].copy()
    rollout = []
    with threadpool_limits(limits=2):
        for horizon in range(5):
            future = x[starts+horizon].copy()
            future[:,:6] = recursive
            recursive = np.clip(sy.inverse_transform(network.predict(sx.transform(future))), STATE_LOW, STATE_HIGH)
            truth = y[starts+horizon]
            rollout.append({'horizon':horizon+1, 'energy_mae_kwh':float(mean_absolute_error(truth[:,5],recursive[:,5])),
                            'production_mae':float(mean_absolute_error(truth[:,4],recursive[:,4])),
                            'temperature_mae':float(mean_absolute_error(truth[:,3],recursive[:,3]))})
    report['recursive_test_rollout'] = rollout
    report['rollout_windows'] = len(starts)
    report['rollout_note'] = 'Five-step open-loop state predictions with held-out recorded commands and exogenous inputs; no measurement correction inside a window.'
    # Compare a tree model on the same trajectory split and targets, independent of the ANN controller.
    tree = MultiOutputRegressor(LGBMRegressor(n_estimators=160,learning_rate=.06,num_leaves=31,n_jobs=2,verbosity=-1,random_state=42))
    train_frame = pd.DataFrame(x[train],columns=INPUT_NAMES)
    test_frame = pd.DataFrame(x[test],columns=INPUT_NAMES)
    with threadpool_limits(limits=2):
        tree.fit(train_frame,y[train])
        tree_pred = tree.predict(test_frame)
    report['lightgbm_comparison_mae'] = {name:float(mean_absolute_error(y[test,i],tree_pred[:,i])) for i,name in enumerate(STATE_NAMES)}
    report['comparison_note'] = 'LightGBM and ANN evaluated on the same held-out dynamic transitions. Tree model is a benchmark, not the MPC internal model.'
    ARTIFACTS.mkdir(parents=True, exist_ok=True); DATA.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(x, columns=INPUT_NAMES)
    for i, name in enumerate(STATE_NAMES):
        frame['next_'+name] = y[:,i]
    frame['episode'] = episode
    frame.to_csv(DATA / 'dynamic_transitions.csv', index=False)
    report['dataset_sha256'] = hashlib.sha256((DATA / 'dynamic_transitions.csv').read_bytes()).hexdigest()
    joblib.dump({'version': NEURAL_VERSION, 'network': network, 'input_scaler': sx, 'target_scaler': sy, 'report': report}, ARTIFACTS / 'neural_dynamics.joblib')
    (ARTIFACTS / 'neural_metrics.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return load_neural()


def load_neural():
    path = ARTIFACTS / 'neural_dynamics.joblib'
    if not path.exists():
        return train_neural()
    bundle = joblib.load(path)
    if bundle.get('version') != NEURAL_VERSION:
        return train_neural()
    return NeuralDynamics(bundle['network'], bundle['input_scaler'], bundle['target_scaler'], bundle['report'], hashlib.sha256(path.read_bytes()).hexdigest())
