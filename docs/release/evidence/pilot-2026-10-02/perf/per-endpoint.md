| Endpoint (worst p95 of 3 runs, ms) | 10 req/s | 20 req/s | 30 req/s | 40 req/s | 50 req/s |
|---|---|---|---|---|---|
| people list | 78 | 102 | 144 | 213 | 308 |
| person profile | 47 | 56 | 69 | 118 | 160 |
| family view | 64 | 78 | 101 | 147 | 182 |
| ancestors d10 | 86 | 89 | 108 | 176 | 312 |
| descendants d4 | 60 | 82 | 108 | 185 | 253 |
| search | 108 | 126 | 206 | 284 | 390 |
| relationship path | 129 | 147 | 176 | 287 | 549 |
| add person | 60 | 72 | 94 | 170 | 229 |
| add relative | 89 | 97 | 128 | 179 | 298 |

generator lag/dropped (run,rate,lag,dropped,load):
(1, 50, {'p50': 1.0, 'p99': 6.0}, 0, [4.4, 5.7])
(2, 50, {'p50': 1.0, 'p99': 14.5}, 0, [4.7, 4.9])
(3, 50, {'p50': 1.0, 'p99': 10.4}, 0, [4.0, 4.9])
