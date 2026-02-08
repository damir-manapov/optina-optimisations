# Meilisearch Optimizer

Bayesian optimization for Meilisearch configuration.

## Usage

```bash
# Infrastructure optimization
uv run python optimizers/meilisearch/optimizer.py --cloud selectel --mode infra --trials 10

# Config optimization on fixed host
uv run python optimizers/meilisearch/optimizer.py --cloud selectel --mode config --cpu 8 --ram 16 --trials 20

# Full optimization
uv run python optimizers/meilisearch/optimizer.py --cloud selectel --mode full --trials 15

# Optimize for p95 latency
uv run python optimizers/meilisearch/optimizer.py --cloud selectel --mode config --metric p95_ms --trials 10

# View results
uv run python optimizers/meilisearch/optimizer.py --cloud selectel --show-results
```

## Optimization Modes

| Mode   | Description                                   |
| ------ | --------------------------------------------- |
| infra  | Tune VM specs - creates new VM per trial      |
| config | Tune Meilisearch config on fixed host         |
| full   | Two-phase: infra first, then config on best   |

## Configuration Space

### Infrastructure (--mode infra)

| Parameter | Values                 | Notes     |
| --------- | ---------------------- | --------- |
| cpu       | 2, 4, 8, 16            | vCPU      |
| ram_gb    | 4, 8, 16, 32           | GB        |
| disk_type | fast, universal, basic | Disk tier |

### Meilisearch Config (--mode config)

| Parameter              | Values               | Notes            |
| ---------------------- | -------------------- | ---------------- |
| max_indexing_memory_mb | 256, 512, 1024, 2048 | RAM for indexing |
| max_indexing_threads   | 0, 2, 4, 8           | 0 = auto         |

## Metrics

| Metric          | Direction | Description             |
| --------------- | --------- | ----------------------- |
| qps             | Maximize  | Queries per second      |
| p95_ms          | Minimize  | 95th percentile latency |
| cost_efficiency | Maximize  | QPS per ₽/mo            |
| indexing_time   | Minimize  | Time to index 500K docs |

## Benchmark

k6 load test with realistic query mix:
- 50% simple keywords
- 20% typo-tolerant
- 20% filtered search
- 10% phrase + sort
