# Authentic measured evidence (15 October 2026)

The uploaded archive `LH6041_Experiment_Results.zip` was the source of the three original measurement files. `raw_requests.csv` contains 1342 HTTP attempts: 1250 benchmark attempts, 60 fault-window attempts and 32 recovery retries. 1250 load attempts all returned 200. 32 fault-window attempts failed and all were retried successfully. `results.json` documents environment (2 logical CPUs, Linux x86_64, cloud version 3.1-ai) and failure timing.

This is **real measured traffic** to an **isolated, local-only** container using a synthetic test database. It is not Raspberry Pi latency, not genuine customer transactions, not evidence of autoscaling, automatic instance failover or multi-restaurant tenant isolation. Test client and Docker container ran on the same small cloud host. The live 15001 service was not intentionally stopped for this experiment.

Measurements: concurrency 1, 5, 10, 25, 50; 250 successful attempts per level; p50/p95/p99 over successful requests only; throughput = attempts / elapsed seconds. The figures are re-generated from `load_summary.csv` by `03_Source_Repository/platform_eval/plot_evaluation.py` or included as PNG here.

Do not publish real customer databases. The benchmark's test SQLite database is intentionally excluded from the submission as it is reproducible from the source script.


## NEW: separate elasticity/failover laboratory

Original verified records are in `elasticity_failover_actual/`. They demonstrate automated scaling from one to two **temporary same-VM application replicas** and replacement after killing one replica, not deployment of this behavior to the live `15001` service. See its `EVIDENCE_INTERPRETATION.md` and regenerate the included plot with `platform_eval/plot_elasticity.py`. The prior single-instance outage test remains valid independently and required explicit restart; do not merge or relabel the two experiments.
