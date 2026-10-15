# Measured isolated application-level elasticity (15 October 2026)

This directory contains the uploaded original event and request records from the independent lab run. Data were validated against the raw CSV and the accompanying JSON before inclusion.

| Item | Observed | What it means |
|---|---|---|
| Workload | baseline 9, surge 240, failure stage 175; **424/424 HTTP 200** | Synthetic orders to localhost-only proxy; not mobile/Pi end-to-end |
| Surge -> second replica healthy | **1.648 s** | 30 req/s offered, controller threshold 11 req/s over a 2-second window |
| Scale-down | **Yes**, after ~4.13 s idle | Temporary application replicas only |
| Injected replica failure -> replacement healthy | **1.370 s** | One replica killed; second stayed serving traffic |
| Failure-stage requests | **175/175 succeeded**, p95=13.620 ms | Proxy switched traffic within one VM |
| First two seconds after kill | **50/50 succeeded**, p95=26.939 ms | Short one-off experiment; no availability SLA |
| Unique accepted test orders | **424**, missing 0, duplicates 0 | Only synthetic SQLite data; shared single-host SQLite |

**Deployment boundary:** The live Alibaba Cloud port 15001 remains a single application container on one VM. Autoscaling/proxy logic above belongs to an **isolated localhost-only laboratory** on ports 15110, 15121, 15122. Neither VM failure tolerance, multi-zone HA, managed autoscaling groups, multi-tenant isolation, nor sustained peak load is demonstrated. One experimental run only.

Regenerate chart:

```bash
python3 ../../../03_Source_Repository/platform_eval/plot_elasticity.py autoscale_events.csv --out elasticity_replicas.png
```
