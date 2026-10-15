# V3.1 isolated HTTP measurement on the actual Alibaba Cloud VM

**No CSV in this repository is a real measurement until you run the commands below. Never invent values.**

Prerequisites: existing cloud host, Docker and the locally present `pi-cafe-classroom-cloud:local` image, V3.1 files in `/root/pi-cafe-classroom/cloud`. CPU and memory load from this isolated extra container may compete with the live demo on a 1 GiB VM: perform after the presentation; monitor free memory; start with `--requests-per-level 100` if necessary.

```bash
cd /root/pi-cafe-classroom/platform_eval
python3 evaluate.py --app-dir /root/pi-cafe-classroom/cloud --levels 1,5,10,25,50 --requests-per-level 250
```

The program starts ONE temporary `lh6041-eval-*` container, bound ONLY to `127.0.0.1:15011`, with its own ephemeral sync key and isolated SQLite file. It read-only mounts V3.1 app source and refuses to proceed if `/health` is not `version=3.1-ai`. It never stops or writes to `cafe-cloud`, port 15001, or the real cloud database. The extra container and test key are removed in `finally`; benchmark orders remain only in its own `runs/` subdirectory.

Each invocation creates a new `runs/run_<UTC_TIMESTAMP>_<ID>/` containing:
- `raw_requests.csv`: one row per HTTP request, measured client-side, including fault window and retries;
- `load_summary.csv`: concurrency, request volume, p50/p95/p99 of successful requests, throughput, errors;
- `results.json`: exact VM environment and failure report; records shortcomings of single-node design;
- `isolated_cloud_db/benchmark.sqlite3`: generated synthetic records (not real customers).

Create reproducible plots where Python has matplotlib:

```bash
python3 plot_evaluation.py runs/<EXACT_RUN_DIRECTORY>/load_summary.csv --out-dir runs/<EXACT_RUN_DIRECTORY>
```

Download output from Windows PowerShell (run `pwd` to identify the local destination):

```powershell
scp -r root@CLOUD_PUBLIC_IP:/root/pi-cafe-classroom/platform_eval/runs .\runs
```

Safety and interpretation:
- `p50/p95/p99` are only over successful requests; error rate is separate.
- This is HTTP sync order ingest, not end-to-end latency from the phone to the Pi.
- Fault test **manually** stops and restarts one isolated instance. Recovery ≠ auto-failover.
- Load client shares CPU/network with server, reducing generalizability.
- Test requests have synthetic IDs, no real customer data, and are excluded from the live cloud dashboard.
- Five concurrency levels do not guarantee actual performance degradation; report the measured limits honestly.
- To observe Raspberry Pi asynchronous resynchronization, capture its `cafe-sync` logs with timestamps during a separate cloud-offline test.
