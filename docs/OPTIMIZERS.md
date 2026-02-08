# Optimizers

Bayesian optimization for cloud infrastructure configurations using [Optuna](https://optuna.org/).

## Available Optimizers

| Optimizer | Target | Benchmark Tool |
|-----------|--------|----------------|
| [redis](../optimizers/redis/) | Redis cache | memtier_benchmark |
| [minio](../optimizers/minio/) | MinIO distributed storage | warp |
| [postgres](../optimizers/postgres/) | PostgreSQL database | pgbench |
| [meilisearch](../optimizers/meilisearch/) | Meilisearch search engine | k6 |

## Setup

```bash
# From project root
uv sync
```

## Usage

```bash
# Redis optimizer
uv run python optimizers/redis/optimizer.py --cloud selectel --trials 10

# MinIO optimizer
uv run python optimizers/minio/optimizer.py --cloud selectel --trials 10

# PostgreSQL optimizer
uv run python optimizers/postgres/optimizer.py --cloud selectel --mode config --trials 10

# Meilisearch optimizer
uv run python optimizers/meilisearch/optimizer.py --cloud selectel --mode infra --trials 10

# Show results
uv run python optimizers/redis/optimizer.py --cloud selectel --show-results
uv run python optimizers/redis/optimizer.py --cloud selectel --export-md
```

## Supported Clouds

- **Selectel** - OpenStack-based, ru-7 region
- **Timeweb** - TWC API, ru-1 location

## Pricing

Cloud pricing is centralized in [pricing.py](../pricing.py):

- CPU/RAM/disk costs per cloud
- `cost_efficiency` metric (performance per ₽/mo)
- Cloud constraints (min RAM per CPU)

## Check

```bash
./check.sh  # ruff format, lint, pyright
```
