# Redis Optimizer

Bayesian optimization for Redis configuration.

## Usage

```bash
# Optimize for ops/sec
uv run python optimizers/redis/optimizer.py --cloud selectel --trials 10 --metric ops_per_sec

# Optimize for p99 latency
uv run python optimizers/redis/optimizer.py --cloud selectel --trials 10 --metric p99_latency_ms

# Optimize for cost efficiency
uv run python optimizers/redis/optimizer.py --cloud selectel --trials 10 --metric cost_efficiency

# Keep infrastructure after
uv run python optimizers/redis/optimizer.py --cloud selectel --trials 10 --no-destroy

# View results
uv run python optimizers/redis/optimizer.py --cloud selectel --show-results
uv run python optimizers/redis/optimizer.py --cloud selectel --export-md
```

## Deployment Modes

| Mode     | Nodes | Description                                         |
| -------- | ----- | --------------------------------------------------- |
| single   | 1     | Single Redis instance at 10.0.0.20                  |
| sentinel | 3     | 1 master + 2 replicas with Sentinel at 10.0.0.20-22 |

## Configuration Space

| Parameter        | Values                    | Notes                          |
| ---------------- | ------------------------- | ------------------------------ |
| mode             | single, sentinel          | Deployment topology            |
| cpu_per_node     | 2, 4, 8                   | vCPU per Redis node            |
| ram_per_node     | 4, 8, 16, 32              | GB per node                    |
| maxmemory_policy | allkeys-lru, volatile-lru | Eviction policy                |
| io_threads       | 1, 2, 4                   | Redis 6+ threaded I/O          |
| persistence      | none, rdb                 | Snapshotting (RDB) or disabled |

## Metrics

| Metric          | Direction | Description                   |
| --------------- | --------- | ----------------------------- |
| ops_per_sec     | Maximize  | Total operations per second   |
| p99_latency_ms  | Minimize  | 99th percentile latency in ms |
| cost_efficiency | Maximize  | ops/sec per $/hr              |

## Benchmark

memtier_benchmark with:
- 80% GET / 20% SET
- 16 threads, 50 connections per thread
- 10,000 requests per connection
- Random keys, 256-byte values

## System Baseline

Before each benchmark, fio and sysbench run on the Redis node (10.0.0.20) to measure:
- Disk: Random 4K IOPS, sequential throughput
- CPU: Events per second
- Memory: Bandwidth (MiB/s)

Baseline results are saved with each trial to help identify hardware variance.
