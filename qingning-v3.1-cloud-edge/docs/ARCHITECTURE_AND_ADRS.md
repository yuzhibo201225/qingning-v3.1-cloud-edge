# QingNing V3.1: architecture and decision records

**Status:** documentary record of the existing prototype, not a claim of high availability or multi-tenancy.

## Industry problem and the cloud force

The named pilot customer is a small independent restaurant with unreliable outbound Internet access, a shop-floor HDMI cashier, and a desire for off-site reporting. Its most time-sensitive operations—taking an order, recording it and displaying it at the counter—should continue if the external connection fails. Its non-local concerns are consolidated historical reporting, remotely viewing operational history and disaster recovery beyond the premises. **Resilience against cloud loss is achieved at the edge; remote access and off-site persistence are the positive reasons to use cloud resources.** In a single shop with no remote users or off-site recovery requirement, the cloud would not be strictly necessary. A future multi-site platform would have a stronger geographical-distribution justification, but such a platform is not yet implemented.

## Deployed architecture

`Phone browser --local Wi-Fi--> Raspberry Pi / edge Flask + SQLite --> background sync (5 s nominal) --> Alibaba Cloud Ubuntu VM / Flask + SQLite --> browser dashboard`.

The V3.1 enhancement runs **only on the cloud**: historical daily/ISO-week aggregates and an optional server-side DeepSeek advisory endpoint. The LLM receives order aggregates, not individual customer notes. When the API key or outbound connectivity is absent, AI reports are unavailable but ordinary ordering and statistics remain independent. QR URLs use the edge device's LAN IP; the cloud dashboard is not a reverse proxy for mobile ordering.

## Six architecture decision records

### ADR-01: Local first, rather than cloud-first order submission
**Decision.** The edge persists every accepted order locally before returning success; remote replication occurs afterward. **Rejected alternative.** Phone sends each order directly to the remote VM. **Trade-off.** The shop stays operational while Internet connectivity is lost, at the price of local disk dependence and eventual rather than immediate off-site visibility. **Reason.** For a small shop, transaction availability during network disruption is more critical than instantaneous centralized statistics. **Evidence.** Local cashier operation under disabled Wi-Fi; cloud-stop functional demonstration. Quantitative RPO/RTO requires additional timestamps.

### ADR-02: Embedded SQLite on edge and cloud rather than hosted relational databases
**Decision.** Persist order state in SQLite using explicit transactions and WAL on each device. **Rejected alternatives.** Managed RDS/PostgreSQL and a shared cloud-only SQL instance. **Trade-off.** Cheap, small dependency footprint and convenient offline operation, at the price of a single-writer bottleneck and operational backups. **Reason.** The launch prototype uses one Raspberry Pi 3B+ and a very small VM; database complexity needs to match traffic. **Risk.** SQLite is not a horizontal shared database; the isolated load test must identify its limits.

### ADR-03: Asynchronous periodic order replication rather than synchronous two-phase commitment
**Decision.** Edge sync polls pending records, sends a versioned payload with authenticated HTTP and marks local state synced only after a matching acknowledgement. **Rejected alternatives.** Synchronous RPC within the customer request and distributed transactions. **Trade-off.** Short user-facing transaction path and reconnection retries; the cloud can lag by at least the polling interval. **Reason.** The edge must continue independently. **Evidence.** Code `edge/sync_agent.py`, unique cloud order identifier and version checking. **Risk.** Stalled network/edge power failure before sync leaves remote data incomplete.

### ADR-04: Separate ARM64 and AMD64 Docker images instead of one uncontainerized installation
**Decision.** Docker Compose describes each service; Raspberry Pi and cloud use architecture-matching images. **Rejected alternative.** Direct ad-hoc Python processes with global dependency installation. **Trade-off.** Rebuild and image-transfer requirements, but reproducible service configuration and health checks. **Reason.** Edge hardware is ARM64 and cloud host AMD64; the two services have different load and deployment profiles. **Evidence.** Compose YAML, Dockerfiles and image build instructions. **Limit.** Compose by itself does not provision the Alibaba Cloud VM; full infrastructure provisioning IaC remains incomplete.

### ADR-05: Local LAN QR ordering plus remote read-only operations dashboard
**Decision.** Table QR codes resolve to a reachable edge private IP. The cloud exposes remote operational history, not customer checkout. **Rejected alternative.** Automatically routing customer orders to a public cloud application. **Trade-off.** Simpler local service and fewer Internet failure modes versus QR codes needing regeneration if local addressing changes. **Reason.** A shop has operational control of its local Wi-Fi. **Evidence.** QR generation endpoint and independent cloud analytics. **Limit.** DHCP changes and client isolation can disrupt mobile access; no public QR gateway is implemented.

### ADR-06: Deterministic aggregates before third-party LLM analysis
**Decision.** The V3.1 history endpoint computes daily/weekly counts and totals directly from stored order snapshots; the DeepSeek client only interprets aggregates and stores reports with cache controls. **Rejected alternatives.** Asking the model to count raw individual orders and streaming every note or order record to the provider. **Trade-off.** Separate implementation paths and remote-model cost, but reproducible numbers and reduced disclosure of personal data. **Reason.** AI must not be the authoritative source for revenue, orders or item counts. **Evidence.** `cloud/analytics.py`, `cloud/ai_engine.py`, unit tests. **Limit.** Order amount is not verified payment or profit; generated business advice has not been validated against future outcomes.

## Requirements/measurement traceability

| Property | Launch target (candidate; not a proven guarantee) | Evidence/current limit |
|---|---|---|
| Local checkout success | Continue during cloud outage | Functional test; no month-long uptime study |
| Critical order submission p50/p95/p99 | Measure all; decide SLO based on observed load | `platform_eval/evaluate.py` targets isolated cloud **ingest**, not phone-to-edge latency |
| Cloud sync durability | No duplicate order IDs and eventual delivery after reconnection | ID/version logic and reconciliation; quantify with raw logs |
| Availability/RTO | Document measured outage and recovery | Single-cloud-instance stop requires manual restart; **no automatic failover** |
| Scale | 1 pilot restaurant, 1 cloud VM; assess 10x/100x scenarios | No demonstrated automatic scaling |
| Tenancy | Single pilot restaurant | **Multi-tenant isolation not implemented**; eight tables are NOT eight tenants |
| Cost | Provider bill + per-request and per-tenant model | Actual bill and valid request-rate assumptions required |
| Security | PIN-protected dashboard, sync token, no repo secrets | Public HTTP currently; HTTPS and stronger controls required for production |
| Compliance | Limit personal fields and API-data exposure | Formal retention/data residency/GDPR assessment not completed |

## Threat model and known limitations

Potential attackers can attempt to access the publicly reachable HTTP dashboard, steal tokens on unencrypted networks, force expensive AI API calls or exhaust SQLite's serialized write path. PINs and sync tokens must remain only in server environment files. Rotate any leaked DeepSeek key. Confirm HTTPS, rate limits, data retention and backup/recovery procedures before production. Cost, automatic elasticity, multi-tenancy, managed cloud service and alerting claims must not be stated as achieved without independent supporting evidence.
