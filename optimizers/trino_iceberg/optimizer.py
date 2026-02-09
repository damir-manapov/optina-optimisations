#!/usr/bin/env python3
"""
Multi-Cloud Trino-Iceberg Configuration Optimizer using Bayesian Optimization (Optuna).

Stack: Trino + Nessie + PostgreSQL (for Nessie catalog)
Benchmark: Point lookups (SELECT * WHERE id = ?) via samples-generation

Supports two optimization modes:
- infra: Tune VM specs (CPU, RAM, disk) - creates new VM per trial
- config: Tune Trino/Iceberg settings on fixed host - reconfigures existing VM

Usage:
    # Infrastructure optimization (tune VM specs)
    uv run python optimizers/trino_iceberg/optimizer.py -c selectel -m infra -t 10 -l damir

    # Config optimization on fixed host (faster, more trials)
    uv run python optimizers/trino_iceberg/optimizer.py -c selectel -m config --cpu 8 --ram 32 -t 20 -l damir

    # Full optimization (infra first, then config on best host)
    uv run python optimizers/trino_iceberg/optimizer.py -c selectel -m full -t 20 -l damir

    # Show results / export
    uv run python optimizers/trino_iceberg/optimizer.py -c selectel --show-results
    uv run python optimizers/trino_iceberg/optimizer.py -c selectel --export-md
"""

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

import optuna
from optuna.samplers import TPESampler

# Add root dir to path for common imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from common import (
    SystemBaseline,
    destroy_all,
    get_metric,
    get_terraform,
    get_tf_output,
    run_ssh_command,
    run_system_baseline,
    wait_for_vm_ready,
)
from metrics import get_metric_value
from pricing import DiskConfig, calculate_vm_cost, filter_valid_ram
from storage import TrialStore, get_store as _get_store

from optimizers.trino_iceberg.cloud_config import (
    CloudConfig,
    get_cloud_config,
    get_config_search_space,
    get_infra_search_space,
    filter_compression_levels,
)
from optimizers.trino_iceberg.metrics import METRICS

RESULTS_DIR = Path(__file__).parent
STUDY_DB = RESULTS_DIR / "study.db"

# Service versions
TRINO_VERSION = "467"  # Latest as of 2026
NESSIE_VERSION = "0.99.0"
POSTGRES_VERSION = "16"

# Network layout
TRINO_IP = "10.0.0.40"
NESSIE_PORT = 19120
TRINO_PORT = 8080

# Data generation
DEFAULT_ROW_COUNT = 500_000_000  # 500M rows for benchmark


def get_store() -> TrialStore:
    """Get the TrialStore for Trino-Iceberg results."""
    return _get_store("trino-iceberg")


class Mode(Enum):
    """Optimization mode."""

    INFRA = "infra"
    CONFIG = "config"
    FULL = "full"


@dataclass
class TrialTimings:
    """Timing measurements for each phase of a trial."""

    terraform_s: float = 0.0
    vm_ready_s: float = 0.0
    service_ready_s: float = 0.0
    baseline_s: float = 0.0
    data_gen_s: float = 0.0  # Generate and load data via samples-generation
    benchmark_s: float = 0.0
    destroy_s: float = 0.0
    trial_total_s: float = 0.0


@dataclass
class BenchmarkResult:
    """Trino lookup by ID benchmark results."""

    lookup_by_id_per_sec: float = 0.0
    lookup_by_id_p50_ms: float = 0.0
    lookup_by_id_p95_ms: float = 0.0
    lookup_by_id_p99_ms: float = 0.0
    total_lookups: int = 0
    duration_s: float = 0.0
    error: str | None = None
    baseline: SystemBaseline | None = None
    timings: TrialTimings | None = None


def config_to_key(infra: dict, trino_config: dict, cloud: str) -> str:
    """Convert config dicts to a hashable key for deduplication."""
    return json.dumps(
        {"cloud": cloud, "infra": infra, "trino": trino_config}, sort_keys=True
    )


def find_cached_result(infra: dict, trino_config: dict, cloud: str) -> dict | None:
    """Find a cached successful result for the given config."""
    target_key = config_to_key(infra, trino_config, cloud)
    store = get_store()
    trial = store.find_by_config_key(target_key)
    if trial is None:
        return None
    if trial.error:
        return None
    lookups = trial.metrics.lookup_by_id_per_sec if trial.metrics else 0
    if (lookups or 0) <= 0:
        return None
    return trial.model_dump()


def wait_for_trino_ready(
    vm_ip: str, timeout: int = 300, jump_host: str | None = None
) -> bool:
    """Wait for Trino to be ready to accept queries."""
    print(f"  Waiting for Trino at {vm_ip}:{TRINO_PORT}...")
    start = time.time()
    while time.time() - start < timeout:
        # Check Trino health endpoint
        cmd = f"curl -s -o /dev/null -w '%{{http_code}}' http://localhost:{TRINO_PORT}/v1/info"
        code, output = run_ssh_command(vm_ip, cmd, timeout=30, jump_host=jump_host)
        if code == 0 and output.strip() == "200":
            # Also verify we can run a simple query via trino CLI
            test_cmd = "java -jar /opt/trino/trino-cli.jar --server localhost:8080 --execute 'SELECT 1' 2>/dev/null"
            code, _ = run_ssh_command(vm_ip, test_cmd, timeout=30, jump_host=jump_host)
            if code == 0:
                print(f"  Trino ready in {time.time() - start:.1f}s")
                return True
        time.sleep(5)
    print(f"  Trino not ready after {timeout}s")
    return False


def wait_for_nessie_ready(
    vm_ip: str, timeout: int = 120, jump_host: str | None = None
) -> bool:
    """Wait for Nessie catalog to be ready."""
    print(f"  Waiting for Nessie at {vm_ip}:{NESSIE_PORT}...")
    start = time.time()
    while time.time() - start < timeout:
        cmd = f"curl -s -o /dev/null -w '%{{http_code}}' http://localhost:{NESSIE_PORT}/api/v2/config"
        code, output = run_ssh_command(vm_ip, cmd, timeout=10, jump_host=jump_host)
        if code == 0 and output.strip() == "200":
            print(f"  Nessie ready in {time.time() - start:.1f}s")
            return True
        time.sleep(3)
    print(f"  Nessie not ready after {timeout}s")
    return False


def generate_trino_config(trino_config: dict, ram_gb: int) -> dict[str, str]:
    """Generate Trino configuration files content.

    Returns dict mapping filename to content.
    """
    heap_mb = int(ram_gb * 1024 * trino_config["trino_heap_pct"] / 100)
    query_max_memory_mb = int(
        heap_mb * trino_config["trino_query_max_memory_pct"] / 100
    )

    jvm_config = f"""-server
-Xmx{heap_mb}m
-Xms{heap_mb}m
-XX:+UseG1GC
-XX:G1HeapRegionSize=32M
-XX:+ExplicitGCInvokesConcurrent
-XX:+HeapDumpOnOutOfMemoryError
-XX:ReservedCodeCacheSize=512M
-Djdk.attach.allowAttachSelf=true
"""

    config_properties = f"""coordinator=true
node-scheduler.include-coordinator=true
http-server.http.port={TRINO_PORT}
query.max-memory={query_max_memory_mb}MB
query.max-memory-per-node={query_max_memory_mb}MB
discovery.uri=http://localhost:{TRINO_PORT}
task.concurrency={trino_config["task_concurrency"]}
task.writer-count={trino_config["task_writer_count"]}
"""

    return {
        "jvm.config": jvm_config,
        "config.properties": config_properties,
    }


def generate_iceberg_table_properties(trino_config: dict) -> dict[str, str]:
    """Generate Iceberg table properties for CREATE TABLE."""
    props = {
        "format": "PARQUET",
        "write.parquet.compression-codec": trino_config["compression"].upper(),
    }

    # Add compression level for algorithms that support it
    if trino_config["compression"] in ["zstd", "gzip"]:
        props["write.parquet.compression-level"] = str(
            trino_config["compression_level"]
        )

    # Target file size
    props["write.target-file-size-bytes"] = str(
        trino_config["target_file_size_mb"] * 1024 * 1024
    )

    return props


def get_partition_spec(partition_key: str) -> str:
    """Get Iceberg partition specification SQL."""
    if partition_key == "none":
        return ""
    elif partition_key == "category":
        return "WITH (partitioning = ARRAY['category'])"
    elif partition_key == "created_date":
        return "WITH (partitioning = ARRAY['day(created_at)'])"
    elif partition_key == "id_bucket_16":
        return "WITH (partitioning = ARRAY['bucket(id, 16)'])"
    elif partition_key == "id_bucket_64":
        return "WITH (partitioning = ARRAY['bucket(id, 64)'])"
    return ""


def reconfigure_trino(
    vm_ip: str,
    trino_config: dict,
    ram_gb: int,
    jump_host: str | None = None,
) -> bool:
    """Reconfigure Trino with new settings."""
    print(f"  Reconfiguring Trino with: {trino_config}")

    configs = generate_trino_config(trino_config, ram_gb)

    # Upload JVM config
    jvm_cmd = f"cat > /etc/trino/jvm.config << 'EOF'\n{configs['jvm.config']}\nEOF"
    code, output = run_ssh_command(vm_ip, jvm_cmd, timeout=30, jump_host=jump_host)
    if code != 0:
        print(f"  Failed to upload jvm.config: {output}")
        return False

    # Upload config.properties
    props_cmd = f"cat > /etc/trino/config.properties << 'EOF'\n{configs['config.properties']}\nEOF"
    code, output = run_ssh_command(vm_ip, props_cmd, timeout=30, jump_host=jump_host)
    if code != 0:
        print(f"  Failed to upload config.properties: {output}")
        return False

    # Restart Trino
    restart_cmd = "systemctl restart trino && sleep 10"
    code, output = run_ssh_command(vm_ip, restart_cmd, timeout=60, jump_host=jump_host)
    if code != 0:
        print(f"  Failed to restart Trino: {output}")
        return False

    # Wait for Trino to be ready
    if not wait_for_trino_ready(vm_ip, timeout=120, jump_host=jump_host):
        return False

    print("  Trino reconfigured successfully")
    return True


def setup_samples_generation(vm_ip: str, jump_host: str | None = None) -> bool:
    """Ensure npx is available for @mkven/samples-generation CLI."""
    # Just verify Node.js and npm are installed (done by cloud-init)
    check_cmd = "which npx && npx --version"
    code, output = run_ssh_command(vm_ip, check_cmd, timeout=30, jump_host=jump_host)
    if code != 0:
        print(f"  npx not available: {output}")
        return False
    print(f"  npx available: {output.strip()}")
    return True


def generate_data(
    vm_ip: str,
    trino_config: dict,
    row_count: int = DEFAULT_ROW_COUNT,
    jump_host: str | None = None,
    max_retries: int = 3,
) -> tuple[bool, float]:
    """Generate test data using samples-generation.

    Returns (success, duration_seconds).

    Note: Nessie catalog has optimistic locking that can cause race conditions.
    We use retries to handle "ref hash is out of date" errors.
    """
    print(f"  Generating {row_count:,} rows with samples-generation...")

    # Build table properties
    table_props = generate_iceberg_table_properties(trino_config)
    partition_spec = get_partition_spec(trino_config["partition_key"])

    # Create scenario file for samples-generation
    # Using the 'simple' scenario with lookup-friendly schema
    scenario_json = json.dumps(
        {
            "name": "benchmark_data",
            "steps": [
                {
                    "table": {
                        "name": "benchmark",
                        "columns": [
                            {
                                "name": "id",
                                "type": "bigint",
                                "generator": {"kind": "sequence", "start": 1},
                            },
                            {
                                "name": "category",
                                "type": "string",
                                "generator": {
                                    "kind": "choice",
                                    "values": ["A", "B", "C", "D", "E"],
                                },
                            },
                            {
                                "name": "value",
                                "type": "float",
                                "generator": {
                                    "kind": "randomFloat",
                                    "min": 0,
                                    "max": 1000,
                                },
                            },
                            {
                                "name": "name",
                                "type": "string",
                                "generator": {"kind": "randomString", "length": 20},
                            },
                            {
                                "name": "created_at",
                                "type": "datetime",
                                "generator": {"kind": "datetime"},
                            },
                        ],
                    },
                    "rowCount": row_count,
                }
            ],
        }
    )

    # Write scenario to VM
    write_scenario_cmd = f"cat > /tmp/benchmark_scenario.json << 'EOFSCENARIO'\n{scenario_json}\nEOFSCENARIO"
    code, output = run_ssh_command(
        vm_ip, write_scenario_cmd, timeout=30, jump_host=jump_host
    )
    if code != 0:
        print(f"  Failed to write scenario: {output}")
        return False, 0

    # First drop existing table if any (use trino CLI directly)
    drop_cmd = 'java -jar /opt/trino/trino-cli.jar --server localhost:8080 --execute "DROP TABLE IF EXISTS iceberg.warehouse.benchmark" 2>/dev/null || true'
    run_ssh_command(vm_ip, drop_cmd, timeout=60, jump_host=jump_host)

    # Generate data using @mkven/samples-generation CLI with retries
    # Nessie can have "ref hash is out of date" errors due to optimistic locking
    batch_size = min(row_count, 10_000_000)  # 10M per batch max
    gen_cmd = f"""
npx @mkven/samples-generation /tmp/benchmark_scenario.json \
    --trino \
    --trino-host localhost \
    --trino-port 8080 \
    --trino-catalog iceberg \
    --trino-schema warehouse \
    -r {row_count} \
    -b {batch_size} \
    --drop \
    2>&1
"""

    start = time.time()
    last_error = ""

    for attempt in range(1, max_retries + 1):
        code, output = run_ssh_command(
            vm_ip, gen_cmd, timeout=3600, jump_host=jump_host
        )

        if code == 0 and "Error" not in output:
            break

        last_error = output[:500]

        # Check for Nessie race condition error
        if "ref hash is out of date" in output:
            print(f"  Nessie race condition, retrying ({attempt}/{max_retries})...")
            time.sleep(2)
            continue
        elif "Error" in output:
            print(f"  Data generation attempt {attempt} failed: {last_error}")
            if attempt < max_retries:
                time.sleep(5)
            continue
        else:
            break

    duration = time.time() - start

    if code != 0 or "Error" in output:
        print(f"  Data generation failed after {max_retries} attempts: {last_error}")
        return False, duration

    # Apply table properties (compression, partitioning) by recreating table
    # samples-generation creates a basic table, we need to recreate with our settings
    if table_props or partition_spec:
        # Build WITH clause for table properties
        props_clause = ""
        if table_props:
            props_items = ", ".join(f"'{k}' = '{v}'" for k, v in table_props.items())
            props_clause = f"WITH ({props_items})"

        # Use full path to trino-cli
        recreate_cmd = f"""
java -jar /opt/trino/trino-cli.jar --server localhost:8080 --execute "
CREATE TABLE iceberg.warehouse.benchmark_opt
{partition_spec}
{props_clause}
AS SELECT * FROM iceberg.warehouse.benchmark
" 2>&1 && \\
java -jar /opt/trino/trino-cli.jar --server localhost:8080 --execute "DROP TABLE iceberg.warehouse.benchmark" 2>&1 && \\
java -jar /opt/trino/trino-cli.jar --server localhost:8080 --execute "ALTER TABLE iceberg.warehouse.benchmark_opt RENAME TO benchmark" 2>&1
"""
        code, output = run_ssh_command(
            vm_ip, recreate_cmd, timeout=1800, jump_host=jump_host
        )
        if code != 0:
            print(f"  Table optimization failed: {output[:300]}")
            # Continue anyway, table exists

    print(f"  Data generated in {duration:.1f}s")
    return True, duration


def run_lookup_by_id_benchmark(
    benchmark_ip: str,
    trino_ip: str,
    duration: int = 60,
    concurrency: int = 8,
    warmup: int = 10,
) -> BenchmarkResult:
    """Run point lookup by ID benchmark against Trino from benchmark VM.

    Executes random ID lookups: SELECT * FROM benchmark WHERE id = ?
    Benchmark runs on benchmark_ip, connecting to Trino at trino_ip:8080.

    Args:
        warmup: Warmup duration in seconds (JVM JIT, page cache, metadata cache)
    """
    print(
        f"  Running lookup benchmark ({warmup}s warmup + {duration}s measured, {concurrency} concurrent) from benchmark VM..."
    )

    # Ensure trino CLI is available on benchmark VM
    setup_cmd = """
if [ ! -f /usr/local/bin/trino-cli.jar ]; then
    echo "Installing Trino CLI on benchmark VM..."
    wget -q https://repo1.maven.org/maven2/io/trino/trino-cli/467/trino-cli-467-executable.jar -O /usr/local/bin/trino-cli.jar
    chmod +x /usr/local/bin/trino-cli.jar
fi
# Create wrapper script if not exists
if [ ! -f /usr/local/bin/trino ]; then
    cat > /usr/local/bin/trino << 'EOFWRAPPER'
#!/bin/bash
exec java -jar /usr/local/bin/trino-cli.jar "$@"
EOFWRAPPER
    chmod +x /usr/local/bin/trino
fi
which java || (apt-get update && apt-get install -y default-jre-headless)
"""
    code, output = run_ssh_command(benchmark_ip, setup_cmd, timeout=120)
    if code != 0:
        return BenchmarkResult(error=f"Failed to setup trino CLI: {output}")

    # Get max ID for random lookups (query from benchmark VM)
    max_id_cmd = f"trino --server http://{trino_ip}:8080 --execute 'SELECT max(id) FROM iceberg.warehouse.benchmark' 2>/dev/null | tail -1"
    code, output = run_ssh_command(benchmark_ip, max_id_cmd, timeout=60)
    if code != 0 or not output.strip().replace('"', "").isdigit():
        return BenchmarkResult(error=f"Failed to get max ID: {output}")
    max_id = int(output.strip().replace('"', ""))

    # Create benchmark script that connects to Trino over network
    bench_script = f"""
import time
import random
import subprocess
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed

TRINO_SERVER = "http://{trino_ip}:8080"
MAX_ID = {max_id}
WARMUP = {warmup}
DURATION = {duration}
CONCURRENCY = {concurrency}

def run_lookup():
    id_val = random.randint(1, MAX_ID)
    start = time.time()
    result = subprocess.run(
        ['trino', '--server', TRINO_SERVER, '--execute', f'SELECT * FROM iceberg.warehouse.benchmark WHERE id = {{id_val}}'],
        capture_output=True, text=True, timeout=30
    )
    elapsed_ms = (time.time() - start) * 1000
    if result.returncode != 0:
        return None
    return elapsed_ms

# Warmup phase (JVM JIT, page cache, metadata cache)
print(f"Warming up for {{WARMUP}}s...", flush=True)
warmup_start = time.time()
with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
    while time.time() - warmup_start < WARMUP:
        futures = [executor.submit(run_lookup) for _ in range(CONCURRENCY)]
        for f in as_completed(futures):
            f.result()  # Discard warmup results

# Measured phase
print(f"Measuring for {{DURATION}}s...", flush=True)
latencies = []
errors = 0
start_time = time.time()
completed = 0

with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
    while time.time() - start_time < DURATION:
        futures = [executor.submit(run_lookup) for _ in range(CONCURRENCY)]
        for f in as_completed(futures):
            lat = f.result()
            if lat is not None:
                latencies.append(lat)
                completed += 1
            else:
                errors += 1

total_time = time.time() - start_time
latencies.sort()

print(f"lookup_by_id_per_sec={{completed / total_time:.2f}}")
print(f"p50_ms={{latencies[len(latencies)//2]:.2f}}" if latencies else "p50_ms=0")
print(f"p95_ms={{latencies[int(len(latencies)*0.95)]:.2f}}" if latencies else "p95_ms=0")
print(f"p99_ms={{latencies[int(len(latencies)*0.99)]:.2f}}" if latencies else "p99_ms=0")
print(f"total_lookups={{completed}}")
print(f"errors={{errors}}")
"""

    # Write and run benchmark script on benchmark VM
    write_cmd = f"cat > /tmp/lookup_bench.py << 'EOFBENCH'\n{bench_script}\nEOFBENCH"
    code, _ = run_ssh_command(benchmark_ip, write_cmd, timeout=30)
    if code != 0:
        return BenchmarkResult(error="Failed to write benchmark script")

    start = time.time()
    bench_cmd = "python3 /tmp/lookup_bench.py 2>&1"
    code, output = run_ssh_command(
        benchmark_ip, bench_cmd, timeout=warmup + duration + 120
    )
    elapsed = time.time() - start

    if code != 0:
        return BenchmarkResult(error=f"Benchmark failed: {output[:500]}")

    return parse_benchmark_output(output, elapsed)


def parse_benchmark_output(output: str, duration: float) -> BenchmarkResult:
    """Parse benchmark output."""
    result = BenchmarkResult(duration_s=duration)

    for line in output.split("\n"):
        if "=" not in line:
            continue
        key, value = line.strip().split("=", 1)
        try:
            if key == "lookup_by_id_per_sec":
                result.lookup_by_id_per_sec = float(value)
            elif key == "p50_ms":
                result.lookup_by_id_p50_ms = float(value)
            elif key == "p95_ms":
                result.lookup_by_id_p95_ms = float(value)
            elif key == "p99_ms":
                result.lookup_by_id_p99_ms = float(value)
            elif key == "total_lookups":
                result.total_lookups = int(value)
        except ValueError:
            continue

    if result.lookup_by_id_per_sec == 0:
        result.error = f"Failed to parse benchmark output: {output[:300]}"

    return result


def calculate_cost(infra_config: dict, cloud: str) -> float:
    """Estimate monthly cost for the configuration."""
    return calculate_vm_cost(
        cloud=cloud,
        cpu=infra_config.get("cpu", 4),
        ram_gb=infra_config.get("ram_gb", 16),
        disks=[
            DiskConfig(
                size_gb=infra_config.get("disk_size_gb", 100),
                disk_type=infra_config.get("disk_type", "fast"),
            )
        ],
    )


def save_result(
    result: BenchmarkResult,
    infra_config: dict,
    trino_config: dict,
    trial_number: int,
    cloud: str,
    mode: str,
    cloud_config: CloudConfig,
    login: str,
) -> None:
    """Save benchmark result to JSON file."""
    store = get_store()

    timings_dict = None
    if result.timings:
        timings_dict = {
            "terraform_s": result.timings.terraform_s,
            "vm_ready_s": result.timings.vm_ready_s,
            "service_ready_s": result.timings.service_ready_s,
            "baseline_s": result.timings.baseline_s,
            "data_gen_s": result.timings.data_gen_s,
            "benchmark_s": result.timings.benchmark_s,
            "destroy_s": result.timings.destroy_s,
            "trial_total_s": result.timings.trial_total_s,
        }

    baseline_metrics = None
    if result.baseline:
        fio_metrics = None
        if result.baseline.fio:
            fio_metrics = {
                "rand_read_iops": result.baseline.fio.rand_read_iops,
                "rand_write_iops": result.baseline.fio.rand_write_iops,
                "rand_read_lat_ms": result.baseline.fio.rand_read_lat_ms,
                "rand_write_lat_ms": result.baseline.fio.rand_write_lat_ms,
                "seq_read_mib_s": result.baseline.fio.seq_read_mib_s,
                "seq_write_mib_s": result.baseline.fio.seq_write_mib_s,
            }
        sysbench_metrics = None
        if result.baseline.sysbench:
            sysbench_metrics = {
                "cpu_events_per_sec": result.baseline.sysbench.cpu_events_per_sec,
                "mem_mib_per_sec": result.baseline.sysbench.mem_mib_per_sec,
            }
        baseline_metrics = {"fio": fio_metrics, "sysbench": sysbench_metrics}

    store.add_dict(
        {
            "trial": trial_number,
            "timestamp": datetime.now().isoformat(),
            "cloud": cloud,
            "login": login,
            "mode": mode,
            "infra_config": infra_config,
            "trino_config": trino_config,
            "metrics": {
                "lookup_by_id_per_sec": result.lookup_by_id_per_sec,
                "lookup_by_id_p50_ms": result.lookup_by_id_p50_ms,
                "lookup_by_id_p95_ms": result.lookup_by_id_p95_ms,
                "lookup_by_id_p99_ms": result.lookup_by_id_p99_ms,
                "total_lookups": result.total_lookups,
                "duration_s": result.duration_s,
            },
            "error": result.error,
            "system_baseline": baseline_metrics,
            "timings": timings_dict,
        }
    )

    export_results_md(cloud)


def ensure_infra(
    cloud_config: CloudConfig,
    infra_config: dict,
    timings: TrialTimings,
) -> tuple[str, str]:
    """Ensure infrastructure exists with given config.

    Returns (benchmark_vm_ip, trino_vm_ip).
    """
    tf = get_terraform(cloud_config.terraform_dir)

    tf_vars = {
        "trino_enabled": "true",
        "trino_cpu": str(infra_config["cpu"]),
        "trino_ram_gb": str(infra_config["ram_gb"]),
        "trino_disk_size_gb": str(infra_config["disk_size_gb"]),
        "trino_disk_type": infra_config["disk_type"],
        # Disable other services
        "redis_enabled": "false",
        "minio_enabled": "false",
        "postgres_enabled": "false",
        "meilisearch_enabled": "false",
    }

    print(f"  Applying Terraform with: {infra_config}")
    tf_start = time.time()
    ret_code, stdout, stderr = tf.apply(skip_plan=True, var=tf_vars)
    timings.terraform_s = time.time() - tf_start

    if ret_code != 0:
        raise RuntimeError(f"Terraform apply failed: {(stderr or '')[:500]}")

    benchmark_ip = get_tf_output(tf, "benchmark_vm_ip")
    trino_ip = get_tf_output(tf, "trino_vm_ip") or TRINO_IP

    if not benchmark_ip:
        raise RuntimeError("Could not get benchmark VM IP from Terraform")

    # Wait for VM to be ready
    vm_start = time.time()
    if not wait_for_vm_ready(trino_ip, timeout=300, jump_host=benchmark_ip):
        raise RuntimeError("Trino VM not ready after 300s")
    timings.vm_ready_s = time.time() - vm_start

    # Wait for services
    svc_start = time.time()
    if not wait_for_nessie_ready(trino_ip, timeout=120, jump_host=benchmark_ip):
        raise RuntimeError("Nessie not ready after 120s")
    if not wait_for_trino_ready(trino_ip, timeout=300, jump_host=benchmark_ip):
        raise RuntimeError("Trino not ready after 300s")
    timings.service_ready_s = time.time() - svc_start

    return benchmark_ip, trino_ip


def objective_infra(
    trial: optuna.Trial,
    cloud_config: CloudConfig,
    metric: str,
    login: str,
    row_count: int,
    default_trino_config: dict,
) -> float:
    """Objective function for infrastructure optimization."""
    trial_start = time.time()
    timings = TrialTimings()

    cloud = cloud_config.name
    space = get_infra_search_space(cloud)

    # Sample infrastructure parameters
    cpu = trial.suggest_categorical("cpu", space["cpu"])
    valid_ram = filter_valid_ram(cloud, cpu, space["ram_gb"])
    ram_gb = trial.suggest_categorical(f"ram_gb_cpu{cpu}", valid_ram)
    disk_type = trial.suggest_categorical("disk_type", space["disk_type"])
    disk_size_gb = trial.suggest_categorical("disk_size_gb", space["disk_size_gb"])

    infra_config = {
        "cpu": cpu,
        "ram_gb": ram_gb,
        "disk_type": disk_type,
        "disk_size_gb": disk_size_gb,
    }

    trino_config = default_trino_config.copy()

    print(f"\n[Trial {trial.number}] Infra: {cpu}cpu/{ram_gb}gb/{disk_type}")

    # Check cache
    cached = find_cached_result(infra_config, trino_config, cloud)
    if cached:
        print("  Using cached result")
        return get_metric_value(cached, metric, METRICS)

    try:
        benchmark_ip, trino_ip = ensure_infra(cloud_config, infra_config, timings)

        # Run system baseline
        baseline_start = time.time()
        baseline = run_system_baseline(
            trino_ip, jump_host=benchmark_ip, test_dir="/data"
        )
        timings.baseline_s = time.time() - baseline_start

        # Setup samples-generation
        if not setup_samples_generation(trino_ip, jump_host=benchmark_ip):
            raise RuntimeError("Failed to setup samples-generation")

        # Generate data
        data_start = time.time()
        success, _ = generate_data(
            trino_ip, trino_config, row_count, jump_host=benchmark_ip
        )
        timings.data_gen_s = time.time() - data_start
        if not success:
            raise RuntimeError("Data generation failed")

        # Run benchmark
        bench_start = time.time()
        result = run_lookup_by_id_benchmark(
            benchmark_ip, trino_ip, duration=60, concurrency=16
        )
        timings.benchmark_s = time.time() - bench_start

        result.baseline = baseline
        result.timings = timings
        timings.trial_total_s = time.time() - trial_start

        if result.error:
            print(f"  Benchmark error: {result.error}")
            raise optuna.TrialPruned()

        print(
            f"  Result: {result.lookup_by_id_per_sec:.1f} lookups/s, "
            f"p50={result.lookup_by_id_p50_ms:.1f}ms, p99={result.lookup_by_id_p99_ms:.1f}ms"
        )

        save_result(
            result,
            infra_config,
            trino_config,
            trial.number,
            cloud,
            "infra",
            cloud_config,
            login,
        )

        return get_metric_value(
            {"metrics": {"lookup_by_id_per_sec": result.lookup_by_id_per_sec}},
            metric,
            METRICS,
        )

    except Exception as e:
        print(f"  Trial failed: {e}")
        raise optuna.TrialPruned()


def objective_config(
    trial: optuna.Trial,
    cloud_config: CloudConfig,
    metric: str,
    login: str,
    fixed_infra: dict,
    benchmark_ip: str,
    trino_ip: str,
    row_count: int,
) -> float:
    """Objective function for config optimization on fixed infrastructure."""
    trial_start = time.time()
    timings = TrialTimings()

    cloud = cloud_config.name
    space = get_config_search_space()
    ram_gb = fixed_infra["ram_gb"]

    # Sample Trino configuration
    compression = trial.suggest_categorical("compression", space["compression"])
    valid_levels = filter_compression_levels(compression, space["compression_level"])
    compression_level = trial.suggest_categorical(
        f"compression_level_{compression}", valid_levels
    )

    trino_config = {
        "trino_heap_pct": trial.suggest_categorical(
            "trino_heap_pct", space["trino_heap_pct"]
        ),
        "trino_query_max_memory_pct": trial.suggest_categorical(
            "trino_query_max_memory_pct", space["trino_query_max_memory_pct"]
        ),
        "task_concurrency": trial.suggest_categorical(
            "task_concurrency", space["task_concurrency"]
        ),
        "task_writer_count": trial.suggest_categorical(
            "task_writer_count", space["task_writer_count"]
        ),
        "compression": compression,
        "compression_level": compression_level,
        "partition_key": trial.suggest_categorical(
            "partition_key", space["partition_key"]
        ),
        "target_file_size_mb": trial.suggest_categorical(
            "target_file_size_mb", space["target_file_size_mb"]
        ),
    }

    print(
        f"\n[Trial {trial.number}] Config: compression={compression}, partition={trino_config['partition_key']}"
    )

    # Check cache
    cached = find_cached_result(fixed_infra, trino_config, cloud)
    if cached:
        print("  Using cached result")
        return get_metric_value(cached, metric, METRICS)

    try:
        # Reconfigure Trino
        if not reconfigure_trino(
            trino_ip, trino_config, ram_gb, jump_host=benchmark_ip
        ):
            raise RuntimeError("Failed to reconfigure Trino")

        # Regenerate data with new table properties
        data_start = time.time()
        success, _ = generate_data(
            trino_ip, trino_config, row_count, jump_host=benchmark_ip
        )
        timings.data_gen_s = time.time() - data_start
        if not success:
            raise RuntimeError("Data generation failed")

        # Run benchmark
        bench_start = time.time()
        result = run_lookup_by_id_benchmark(
            benchmark_ip, trino_ip, duration=60, concurrency=16
        )
        timings.benchmark_s = time.time() - bench_start

        result.timings = timings
        timings.trial_total_s = time.time() - trial_start

        if result.error:
            print(f"  Benchmark error: {result.error}")
            raise optuna.TrialPruned()

        print(
            f"  Result: {result.lookup_by_id_per_sec:.1f} lookups/s, "
            f"p50={result.lookup_by_id_p50_ms:.1f}ms, p99={result.lookup_by_id_p99_ms:.1f}ms"
        )

        save_result(
            result,
            fixed_infra,
            trino_config,
            trial.number,
            cloud,
            "config",
            cloud_config,
            login,
        )

        return get_metric_value(
            {"metrics": {"lookup_by_id_per_sec": result.lookup_by_id_per_sec}},
            metric,
            METRICS,
        )

    except Exception as e:
        print(f"  Trial failed: {e}")
        raise optuna.TrialPruned()


def infra_summary(c: dict) -> str:
    """Format infra config as compact string."""
    return f"{c.get('cpu', 0)}cpu/{c.get('ram_gb', 0)}gb/{c.get('disk_type', '?')}"


def trino_summary(c: dict) -> str:
    """Format trino config as compact string."""
    return f"{c.get('compression', '?')}/{c.get('partition_key', 'none')}"


def format_results(cloud: str) -> dict | None:
    """Format benchmark results for display."""
    store = get_store()
    results = store.as_dicts()
    if not results:
        return None

    results = [r for r in results if r.get("cloud", "") == cloud]
    if not results:
        return None

    results_sorted = sorted(
        results, key=lambda x: get_metric(x, "lookup_by_id_per_sec"), reverse=True
    )

    rows = []
    for r in results_sorted:
        infra = r.get("infra_config", {})
        trino = r.get("trino_config", {})
        cloud_name = r.get("cloud", cloud)
        cost = calculate_cost(infra, cloud_name)
        lookups = get_metric(r, "lookup_by_id_per_sec")
        eff = lookups / cost if cost > 0 else 0
        rows.append(
            {
                "mode": r.get("mode", "?"),
                "cpu": infra.get("cpu", 0),
                "ram": infra.get("ram_gb", 0),
                "disk": infra.get("disk_type", "?"),
                "compression": trino.get("compression", "?"),
                "partition": trino.get("partition_key", "none"),
                "lookups": lookups,
                "p50": get_metric(r, "lookup_by_id_p50_ms"),
                "p99": get_metric(r, "lookup_by_id_p99_ms"),
                "cost": cost,
                "eff": eff,
            }
        )

    best_lookups_row = max(rows, key=lambda x: x.get("lookups", 0))
    best_lat_row = min(rows, key=lambda x: x.get("p99", float("inf")))
    best_eff_row = max(rows, key=lambda x: x.get("eff", 0))

    return {
        "cloud": cloud,
        "rows": rows,
        "best_lookups": best_lookups_row,
        "best_latency": best_lat_row,
        "best_efficiency": best_eff_row,
    }


def show_results(cloud: str) -> None:
    """Display results table to console."""
    data = format_results(cloud)
    if not data:
        print(f"No results found for {cloud}")
        return

    print(f"\n=== Trino-Iceberg Results ({cloud.upper()}) ===\n")
    print(
        f"{'Mode':<6} {'CPU':>3} {'RAM':>4} {'Disk':<5} {'Compress':<8} {'Partition':<12} "
        f"{'Lookups/s':>10} {'P50ms':>7} {'P99ms':>7} {'Cost':>8} {'Eff':>8}"
    )
    print("-" * 100)

    for row in data["rows"][:20]:
        print(
            f"{row['mode']:<6} {row['cpu']:>3} {row['ram']:>4} {row['disk']:<5} "
            f"{row['compression']:<8} {row['partition']:<12} "
            f"{row['lookups']:>10.1f} {row['p50']:>7.1f} {row['p99']:>7.1f} "
            f"{row['cost']:>8.0f} {row['eff']:>8.2f}"
        )

    print("\n--- Best Configurations ---")
    best = data["best_lookups"]
    print(
        f"Best lookups/s: {best['lookups']:.1f} ({best['cpu']}cpu/{best['ram']}gb, {best['compression']})"
    )
    best = data["best_latency"]
    print(
        f"Best P99 latency: {best['p99']:.1f}ms ({best['cpu']}cpu/{best['ram']}gb, {best['compression']})"
    )
    best = data["best_efficiency"]
    print(
        f"Best efficiency: {best['eff']:.2f} ({best['cpu']}cpu/{best['ram']}gb, {best['compression']})"
    )


def export_results_md(cloud: str, output_path: Path | None = None) -> None:
    """Export results to markdown file."""
    data = format_results(cloud)
    if not data:
        return

    if output_path is None:
        output_path = RESULTS_DIR / f"RESULTS_{cloud.upper()}.md"

    lines = [
        f"# Trino-Iceberg Benchmark Results - {cloud.upper()}",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Results",
        "",
        "| Mode | CPU | RAM | Disk | Compression | Partition | Lookups/s | P50ms | P99ms | Cost | Eff |",
        "|------|----:|----:|------|-------------|-----------|----------:|------:|------:|-----:|----:|",
    ]

    for row in data["rows"]:
        lines.append(
            f"| {row['mode']} | {row['cpu']} | {row['ram']} | {row['disk']} | "
            f"{row['compression']} | {row['partition']} | "
            f"{row['lookups']:.1f} | {row['p50']:.1f} | {row['p99']:.1f} | "
            f"{row['cost']:.0f} | {row['eff']:.2f} |"
        )

    lines.extend(
        [
            "",
            "## Best Configurations",
            "",
        ]
    )

    best = data["best_lookups"]
    lines.append(
        f"- **Best lookups/s**: {best['lookups']:.1f} ({best['cpu']}cpu/{best['ram']}gb, {best['compression']})"
    )
    best = data["best_latency"]
    lines.append(
        f"- **Best P99 latency**: {best['p99']:.1f}ms ({best['cpu']}cpu/{best['ram']}gb, {best['compression']})"
    )
    best = data["best_efficiency"]
    lines.append(
        f"- **Best efficiency**: {best['eff']:.2f} lookups/₽/mo ({best['cpu']}cpu/{best['ram']}gb)"
    )

    output_path.write_text("\n".join(lines))
    print(f"Results exported to {output_path}")


def get_default_trino_config() -> dict:
    """Get default Trino configuration for infra optimization."""
    return {
        "trino_heap_pct": 70,
        "trino_query_max_memory_pct": 40,
        "task_concurrency": 16,
        "task_writer_count": 2,
        "compression": "zstd",
        "compression_level": 3,
        "partition_key": "none",
        "target_file_size_mb": 128,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Trino-Iceberg Configuration Optimizer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Tune VM specs
  uv run python optimizers/trino_iceberg/optimizer.py --cloud selectel --mode infra --trials 10 --login damir

  # Tune Trino/Iceberg config on 8cpu/32gb host
  uv run python optimizers/trino_iceberg/optimizer.py --cloud selectel --mode config --cpu 8 --ram 32 --trials 50 --login damir

  # Full optimization
  uv run python optimizers/trino_iceberg/optimizer.py --cloud selectel --mode full --trials 20 --login damir
""",
    )

    # Use common argument helpers
    from argparse_helpers import add_common_arguments

    add_common_arguments(
        parser,
        metrics=METRICS,
        default_metric="lookup_by_id_per_sec",
        default_trials=20,
        study_prefix="trino-iceberg",
        with_mode=True,
        mode_default="infra",
        with_fixed_host=True,
        cpu_default=4,
        ram_default=16,
        with_benchmark_vm=False,  # Benchmark runs on same VM
    )
    # Add trino-iceberg specific argument
    parser.add_argument(
        "--rows", type=int, default=DEFAULT_ROW_COUNT, help="Number of rows to generate"
    )
    args = parser.parse_args()

    cloud_config = get_cloud_config(args.cloud)

    if args.show_results:
        show_results(args.cloud)
        return

    if args.export_md:
        export_results_md(args.cloud)
        return

    # Create Optuna study
    storage = f"sqlite:///{STUDY_DB}"
    study_name = (
        args.study_name or f"trino-iceberg-{args.cloud}-{args.mode}-{args.metric}"
    )

    metric_config = METRICS[args.metric]
    direction = (
        "maximize" if metric_config.direction.value == "maximize" else "minimize"
    )

    study = optuna.create_study(
        study_name=study_name,
        storage=storage,
        direction=direction,
        sampler=TPESampler(),
        load_if_exists=True,
    )

    print(f"\n{'=' * 60}")
    print("Trino-Iceberg Optimizer")
    print(f"Cloud: {args.cloud}, Mode: {args.mode}, Metric: {args.metric}")
    print(f"Trials: {args.trials}, Rows: {args.rows:,}")
    print(f"{'=' * 60}\n")

    try:
        if args.mode == "infra":
            study.optimize(
                lambda t: objective_infra(
                    t,
                    cloud_config,
                    args.metric,
                    args.login,
                    args.rows,
                    get_default_trino_config(),
                ),
                n_trials=args.trials,
            )
        elif args.mode == "config":
            # For config mode, infrastructure must already exist
            fixed_infra = {
                "cpu": args.cpu,
                "ram_gb": args.ram,
                "disk_type": "fast",
                "disk_size_gb": 200,
            }
            tf = get_terraform(cloud_config.terraform_dir)
            benchmark_ip = get_tf_output(tf, "benchmark_vm_ip")
            trino_ip = get_tf_output(tf, "trino_vm_ip") or TRINO_IP

            if not benchmark_ip:
                print(
                    "Error: No infrastructure found. Run --mode infra first or create infrastructure manually."
                )
                return

            study.optimize(
                lambda t: objective_config(
                    t,
                    cloud_config,
                    args.metric,
                    args.login,
                    fixed_infra,
                    benchmark_ip,
                    trino_ip,
                    args.rows,
                ),
                n_trials=args.trials,
            )
        elif args.mode == "full":
            # Phase 1: Infrastructure optimization
            print("\n=== Phase 1: Infrastructure Optimization ===\n")
            study_infra = optuna.create_study(
                study_name=f"{study_name}-infra",
                storage=storage,
                direction=direction,
                sampler=TPESampler(),
                load_if_exists=True,
            )
            study_infra.optimize(
                lambda t: objective_infra(
                    t,
                    cloud_config,
                    args.metric,
                    args.login,
                    args.rows,
                    get_default_trino_config(),
                ),
                n_trials=args.trials // 2,
            )

            # Get best infra from results
            store = get_store()
            results = [
                r
                for r in store.as_dicts()
                if r.get("cloud") == args.cloud and r.get("mode") == "infra"
            ]
            if not results:
                print("No infra results found, cannot proceed to config optimization")
                return

            best_result = max(
                results, key=lambda r: get_metric(r, "lookup_by_id_per_sec")
            )
            best_infra = best_result.get("infra_config", {})
            print(f"\nBest infra: {infra_summary(best_infra)}")

            # Phase 2: Config optimization on best infra
            print("\n=== Phase 2: Config Optimization ===\n")
            tf = get_terraform(cloud_config.terraform_dir)
            benchmark_ip = get_tf_output(tf, "benchmark_vm_ip")
            trino_ip = get_tf_output(tf, "trino_vm_ip") or TRINO_IP

            if not benchmark_ip:
                raise RuntimeError(
                    "Could not get benchmark VM IP for config optimization"
                )

            study_config = optuna.create_study(
                study_name=f"{study_name}-config",
                storage=storage,
                direction=direction,
                sampler=TPESampler(),
                load_if_exists=True,
            )
            study_config.optimize(
                lambda t: objective_config(
                    t,
                    cloud_config,
                    args.metric,
                    args.login,
                    best_infra,
                    benchmark_ip,
                    trino_ip,
                    args.rows,
                ),
                n_trials=args.trials - args.trials // 2,
            )

    finally:
        if not args.no_destroy:
            print("\nDestroying infrastructure...")
            destroy_all(cloud_config.terraform_dir, args.cloud)

    print("\n=== Optimization Complete ===")
    show_results(args.cloud)


if __name__ == "__main__":
    main()
