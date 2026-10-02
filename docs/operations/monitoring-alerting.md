# Monitoring and alerting

The pilot runs Prometheus, Alertmanager and node-exporter on the same VM (Compose profile
`monitoring`, ADR-0014). Rules are in `deploy/pilot/monitoring/alerts.yml`.
- **Tests:** each important rule has a promtool unit test (`alerts.test.yml`), run in CI's
  `deploy-config` job.
- **External uptime check (go-live checklist):** a monitor on another network must probe
  `https://<domain>/api/v1/health` every minute. A monitor on the VM cannot report that the VM
  itself is down.

Start the monitoring profile:
```bash
cd /opt/vanshavali && source deploy/pilot/scripts/lib.sh
dc --profile monitoring up -d prometheus alertmanager node-exporter
ssh -L 9090:127.0.0.1:9090 -L 9093:127.0.0.1:9093 vanshavali@<vm>   # UIs: localhost:9090, :9093
```

## Logs
- **Format:** one JSON object per line (`VSH_LOG_FORMAT=json`). Fields: `ts`, `level`, `logger`,
  `msg`, `request_id`, plus `method`, `route`, `status`, `duration_ms` on access lines. Docker
  rotates them at 20 MB × 5 files per container. Read them with
  `dc logs --since 1h backend worker | grep '"level": "ERROR"'`.
- **Request IDs:**
  - every response carries `X-Request-ID`;
  - a user-reported problem can be traced with `dc logs backend | grep <id>`;
  - worker jobs log their own lines.
- **What is never logged** (tested; `docs/security/privacy-model.md`):
  - request/response bodies, cookies, headers other than the request ID;
  - raw paths and query strings (access logs use route templates; signed download tokens travel
    in query strings);
  - email bodies, subjects and full addresses (masked `r***@domain`);
  - tokens;
  - GEDCOM file content (import failures log the exception type and code location only);
  - document content or OCR text;
  - settings and secrets.

  Caddy writes no access log at all.
- **Retention:** the pilot keeps logs on the VM only (rotation ≈ 100 MB per container). Shipping
  them to a managed log service is a week-1 improvement (go-live checklist, "Recommended"). If you
  ship them, keep the same exclusions and a retention of 30–90 days.

## Health checks

| Endpoint | Meaning | Used by |
|---|---|---|
| `GET /api/v1/health` | Liveness: the process serves requests; touches no dependency | Docker healthcheck (each backend replica), external uptime monitor |
| `GET /api/v1/health/ready` | Readiness: database reachable, Redis reachable, **RLS in force** (503 in production if the app role bypasses RLS) | `deploy.sh` (every replica before smoke), manual checks |
| `GET /api/v1/metrics` | Prometheus text, Bearer token | Prometheus (each replica via Compose DNS) |

Readiness checks include Redis because the app runs with `JOB_MODE=rq` and `RATE_LIMIT_BACKEND=redis`.

## Metrics

| Metric | Type | Scope | What it tells you |
|---|---|---|---|
| `vsh_http_requests_total{method,route,status}` | counter | per process | request rate and error rate by route template and status class |
| `vsh_http_request_duration_seconds{method,route}` | histogram | per process | latency (p50/p95/p99 by route) |
| `vsh_requests_shed_total` | counter | per process | requests refused by admission control (503 `server_busy`) |
| `vsh_db_up` | gauge | per process | the replica reached PostgreSQL during the scrape |
| `vsh_db_pool_size`, `vsh_db_pool_checked_out`, `vsh_db_pool_overflow` | gauge | per process | DB pool usage (saturation precedes shedding) |
| `vsh_queue_up` | gauge | shared | Redis answered |
| `vsh_jobs_queued`, `vsh_jobs_running`, `vsh_jobs_scheduled`, `vsh_jobs_failed`, `vsh_workers` | gauge | shared | queue depth, in-flight jobs, retries waiting, failed jobs (kept 7 days), live workers |
| `vsh_job_runs_total{job,outcome}` | counter | shared | job outcomes per job (`documents.process_document`, `mailer.deliver`); each retry counts |
| `vsh_job_duration_seconds_sum/_count{job}` | summary | shared | mean job duration; for `documents.process_document` this is scan + previews + **OCR** time |
| `vsh_events_total{event}` | counter | shared | `mail_delivery_failed`, `mail_send_failed`, `storage_error`, `document_preview_failed`, `document_ocr_failed`, `gedcom_import_failed` |
| `node_*` | node-exporter | host | CPU, memory, disk, network |
| `vsh_backup_last_status`, `vsh_backup_last_success_timestamp_seconds`, `_size_bytes`, `_duration_seconds` | textfile | host | written by `backup.sh` |

- **Shared counters:** counters marked "shared" live in Redis. Every replica reports the same
  value, so aggregate them with `max()`, not `sum()`. The alert rules do.
- **Restarts:** counters reset when the process restarts (per-process counters) or when Redis loses
  its data. Use `increase()`/`rate()`.

Useful queries:
```promql
sum by (route) (rate(vsh_http_requests_total[5m]))                                  # request rate
sum(rate(vsh_http_requests_total{status="5xx"}[5m])) / sum(rate(vsh_http_requests_total[5m]))   # error ratio
histogram_quantile(0.95, sum by (le, route) (rate(vsh_http_request_duration_seconds_bucket[10m])))
max(vsh_job_duration_seconds_sum{job="documents.process_document"}) / max(vsh_job_duration_seconds_count{job="documents.process_document"})  # mean document processing (OCR) time
sum(vsh_db_pool_checked_out) / sum(vsh_db_pool_size + 10)                           # pool saturation
```

## Alerts and responses
Severity `page` = act now (email to the on-call address; add SMS/chat in Alertmanager when the
pilot has an on-call rota). Severity `warn` = act within the working day.

| Alert | Fires when | First response |
|---|---|---|
| `NoApiReplicas` / `ApiReplicaDown` | no replica / one replica not scraped for 2 min | `dc ps`; `dc logs --tail 200 backend`; `dc up -d backend`. If every replica fails readiness, check the DB (next row). Incident runbook "Service outage" |
| `DatabaseUnavailable` | no replica reaches PostgreSQL for 1 min | Provider status page and console (instance state, storage full, connections); `dc exec backend python -c "…"` readiness; incident runbook "Database failure" |
| `HighServerErrorRate` (5xx spike) | > 5% of requests are 5xx for 5 min | Logs by `request_id` and route; which dependency? (`storage_unavailable` → storage; `server_busy` → capacity). Roll back if it started with a deploy (`rollback.sh`) |
| `SustainedHighLatency` | p95 > 500 ms for 15 min (uploads, imports and exports excluded) | Pool saturation, `LoadShedding`, DB CPU (provider metrics), host CPU. Add a backend replica (`BACKEND_REPLICAS`) if CPU-bound; re-run the performance certification |
| `LoadShedding` | admission control refused requests for 10 min | Capacity: add replicas or a bigger VM (performance.md sizing) |
| `JobQueueUnreachable` | Redis not answering for 2 min | `dc ps redis`; `dc logs redis`; `dc up -d redis` (AOF keeps the queue). Incident runbook "Redis failure" |
| `NoWorkers` | no worker for 5 min | `dc up -d worker`; `dc logs worker` |
| `JobBacklog` | > 50 queued jobs for 15 min | Worker alive? OCR-heavy uploads? Raise `WORKER_REPLICAS` temporarily (RAM permitting) |
| `JobFailures` | > 5 failed runs of one job in 30 min | `dc logs worker \| grep -i failed`; `vsh_events_total` for the cause |
| `EmailDeliveryFailing` | > 3 delivery failures in 30 min | `docs/operations/email-runbook.md` |
| `StorageErrors` | any object-store error in 15 min | Provider status; credentials (rotated?); bucket policy; incident runbook "Object-storage failure" |
| `GedcomImportFailures` | > 2 failed imports in 1 h | Logs (exception type and code location); reproduce with the user's permission on staging only |
| `DiskSpaceLow` | < 15% free | `docker system df`; `docker image prune -af --filter until=168h`; old local backups (`/var/lib/vanshavali/backups`); grow the disk |
| `MemoryPressure` | < 10% available for 10 min | Fewer worker replicas (OCR is memory-hungry); ClamAV needs about 1.5–2.5 GB; resize the VM |
| `BackupFailed` / `BackupStale` | last run failed / no success for 26 h | `tail -100 /var/lib/vanshavali/backup.log`; run `backup.sh manual`; backup-restore runbook |

## Alert routing
- Alertmanager emails the operations mailbox (`/etc/vanshavali/alertmanager.yml`, from
  `alertmanager.yml.example`), using the same SMTP provider as the app but separate credentials.
- **Test the route at go-live:** send a test alert to Alertmanager and confirm the email arrives.
  ```bash
  curl -XPOST localhost:9093/api/v2/alerts -H 'Content-Type: application/json' \
    -d '[{"labels":{"alertname":"GoLiveTest","severity":"page"}}]'
  ```
- **External signals (configured outside this repository):**
  - the uptime monitor;
  - the backup heartbeat (`BACKUP_HEARTBEAT_URL`);
  - the provider's alarms on the managed DB (CPU, free storage, connections) and on the bucket.
  
  These still work when the VM is down.

## Not yet covered (tracked in the go-live checklist, "Recommended")
- Tracing (OpenTelemetry), deferred since Phase 8.
- Central log shipping and search.
- TLS certificate expiry probe. Caddy renews automatically, and the external uptime monitor catches
  a lapse; add a blackbox exporter if the pilot grows.
- Per-tenant usage dashboards.
