# Postgres Benchmark Results - SELECTEL

Generated: 2026-02-09 08:01:32

## Results

| # | Mode | CPU | RAM | Disk | SB% | WM | MC | TPS | Lat(ms) | $/hr | Efficiency |
|--:|------|----:|----:|------|----:|---:|---:|----:|--------:|-----:|-----------:|
| 1 | infra | 16 | 32 | fast | 25 | 64 | 100 | 4788.9 | 13.33 | 25896.00 | 0 |
| 2 | infra | 4 | 8 | fast | 25 | 64 | 100 | 3271.5 | 4.88 | 6474.00 | 1 |
| 3 | infra | 2 | 8 | fast | 25 | 64 | 100 | 0.0 | 0.00 | 5164.00 | 0 |
| 4 | infra | 2 | 8 | fast | 25 | 64 | 100 | 0.0 | 0.00 | 5164.00 | 0 |
| 5 | infra | 2 | 16 | fast | 25 | 64 | 100 | 0.0 | 0.00 | 7068.00 | 0 |

## Best Configurations

- **Best by TPS:** 4788.9 TPS — `16cpu/32gb/fast` `sb=25% wm=64mb mc=100`
- **Best by latency:** 0.00ms — `2cpu/8gb/fast` `sb=25% wm=64mb mc=100`
- **Best by efficiency:** 1 TPS/$/hr — `4cpu/8gb/fast` `sb=25% wm=64mb mc=100`
