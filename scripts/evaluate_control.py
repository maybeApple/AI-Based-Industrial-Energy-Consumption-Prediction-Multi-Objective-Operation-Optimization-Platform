"""Reproducible default control run and a small multi-seed simulation evaluation."""
import json
from api.industrial.data import ARTIFACTS
from api.industrial.neural import load_neural
from api.industrial.schemas import ControlSettings
from api.industrial.control import run_control


if __name__ == '__main__':
    model=load_neural()
    results=[]
    for seed in [7,42,99]:
        run=run_control(model,ControlSettings(seed=seed))
        if seed==42:
            (ARTIFACTS/'control_default_run.json').write_text(json.dumps(run,indent=2),encoding='utf-8')
        results.append({'seed':seed,'ann_mpc':run['summary'],'fixed_commands':run['baseline_summary']})
    report={'source':'synthetic_dynamic_plant','model_sha256':model.artifact_hash,'results':results}
    (ARTIFACTS/'control_evaluation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
