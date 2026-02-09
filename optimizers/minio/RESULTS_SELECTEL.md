# MinIO Benchmark Results - SELECTEL

Generated: 2026-02-09 23:02:16

## Results

| # | Nodes | CPU | RAM | Drives | Size | Type | Total (MiB/s) | GET | PUT | $/hr | Efficiency |
|--:|------:|----:|----:|-------:|-----:|------|-------------:|----:|----:|-----:|-----------:|
| 1 | 4 | 8 | 16 | 3 | 100 | fast | 410.0 | 351.5 | 60.0 | 82992.00 | 0.0 |
| 2 | 1 | 4 | 4 | 2 | 200 | universal2 | 410.0 | 352.3 | 60.3 | 7172.00 | 0.1 |
| 3 | 4 | 8 | 32 | 3 | 200 | universal2 | 409.8 | 351.8 | 59.8 | 73024.00 | 0.0 |
| 4 | 1 | 2 | 16 | 2 | 200 | basicssd | 409.5 | 352.4 | 59.9 | 8718.00 | 0.0 |
| 5 | 3 | 2 | 8 | 1 | 100 | basic | 409.4 | 351.8 | 59.8 | 11742.00 | 0.0 |
| 6 | 2 | 2 | 4 | 1 | 200 | basicssd | 408.7 | 350.8 | 59.7 | 8124.00 | 0.1 |
| 7 | 2 | 4 | 4 | 4 | 200 | fast | 408.6 | 350.6 | 60.0 | 69544.00 | 0.0 |

## Best Configurations

- **Best by total:** 410.0 MiB/s — `4n×8cpu/16gb 3×100gb fast`
- **Best by GET:** 352.4 MiB/s — `1n×2cpu/16gb 2×200gb basicssd`
- **Best by PUT:** 60.3 MiB/s — `1n×4cpu/4gb 2×200gb universal2`
- **Best by efficiency:** 0.1 MiB/s/$/hr — `1n×4cpu/4gb 2×200gb universal2`
