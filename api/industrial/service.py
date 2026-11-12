import json
import numpy as np
import pandas as pd
from .data import DATA, ARTIFACTS, FEATURES, operating_frame
from .models import load_operations
from .neural import load_neural


class IndustrialService:
    def __init__(self):
        self.bundle, self.history = load_operations()
        self.model = self.bundle['model']
        self.neural = load_neural()
        self.history['timestamp'] = self.history.timestamp.astype(str)
        self.history['forecast'] = self.model.predict(self.history[FEATURES])
        forest_flag = self.bundle['anomaly'].predict(self.history[FEATURES + ['energy_kwh']]) == -1
        residual_flag = abs(self.history.energy_kwh-self.history.forecast) > 3*self.bundle['radius']
        self.history['anomaly'] = forest_flag | residual_flag
        self.history['anomaly_reason'] = np.where(residual_flag, 'large_prediction_residual', np.where(forest_flag, 'isolation_forest', 'none'))
        train_rows = self.bundle['metrics']['train_rows']
        cal_rows = self.bundle['metrics']['calibration_rows']
        self.history['evaluation_split'] = (['train']*train_rows + ['calibration']*cal_rows
                                            + ['test']*(len(self.history)-train_rows-cal_rows))

    def predict(self, point):
        frame = operating_frame([point.machine_load, point.machine_speed, point.power_factor], point.temperature)
        energy = float(max(0, self.model.predict(frame)[0]))
        anomaly = score = None
        reasons = []
        if point.energy_kwh is not None:
            observed = frame.assign(energy_kwh=point.energy_kwh)
            if self.bundle['anomaly'].predict(observed)[0] == -1:
                reasons.append('isolation_forest')
            if abs(point.energy_kwh-energy) > 3*self.bundle['radius']:
                reasons.append('large_prediction_residual')
            anomaly = bool(reasons)
            score = float(self.bundle['anomaly'].decision_function(observed)[0])
        return {'predicted_energy_kwh': energy, 'interval_minutes': 15,
                'lower_kwh': max(0, energy-self.bundle['radius']), 'upper_kwh': energy+self.bundle['radius'],
                'interval_label': '90% nominal calibrated prediction interval',
                'operating_point': frame.iloc[0].to_dict(), 'anomaly': anomaly, 'anomaly_score': score,
                'anomaly_reasons': reasons, 'residual_threshold_kwh': 3*self.bundle['radius'],
                'source': 'synthetic_operations'}

    def summary(self):
        recent = self.history.tail(96)
        row = recent.iloc[-1]
        return {'rows': len(self.history), 'source': 'synthetic_operations', 'interval_minutes': 15,
                'latest_timestamp': row.timestamp, 'last_24h_energy_kwh': float(recent.energy_kwh.sum()),
                'last_24h_units': float(recent.production_rate.sum()*.25),
                'last_24h_anomalies': int(recent.anomaly.sum()),
                'machine': {'id': row.machine_id, 'status': 'historical simulation',
                            **{k: float(row[k]) for k in FEATURES}},
                'metrics': self.bundle['metrics']}

    def steel(self):
        path = ARTIFACTS / 'steel_metrics.json'
        if not path.exists():
            return {'available': False, 'message': 'Run python -m scripts.prepare_industrial --download-steel first.'}
        return {'available': True, 'metrics': json.loads(path.read_text(encoding='utf-8')),
                'history': pd.read_csv(DATA / 'steel_test_preview.csv').to_dict(orient='records')}
