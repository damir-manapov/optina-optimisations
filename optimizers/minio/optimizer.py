#!/usr/bin/env python3
"""
Multi-Cloud MinIO Configuration Optimizer using Bayesian Optimization (Optuna).

Supports both Selectel and Timeweb Cloud providers.
Automatically creates benchmark VM if not provided.

Usage:
    uv run python optimizers/minio/optimizer.py --cloud selectel --trials 5
    uv run python optimizers/minio/optimizer.py --cloud selectel --trials 10 --metric cost_efficiency
    uv run python optimizers/minio/optimizer.py --cloud timeweb --trials 10 --no-destroy
    uv run python optimizers/minio/optimizer.py --cloud selectel --show-results
    uv run python optimizers/minio/optimizer.py --cloud selectel --export-md
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
    InfraTimings,
    SystemBaseline,
    clear_known_hosts_on_vm,
    clear_terraform_state,
    destroy_all,
    get_metric,
    get_terraform,
    get_tf_output,
    is_stale_state_error,
    run_ssh_command,
    run_system_baseline,
    validate_vm_exists,
    wait_for_vm_ready,
)
from storage import TrialStore, get_store as _get_store

from optimizers.minio.cloud_config import (
    CloudConfig,
    get_cloud_config,
    get_config_space,
)
from metrics import get_metric_value
from optimizers.minio.metrics import METRICS
from pricing import DiskConfig, calculate_vm_cost, filter_valid_ram

RESULTS_DIR = Path(__file__).parent  # For local files (study.db, markdown)
STUDY_DB = RESULTS_DIR / "study.db"


def get_store() -> TrialStore:
    """Get the TrialStore for MinIO results."""
    return _get_store("minio")


def config_summary(r: dict) -> str:
    """Format config as a compact string."""
    c = r.get("config", {})
    return f"{c.get('nodes', 0)}n×{c.get('cpu_per_node', 0)}cpu/{c.get('ram_per_node', 0)}gb {c.get('drives_per_node', 0)}×{c.get('drive_size_gb', 0)}gb {c.get('drive_type', '?')}"


def format_results(cloud: str) -> dict | None:
    """Format benchmark results for display/export. Returns None if no results."""
    store = get_store()
    results = store.as_dicts()

    if not results:
        return None

    results_sorted = sorted(
        results, key=lambda x: get_metric(x, "total_mib_s"), reverse=True
    )

    # Extract row data
    rows = []
    for r in results_sorted:
        cfg = r.get("config", {})
        cloud_name = r.get("cloud", cloud)
        # Calculate cost on-the-fly from config
        cost = calculate_cost(cfg, cloud_name)
        total = get_metric(r, "total_mib_s")
        eff = total / cost if cost > 0 else 0
        rows.append(
            {
                "nodes": cfg.get("nodes", 0),
                "cpu": cfg.get("cpu_per_node", 0),
                "ram": cfg.get("ram_per_node", 0),
                "drives": cfg.get("drives_per_node", 0),
                "size": cfg.get("drive_size_gb", 0),
                "dtype": cfg.get("drive_type", "?"),
                "total": total,
                "get": get_metric(r, "get_mib_s"),
                "put": get_metric(r, "put_mib_s"),
                "cost": cost,
                "eff": eff,
                "_result": r,  # Keep reference for best calculation
            }
        )

    # Best configs - use rows for efficiency (calculated on-the-fly)
    best_total_row = max(rows, key=lambda x: x.get("total", 0))
    best_get_row = max(rows, key=lambda x: x.get("get", 0))
    best_put_row = max(rows, key=lambda x: x.get("put", 0))
    best_eff_row = max(rows, key=lambda x: x.get("eff", 0))

    return {
        "cloud": cloud,
        "rows": rows,
        "best": {
            "total": {
                "value": best_total_row.get("total", 0),
                "config": config_summary(best_total_row["_result"]),
            },
            "get": {
                "value": best_get_row.get("get", 0),
                "config": config_summary(best_get_row["_result"]),
            },
            "put": {
                "value": best_put_row.get("put", 0),
                "config": config_summary(best_put_row["_result"]),
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

    print(f"\n{'=' * 110}")
    print(f"MinIO Benchmark Results - {cloud.upper()}")
    print(f"{'=' * 110}")

    # Header
    print(
        f"{'#':>3} {'Nodes':>5} {'CPU':>4} {'RAM':>4} {'Drives':>6} {'Size':>5} {'Type':<8} "
        f"{'Total':>8} {'GET':>8} {'PUT':>8} {'$/hr':>7} {'Eff':>8}"
    )
    print("-" * 110)

    for i, r in enumerate(data["rows"], 1):
        print(
            f"{i:>3} {r['nodes']:>5} {r['cpu']:>4} {r['ram']:>4} {r['drives']:>6} {r['size']:>5} {r['dtype'][:8]:<8} "
            f"{r['total']:>8.1f} {r['get']:>8.1f} {r['put']:>8.1f} {r['cost']:>7.2f} {r['eff']:>8.1f}"
        )

    print("-" * 110)
    print(f"Total: {len(data['rows'])} results")

    best = data["best"]
    print(
        f"\nBest by total:      {best['total']['value']:>8.1f} {'MiB/s':<11} [{best['total']['config']}]"
    )
    print(
        f"Best by GET:        {best['get']['value']:>8.1f} {'MiB/s':<11} [{best['get']['config']}]"
    )
    print(
        f"Best by PUT:        {best['put']['value']:>8.1f} {'MiB/s':<11} [{best['put']['config']}]"
    )
    print(
        f"Best by efficiency: {best['efficiency']['value']:>8.1f} {'MiB/s/$/hr':<11} [{best['efficiency']['config']}]"
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
        f"# MinIO Benchmark Results - {cloud.upper()}",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Results",
        "",
        "| # | Nodes | CPU | RAM | Drives | Size | Type | Total (MiB/s) | GET | PUT | $/hr | Efficiency |",
        "|--:|------:|----:|----:|-------:|-----:|------|-------------:|----:|----:|-----:|-----------:|",
    ]

    for i, r in enumerate(data["rows"], 1):
        lines.append(
            f"| {i} | {r['nodes']} | {r['cpu']} | {r['ram']} | {r['drives']} | {r['size']} | {r['dtype']} | {r['total']:.1f} | {r['get']:.1f} | {r['put']:.1f} | {r['cost']:.2f} | {r['eff']:.1f} |"
        )

    best = data["best"]
    lines.extend(
        [
            "",
            "## Best Configurations",
            "",
            f"- **Best by total:** {best['total']['value']:.1f} MiB/s — `{best['total']['config']}`",
            f"- **Best by GET:** {best['get']['value']:.1f} MiB/s — `{best['get']['config']}`",
            f"- **Best by PUT:** {best['put']['value']:.1f} MiB/s — `{best['put']['config']}`",
            f"- **Best by efficiency:** {best['efficiency']['value']:.1f} MiB/s/$/hr — `{best['efficiency']['config']}`",
            "",
        ]
    )

    output_path.write_text("\n".join(lines))
    print(f"Results exported to {output_path}")


@dataclass
class TrialTimings:
    """Timing measurements for each phase of a trial."""

    terraform_s: float = 0.0  # Terraform create MinIO cluster
    vm_ready_s: float = 0.0  # Wait for VM cloud-init
    service_ready_s: float = 0.0  # Wait for MinIO to be ready
    baseline_s: float = 0.0  # fio + sysbench tests
    benchmark_s: float = 0.0  # warp benchmark
    destroy_s: float = 0.0  # Terraform destroy MinIO
    trial_total_s: float = 0.0  # End-to-end trial time


@dataclass
class BenchmarkResult:
    config: dict
    get_mib_s: float = 0.0
    put_mib_s: float = 0.0
    total_mib_s: float = 0.0
    get_obj_s: float = 0.0
    put_obj_s: float = 0.0
    total_obj_s: float = 0.0
    duration_s: float = 0.0
    error: str | None = None
    baseline: SystemBaseline | None = None
    timings: TrialTimings | None = None


def config_to_key(config: dict, cloud: str) -> str:
    """Convert config dict to a hashable key for deduplication."""
    return json.dumps(
        {
            "cloud": cloud,
            "nodes": config["nodes"],
            "cpu_per_node": config["cpu_per_node"],
            "ram_per_node": config["ram_per_node"],
            "drives_per_node": config["drives_per_node"],
            "drive_size_gb": config["drive_size_gb"],
            "drive_type": config["drive_type"],
        },
        sort_keys=True,
    )


def find_cached_result(config: dict, cloud: str) -> dict | None:
    """Find a cached successful result for the given config.

    Returns None if:
    - No cached result exists
    - Cached result has error (failed trial)
    - Cached result has 0 throughput (benchmark failed)
    - Cached result is missing required metrics (system_baseline, timings)
    """
    target_key = config_to_key(config, cloud)
    store = get_store()
    trial = store.find_by_config_key(target_key)
    if trial is None:
        return None
    # Skip failed results - they should be retried
    if trial.error:
        return None
    total = trial.metrics.total_mib_s if trial.metrics else 0
    if (total or 0) <= 0:
        return None
    # Skip results missing required metrics
    result = trial.model_dump()
    if not result.get("system_baseline"):
        return None
    if not result.get("timings"):
        return None
    return result


def load_historical_trials(study: optuna.Study, cloud: str, metric: str) -> int:
    """Load historical results into Optuna study as completed trials.

    This helps Optuna make better suggestions by learning from past results.
    Returns the number of trials loaded.
    """
    store = get_store()
    if store.count() == 0:
        return 0

    # Filter results for this cloud that have valid throughput
    valid_results = [
        r
        for r in store.as_dicts()
        if r.get("cloud") == cloud
        and not r.get("error")
        and get_metric(r, "total_mib_s") > 0
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

        nodes = config.get("nodes")
        cpu = config.get("cpu_per_node")
        ram = config.get("ram_per_node")
        drives = config.get("drives_per_node")
        drive_size = config.get("drive_size_gb")
        drive_type = config.get("drive_type")

        # Validate all values are in search space
        if nodes not in config_space["nodes"]:
            continue
        if cpu not in config_space["cpu_per_node"]:
            continue
        if drives not in config_space["drives_per_node"]:
            continue
        if drive_size not in config_space["drive_size_gb"]:
            continue
        if drive_type not in config_space["drive_type"]:
            continue

        # Check RAM is valid for this CPU
        valid_ram = filter_valid_ram(cloud, cpu, config_space["ram_per_node"])
        if ram not in valid_ram:
            continue

        # Build params with CPU-specific RAM param name (matches objective function)
        params = {
            "nodes": nodes,
            "cpu_per_node": cpu,
            f"ram_per_node_cpu{cpu}": ram,
            "drives_per_node": drives,
            "drive_size_gb": drive_size,
            "drive_type": drive_type,
        }

        # Build distributions
        distributions = {
            "nodes": optuna.distributions.CategoricalDistribution(
                config_space["nodes"]
            ),
            "cpu_per_node": optuna.distributions.CategoricalDistribution(
                config_space["cpu_per_node"]
            ),
            f"ram_per_node_cpu{cpu}": optuna.distributions.CategoricalDistribution(
                valid_ram
            ),
            "drives_per_node": optuna.distributions.CategoricalDistribution(
                config_space["drives_per_node"]
            ),
            "drive_size_gb": optuna.distributions.CategoricalDistribution(
                config_space["drive_size_gb"]
            ),
            "drive_type": optuna.distributions.CategoricalDistribution(
                config_space["drive_type"]
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


def wait_for_minio_ready(
    vm_ip: str, minio_ip: str = "10.0.0.10", timeout: int = 300
) -> tuple[bool, float, float]:
    """Wait for MinIO to be ready (cloud-init complete and service responding).

    Uses SSH agent forwarding to check MinIO node via benchmark VM.
    Returns (success, vm_ready_s, service_ready_s).
    """
    # Clear stale known_hosts to avoid host key change errors
    clear_known_hosts_on_vm(vm_ip)

    print(f"  Waiting for MinIO at {minio_ip} to be ready...")

    start = time.time()
    ssh_ready = False
    vm_ready_time = 0.0

    while time.time() - start < timeout:
        elapsed = time.time() - start
        try:
            if not ssh_ready:
                # First, just check if SSH is reachable
                ssh_cmd = (
                    f"ssh -A -o StrictHostKeyChecking=no -o ConnectTimeout=5 root@{minio_ip} "
                    f"'echo ok'"
                )
                code, _ = run_ssh_command(
                    vm_ip, ssh_cmd, timeout=15, forward_agent=True
                )
                if code == 0:
                    vm_ready_time = elapsed
                    print(f"  SSH to MinIO node available ({elapsed:.0f}s)")
                    ssh_ready = True
                else:
                    print(f"  Waiting for SSH ({elapsed:.0f}s)...")
                    time.sleep(10)
                    continue

            # Check if cloud-init is complete and MinIO is healthy
            check_cmd = (
                f"ssh -A -o StrictHostKeyChecking=no -o ConnectTimeout=5 root@{minio_ip} "
                f"'test -f /root/cloud-init-ready && curl -sf http://localhost:9000/minio/health/ready'"
            )
            code, output = run_ssh_command(
                vm_ip, check_cmd, timeout=20, forward_agent=True
            )
            if code == 0:
                service_ready_time = elapsed - vm_ready_time
                print(f"  MinIO is ready! ({elapsed:.0f}s)")
                return True, vm_ready_time, service_ready_time
            else:
                print(f"  MinIO not ready yet ({elapsed:.0f}s)...")
        except Exception as e:
            print(f"  MinIO check failed ({elapsed:.0f}s): {e}")
        time.sleep(10)

    print(f"  Warning: MinIO not ready after {timeout}s, continuing anyway...")
    return False, time.time() - start, 0.0


def terraform_refresh_and_validate(tf) -> bool:
    """Run terraform refresh and check if resources are valid."""
    ret_code, stdout, stderr = tf.refresh()
    # Check for "not found" errors indicating stale state
    if is_stale_state_error(stderr):
        return False
    return ret_code == 0


def ensure_benchmark_vm(cloud_config: CloudConfig) -> str:
    """Ensure benchmark VM exists and return its IP."""
    print(f"\nChecking benchmark VM for {cloud_config.name}...")

    tf = get_terraform(cloud_config.terraform_dir)

    # Check if VM already exists in state
    vm_ip = get_tf_output(tf, "benchmark_vm_ip")
    if vm_ip:
        # Validate that the VM is actually reachable
        print(f"  Found VM IP in state: {vm_ip}")
        if validate_vm_exists(vm_ip):
            print(f"  Benchmark VM verified and reachable: {vm_ip}")
            return vm_ip
        else:
            print("  VM in state is not reachable, checking if state is stale...")
            # Try to refresh and see if resources still exist
            if not terraform_refresh_and_validate(tf):
                print("  State is stale (resources deleted), clearing state...")
                clear_terraform_state(cloud_config.terraform_dir)
                tf = get_terraform(
                    cloud_config.terraform_dir
                )  # Re-init after clearing state
            else:
                # Resources exist but VM not reachable yet, wait for it
                print("  Resources exist, waiting for VM to become ready...")
                if wait_for_vm_ready(vm_ip, timeout=180):
                    return vm_ip

    # Create VM only (explicitly disable MinIO to avoid terraform.tfvars override)
    print("  Creating benchmark VM...")
    tf_vars = {"minio_enabled": False}
    ret_code, stdout, stderr = tf.apply(skip_plan=True, var=tf_vars)

    if ret_code != 0:
        # Check if it's a stale state error
        if is_stale_state_error(stderr):
            print("  Stale state detected, clearing and retrying...")
            clear_terraform_state(cloud_config.terraform_dir)
            tf = get_terraform(cloud_config.terraform_dir)
            ret_code, stdout, stderr = tf.apply(skip_plan=True, var=tf_vars)

        if ret_code != 0:
            raise RuntimeError(f"Failed to create benchmark VM: {stderr}")

    # Get IP
    vm_ip = get_tf_output(tf, "benchmark_vm_ip")
    if not vm_ip:
        raise RuntimeError("Benchmark VM created but no IP returned")

    print(f"  Benchmark VM created: {vm_ip}")

    # Wait for VM to be ready
    wait_for_vm_ready(vm_ip)

    return vm_ip


def is_ip_conflict_error(stderr: str | None) -> bool:
    """Check if the error indicates IP/resource conflict (retryable)."""
    if stderr is None:
        return False
    stderr_lower = stderr.lower()
    # Skip flavor conflicts - those are not transient
    if "flavor" in stderr_lower:
        return False
    # OpenStack (Selectel) IP conflicts
    if "IpAddressAlreadyAllocated" in stderr or "already allocated" in stderr_lower:
        return True
    # Timeweb resource conflicts (not flavor-related)
    if "already exists" in stderr_lower and "ip" in stderr_lower:
        return True
    # Generic transient errors
    if "resource is busy" in stderr_lower or "try again" in stderr_lower:
        return True
    return False


def deploy_minio(
    config: dict, cloud_config: CloudConfig, vm_ip: str, max_retries: int = 3
) -> tuple[bool, InfraTimings]:
    """Deploy MinIO cluster with given configuration. Returns (success, timings).

    Args:
        config: MinIO configuration dict
        cloud_config: Cloud provider configuration
        vm_ip: Benchmark VM IP for SSH connectivity checks
        max_retries: Number of retries for transient errors
    """
    print(f"  Deploying MinIO on {cloud_config.name}: {config}")
    timings = InfraTimings()
    tf_start = time.time()

    tf = get_terraform(cloud_config.terraform_dir)

    # Build variables for terraform apply
    tf_vars = {
        "minio_enabled": True,
        "minio_node_count": config["nodes"],
        "minio_node_cpu": config["cpu_per_node"],
        "minio_node_ram_gb": config["ram_per_node"],
        "minio_drives_per_node": config["drives_per_node"],
        "minio_drive_size_gb": config["drive_size_gb"],
        "minio_drive_type": config["drive_type"],
    }

    # Apply with retries for transient errors
    ret_code = 1
    stderr = ""
    for attempt in range(max_retries):
        ret_code, stdout, stderr = tf.apply(skip_plan=True, var=tf_vars)

        if ret_code == 0:
            break

        # Check for stale state errors
        if is_stale_state_error(stderr):
            print("  Stale state detected, clearing and retrying...")
            clear_terraform_state(cloud_config.terraform_dir)
            tf = get_terraform(cloud_config.terraform_dir)
            continue

        # Check for IP conflict (OpenStack hasn't released ports yet)
        if is_ip_conflict_error(stderr):
            wait_time = 15 * (attempt + 1)  # 15s, 30s, 45s
            print(
                f"  IP conflict detected, waiting {wait_time}s for ports to release..."
            )
            time.sleep(wait_time)
            continue

        # Unknown error
        print(f"  Terraform apply failed: {stderr}")
        timings.terraform_s = time.time() - tf_start
        return False, timings

    timings.terraform_s = time.time() - tf_start

    if ret_code != 0:
        print(f"  Terraform apply failed after {max_retries} retries: {stderr}")
        return False, timings

    # Wait for MinIO to be ready (cloud-init + service health check)
    ready, vm_ready_s, service_ready_s = wait_for_minio_ready(vm_ip)
    timings.vm_ready_s = vm_ready_s
    timings.service_ready_s = service_ready_s

    if not ready:
        print("  Warning: MinIO may not be fully ready")

    total = timings.terraform_s + timings.vm_ready_s + timings.service_ready_s
    print(
        f"  MinIO deployed in {total:.1f}s (tf={timings.terraform_s:.0f}s, vm={timings.vm_ready_s:.0f}s, svc={timings.service_ready_s:.0f}s)"
    )
    return True, timings


def destroy_minio(cloud_config: CloudConfig) -> tuple[bool, float]:
    """Destroy MinIO cluster but keep benchmark VM. Returns (success, duration_s)."""
    print(f"  Destroying MinIO on {cloud_config.name}...")
    start = time.time()

    tf = get_terraform(cloud_config.terraform_dir)

    # Apply with minio_enabled=false to destroy MinIO but keep VM
    ret_code, stdout, stderr = tf.apply(skip_plan=True, var={"minio_enabled": False})

    if ret_code != 0:
        # Handle stale state gracefully
        if is_stale_state_error(stderr):
            print("  Stale state detected during MinIO destroy, clearing state...")
            clear_terraform_state(cloud_config.terraform_dir)
            return True, time.time() - start  # State cleared, nothing to destroy
        print(f"  Warning: MinIO destroy may have failed: {stderr}")
        return False, time.time() - start

    duration = time.time() - start
    print(f"  MinIO destroyed in {duration:.1f}s")
    return True, duration


def run_warp_benchmark(
    vm_ip: str, minio_ip: str = "10.0.0.10"
) -> BenchmarkResult | None:
    """Run warp benchmark and parse results."""
    print("  Running warp benchmark...")

    warp_cmd = (
        f"warp mixed "
        f"--host={minio_ip}:9000 "
        f"--access-key=minioadmin "
        f"--secret-key=minioadmin123 "
        f"--get-distrib 60 "
        f"--stat-distrib 25 "
        f"--put-distrib 10 "
        f"--delete-distrib 5 "
        f"--autoterm 2>&1"
    )

    start_time = time.time()
    try:
        code, output = run_ssh_command(vm_ip, warp_cmd, timeout=600)
    except Exception as e:
        print(f"  Warp failed: {e}")
        return None

    duration = time.time() - start_time

    if code != 0:
        print(f"  Warp failed: {output[:500]}")
        return None

    return parse_warp_output(output, duration)


def parse_warp_output(output: str, duration: float) -> BenchmarkResult:
    """Parse warp benchmark output."""
    result = {
        "get_mib_s": 0.0,
        "put_mib_s": 0.0,
        "total_mib_s": 0.0,
        "get_obj_s": 0.0,
        "put_obj_s": 0.0,
        "total_obj_s": 0.0,
    }

    # Parse new warp output format
    # Operation: GET, 70%, Concurrency: 20, Ran 29s.
    #  * Throughput: 305.61 MiB/s, 305.61 obj/s
    get_pattern = (
        r"Operation:\s*GET.*?Throughput:\s*([\d.]+)\s*MiB/s,\s*([\d.]+)\s*obj/s"
    )
    put_pattern = (
        r"Operation:\s*PUT.*?Throughput:\s*([\d.]+)\s*MiB/s,\s*([\d.]+)\s*obj/s"
    )
    total_pattern = r"Cluster Total:\s*([\d.]+)\s*MiB/s,\s*([\d.]+)\s*obj/s"

    get_match = re.search(get_pattern, output, re.DOTALL | re.IGNORECASE)
    if get_match:
        result["get_mib_s"] = float(get_match.group(1))
        result["get_obj_s"] = float(get_match.group(2))

    put_match = re.search(put_pattern, output, re.DOTALL | re.IGNORECASE)
    if put_match:
        result["put_mib_s"] = float(put_match.group(1))
        result["put_obj_s"] = float(put_match.group(2))

    total_match = re.search(total_pattern, output, re.DOTALL | re.IGNORECASE)
    if total_match:
        result["total_mib_s"] = float(total_match.group(1))
        result["total_obj_s"] = float(total_match.group(2))

    if result["total_mib_s"] == 0:
        print(f"  Warning: Could not parse warp output. Sample: {output[:500]}...")

    return BenchmarkResult(
        config={},
        get_mib_s=result["get_mib_s"],
        put_mib_s=result["put_mib_s"],
        total_mib_s=result["total_mib_s"],
        get_obj_s=result["get_obj_s"],
        put_obj_s=result["put_obj_s"],
        total_obj_s=result["total_obj_s"],
        duration_s=duration,
    )


def calculate_cost(config: dict, cloud: str) -> float:
    """Estimate monthly cost for the configuration."""
    # Handle Optuna's CPU-specific param names (ram_per_node_cpu2 -> ram_per_node)
    ram = config.get("ram_per_node")
    if ram is None:
        for key, val in config.items():
            if key.startswith("ram_per_node_cpu"):
                ram = val
                break
    assert ram is not None, f"Could not find ram_per_node in config: {config}"
    return calculate_vm_cost(
        cloud=cloud,
        cpu=config["cpu_per_node"],
        ram_gb=ram,
        disks=[
            DiskConfig(
                size_gb=config["drive_size_gb"],
                disk_type=config["drive_type"],
                count=config["drives_per_node"],
            )
        ],
        nodes=config["nodes"],
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

    total_drives = config["nodes"] * config["drives_per_node"]

    # Build baseline metrics dict if available
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
        baseline_metrics = {
            "fio": fio_metrics,
            "sysbench": sysbench_metrics,
        }

    # Build timings dict if available
    timings_metrics = None
    if result.timings:
        timings_metrics = {
            "terraform_s": result.timings.terraform_s,
            "vm_ready_s": result.timings.vm_ready_s,
            "service_ready_s": result.timings.service_ready_s,
            "baseline_s": result.timings.baseline_s,
            "benchmark_s": result.timings.benchmark_s,
            "destroy_s": result.timings.destroy_s,
            "trial_total_s": result.timings.trial_total_s,
        }

    store.add_dict(
        {
            "trial": trial_number,
            "timestamp": datetime.now().isoformat(),
            "cloud": cloud,
            "login": login,
            "config": config,
            "total_drives": total_drives,
            "metrics": {
                "total_mib_s": result.total_mib_s,
                "get_mib_s": result.get_mib_s,
                "put_mib_s": result.put_mib_s,
                "duration_s": result.duration_s,
            },
            "error": result.error,
            "system_baseline": baseline_metrics,
            "timings": timings_metrics,
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
    metric: str = "total_mib_s",
) -> float:
    """Optuna objective function."""
    config_space = get_config_space(cloud)

    # Select CPU first, then filter valid RAM options for that CPU
    cpu_per_node = trial.suggest_categorical(
        "cpu_per_node", config_space["cpu_per_node"]
    )
    valid_ram = filter_valid_ram(cloud, cpu_per_node, config_space["ram_per_node"])

    config = {
        "nodes": trial.suggest_categorical("nodes", config_space["nodes"]),
        "cpu_per_node": cpu_per_node,
        "ram_per_node": trial.suggest_categorical(
            f"ram_per_node_cpu{cpu_per_node}", valid_ram
        ),
        "drives_per_node": trial.suggest_categorical(
            "drives_per_node", config_space["drives_per_node"]
        ),
        "drive_size_gb": trial.suggest_categorical(
            "drive_size_gb", config_space["drive_size_gb"]
        ),
        "drive_type": trial.suggest_categorical(
            "drive_type", config_space["drive_type"]
        ),
    }

    print(f"\n{'=' * 60}")
    print(f"Trial {trial.number} [{cloud}]: {config}")
    print(f"{'=' * 60}")

    # Check cache
    cached = find_cached_result(config, cloud)
    if cached:
        cached_value = get_metric_value(cached, metric, METRICS)
        print(f"  Using cached result: {cached_value:.2f} ({metric})")
        return cached_value

    # Start timing the trial
    trial_start = time.time()
    timings = TrialTimings()

    # Destroy any existing MinIO before deploying new config
    # (volumes can't be shrunk, so we must recreate)
    print("  Cleaning up previous MinIO deployment...")
    _, cleanup_time = destroy_minio(cloud_config)
    # OpenStack needs time to release ports/IPs, Timeweb is faster
    post_destroy_wait = 15 if cloud == "selectel" else 5
    time.sleep(post_destroy_wait)

    # Deploy MinIO
    success, deploy_timings = deploy_minio(config, cloud_config, vm_ip)
    timings.terraform_s = deploy_timings.terraform_s
    timings.vm_ready_s = deploy_timings.vm_ready_s
    timings.service_ready_s = deploy_timings.service_ready_s
    if not success:
        timings.trial_total_s = time.time() - trial_start
        save_result(
            BenchmarkResult(config=config, error="Deploy failed", timings=timings),
            config,
            trial.number,
            cloud,
            cloud_config,
            login,
        )
        raise optuna.TrialPruned("Deploy failed")

    # Run system baseline (fio + sysbench) on first MinIO node
    baseline_start = time.time()
    baseline = run_system_baseline(vm_ip, target_ip="10.0.0.10", test_dir="/data1")
    timings.baseline_s = time.time() - baseline_start

    # Run benchmark
    benchmark_start = time.time()
    result = run_warp_benchmark(vm_ip)
    timings.benchmark_s = time.time() - benchmark_start

    if result is None:
        timings.trial_total_s = time.time() - trial_start
        save_result(
            BenchmarkResult(
                config=config,
                error="Benchmark failed",
                baseline=baseline,
                timings=timings,
            ),
            config,
            trial.number,
            cloud,
            cloud_config,
            login,
        )
        raise optuna.TrialPruned("Benchmark failed")

    # Destroy MinIO after benchmark to measure destroy time
    _, destroy_time = destroy_minio(cloud_config)
    timings.destroy_s = destroy_time
    timings.trial_total_s = time.time() - trial_start

    result.config = config
    result.baseline = baseline
    result.timings = timings
    save_result(result, config, trial.number, cloud, cloud_config, login)

    cost = calculate_cost(config, cloud)
    cost_efficiency = result.total_mib_s / cost if cost > 0 else 0
    result_metrics = {
        "total_mib_s": result.total_mib_s,
        "get_mib_s": result.get_mib_s,
        "put_mib_s": result.put_mib_s,
        "cost_efficiency": cost_efficiency,
    }
    metric_value = get_metric_value(result_metrics, metric, METRICS)
    print(
        f"  Result: {result.total_mib_s:.1f} MiB/s, Cost: {cost:.2f}/hr, {metric}={metric_value:.2f}"
    )
    print(
        f"  Timings: tf={timings.terraform_s:.0f}s, vm={timings.vm_ready_s:.0f}s, svc={timings.service_ready_s:.0f}s, baseline={timings.baseline_s:.0f}s, bench={timings.benchmark_s:.0f}s, destroy={timings.destroy_s:.0f}s, total={timings.trial_total_s:.0f}s"
    )

    return metric_value


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Multi-Cloud MinIO Optimizer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Optimize for throughput (default)
  uv run python optimizers/minio/optimizer.py --cloud selectel --trials 5

  # Optimize for cost efficiency (throughput per ruble)
  uv run python optimizers/minio/optimizer.py --cloud selectel --trials 5 --metric cost_efficiency

  # Optimize for read-heavy workloads
  uv run python optimizers/minio/optimizer.py --cloud timeweb --trials 5 --metric get_mib_s

  # Keep infrastructure after optimization
  uv run python optimizers/minio/optimizer.py --cloud timeweb --trials 5 --no-destroy

  # Show all results
  uv run python optimizers/minio/optimizer.py --cloud selectel --show-results

  # Export results to markdown
  uv run python optimizers/minio/optimizer.py --cloud selectel --export-md
        """,
    )

    # Use common argument helpers
    from argparse_helpers import add_common_arguments

    add_common_arguments(
        parser,
        metrics=METRICS,
        default_metric="total_mib_s",
        default_trials=5,
        study_prefix="minio",
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
    study_name = args.study_name or f"minio-{args.cloud}-{args.metric}"

    print("=" * 60)
    print(f"MinIO Optimizer - {args.cloud.upper()}")
    print("=" * 60)
    print(f"Metric: {args.metric} ({METRICS[args.metric]})")
    print(f"Trials: {args.trials}")
    print(f"Terraform dir: {cloud_config.terraform_dir}")
    print(f"Results file: {get_store().path}")
    print(f"Disk types: {cloud_config.disk_types}")
    print(f"Destroy at end: {not args.no_destroy}")
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
            # No successful trials yet
            pass
    print()

    try:
        # Run optimization
        study.optimize(
            lambda trial: objective(
                trial, args.cloud, cloud_config, vm_ip, args.login, args.metric
            ),
            n_trials=args.trials,
            show_progress_bar=True,
            catch=(optuna.TrialPruned,),
        )

        # Print results
        print("\n" + "=" * 60)
        print(f"OPTIMIZATION COMPLETE ({args.cloud.upper()})")
        print("=" * 60)

        try:
            best = study.best_trial
            print(f"Best trial: {best.number}")
            print(f"Best config: {best.params}")
            print(f"Best {args.metric}: {best.value:.2f}")

            # Calculate cost for best config
            best_cost = calculate_cost(best.params, args.cloud)
            print(f"Best config cost: {best_cost:.2f}/hr")
        except ValueError:
            print("No successful trials completed")

        # Auto-export results to markdown
        export_results_md(args.cloud)
        print(f"\nResults exported to RESULTS_{args.cloud.upper()}.md")

    finally:
        # Cleanup
        if not args.no_destroy:
            destroy_all(cloud_config.terraform_dir, cloud_config.name)
        else:
            print("\n--no-destroy specified, keeping infrastructure.")


if __name__ == "__main__":
    main()
