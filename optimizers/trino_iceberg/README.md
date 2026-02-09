# Trino-Iceberg Optimizer

Bayesian optimization for Trino + Iceberg + Nessie configuration.

## Stack

| Component  | Version | Purpose                     |
| ---------- | ------- | --------------------------- |
| Trino      | 467     | Distributed SQL query engine |
| Iceberg    | -       | Table format (via Trino)    |
| Nessie     | 0.99.0  | Catalog (Git-like versioning) |
| PostgreSQL | 16      | Nessie metadata storage     |

## Usage

```bash
# Infrastructure optimization (tune VM specs)
uv run python optimizers/trino_iceberg/optimizer.py -c selectel -m infra -t 10 -l damir

# Config optimization on fixed host
uv run python optimizers/trino_iceberg/optimizer.py -c selectel -m config --cpu 8 --ram 32 -t 20 -l damir

# Full optimization (infra first, then config)
uv run python optimizers/trino_iceberg/optimizer.py -c selectel -m full -t 20 -l damir

# Custom row count for larger datasets
uv run python optimizers/trino_iceberg/optimizer.py -c selectel -m infra -t 10 --rows 100000000 -l damir

# Optimize for latency instead of throughput
uv run python optimizers/trino_iceberg/optimizer.py -c selectel -m config --metric lookup_by_id_p99_ms -t 20 -l damir

# View results
uv run python optimizers/trino_iceberg/optimizer.py -c selectel --show-results
uv run python optimizers/trino_iceberg/optimizer.py -c selectel --export-md
```

## Optimization Modes

| Mode   | Description                                 |
| ------ | ------------------------------------------- |
| infra  | Tune VM specs - creates new VM per trial    |
| config | Tune Trino/Iceberg settings on fixed host   |
| full   | Two-phase: infra first, then config on best |

## Configuration Space

### Infrastructure (--mode infra)

| Parameter    | Values                           | Notes          |
| ------------ | -------------------------------- | -------------- |
| cpu          | 2, 4, 8, 16                      | vCPU           |
| ram_gb       | 8, 16, 32, 64                    | GB (Trino needs RAM) |
| disk_type    | nvme (timeweb) / fast (selectel) | Cloud-specific |
| disk_size_gb | 100, 200, 400                    | For Iceberg data |

### Trino + Iceberg Config (--mode config)

| Parameter                  | Values                                    | Notes                    |
| -------------------------- | ----------------------------------------- | ------------------------ |
| trino_heap_pct             | 50, 60, 70, 80                            | % of RAM for JVM heap    |
| trino_query_max_memory_pct | 30, 40, 50                                | % of heap per query      |
| task_concurrency           | 4, 8, 16, 32                              | Parallel tasks           |
| task_writer_count          | 1, 2, 4                                   | Parallel writers         |
| compression                | zstd, snappy, lz4, gzip, none             | Parquet compression      |
| compression_level          | 1, 3, 6, 9                                | Level (zstd/gzip only)   |
| partition_key              | none, category, created_date, id_bucket_* | Data layout              |
| target_file_size_mb        | 64, 128, 256, 512                         | Target Parquet file size |

### Partition Keys

| Key           | Description                           | Best For                |
| ------------- | ------------------------------------- | ----------------------- |
| none          | No partitioning                       | Small tables            |
| category      | Partition by category column          | Filter by category      |
| created_date  | Partition by day(created_at)          | Time-series queries     |
| id_bucket_16  | Hash partition into 16 buckets        | Point lookups (small)   |
| id_bucket_64  | Hash partition into 64 buckets        | Point lookups (large)   |

## Metrics

| Metric                | Direction | Description                       |
| --------------------- | --------- | --------------------------------- |
| lookup_by_id_per_sec  | Maximize  | Point lookups by ID per second    |
| lookup_by_id_p50_ms   | Minimize  | Median lookup by ID latency       |
| lookup_by_id_p95_ms   | Minimize  | 95th percentile latency           |
| lookup_by_id_p99_ms   | Minimize  | 99th percentile latency           |
| cost_efficiency       | Maximize  | Lookups per ₽/mo                  |

## Benchmark

Point lookup by ID benchmark using concurrent queries:
- Query: `SELECT * FROM benchmark WHERE id = ?`
- Random IDs from dataset
- Concurrency: 16 (fixed for fair comparison)
- Warmup: 10 seconds (JVM JIT, page cache, metadata cache)
- Duration: 60 seconds (measured after warmup)
- Runs from benchmark VM (over network) to Trino VM

## Data Generation

Uses [samples-generation](https://github.com/making-ventures/samples-generation) to create test data:

| Column     | Type     | Generator          |
| ---------- | -------- | ------------------ |
| id         | bigint   | sequence(1, N)     |
| category   | string   | choice(A-E)        |
| value      | float    | randomFloat(0-1000)|
| name       | string   | randomString(20)   |
| created_at | datetime | datetime()         |

Default: 10 million rows. Use `--rows` to change.

## System Baseline

During infrastructure optimization, fio and sysbench run on the Trino node to measure:
- Disk: Random 4K IOPS, sequential throughput on /data
- CPU: Events per second
- Memory: Bandwidth (MiB/s)

Baseline results are saved with each trial to help identify hardware variance.

## Network Layout

| Service    | IP          | Port  |
| ---------- | ----------- | ----- |
| Trino      | 10.0.0.40   | 8080  |
| Nessie     | 10.0.0.40   | 19120 |
| PostgreSQL | 10.0.0.40   | 5432  |

All services run on a single VM for simplicity. Future versions may support distributed Trino clusters.
