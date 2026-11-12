# Measured industrial energy benchmarks

Open **Real-data Validation** and select a measured dataset. Each model is trained and tested on its own asset or site, without combining the sources. The first and final 48-hour test windows can be viewed and exported; full-test accuracy does not change when switching chart windows. All results are rolling one-step replays: a meter reading becomes usable after its interval ends.

| Source | Included use | Limits |
| --- | --- | --- |
| [UCI Steel Industry Energy Consumption](https://archive.ics.uci.edu/dataset/851/steel+industry+energy+consumption) | Shipped. Steel plant electricity, 35,040 measured intervals. A retrained LightGBM, the previous model, and the last-reading baseline are scored on the same test timestamps. | The test period has been inspected before. No machine commands or actual throughput. |
| [Industrial Asset-Level Electrical Energy Dataset](https://doi.org/10.5281/zenodo.19180972) | Shipped as a separately trained benchmark on the Irish site's compressed-air meter, comp_a. The publisher's full release covers 43 assets; this benchmark uses one. | Meter telemetry supports forecasting. It does not show compressor commands, pressure targets or output. |
| [HIPE](https://zenodo.org/records/14054775) | Candidate. KIT publishes 5-second meter readings for ten machines and a main meter in a power-electronics plant. Suitable for machine-level load forecasting and equipment-state research. | Metering does not provide aligned product counts or actuator commands for the current optimizer. |
| [Discrete Manufacturing Dataset](https://github.com/HumanCenteredTechnology/SME-Manufacturing-Dataset) | Candidate for research. Company A logs power, produced items, cycle time and operating status together. | Supports measured energy-per-item analysis; lacks the continuous settings needed to fit the current actuator model. The authors state research and educational availability. |
| [CNC machining data with command and response traces](https://data.mendeley.com/datasets/gtvvwmz7r7/2) | Candidate for a separate machine-specific control study. The [data paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC12269468/) describes commanded and actual position and speed, torque, load, current and power. | The records cover specific machining programs, materials, and equipment. Validate held-out programs and command coverage before using the data for counterfactual settings or control. |

The first two sources are CC BY 4.0. Attribution and links are displayed in the dashboard and the SCADA archive checksum is pinned in the preparation script. The downloadable project contains trained artifacts and derived preview rows, rather than the 218 MB SCADA archive.

## Reproduce the release

Run the commands below from the project root in PowerShell after setup. The original steel meter CSV is already included. Download the original SCADA ZIP from its DOI above and save it as the file shown in the second command. Keep it outside the distributable project or in the excluded runtime folder.

~~~powershell
.\.venv\Scripts\python.exe -m scripts.train_real_steel --output .\runtime\real-steel-training
.\.venv\Scripts\python.exe -m scripts.prepare_real_benchmarks --steel-run .\runtime\real-steel-training --scada-zip .\runtime\scada-19180972.zip
~~~

Omit the SCADA option to regenerate only the steel comparison. The API serves the generated evaluation files; it does not train or download data during requests. The original steel endpoint remains available.

SCADA preparation keeps only the published ALL phase for comp_a and checks the reliability flag and nonnegative finite energy. The 15-minute UTC grid is preserved, including missing or rejected intervals. A forecast is scored only if the target, previous interval and same interval 24 hours earlier are all available, ensuring identical samples for LightGBM, last reading and prior-day baselines. LightGBM loss and blending weight are selected on the chronological validation period, then the model is refitted on pre-test rows. Features use the local calendar and earlier metered values only.

The last 48 hours of the compressor test period have near-zero measured consumption. Their error metrics should not be extrapolated to active operation. The forecast and control results answer different questions: neither measured forecasting benchmark demonstrates plant savings, safe closed-loop control, or transfer of a model between assets.
