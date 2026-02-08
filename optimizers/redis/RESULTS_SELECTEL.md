# Redis Benchmark Results - SELECTEL

Generated: 2026-02-08 23:18:06

## Results

| # | Mode | Nodes | CPU | RAM | Policy | IO | Persist | Ops/s | p99 (ms) | $/hr | Efficiency |
|--:|------|------:|----:|----:|--------|---:|---------|------:|---------:|-----:|-----------:|
| 1 | sentinel | 3 | 2 | 8 | allkeys-lru | 1 | rdb | 117594 | 2.69 | 15492.00 | 8 |
| 2 | single | 1 | 4 | 16 | allkeys-lru | 1 | rdb | 92592 | 3.85 | 8378.00 | 11 |
| 3 | single | 1 | 2 | 16 | allkeys-lru | 2 | none | 85534 | 3.38 | 7068.00 | 12 |
| 4 | sentinel | 3 | 2 | 16 | allkeys-lru | 1 | rdb | 81348 | 3.92 | 21204.00 | 4 |
| 5 | sentinel | 3 | 4 | 4 | allkeys-lru | 2 | none | 78126 | 3.44 | 16566.00 | 5 |

## Best Configurations

- **Best by ops/sec:** 117594 ops/s — `sentinel 3×2cpu/8gb io=1 rdb`
- **Best by p99 latency:** 2.69ms — `sentinel 3×2cpu/8gb io=1 rdb`
- **Best by efficiency:** 12 ops/$/hr — `single 1×2cpu/16gb io=2 none`
