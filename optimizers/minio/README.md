# MinIO Optimizer

Bayesian optimization for MinIO cluster configuration.

## Usage

```bash
# Run optimization
uv run python optimizers/minio/optimizer.py --cloud selectel --trials 10

# Keep infrastructure after
uv run python optimizers/minio/optimizer.py --cloud selectel --trials 10 --no-destroy

# View results
uv run python optimizers/minio/optimizer.py --cloud selectel --show-results
uv run python optimizers/minio/optimizer.py --cloud selectel --export-md
```

## Configuration Space

| Parameter       | Values                                       | Notes                 |
| --------------- | -------------------------------------------- | --------------------- |
| nodes           | 1, 2, 3, 4                                   | Number of MinIO nodes |
| cpu_per_node    | 2, 4, 8                                      | vCPU per node         |
| ram_per_node    | 4, 8, 16, 32                                 | GB per node           |
| drives_per_node | 1, 2, 4                                      | Drives per node       |
| drive_size_gb   | 100, 200                                     | Size per drive        |
| drive_type      | fast, universal2, universal, basicssd, basic | Disk tier             |

## Erasure Coding

MinIO requires at least 4 drives for erasure coding:

| Config | Total Drives | EC Level | Fault Tolerance |
| ------ | ------------ | -------- | --------------- |
| 1×1    | 1            | 0        | None            |
| 4×1    | 4            | 2        | 2 failures      |
| 2×4    | 8            | 4        | 4 failures      |
| 4×4    | 16           | 8        | 8 failures      |

## Metrics

| Metric          | Direction | Description           |
| --------------- | --------- | --------------------- |
| total_mib_s     | Maximize  | Total throughput      |
| cost_efficiency | Maximize  | MiB/s per $/hr        |

## Benchmark

warp benchmark tool measuring PUT/GET throughput with mixed workload.

## System Baseline

Before each benchmark, fio and sysbench run on the first MinIO node to measure:
- Disk: Random 4K IOPS, sequential throughput on /data1
- CPU: Events per second
- Memory: Bandwidth (MiB/s)

Baseline results are saved with each trial to help identify hardware variance.
