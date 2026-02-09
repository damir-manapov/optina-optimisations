# Redis Benchmark Results - SELECTEL

Generated: 2026-02-09 07:07:57

## Results

| # | Mode | Nodes | CPU | RAM | Policy | IO | Persist | Ops/s | p99 (ms) | $/hr | Efficiency |
|--:|------|------:|----:|----:|--------|---:|---------|------:|---------:|-----:|-----------:|
| 1 | sentinel | 3 | 2 | 8 | allkeys-lru | 1 | rdb | 63916 | 5.41 | 15492.00 | 4 |
| 2 | sentinel | 3 | 2 | 16 | allkeys-lru | 1 | rdb | 0 | 0.00 | 21204.00 | 0 |
| 3 | sentinel | 3 | 2 | 8 | allkeys-lru | 1 | rdb | 0 | 0.00 | 15492.00 | 0 |
| 4 | single | 1 | 2 | 16 | allkeys-lru | 2 | none | 0 | 0.00 | 7068.00 | 0 |
| 5 | sentinel | 3 | 4 | 4 | allkeys-lru | 2 | none | 0 | 0.00 | 16566.00 | 0 |
| 6 | single | 1 | 4 | 16 | allkeys-lru | 1 | rdb | 0 | 0.00 | 8378.00 | 0 |
| 7 | sentinel | 3 | 8 | 32 | volatile-lru | 4 | rdb | 0 | 0.00 | 44418.00 | 0 |
| 8 | sentinel | 3 | 2 | 4 | allkeys-lru | 1 | rdb | 0 | 0.00 | 12636.00 | 0 |
| 9 | sentinel | 3 | 2 | 32 | allkeys-lru | 1 | rdb | 0 | 0.00 | 32628.00 | 0 |

## Best Configurations

- **Best by ops/sec:** 63916 ops/s — `sentinel 3×2cpu/8gb io=1 rdb`
- **Best by p99 latency:** 0.00ms — `sentinel 3×2cpu/16gb io=1 rdb`
- **Best by efficiency:** 4 ops/$/hr — `sentinel 3×2cpu/8gb io=1 rdb`
