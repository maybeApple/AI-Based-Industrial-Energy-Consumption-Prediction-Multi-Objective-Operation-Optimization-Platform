"""Run from repo root: python -m scripts.prepare_industrial [--download-steel]."""
import argparse
import io
import json
import urllib.request
import zipfile
from api.industrial.data import DATA
from api.industrial.models import train_operations, train_steel
from api.industrial.neural import train_neural

STEEL_URL = 'https://archive.ics.uci.edu/static/public/851/steel+industry+energy+consumption.zip'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--download-steel', action='store_true')
    args = parser.parse_args()
    bundle, _ = train_operations()
    print(json.dumps(bundle['metrics'], indent=2))
    neural = train_neural()
    print(json.dumps({k:v for k,v in neural.report.items() if k != 'loss_curve'}, indent=2))
    path = DATA / 'Steel_industry_data.csv'
    if args.download_steel:
        with urllib.request.urlopen(STEEL_URL, timeout=60) as response:
            archive = zipfile.ZipFile(io.BytesIO(response.read()))
        name = next(n for n in archive.namelist() if n.endswith('Steel_industry_data.csv'))
        # Extract only the known CSV into a fixed path.
        path.write_bytes(archive.read(name))
    if path.exists():
        print(json.dumps(train_steel(path), indent=2))
    else:
        print('Demo ready. Optional real-data benchmark: add --download-steel.')


if __name__ == '__main__':
    main()
