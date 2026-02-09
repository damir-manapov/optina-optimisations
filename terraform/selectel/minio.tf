# MinIO Storage - supports solo (single node) and cluster (distributed erasure) topologies

# ============================================================================
# Variables (only MinIO-specific ones not in variables.tf)
# ============================================================================

variable "minio_enabled" {
  description = "Enable MinIO deployment"
  type        = bool
  default     = false
}

variable "minio_root_user" {
  description = "MinIO root user"
  type        = string
  default     = "minioadmin"
}

variable "minio_root_password" {
  description = "MinIO root password"
  type        = string
  sensitive   = true
  default     = "minioadmin123"
}

# ============================================================================
# Locals - Computed values for topology
# ============================================================================

locals {
  # Node count based on topology
  minio_is_cluster      = var.minio_topology == "cluster"
  minio_actual_nodes    = local.minio_is_cluster ? var.minio_nodes : 1
  minio_actual_drives   = local.minio_is_cluster ? var.minio_drives_per_node : 1

  # Use centralized variables
  minio_actual_cpu      = var.minio_cpu
  minio_actual_ram_gb   = var.minio_ram_gb
  minio_actual_disk_gb  = var.minio_disk_size_gb
  minio_actual_disk_type = var.minio_disk_type
}

# ============================================================================
# Flavor
# ============================================================================

resource "openstack_compute_flavor_v2" "minio" {
  count = var.minio_enabled ? 1 : 0

  name      = "minio-${var.environment_name}-${local.minio_actual_cpu}vcpu-${local.minio_actual_ram_gb}gb"
  ram       = local.minio_actual_ram_gb * 1024
  vcpus     = local.minio_actual_cpu
  disk      = 0
  is_public = false

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [
    selectel_vpc_project_v2.benchmark,
    selectel_iam_serviceuser_v1.benchmark
  ]
}

# ============================================================================
# Security Group Rules
# ============================================================================

resource "openstack_networking_secgroup_rule_v2" "minio_api" {
  count = var.minio_enabled ? 1 : 0

  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 9000
  port_range_max    = 9000
  remote_ip_prefix  = "0.0.0.0/0"
  security_group_id = openstack_networking_secgroup_v2.benchmark.id
}

resource "openstack_networking_secgroup_rule_v2" "minio_console" {
  count = var.minio_enabled ? 1 : 0

  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 9001
  port_range_max    = 9001
  remote_ip_prefix  = "0.0.0.0/0"
  security_group_id = openstack_networking_secgroup_v2.benchmark.id
}

# ============================================================================
# Boot Volumes
# ============================================================================

resource "openstack_blockstorage_volume_v3" "minio_boot" {
  count = var.minio_enabled ? local.minio_actual_nodes : 0

  name              = "minio-${count.index + 1}-boot"
  size              = 50
  image_id          = data.openstack_images_image_v2.ubuntu.id
  volume_type       = "fast.${var.availability_zone}"
  availability_zone = var.availability_zone
}

# ============================================================================
# Data Volumes (drives_per_node * node_count total)
# ============================================================================

resource "openstack_blockstorage_volume_v3" "minio_data" {
  count = var.minio_enabled ? local.minio_actual_nodes * local.minio_actual_drives : 0

  name              = "minio-${floor(count.index / local.minio_actual_drives) + 1}-data-${count.index % local.minio_actual_drives + 1}"
  size              = local.minio_actual_disk_gb
  volume_type       = "${local.minio_actual_disk_type}.${var.availability_zone}"
  availability_zone = var.availability_zone

  depends_on = [
    selectel_vpc_project_v2.benchmark,
    selectel_iam_serviceuser_v1.benchmark
  ]
}

# ============================================================================
# Network Ports (10.0.0.10, 10.0.0.11, ...)
# ============================================================================

resource "openstack_networking_port_v2" "minio" {
  count = var.minio_enabled ? local.minio_actual_nodes : 0

  name           = "minio-${count.index + 1}-port"
  network_id     = openstack_networking_network_v2.benchmark.id
  admin_state_up = true

  fixed_ip {
    subnet_id  = openstack_networking_subnet_v2.benchmark.id
    ip_address = "10.0.0.${10 + count.index}"
  }

  security_group_ids = [openstack_networking_secgroup_v2.benchmark.id]

  depends_on = [
    selectel_vpc_project_v2.benchmark,
    selectel_iam_serviceuser_v1.benchmark
  ]
}

# ============================================================================
# Cloud-init Configuration
# ============================================================================

locals {
  # Generate device letters (vdb, vdc, vdd, ...)
  minio_drive_letters = [for i in range(local.minio_actual_drives) : element(["b", "c", "d", "e", "f", "g", "h", "i", "j"], i)]

  # Chown directories
  minio_chown_dirs = join(" ", [for i in range(1, local.minio_actual_drives + 1) : "/data${i}"])

  # MinIO volume spec:
  # - Solo with single drive: /data1 (no erasure coding)
  # - Solo with multiple drives: /data{1...N} (single-node erasure)
  # - Cluster: http://minio{1...N}:9000/data{1...M} (distributed erasure)
  minio_volume_spec = (
    local.minio_actual_nodes == 1 && local.minio_actual_drives == 1
    ? "/data1"
    : local.minio_actual_nodes == 1
    ? "/data{1...${local.minio_actual_drives}}"
    : "http://minio{1...${local.minio_actual_nodes}}:9000/data{1...${local.minio_actual_drives}}"
  )

  minio_cloud_init = var.minio_enabled ? templatefile("${path.module}/minio-cloud-init.yaml", {
    node_count      = local.minio_actual_nodes
    drives_per_node = local.minio_actual_drives
    drive_letters   = local.minio_drive_letters
    chown_dirs      = local.minio_chown_dirs
    root_user       = var.minio_root_user
    root_password   = var.minio_root_password
    volume_spec     = local.minio_volume_spec
  }) : ""
}

# ============================================================================
# Compute Instances
# ============================================================================

resource "openstack_compute_instance_v2" "minio" {
  count = var.minio_enabled ? local.minio_actual_nodes : 0

  name              = local.minio_is_cluster ? "minio-${count.index + 1}" : "minio"
  flavor_id         = openstack_compute_flavor_v2.minio[0].id
  key_pair          = selectel_vpc_keypair_v2.benchmark.name
  availability_zone = var.availability_zone
  user_data         = local.minio_cloud_init

  network {
    port = openstack_networking_port_v2.minio[count.index].id
  }

  # Boot volume
  block_device {
    uuid                  = openstack_blockstorage_volume_v3.minio_boot[count.index].id
    source_type           = "volume"
    destination_type      = "volume"
    boot_index            = 0
    delete_on_termination = true
  }

  # Data volumes (dynamic based on drives)
  dynamic "block_device" {
    for_each = range(local.minio_actual_drives)
    content {
      uuid                  = openstack_blockstorage_volume_v3.minio_data[count.index * local.minio_actual_drives + block_device.value].id
      source_type           = "volume"
      destination_type      = "volume"
      boot_index            = block_device.value + 1
      delete_on_termination = false
    }
  }

  lifecycle {
    ignore_changes = [image_id]
  }

  vendor_options {
    ignore_resize_confirmation = true
  }

  depends_on = [openstack_networking_router_interface_v2.benchmark]
}

# ============================================================================
# Outputs
# ============================================================================

output "minio_internal_endpoints" {
  description = "MinIO internal endpoints for Trino"
  value       = var.minio_enabled ? [for i in range(local.minio_actual_nodes) : "http://10.0.0.${10 + i}:9000"] : null
}

output "minio_credentials" {
  description = "MinIO credentials"
  value = var.minio_enabled ? {
    access_key = var.minio_root_user
    secret_key = "Use minio_root_password variable"
  } : null
}

output "minio_ssh_tunnel" {
  description = "SSH tunnel command to access MinIO console"
  value       = var.minio_enabled ? "ssh -L 9001:10.0.0.10:9001 -L 9000:10.0.0.10:9000 root@${openstack_networking_floatingip_v2.benchmark.address}" : null
}

output "minio_topology_info" {
  description = "MinIO topology information"
  value = var.minio_enabled ? {
    mode            = var.minio_topology
    nodes           = local.minio_actual_nodes
    cpu_per_node    = local.minio_actual_cpu
    ram_per_node_gb = local.minio_actual_ram_gb
    drives_per_node = local.minio_actual_drives
    drive_size_gb   = local.minio_actual_disk_gb
    drive_type      = local.minio_actual_disk_type
    total_drives    = local.minio_actual_nodes * local.minio_actual_drives
    total_storage_gb = local.minio_actual_nodes * local.minio_actual_drives * local.minio_actual_disk_gb
  } : null
}
