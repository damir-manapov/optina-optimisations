# Trino-Iceberg Benchmark Results - SELECTEL
Generated: 2026-02-09 20:35:00

## Results

| Mode | CPU | RAM | Disk | Compression | Partition | Lookups/s | P50ms | P99ms | Cost | Eff |
|------|----:|----:|------|-------------|-----------|----------:|------:|------:|-----:|----:|
| config | 4 | 16 | fast | ? | none | 4.7 | 3277.8 | 3632.1 | 14228 | 0.00 |
| cluster | 16 | 64 | fast | ? | none | 2.8 | 5380.9 | 5880.5 | 41312 | 0.00 |

## Best Configurations

- **Best lookups/s**: 4.7 (4cpu/16gb, ?)
- **Best P99 latency**: 3632.1ms (4cpu/16gb, ?)
- **Best efficiency**: 0.00 lookups/₽/mo (4cpu/16gb)