# Trino-Iceberg Benchmark Results - SELECTEL
Generated: 2026-02-10 05:00:16

## Results

| Mode | CPU | RAM | Disk | Compression | Partition | Lookups/s | P50ms | P99ms | Cost | Eff |
|------|----:|----:|------|-------------|-----------|----------:|------:|------:|-----:|----:|
| cluster | 8 | 64 | fast | zstd | none | 2.8 | 4953.7 | 6184.7 | 28272 | 0.00 |
| cluster | 4 | 16 | fast | zstd | none | 2.7 | 5152.5 | 6231.9 | 10328 | 0.00 |
| cluster | 8 | 32 | fast | zstd | none | 2.7 | 5189.4 | 6518.9 | 28456 | 0.00 |
| cluster | 16 | 32 | fast | zstd | none | 2.7 | 5460.2 | 6177.6 | 33696 | 0.00 |
| cluster | 4 | 64 | fast | zstd | none | 2.7 | 5155.5 | 6505.9 | 33452 | 0.00 |
| cluster | 16 | 32 | fast | zstd | none | 2.7 | 5321.0 | 6303.8 | 21996 | 0.00 |
| cluster | 16 | 64 | fast | zstd | none | 2.6 | 5427.8 | 6602.3 | 29612 | 0.00 |

## Best Configurations

- **Best lookups/s**: 2.8 (8cpu/64gb, zstd)
- **Best P99 latency**: 6177.6ms (16cpu/32gb, zstd)
- **Best efficiency**: 0.00 lookups/₽/mo (4cpu/16gb)