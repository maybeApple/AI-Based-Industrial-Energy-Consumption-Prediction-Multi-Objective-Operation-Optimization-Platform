# Upstream provenance

This is a local derivative checkout of https://github.com/Kaviyathamizhan/EnergyOpt at commit `e7772bb9042d5ea24b38699cc9b29313ba30994b`.

Retained: React/Vite entry, Recharts chart component and dashboard styling base, Axios client pattern, FastAPI routers/services organization. New industrial modules replace the active household pipeline and LP optimizer. Original backend, scripts, models, components and tests remain for comparison; V1 uses `api.industrial_app:app` and `tests_industrial/` exclusively. Frontend entry now uses the industrial dashboard.

The upstream README identifies the project as MIT-licensed, but the LICENSE file it references is missing both at the source revision and on the upstream default branch. This checkout preserves that attribution and does not supply a license on the author's behalf. Confirm the applicable terms with the upstream author before redistributing the derivative.
