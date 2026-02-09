# PostgreSQL Optimizer

Bayesian optimization for PostgreSQL configuration.

## Usage

```bash
# Infrastructure optimization (CPU, RAM, disk)
uv run python optimizers/postgres/optimizer.py --cloud timeweb --mode infra --trials 10

# Config optimization on fixed host
uv run python optimizers/postgres/optimizer.py --cloud timeweb --mode config --cpu 8 --ram 32 --trials 20

# Full optimization (infra first, then config)
uv run python optimizers/postgres/optimizer.py --cloud timeweb --mode full --trials 20

# Optimize for latency instead of TPS
uv run python optimizers/postgres/optimizer.py --cloud timeweb --mode config --metric latency_avg_ms --trials 20

# View results
uv run python optimizers/postgres/optimizer.py --cloud timeweb --show-results
```

## Optimization Modes

| Mode   | Description                                    |
| ------ | ---------------------------------------------- |
| infra  | Tune VM specs - creates new VM per trial       |
| config | Tune postgresql.conf on fixed host (faster)    |
| full   | Two-phase: infra first, then config on best    |

## Deployment Modes

| Mode    | Nodes | Description                                |
| ------- | ----- | ------------------------------------------ |
| single  | 1     | Single PostgreSQL 18 instance at 10.0.0.30 |
| cluster | 3     | Patroni + etcd HA cluster at 10.0.0.30-32  |

## Configuration Space

### Infrastructure (--mode infra)

| Parameter    | Values                           | Notes                |
| ------------ | -------------------------------- | -------------------- |
| mode         | single, cluster                  | Topology             |
| cpu          | 2, 4, 8, 16                      | vCPU                 |
| ram_gb       | 4, 8, 16, 32, 64                 | GB                   |
| disk_type    | nvme (timeweb) / fast (selectel) | Cloud-specific       |
| disk_size_gb | 50, 100, 200                     | Disk size            |

### PostgreSQL Config (--mode config)

| Parameter                       | Values                     | Notes                  |
| ------------------------------- | -------------------------- | ---------------------- |
| shared_buffers_pct              | 15, 20, 25, 30, 35, 40     | % of RAM               |
| effective_cache_size_pct        | 50, 60, 70, 75             | % of RAM               |
| work_mem_mb                     | 4, 16, 32, 64, 128, 256    | Per-operation memory   |
| maintenance_work_mem_mb         | 64, 128, 256, 512, 1024    | VACUUM/CREATE INDEX    |
| max_connections                 | 50, 100, 200, 500          | Max connections        |
| random_page_cost                | 1.1, 1.5, 2.0, 4.0         | Random I/O cost        |
| effective_io_concurrency        | 1, 50, 100, 200            | Async I/O operations   |
| wal_buffers_mb                  | 16, 32, 64, 128            | WAL buffer size        |
| max_wal_size_gb                 | 1, 2, 4, 8                 | Max WAL size           |
| checkpoint_completion_target    | 0.5, 0.7, 0.9              | Checkpoint spread      |
| max_worker_processes            | 2, 4, 8                    | Background workers     |
| max_parallel_workers_per_gather | 0, 1, 2, 4                 | Parallel query workers |

## Metrics

| Metric          | Direction | Description             |
| --------------- | --------- | ----------------------- |
| tps             | Maximize  | Transactions per second |
| latency_avg_ms  | Minimize  | Average latency in ms   |
| cost_efficiency | Maximize  | TPS per $/hr            |

## Benchmark

pgbench with TPC-B-like workload:
- Scale factor = 10 × RAM in GB
- 60-second benchmark runs
- Clients = 4 × CPU cores

## System Baseline

During infrastructure optimization (--mode infra), fio and sysbench run on the Postgres node to measure:
- Disk: Random 4K IOPS, sequential throughput
- CPU: Events per second
- Memory: Bandwidth (MiB/s)

Baseline results are saved with each trial to help identify hardware variance.
