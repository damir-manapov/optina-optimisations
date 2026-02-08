#!/usr/bin/env python3
"""
Multi-Cloud Redis Configuration Optimizer using Bayesian Optimization (Optuna).

Supports both Selectel and Timeweb Cloud providers.
Optimizes Redis single-node and Sentinel configurations.

Usage:
    uv run python optimizers/redis/optimizer.py --cloud selectel --trials 10 --metric ops_per_sec
    uv run python optimizers/redis/optimizer.py --cloud selectel --trials 10 --metric p99_latency_ms
    uv run python optimizers/redis/optimizer.py --cloud selectel --no-destroy
    uv run python optimizers/redis/optimizer.py --cloud selectel --show-results
    uv run python optimizers/redis/optimizer.py --cloud selectel --export-md
"""

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import optuna
from optuna.samplers import TPESampler

# Add root dir to path for common imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from common import (
    clear_known_hosts_on_vm,
    destroy_all,
    get_terraform,
    get_tf_output,
    run_ssh_command,
    wait_for_vm_ready,
)
from storage import TrialStore, get_store as _get_store

from optimizers.redis.cloud_config import (
    CloudConfig,
    get_cloud_config,
    get_config_space,
)
from metrics import get_metric_value
from optimizers.redis.metrics import METRICS
from pricing import DiskConfig, calculate_vm_cost, filter_valid_ram

RESULTS_DIR = Path(__file__).parent  # For local files (study.db, markdown)
STUDY_DB = RESULTS_DIR / "study.db"


def get_store() -> TrialStore:
    """Get the TrialStore for Redis results."""
    return _get_store("redis")


def config_summary(r: dict) -> str:
    """Format config as a compact string."""
    c = r.get("config", {})
    nodes = r.get("nodes", 1 if c.get("mode") == "single" else 3)
    return f"{c.get('mode', '?')} {nodes}×{c.get('cpu_per_node', 0)}cpu/{c.get('ram_per_node', 0)}gb io={c.get('io_threads', 0)} {c.get('persistence', '?')}"


def format_results(cloud: str) -> dict | None:
    """Format benchmark results for display/export. Returns None if no results."""
    store = get_store()
    results = store.as_dicts()

    if not results:
        return None

    results_sorted = sorted(
        results, key=lambda x: x.get("ops_per_sec", 0), reverse=True
    )

    # Extract row data
    rows = []
    for r in results_sorted:
        cfg = r.get("config", {})
        mode = cfg.get("mode", "?")
        cloud_name = r.get("cloud", cloud)
        # Calculate cost on-the-fly from config
        cost = calculate_cost(cfg, cloud_name)
        ops = r.get("ops_per_sec", 0)
        eff = ops / cost if cost > 0 else 0
        rows.append(
            {
                "mode": mode,
                "nodes": r.get("nodes", 1 if mode == "single" else 3),
                "cpu": cfg.get("cpu_per_node", 0),
                "ram": cfg.get("ram_per_node", 0),
                "policy": cfg.get("maxmemory_policy", "?"),
                "io": cfg.get("io_threads", 0),
                "persist": cfg.get("persistence", "?"),
                "ops": ops,
                "p99": r.get("p99_latency_ms", 0),
                "cost": cost,
                "eff": eff,
                "_result": r,  # Keep reference for best calculation
            }
        )

    # Best configs - use rows for efficiency (calculated on-the-fly)
    best_ops_row = max(rows, key=lambda x: x.get("ops", 0))
    best_latency_row = min(rows, key=lambda x: x.get("p99", float("inf")))
    best_eff_row = max(rows, key=lambda x: x.get("eff", 0))

    return {
        "cloud": cloud,
        "rows": rows,
        "best": {
            "ops": {
                "value": best_ops_row.get("ops", 0),
                "config": config_summary(best_ops_row["_result"]),
            },
            "latency": {
                "value": best_latency_row.get("p99", 0),
                "config": config_summary(best_latency_row["_result"]),
            },
            "efficiency": {
                "value": best_eff_row.get("eff", 0),
                "config": config_summary(best_eff_row["_result"]),
            },
        },
    }


def show_results(cloud: str) -> None:
    """Display all benchmark results for a cloud in a table format."""
    data = format_results(cloud)

    if not data:
        print(f"No results found for {cloud}")
        return

    print(f"\n{'=' * 100}")
    print(f"Redis Benchmark Results - {cloud.upper()}")
    print(f"{'=' * 100}")

    # Header
    print(
        f"{'#':>3} {'Mode':<8} {'Nodes':>5} {'CPU':>4} {'RAM':>4} {'Policy':<12} "
        f"{'IO':>3} {'Persist':<5} {'Ops/s':>10} {'p99ms':>7} {'$/hr':>6} {'Eff':>8}"
    )
    print("-" * 100)

    for i, r in enumerate(data["rows"], 1):
        print(
            f"{i:>3} {r['mode'][:8]:<8} {r['nodes']:>5} {r['cpu']:>4} {r['ram']:>4} {r['policy'][:12]:<12} "
            f"{r['io']:>3} {r['persist'][:5]:<5} {r['ops']:>10.0f} {r['p99']:>7.2f} {r['cost']:>6.2f} {r['eff']:>8.0f}"
        )

    print("-" * 100)
    print(f"Total: {len(data['rows'])} results")

    best = data["best"]
    print(
        f"\nBest by ops/sec:     {best['ops']['value']:>10.0f} {'ops/s':<9} [{best['ops']['config']}]"
    )
    print(
        f"Best by p99 latency: {best['latency']['value']:>10.2f} {'ms':<9} [{best['latency']['config']}]"
    )
    print(
        f"Best by efficiency:  {best['efficiency']['value']:>10.0f} {'ops/$/hr':<9} [{best['efficiency']['config']}]"
    )


def export_results_md(cloud: str, output_path: Path | None = None) -> None:
    """Export benchmark results to a markdown file."""
    data = format_results(cloud)

    if not data:
        print(f"No results found for {cloud}")
        return

    if output_path is None:
        output_path = RESULTS_DIR / f"RESULTS_{cloud.upper()}.md"

    lines = [
        f"# Redis Benchmark Results - {cloud.upper()}",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Results",
        "",
        "| # | Mode | Nodes | CPU | RAM | Policy | IO | Persist | Ops/s | p99 (ms) | $/hr | Efficiency |",
        "|--:|------|------:|----:|----:|--------|---:|---------|------:|---------:|-----:|-----------:|",
    ]

    for i, r in enumerate(data["rows"], 1):
        lines.append(
            f"| {i} | {r['mode']} | {r['nodes']} | {r['cpu']} | {r['ram']} | {r['policy']} | {r['io']} | {r['persist']} | {r['ops']:.0f} | {r['p99']:.2f} | {r['cost']:.2f} | {r['eff']:.0f} |"
        )

    best = data["best"]
    lines.extend(
        [
            "",
            "## Best Configurations",
            "",
            f"- **Best by ops/sec:** {best['ops']['value']:.0f} ops/s — `{best['ops']['config']}`",
            f"- **Best by p99 latency:** {best['latency']['value']:.2f}ms — `{best['latency']['config']}`",
            f"- **Best by efficiency:** {best['efficiency']['value']:.0f} ops/$/hr — `{best['efficiency']['config']}`",
            "",
        ]
    )

    output_path.write_text("\n".join(lines))
    print(f"Results exported to {output_path}")


@dataclass
class MemtierResult:
    """Memtier benchmark results."""

    ops_per_sec: float = 0.0
    get_ops_per_sec: float = 0.0
    set_ops_per_sec: float = 0.0
    avg_latency_ms: float = 0.0
    p50_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    p999_latency_ms: float = 0.0
    kb_per_sec: float = 0.0


@dataclass
class TrialTimings:
    """Timing measurements for each phase of a trial."""

    redis_deploy_s: float = 0.0  # Terraform + wait for Redis
    benchmark_s: float = 0.0  # memtier benchmark
    trial_total_s: float = 0.0  # End-to-end trial time


@dataclass
class BenchmarkResult:
    config: dict
    ops_per_sec: float = 0.0
    p50_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    p999_latency_ms: float = 0.0
    avg_latency_ms: float = 0.0
    kb_per_sec: float = 0.0
    duration_s: float = 0.0
    error: str | None = None
    timings: TrialTimings | None = None


def config_to_key(config: dict, cloud: str) -> str:
    """Convert config dict to a hashable key for deduplication."""
    return json.dumps(
        {
            "cloud": cloud,
            "mode": config["mode"],
            "cpu_per_node": config["cpu_per_node"],
            "ram_per_node": config["ram_per_node"],
            "maxmemory_policy": config["maxmemory_policy"],
            "io_threads": config["io_threads"],
            "persistence": config["persistence"],
        },
        sort_keys=True,
    )


def find_cached_result(config: dict, cloud: str) -> dict | None:
    """Find a cached successful result for the given config."""
    target_key = config_to_key(config, cloud)
    store = get_store()
    trial = store.find_by_config_key(target_key)
    if trial is None:
        return None
    if trial.error:
        return None
    if (trial.ops_per_sec or 0) <= 0:
        return None
    return trial.model_dump()


def load_historical_trials(study: optuna.Study, cloud: str, metric: str) -> int:
    """Load historical results into Optuna study as completed trials.

    This helps Optuna make better suggestions by learning from past results.
    Returns the number of trials loaded.
    """
    store = get_store()
    if store.count() == 0:
        return 0

    # Filter results for this cloud that have valid ops
    valid_results = [
        r
        for r in store.as_dicts()
        if r.get("cloud") == cloud
        and not r.get("error")
        and r.get("ops_per_sec", 0) > 0
        and r.get("config", {}).get("cpu_per_node")
    ]

    if not valid_results:
        return 0

    config_space = get_config_space(cloud)
    loaded = 0
    seen_configs = set()

    for result in valid_results:
        config = result.get("config", {})

        # Create a unique key to avoid duplicates
        config_key = config_to_key(config, cloud)
        if config_key in seen_configs:
            continue
        seen_configs.add(config_key)

        cpu = config.get("cpu_per_node")
        ram = config.get("ram_per_node")
        mode = config.get("mode")
        policy = config.get("maxmemory_policy")
        io_threads = config.get("io_threads")
        persistence = config.get("persistence")

        # Validate all values are in search space
        if cpu not in config_space["cpu_per_node"]:
            continue
        if mode not in config_space["mode"]:
            continue
        if policy not in config_space["maxmemory_policy"]:
            continue
        if io_threads not in config_space["io_threads"]:
            continue
        if persistence not in config_space["persistence"]:
            continue

        # Check RAM is valid for this CPU
        valid_ram = filter_valid_ram(cloud, cpu, config_space["ram_per_node"])
        if ram not in valid_ram:
            continue

        # Build params with CPU-specific RAM param name (matches objective function)
        params = {
            "cpu_per_node": cpu,
            f"ram_per_node_cpu{cpu}": ram,
            "mode": mode,
            "maxmemory_policy": policy,
            "io_threads": io_threads,
            "persistence": persistence,
        }

        # Build distributions
        distributions = {
            "cpu_per_node": optuna.distributions.CategoricalDistribution(
                config_space["cpu_per_node"]
            ),
            f"ram_per_node_cpu{cpu}": optuna.distributions.CategoricalDistribution(
                valid_ram
            ),
            "mode": optuna.distributions.CategoricalDistribution(config_space["mode"]),
            "maxmemory_policy": optuna.distributions.CategoricalDistribution(
                config_space["maxmemory_policy"]
            ),
            "io_threads": optuna.distributions.CategoricalDistribution(
                config_space["io_threads"]
            ),
            "persistence": optuna.distributions.CategoricalDistribution(
                config_space["persistence"]
            ),
        }

        # Calculate metric value
        value = get_metric_value(result, metric, METRICS)

        # Create and add trial
        try:
            trial = optuna.trial.create_trial(
                params=params,
                distributions=dict(distributions),  # type: ignore[arg-type]
                values=[value],
            )
            study.add_trial(trial)
            loaded += 1
        except Exception as e:
            print(f"  Warning: Could not add historical trial: {e}")
            continue

    return loaded


def wait_for_redis_ready(
    vm_ip: str, redis_ip: str = "10.0.0.20", timeout: int = 180
) -> bool:
    """Wait for Redis to be ready."""
    clear_known_hosts_on_vm(vm_ip)

    print(f"  Waiting for Redis at {redis_ip} to be ready...")

    start = time.time()
    while time.time() - start < timeout:
        elapsed = time.time() - start
        try:
            check_cmd = (
                f"ssh -A -o StrictHostKeyChecking=no -o ConnectTimeout=5 root@{redis_ip} "
                f"'test -f /root/cloud-init-ready && redis-cli ping'"
            )
            code, output = run_ssh_command(
                vm_ip, check_cmd, timeout=20, forward_agent=True
            )
            if code == 0 and "PONG" in output:
                print(f"  Redis is ready! ({elapsed:.0f}s)")
                return True
            else:
                print(f"  Redis not ready yet ({elapsed:.0f}s)...")
        except Exception as e:
            print(f"  Redis check failed ({elapsed:.0f}s): {e}")
        time.sleep(10)

    print(f"  Warning: Redis not ready after {timeout}s")
    return False


def ensure_benchmark_vm(cloud_config: CloudConfig) -> str:
    """Ensure benchmark VM exists and return its IP."""
    print(f"\nChecking benchmark VM for {cloud_config.name}...")

    tf = get_terraform(cloud_config.terraform_dir)

    vm_ip = get_tf_output(tf, "benchmark_vm_ip")
    if vm_ip:
        print(f"  Found VM: {vm_ip}")
        try:
            code, _ = run_ssh_command(vm_ip, "echo ok", timeout=10)
            if code == 0:
                return vm_ip
        except Exception:
            pass

    print("  Creating benchmark VM...")
    tf_vars = {"redis_enabled": False, "minio_enabled": False}
    ret_code, stdout, stderr = tf.apply(skip_plan=True, var=tf_vars)

    if ret_code != 0:
        raise RuntimeError(f"Failed to create benchmark VM: {stderr}")

    vm_ip = get_tf_output(tf, "benchmark_vm_ip")
    if not vm_ip:
        raise RuntimeError("Benchmark VM created but no IP returned")

    print(f"  Benchmark VM created: {vm_ip}")
    wait_for_vm_ready(vm_ip)

    # Install memtier_benchmark
    print("  Installing memtier_benchmark...")
    install_cmd = (
        "apt-get update && "
        "apt-get install -y build-essential autoconf automake libpcre3-dev "
        "libevent-dev pkg-config zlib1g-dev libssl-dev git && "
        "cd /tmp && "
        "git clone https://github.com/RedisLabs/memtier_benchmark.git && "
        "cd memtier_benchmark && "
        "autoreconf -ivf && ./configure && make -j$(nproc) && make install"
    )
    code, output = run_ssh_command(vm_ip, install_cmd, timeout=300)
    if code != 0:
        print(
            f"  Warning: memtier_benchmark installation may have failed: {output[:500]}"
        )

    return vm_ip


def deploy_redis(
    config: dict, cloud_config: CloudConfig, vm_ip: str
) -> tuple[bool, float]:
    """Deploy Redis with given configuration."""
    print(f"  Deploying Redis on {cloud_config.name}: {config}")
    start = time.time()

    tf = get_terraform(cloud_config.terraform_dir)

    tf_vars = {
        "redis_enabled": True,
        "minio_enabled": False,
        "redis_mode": config["mode"],
        "redis_node_cpu": config["cpu_per_node"],
        "redis_node_ram_gb": config["ram_per_node"],
        "redis_maxmemory_policy": config["maxmemory_policy"],
        "redis_io_threads": config["io_threads"],
        "redis_persistence": config["persistence"],
    }

    ret_code, stdout, stderr = tf.apply(skip_plan=True, var=tf_vars)

    if ret_code != 0:
        print(f"  Terraform apply failed: {stderr}")
        return False, time.time() - start

    if not wait_for_redis_ready(vm_ip):
        print("  Warning: Redis may not be fully ready")

    duration = time.time() - start
    print(f"  Redis deployed in {duration:.1f}s")
    return True, duration


def destroy_redis(cloud_config: CloudConfig) -> tuple[bool, float]:
    """Destroy Redis but keep benchmark VM."""
    print(f"  Destroying Redis on {cloud_config.name}...")
    start = time.time()

    tf = get_terraform(cloud_config.terraform_dir)
    ret_code, stdout, stderr = tf.apply(
        skip_plan=True, var={"redis_enabled": False, "minio_enabled": False}
    )

    if ret_code != 0:
        print(f"  Warning: Redis destroy may have failed: {stderr}")
        return False, time.time() - start

    duration = time.time() - start
    print(f"  Redis destroyed in {duration:.1f}s")
    return True, duration


def run_memtier_benchmark(
    vm_ip: str, redis_ip: str = "10.0.0.20", duration: int = 60
) -> BenchmarkResult | None:
    """Run memtier_benchmark and parse results."""
    print("  Running memtier_benchmark...")

    # Cache-like workload: 80% GET, 20% SET
    memtier_cmd = (
        f"memtier_benchmark "
        f"--server={redis_ip} "
        f"--port=6379 "
        f"--clients=50 "
        f"--threads=4 "
        f"--ratio=1:4 "  # 1 SET : 4 GET = 20% write, 80% read
        f"--key-pattern=R:R "
        f"--key-minimum=1 "
        f"--key-maximum=10000000 "
        f"--data-size=256 "
        f"--test-time={duration} "
        f"--hide-histogram "
        f"2>&1"
    )

    start_time = time.time()
    try:
        code, output = run_ssh_command(vm_ip, memtier_cmd, timeout=duration + 60)
    except Exception as e:
        print(f"  Memtier failed: {e}")
        return None

    elapsed = time.time() - start_time

    if code != 0:
        print(f"  Memtier failed: {output[:500]}")
        return None

    return parse_memtier_output(output, elapsed)


def parse_memtier_output(output: str, duration: float) -> BenchmarkResult:
    """Parse memtier_benchmark output."""
    result = BenchmarkResult(config={}, duration_s=duration)

    # Parse Totals line:
    # Type         Ops/sec     Hits/sec   Misses/sec    Avg. Latency     p50 Latency     p99 Latency   p99.9 Latency       KB/sec
    # Totals     123456.78     98765.43       0.00         1.234           1.111           2.345           5.678        12345.67

    totals_pattern = r"Totals\s+([\d.]+)\s+[\d.]+\s+[\d.]+\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)"
    match = re.search(totals_pattern, output)
    if match:
        result.ops_per_sec = float(match.group(1))
        result.avg_latency_ms = float(match.group(2))
        result.p50_latency_ms = float(match.group(3))
        result.p99_latency_ms = float(match.group(4))
        result.p999_latency_ms = float(match.group(5))
        result.kb_per_sec = float(match.group(6))
    else:
        print(f"  Warning: Could not parse memtier output. Sample: {output[:500]}...")

    return result


def calculate_cost(config: dict, cloud: str) -> float:
    """Estimate monthly cost for the configuration."""
    nodes = 1 if config["mode"] == "single" else 3
    return calculate_vm_cost(
        cloud=cloud,
        cpu=config["cpu_per_node"],
        ram_gb=config["ram_per_node"],
        disks=[DiskConfig(size_gb=50, disk_type="fast")],
        nodes=nodes,
    )


def save_result(
    result: BenchmarkResult,
    config: dict,
    trial_number: int,
    cloud: str,
    cloud_config: CloudConfig,
    login: str,
) -> None:
    """Save benchmark result to JSON file."""
    store = get_store()

    timings_dict = None
    if result.timings:
        timings_dict = {
            "redis_deploy_s": result.timings.redis_deploy_s,
            "benchmark_s": result.timings.benchmark_s,
            "trial_total_s": result.timings.trial_total_s,
        }

    store.add_dict(
        {
            "trial": trial_number,
            "timestamp": datetime.now().isoformat(),
            "cloud": cloud,
            "login": login,
            "config": config,
            "nodes": 1 if config["mode"] == "single" else 3,
            "ops_per_sec": result.ops_per_sec,
            "avg_latency_ms": result.avg_latency_ms,
            "p50_latency_ms": result.p50_latency_ms,
            "p99_latency_ms": result.p99_latency_ms,
            "p999_latency_ms": result.p999_latency_ms,
            "kb_per_sec": result.kb_per_sec,
            "duration_s": result.duration_s,
            "error": result.error,
            "timings": timings_dict,
        }
    )

    # Auto-export markdown after each trial
    export_results_md(cloud)


def objective(
    trial: optuna.Trial,
    cloud: str,
    cloud_config: CloudConfig,
    vm_ip: str,
    login: str,
    metric: str = "ops_per_sec",
) -> float:
    """Optuna objective function."""
    config_space = get_config_space(cloud)

    # Select CPU first, then filter valid RAM options for that CPU
    cpu_per_node = trial.suggest_categorical(
        "cpu_per_node", config_space["cpu_per_node"]
    )
    valid_ram = filter_valid_ram(cloud, cpu_per_node, config_space["ram_per_node"])

    config = {
        "mode": trial.suggest_categorical("mode", config_space["mode"]),
        "cpu_per_node": cpu_per_node,
        "ram_per_node": trial.suggest_categorical(
            f"ram_per_node_cpu{cpu_per_node}", valid_ram
        ),
        "maxmemory_policy": trial.suggest_categorical(
            "maxmemory_policy", config_space["maxmemory_policy"]
        ),
        "io_threads": trial.suggest_categorical(
            "io_threads", config_space["io_threads"]
        ),
        "persistence": trial.suggest_categorical(
            "persistence", config_space["persistence"]
        ),
    }

    print(f"\n{'=' * 60}")
    print(f"Trial {trial.number} [{cloud}]: {config}")
    print(f"{'=' * 60}")
    trial_start = time.time()

    # Check cache
    cached = find_cached_result(config, cloud)
    if cached:
        cached_value = get_metric_value(cached, metric, METRICS)
        print(f"  Using cached result: {cached_value:.2f} ({metric})")
        return cached_value

    timings = TrialTimings()

    # Destroy any existing Redis
    print("  Cleaning up previous Redis deployment...")
    destroy_redis(cloud_config)
    time.sleep(10)

    # Deploy Redis
    success, deploy_time = deploy_redis(config, cloud_config, vm_ip)
    timings.redis_deploy_s = deploy_time
    if not success:
        print("  Deploy failed - marking trial as pruned (will retry config later)")
        raise optuna.TrialPruned("Deploy failed")

    # Run benchmark
    bench_start = time.time()
    result = run_memtier_benchmark(vm_ip)
    timings.benchmark_s = time.time() - bench_start

    if result is None or result.ops_per_sec == 0:
        print("  Benchmark failed - marking trial as pruned (will retry config later)")
        raise optuna.TrialPruned("Benchmark failed")

    timings.trial_total_s = time.time() - trial_start
    result.config = config
    result.timings = timings
    save_result(result, config, trial.number, cloud, cloud_config, login)

    cost = calculate_cost(config, cloud)
    result_metrics = {
        "ops_per_sec": result.ops_per_sec,
        "p99_latency_ms": result.p99_latency_ms,
        "cost_efficiency": result.ops_per_sec / cost if cost > 0 else 0,
    }

    metric_value = get_metric_value(result_metrics, metric, METRICS)

    print(
        f"  Result: {result.ops_per_sec:.0f} ops/s, p99={result.p99_latency_ms:.2f}ms, Cost: {cost:.2f}/hr"
    )
    print(
        f"  Timings: deploy={timings.redis_deploy_s:.0f}s, bench={timings.benchmark_s:.0f}s, total={timings.trial_total_s:.0f}s"
    )

    return metric_value


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Multi-Cloud Redis Optimizer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Optimize for throughput
  uv run python optimizers/redis/optimizer.py --cloud selectel --trials 10 --metric ops_per_sec

  # Optimize for latency
  uv run python optimizers/redis/optimizer.py --cloud selectel --trials 10 --metric p99_latency_ms

  # Keep infrastructure after optimization
  uv run python optimizers/redis/optimizer.py --cloud selectel --trials 10 --no-destroy

  # Show all results
  uv run python optimizers/redis/optimizer.py --cloud selectel --show-results

  # Export results to markdown
  uv run python optimizers/redis/optimizer.py --cloud selectel --export-md
        """,
    )

    # Use common argument helpers
    from argparse_helpers import add_common_arguments

    add_common_arguments(
        parser,
        metrics=METRICS,
        default_metric="ops_per_sec",
        default_trials=10,
        study_prefix="redis",
    )
    args = parser.parse_args()

    # Handle --show-results
    if args.show_results:
        show_results(args.cloud)
        return

    # Handle --export-md
    if args.export_md:
        export_results_md(args.cloud)
        return

    cloud_config = get_cloud_config(args.cloud)
    study_name = args.study_name or f"redis-{args.cloud}-{args.metric}"

    print("=" * 60)
    print(f"Redis Optimizer - {args.cloud.upper()}")
    print("=" * 60)
    print(f"Metric: {args.metric} ({METRICS[args.metric]})")
    print(f"Trials: {args.trials}")
    print(f"Terraform dir: {cloud_config.terraform_dir}")
    print(f"Results file: {get_store().path}")
    print()

    # Ensure benchmark VM exists
    if args.benchmark_vm_ip:
        vm_ip = args.benchmark_vm_ip
        print(f"Using provided benchmark VM: {vm_ip}")
    else:
        vm_ip = ensure_benchmark_vm(cloud_config)

    print(f"\nBenchmark VM IP: {vm_ip}")
    print()

    # Create/load Optuna study
    storage = f"sqlite:///{STUDY_DB}"
    study = optuna.create_study(
        study_name=study_name,
        storage=storage,
        direction="maximize",
        sampler=TPESampler(seed=42),
        load_if_exists=True,
    )

    # Load historical results into study for better suggestions
    n_loaded = load_historical_trials(study, args.cloud, args.metric)
    if n_loaded > 0:
        print(f"Loaded {n_loaded} historical trials from results.json")

    existing_trials = len(study.trials)
    if existing_trials > 0:
        print(f"Resuming study with {existing_trials} existing trials")
        try:
            best = study.best_trial
            print(f"Current best: {best.value:.2f} ({args.metric})")
        except ValueError:
            pass
    print()

    try:
        study.optimize(
            lambda trial: objective(
                trial, args.cloud, cloud_config, vm_ip, args.login, args.metric
            ),
            n_trials=args.trials,
            show_progress_bar=True,
        )

        print("\n" + "=" * 60)
        print(f"OPTIMIZATION COMPLETE ({args.cloud.upper()})")
        print("=" * 60)

        try:
            best = study.best_trial
            print(f"Best trial: {best.number}")
            print(f"Best config: {best.params}")
            if args.metric == "p99_latency_ms" and best.value is not None:
                print(f"Best {args.metric}: {-best.value:.2f}ms")
            elif best.value is not None:
                print(f"Best {args.metric}: {best.value:.2f}")
            else:
                print(f"Best {args.metric}: N/A")

            best_cost = calculate_cost(best.params, args.cloud)
            print(f"Best config cost: {best_cost:.2f}/hr")
        except ValueError:
            print("No successful trials completed")

        # Auto-export results to markdown
        export_results_md(args.cloud)
        print(f"\nResults exported to RESULTS_{args.cloud.upper()}.md")

    finally:
        if not args.no_destroy:
            destroy_all(cloud_config.terraform_dir, cloud_config.name)
        else:
            print("\n--no-destroy specified, keeping infrastructure.")


if __name__ == "__main__":
    main()
