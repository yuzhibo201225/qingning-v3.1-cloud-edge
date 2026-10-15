# QingNing V3.1 — Edge-First Cloud–Edge Restaurant Ordering

A functional restaurant-ordering prototype built on a physical Raspberry Pi 3B+ (edge) and an independent Ubuntu cloud VM. Edge-side orders are durable in SQLite even if the remote cloud service becomes unavailable. V3.1 adds daily/weekly cloud reporting and an optional DeepSeek advisory feature.

## Architecture

```text
Customer phone -- restaurant LAN --> Raspberry Pi (Flask + SQLite)
                                           |  QR menu, cashier, dish management
                                           |  asynchronous versioned sync
                                           v
                                    Ubuntu VM (Flask + SQLite)
                                    dashboard + historical analytics
                                           |
                                    optional server-side DeepSeek API
```

- The **edge database is authoritative** for restaurant orders. Customer requests do not synchronously depend on cloud availability.
- **Phone and Raspberry Pi must be on a mutually reachable LAN.** The Raspberry Pi and cloud do **not** need the same Wi-Fi; the Pi needs an outbound route to the cloud public endpoint.
- The **production cloud deployment** is one Docker Compose container on one VM. It has **no production autoscaler, multi-host high availability, or multi-restaurant tenant isolation**.
- `platform_eval/elasticity_failover_experiment.py` instead demonstrates **laboratory-scale application replica elasticity on a single host** with isolated test stores. It is not deployed on the public cloud endpoint.
- No real payment integration is implemented. Order totals do not equal collected revenue.

历史订单快照（historical order price snapshots）保留已下单菜品的原始价格，不随菜单后续改价而改变。

## Components

| Path | Role |
|---|---|
| `edge/` | Raspberry Pi ordering API, local SQLite, sync agent, web UI, Docker files |
| `cloud/` | Cloud order mirror, dashboard, daily/weekly reports, optional AI module |
| `ops/` | Optional Raspberry Pi cashier kiosk scripts and network diagnostics |
| `platform_eval/` | Reproducible synthetic workload, fault injection, test autoscaler, cost model |
| `experiments/` | Synthetic load and isolated failover raw request/event CSV + JSON |
| `cost_analysis/` | Explicitly illustrative cost-model assumptions, not actual invoices |
| `tests/` | Python and JavaScript checks |
| `.github/workflows/ci.yml` | Automated checks; **not** an automatic production deploy pipeline |

## Local/edge setup

1. Install Docker and Docker Compose on an ARM64 Raspberry Pi with a reachable restaurant LAN.
2. Copy `edge/.env.example` to `edge/.env` and use new, independent secrets. Set `PUBLIC_EDGE_URL=http://EDGE_LOCAL_IP:18080`, and `CLOUD_URL=http://CLOUD_PUBLIC_IP:15001` to match your deployment.
3. From `edge/` run `docker compose -p pi-cafe-classroom up -d --build` if base images and package access are available. In restricted networks, pre-load a matching ARM64 base image; do not copy x86_64 layers to ARM64.
4. Open `http://127.0.0.1:18080/cashier` on the Pi; create QR codes for a real LAN address under `/qr`.

## Cloud setup

1. On an independent Ubuntu VM, copy `cloud/.env.example` to `cloud/.env`, use the same new `SYNC_TOKEN` as the edge, and set a distinct `DASHBOARD_PIN` and `CLOUD_SESSION_SECRET`.
2. Run `docker compose -p pi-cafe-classroom-cloud up -d --build` in `cloud/`.
3. Check the cloud's `/health` endpoint and the protected dashboard on port `15001`.
4. Set `DEEPSEEK_API_KEY` only in the server-side `.env` if optional AI advisory is desired. Never send the key to a browser or commit it.

**Security:** The example deployment uses HTTP and a teaching-grade PIN; it is **not ready for public production use** without HTTPS, access restrictions, logging/monitoring, backup controls, and secret rotation. The source is public, but access credentials and persistent business data must remain private.

## Tests and evidence

```bash
python3 -m pip install -r edge/requirements.txt -r cloud/requirements.txt pytest
python3 -m pytest tests -q
```

See `platform_eval/README.md` to regenerate synthetic benchmark CSV and the isolated two-replica elasticity/failover experiment. These tests should be run on **staging/isolated containers**, not against customer orders.

Actual isolated cloud-ingest measurement: five concurrency levels (1/5/10/25/50), 250 requests each, 1250/1250 accepted. Isolated 1-to-2 replica experiment: 1.648 s to second replica ready, 1.370 s automatic test-replica replacement, 175/175 fault-window requests successful. Measurements are **not** production SLAs or cross-VM failover results. See `experiments/` for machine-readable evidence.

## Public repository scope

This repository intentionally contains **source code and reproducibility artifacts only**. Academic papers, slides, private admin credentials, real SQLite databases, deployment-specific `.env` files and backup videos are excluded.

## License

No open-source license has been selected. Public visibility permits viewing the repository; it does not by itself grant permission to redistribute or commercially reuse the code or media assets. Contact the author before reuse.
