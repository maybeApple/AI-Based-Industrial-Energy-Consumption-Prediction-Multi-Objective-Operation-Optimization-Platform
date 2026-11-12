"""Train and evaluate ANN dynamics: python -m scripts.train_neural."""
import json
from api.industrial.neural import train_neural

if __name__ == '__main__':
    model = train_neural()
    print(json.dumps({k:v for k,v in model.report.items() if k != 'loss_curve'}, indent=2))
