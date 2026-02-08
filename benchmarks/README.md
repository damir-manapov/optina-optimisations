# optina-benchmarks

Benchmark queries on Trino+Iceberg, PostgreSQL, and ClickHouse without indexes.

## Overview

This module benchmarks query performance on tables without traditional indexes, demonstrating how columnar databases and modern storage formats handle full-scan workloads.

### Databases Tested

- **PostgreSQL** - Traditional RDBMS for baseline comparison
- **ClickHouse** - Columnar OLAP database
- **Trino + Iceberg** - Query engine with lakehouse storage

### Query Types

**Basic:** COUNT, filters, aggregations, pagination, LIKE patterns, percentiles

**JOIN:** Filter/aggregate with lookup tables, multiple conditions

**Deduplication:** Find duplicates, group size distribution, window functions

**Matching:** Record linking, self-join, fuzzy match (Levenshtein)

## Prerequisites

- Node.js 20+
- pnpm
- Docker

## Installation

```bash
pnpm install
```

## Usage

### Start Databases

```bash
pnpm compose:up
```

Memory-constrained options:
```bash
pnpm compose:up:postgres:16gb
pnpm compose:up:clickhouse:32gb
pnpm compose:up:trino:64gb
```

### Generate Test Data

```bash
# Generate 100 million rows (default)
pnpm generate

# Custom row count
pnpm generate -n 1_000_000

# Specific database
pnpm generate:postgres -n 10_000_000
```

### Run Benchmarks

```bash
# All databases
pnpm benchmark

# Specific database
pnpm benchmark --postgres

# With report
pnpm benchmark --report
```

### Stop

```bash
pnpm compose:down
pnpm compose:reset  # Remove volumes
```

## Docker Services

| Service    | Port(s)     | Credentials           |
| ---------- | ----------- | --------------------- |
| PostgreSQL | 5432        | postgres:postgres     |
| ClickHouse | 8123, 9009  | default:clickhouse    |
| Trino      | 8080        | trino (no password)   |
| MinIO      | 9000, 9001  | minioadmin:minioadmin |

## Development

```bash
pnpm lint
pnpm typecheck
pnpm test
```
