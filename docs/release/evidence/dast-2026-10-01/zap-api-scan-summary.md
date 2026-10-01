# ZAP API scan (active, ID-aware) - summary

Final run, 1 Oct 2026, against the production nginx image and the API as the RLS app role,
with `.zap/rules.tsv` and real demo-tree IDs (`dast-ids.prop`). The full report (522 KB, mostly
informational 4xx listings) is not committed; regenerate it with the steps in
`docs/release/production-readiness.md`.

## Result line

```
FAIL-NEW: 0	FAIL-INPROG: 0	WARN-NEW: 0	WARN-INPROG: 0	INFO: 0	IGNORE: 0	PASS: 113
```

## Alerts (all risk levels, including informational and out-of-scope)

| Rule | Name | Risk (confidence) | Instances |
|---|---|---|---|
| 2 | Private IP Disclosure | Low (Medium) | 1 |
| 100001 | Unexpected Content-Type was returned | Low (High) | 117 |
| 100000 | A Client Error response code was returned by the server | Informational (High) | 1303 |
| 10111 | Authentication Request Identified | Informational (High) | 1 |
| 10104 | User Agent Fuzzer | Informational (Medium) | 5 |

Rules 2 and 100001 appear above but are out of scope for the scoped URLs only (own
session IPs on `/auth/sessions`; non-JSON outside `/api/` and the zip archive export), which
is why the result line shows 0 WARN.

## ZAP's own report header

# ZAP Scanning Report

ZAP by [Checkmarx](https://checkmarx.com/).


## Summary of Alerts

| Risk Level | Number of Alerts |
| --- | --- |
| High | 0 |
| Medium | 0 |
| Low | 2 |
| Informational | 3 |




## Insights

| Level | Reason | Site | Description | Statistic |
| --- | --- | --- | --- | --- |
| Low | Warning |  | ZAP errors logged - see the zap.log file for details | 3    |
| Low | Warning |  | ZAP warnings logged - see the zap.log file for details | 1,147    |
| Low | Exceeded High | http://localhost:8080 | Percentage of responses with status code 4xx | 96 % |
| Info | Informational |  | Percentage of network failures | 1 % |
| Info | Informational | http://localhost:8080 | Percentage of responses with status code 2xx | 3 % |
| Info | Informational | http://localhost:8080 | Percentage of endpoints with content type application/json | 92 % |
| Info | Informational | http://localhost:8080 | Percentage of endpoints with content type text/html | 6 % |
| Info | Informational | http://localhost:8080 | Percentage of endpoints with method DELETE | 1 % |
| Info | Informational | http://localhost:8080 | Percentage of endpoints with method GET | 58 % |
| Info | Informational | http://localhost:8080 | Percentage of endpoints with method PATCH | 1 % |
| Info | Informational | http://localhost:8080 | Percentage of endpoints with method POST | 38 % |
| Info | Informational | http://localhost:8080 | Count of total endpoints | 1,425    |
| Info | Informational | http://localhost:8080 | Percentage of slow responses | 1 % |
