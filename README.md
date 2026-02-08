# optina-optimisations

Bayesian optimization for cloud infrastructure using [Optuna](https://optuna.org/).

## What It Does

Automatically finds optimal configurations for cloud services:

| Optimizer | Target | Benchmark | Metrics |
|-----------|--------|-----------|---------|
| [redis](optimizers/redis/) | Redis cache | memtier_benchmark | ops/sec, p99 latency |
| [minio](optimizers/minio/) | MinIO storage | warp | throughput, IOPS |
| [postgres](optimizers/postgres/) | PostgreSQL | pgbench | TPS, latency |
| [meilisearch](optimizers/meilisearch/) | Meilisearch | k6 | queries/sec |

**Supported clouds:** Selectel, Timeweb

## Quick Start

### 1. Install Tools

```bash
# Ubuntu - core tools
curl -LsSf https://astral.sh/uv/install.sh | sh
sudo apt install -y jq docker.io docker-compose-plugin

# Terraform
wget -O- https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt update && sudo apt install -y terraform
```

For full tool list (gitleaks, tflint, trivy), see [terraform/README.md](terraform/README.md).

### 2. Setup

```bash
git clone https://github.com/damir-manapov/optina-optimisations.git
cd optina-optimisations
uv sync
```

### 3. Configure Cloud

See [terraform/README.md](terraform/README.md) for Selectel/Timeweb setup.

### 4. Run Optimizer

```bash
# Redis - optimize for ops/sec
uv run python optimizers/redis/optimizer.py --cloud selectel --trials 10

# View results
uv run python optimizers/redis/optimizer.py --cloud selectel --show-results
```

## How It Works

1. **Optuna suggests** configuration (CPU, RAM, disk, software settings)
2. **Terraform deploys** infrastructure
3. **Benchmark runs** against deployed system
4. **Results logged** and Optuna learns
5. **Repeat** until convergence

## Project Structure

```
optina-optimisations/
├── optimizers/           # Bayesian optimizers
│   ├── redis/
│   ├── minio/
│   ├── postgres/
│   ├── meilisearch/
│   └── storage/          # Trial persistence (Pydantic models)
├── terraform/            # Cloud infrastructure
│   ├── selectel/
│   └── timeweb/
├── benchmarks/           # Database query benchmarks (TypeScript)
├── tests/                # Shared module tests
├── argparse_helpers.py   # Common CLI argument definitions
├── cloud_config.py       # Cloud configuration (Selectel, Timeweb)
├── common.py             # SSH, Terraform, results I/O utilities
├── metrics.py            # Base MetricConfig for optimization targets
├── pricing.py            # Cloud pricing data and cost calculation
└── pyproject.toml
```

## Development

```bash
./check.sh        # Python + TypeScript checks
./all-checks.sh   # Full checks (secrets, vulnerabilities, dependencies)
```

## Documentation

- [terraform/README.md](terraform/README.md) - Cloud setup
- [docs/OPTIMIZERS.md](docs/OPTIMIZERS.md) - Optimizer usage
- [docs/OPTIMIZER_GUIDE.md](docs/OPTIMIZER_GUIDE.md) - Creating new optimizers
- [benchmarks/README.md](benchmarks/README.md) - Database benchmarks
