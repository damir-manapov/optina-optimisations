"""Common utilities shared between optimizers."""

import json
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from python_terraform import Terraform

# Re-export pricing for backward compatibility
from pricing import CloudPricing, get_cloud_pricing  # noqa: F401


# ============================================================================
# Timing Dataclasses
# ============================================================================


@dataclass
class InfraTimings:
    """Timing breakdown for infrastructure deployment phases."""

    terraform_s: float = 0.0  # Terraform apply
    vm_ready_s: float = 0.0  # Wait for VM cloud-init/SSH
    service_ready_s: float = 0.0  # Wait for service health


# ============================================================================
# System Baseline Dataclasses
# ============================================================================


@dataclass
class FioResult:
    """FIO benchmark results for disk baseline."""

    # Random 4K I/O
    rand_read_iops: float = 0.0
    rand_write_iops: float = 0.0
    rand_read_lat_ms: float = 0.0
    rand_write_lat_ms: float = 0.0
    # Sequential 1M I/O
    seq_read_mib_s: float = 0.0
    seq_write_mib_s: float = 0.0


@dataclass
class SysbenchResult:
    """Sysbench benchmark results for CPU and memory baseline."""

    # CPU benchmark
    cpu_events_per_sec: float = 0.0
    # Memory benchmark
    mem_mib_per_sec: float = 0.0


@dataclass
class SystemBaseline:
    """Combined system baseline metrics."""

    fio: FioResult | None = None
    sysbench: SysbenchResult | None = None


# ============================================================================
# Metrics Helpers
# ============================================================================


def get_metric(r: dict, key: str, default: float = 0) -> float:
    """Get metric value from nested metrics dict or top-level (legacy)."""
    metrics = r.get("metrics", {})
    if metrics and key in metrics:
        return metrics.get(key, default) or default
    # Fallback to top-level for legacy data
    return r.get(key, default) or default


# ============================================================================
# SSH Utilities
# ============================================================================


def run_ssh_command(
    vm_ip: str,
    command: str,
    timeout: int = 300,
    forward_agent: bool = False,
    jump_host: str | None = None,
) -> tuple[int, str]:
    """Run command on remote VM via SSH.

    Args:
        vm_ip: IP address of VM to connect to
        command: Command to run on VM
        timeout: Command timeout in seconds
        forward_agent: If True, forward SSH agent for nested SSH connections
        jump_host: If set, use this host as SSH jump/proxy host (for internal IPs)
    """
    ssh_args = [
        "ssh",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "LogLevel=ERROR",
    ]
    if forward_agent:
        ssh_args.append("-A")
    if jump_host:
        # Use ProxyCommand instead of -J to pass SSH options to jump host too
        proxy_cmd = f"ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -W %h:%p root@{jump_host}"
        ssh_args.extend(["-o", f"ProxyCommand={proxy_cmd}"])
    ssh_args.extend([f"root@{vm_ip}", command])

    result = subprocess.run(
        ssh_args,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.returncode, result.stdout + result.stderr


def wait_for_vm_ready(
    vm_ip: str,
    timeout: int = 600,
    jump_host: str | None = None,
) -> bool:
    """Wait for VM to be ready (cloud-init complete)."""
    print(f"  Waiting for VM {vm_ip} to be ready...")

    start = time.time()
    while time.time() - start < timeout:
        try:
            code, output = run_ssh_command(
                vm_ip, "test -f /root/cloud-init-ready", timeout=15, jump_host=jump_host
            )
            if code == 0:
                elapsed = int(time.time() - start)
                print(f"  VM is ready! ({elapsed}s)")
                return True

            elapsed = int(time.time() - start)
            # Check if SSH itself failed (connection refused, etc.)
            if "Connection refused" in output or "No route to host" in output:
                print(f"  SSH not ready yet ({elapsed}s elapsed)")
            else:
                # SSH works but marker not ready - show cloud-init log
                _, log_tail = run_ssh_command(
                    vm_ip,
                    "tail -3 /var/log/cloud-init-output.log 2>/dev/null || echo 'no log yet'",
                    timeout=10,
                    jump_host=jump_host,
                )
                log_preview = (
                    log_tail.strip().replace("\n", " | ") if log_tail else "no output"
                )
                print(
                    f"  Marker file not ready yet ({elapsed}s elapsed): {log_preview}"
                )
        except Exception as e:
            elapsed = int(time.time() - start)
            print(f"  SSH not ready yet ({elapsed}s elapsed): {e}")
        time.sleep(10)

    print(f"  Warning: VM not ready after {timeout}s, continuing anyway...")
    return False


def clear_known_hosts_on_vm(vm_ip: str) -> None:
    """Clear known_hosts on benchmark VM to avoid stale host key errors.

    When VMs are recreated, their host keys change. This causes SSH to reject
    connections due to 'host key has changed' warnings.
    """
    try:
        run_ssh_command(vm_ip, "rm -f /root/.ssh/known_hosts", timeout=10)
    except Exception:
        pass  # Ignore errors, file may not exist


def validate_vm_exists(vm_ip: str) -> bool:
    """Check if VM is actually reachable (not just in state)."""
    try:
        code, _ = run_ssh_command(vm_ip, "echo ok", timeout=10)
        return code == 0
    except Exception:
        return False


def get_terraform(terraform_dir: Path) -> Terraform:
    """Get Terraform instance, initializing if needed."""
    tf_dir = str(terraform_dir)
    tf = Terraform(working_dir=tf_dir)

    # Check if init needed
    dot_terraform = terraform_dir / ".terraform"
    if not dot_terraform.exists():
        print(f"  Initializing Terraform in {tf_dir}...")
        ret_code, stdout, stderr = tf.init()
        if ret_code != 0:
            raise RuntimeError(f"Terraform init failed: {stderr}")

    return tf


def get_tf_output(tf: Terraform, name: str) -> str | None:
    """Get terraform output value, handling different return formats."""
    try:
        ret, out, err = tf.output_cmd(name)
        if ret != 0 or not out:
            return None
        # Output is JSON-formatted, strip quotes and newlines
        value = out.strip().strip('"')
        # Check if it's a valid value (not a warning message or null)
        if not value or value == "null" or value.startswith("╷") or "Warning" in value:
            return None
        return value
    except Exception:
        return None


def is_stale_state_error(stderr: str | None) -> bool:
    """Check if the error indicates stale terraform state."""
    if stderr is None:
        return False
    return "not found" in stderr.lower() or "404" in stderr


def clear_terraform_state(terraform_dir: Path) -> None:
    """Clear Terraform state files to start fresh."""
    import os

    for f in ["terraform.tfstate", "terraform.tfstate.backup"]:
        path = terraform_dir / f
        if path.exists():
            os.remove(path)
            print(f"  Removed stale state: {path}")


def destroy_all(terraform_dir: Path, cloud_name: str) -> bool:
    """Destroy all infrastructure."""
    print(f"\nDestroying all resources on {cloud_name}...")

    result = subprocess.run(
        ["terraform", "destroy", "-auto-approve"],
        cwd=str(terraform_dir),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"  Warning: Destroy may have failed: {result.stderr}")
        return False

    print("  All resources destroyed.")
    return True


# ============================================================================
# System Baseline Functions
# ============================================================================


def run_fio_baseline(
    vm_ip: str,
    target_ip: str | None = None,
    test_dir: str = "/tmp",
    jump_host: str | None = None,
) -> FioResult | None:
    """Run fio to get disk baseline performance.

    Args:
        vm_ip: IP of VM to run fio on (or jump host if target_ip is set)
        target_ip: If set, SSH to this IP via vm_ip to run fio
        test_dir: Directory to run fio tests in (e.g., /data1 for MinIO, /tmp for others)
        jump_host: Alternative jump host (if vm_ip is the target itself)

    Runs random 4K and sequential 1M tests.
    """
    print("  Running fio disk baseline...")

    # Build fio command
    fio_inner = (
        f"fio --name=random_rw --directory={test_dir} --rw=randrw --rwmixread=70 "
        f"--bs=4k --size=256M --numjobs=4 --runtime=20 --time_based --group_reporting "
        f"--stonewall "
        f"--name=seq_read --directory={test_dir} --rw=read "
        f"--bs=1M --size=512M --numjobs=1 --runtime=10 --time_based "
        f"--stonewall "
        f"--name=seq_write --directory={test_dir} --rw=write "
        f"--bs=1M --size=512M --numjobs=1 --runtime=10 --time_based "
        f"--output-format=json 2>/dev/null"
    )

    if target_ip:
        # SSH to target via vm_ip (jump host)
        fio_cmd = (
            f"ssh -A -o StrictHostKeyChecking=no -o ConnectTimeout=10 root@{target_ip} "
            f'"{fio_inner}" 2>/dev/null'
        )
        try:
            code, output = run_ssh_command(
                vm_ip, fio_cmd, timeout=120, forward_agent=True
            )
        except Exception as e:
            print(f"  Fio failed: {e}")
            return None
    else:
        # Run directly on vm_ip
        try:
            code, output = run_ssh_command(
                vm_ip, fio_inner, timeout=120, jump_host=jump_host
            )
        except Exception as e:
            print(f"  Fio failed: {e}")
            return None

    if code != 0:
        print(f"  Fio failed with code {code}")
        return None

    return parse_fio_output(output)


def parse_fio_output(output: str) -> FioResult | None:
    """Parse fio JSON output with random and sequential tests."""
    try:
        # Find JSON in output (may have some stderr before it)
        json_start = output.find("{")
        if json_start == -1:
            print("  Warning: No JSON found in fio output")
            return None

        try:
            data = json.loads(output[json_start:])
        except json.JSONDecodeError as e:
            print(f"  Warning: Failed to parse fio JSON: {e}")
            return None

        jobs = data.get("jobs", [])
        if not jobs:
            print("  Warning: No jobs in fio output")
            return None

        result = FioResult()

        for job in jobs:
            job_name = job.get("jobname", "").lower()
            read_stats = job.get("read", {})
            write_stats = job.get("write", {})

            if "random" in job_name:
                # Random 4K - get IOPS and latency
                result.rand_read_iops = read_stats.get("iops", 0)
                result.rand_write_iops = write_stats.get("iops", 0)
                read_lat_ns = read_stats.get("lat_ns", {}).get("mean", 0)
                write_lat_ns = write_stats.get("lat_ns", {}).get("mean", 0)
                result.rand_read_lat_ms = read_lat_ns / 1_000_000
                result.rand_write_lat_ms = write_lat_ns / 1_000_000
            elif "seq_read" in job_name:
                # Sequential read 1M - get bandwidth
                read_bw_kib = read_stats.get("bw", 0)
                result.seq_read_mib_s = read_bw_kib / 1024
            elif "seq_write" in job_name:
                # Sequential write 1M - get bandwidth
                write_bw_kib = write_stats.get("bw", 0)
                result.seq_write_mib_s = write_bw_kib / 1024

        print(
            f"  Fio: rand {result.rand_read_iops:.0f}/{result.rand_write_iops:.0f} IOPS, "
            f"seq {result.seq_read_mib_s:.0f}/{result.seq_write_mib_s:.0f} MiB/s"
        )

        return result
    except json.JSONDecodeError as e:
        print(f"  Warning: Failed to parse fio JSON: {e}")
        return None
    except Exception as e:
        print(f"  Warning: Failed to parse fio output: {e}")
        return None


def run_sysbench_baseline(
    vm_ip: str,
    target_ip: str | None = None,
    jump_host: str | None = None,
) -> SysbenchResult | None:
    """Run sysbench to get CPU and memory baseline.

    Args:
        vm_ip: IP of VM to run sysbench on (or jump host if target_ip is set)
        target_ip: If set, SSH to this IP via vm_ip to run sysbench
        jump_host: Alternative jump host (if vm_ip is the target itself)
    """
    print("  Running sysbench CPU/memory baseline...")

    result = SysbenchResult()

    def run_cmd(cmd: str, timeout: int = 30) -> tuple[int, str]:
        if target_ip:
            nested_cmd = (
                f"ssh -A -o StrictHostKeyChecking=no -o ConnectTimeout=10 root@{target_ip} "
                f'"{cmd}" 2>/dev/null'
            )
            return run_ssh_command(
                vm_ip, nested_cmd, timeout=timeout, forward_agent=True
            )
        else:
            return run_ssh_command(vm_ip, cmd, timeout=timeout, jump_host=jump_host)

    # CPU benchmark
    try:
        code, output = run_cmd("sysbench cpu --time=10 run 2>/dev/null")
        if code == 0:
            match = re.search(r"events per second:\s*([\d.]+)", output)
            if match:
                result.cpu_events_per_sec = float(match.group(1))
    except Exception as e:
        print(f"  CPU benchmark failed: {e}")

    # Memory benchmark
    try:
        code, output = run_cmd(
            "sysbench memory --memory-block-size=1M --memory-total-size=10G run 2>/dev/null"
        )
        if code == 0:
            match = re.search(r"([\d.]+)\s*MiB/sec", output)
            if match:
                result.mem_mib_per_sec = float(match.group(1))
    except Exception as e:
        print(f"  Memory benchmark failed: {e}")

    print(
        f"  Sysbench: CPU {result.cpu_events_per_sec:.0f} events/s, "
        f"MEM {result.mem_mib_per_sec:.0f} MiB/s"
    )

    return result


def run_system_baseline(
    vm_ip: str,
    target_ip: str | None = None,
    test_dir: str = "/tmp",
    jump_host: str | None = None,
) -> SystemBaseline:
    """Run all system baseline benchmarks.

    Args:
        vm_ip: IP of VM to run baselines on (or jump host if target_ip is set)
        target_ip: If set, SSH to this IP via vm_ip to run baselines
        test_dir: Directory to run fio tests in
        jump_host: Alternative jump host (if vm_ip is the target itself)
    """
    fio_result = run_fio_baseline(vm_ip, target_ip, test_dir, jump_host)
    sysbench_result = run_sysbench_baseline(vm_ip, target_ip, jump_host)

    return SystemBaseline(fio=fio_result, sysbench=sysbench_result)
