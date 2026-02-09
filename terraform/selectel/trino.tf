# Trino + Nessie + PostgreSQL Configuration for Selectel
# Supports: solo (all-in-one) and cluster (coordinator + workers) topologies

# ============================================================================
# Variables
# ============================================================================

variable "trino_enabled" {
  description = "Enable Trino-Iceberg deployment"
  type        = bool
  default     = false
}

variable "trino_cpu" {
  description = "CPU cores for Trino coordinator (and workers in solo mode)"
  type        = number
  default     = 8
}

variable "trino_ram_gb" {
  description = "RAM in GB for Trino coordinator (and workers in solo mode)"
  type        = number
  default     = 32
}

variable "trino_disk_size_gb" {
  description = "Disk size in GB per Trino node"
  type        = number
  default     = 200
}

variable "trino_disk_type" {
  description = "Disk type: fast or universal"
  type        = string
  default     = "fast"
}

# ============================================================================
# Locals - Computed values for topology
# ============================================================================

locals {
  # Topology flags
  trino_is_cluster   = var.trino_topology == "cluster"
  trino_node_count   = local.trino_is_cluster ? 1 + var.trino_workers : 1
  trino_worker_count = local.trino_is_cluster ? var.trino_workers : 0

  # Worker specs (use dedicated or fallback to coordinator specs)
  trino_worker_actual_cpu    = coalesce(var.trino_worker_cpu, var.trino_cpu)
  trino_worker_actual_ram_gb = coalesce(var.trino_worker_ram_gb, var.trino_ram_gb)

  # IP addresses: coordinator=10.0.0.40, workers=10.0.0.41, 10.0.0.42, ...
  trino_coordinator_ip = "10.0.0.40"
  trino_worker_ips     = [for i in range(local.trino_worker_count) : "10.0.0.${41 + i}"]

  # MinIO endpoint - use external MinIO if enabled, else local
  trino_minio_endpoint = var.minio_enabled ? "http://10.0.0.10:9000" : "http://localhost:9000"
}

# ============================================================================
# Flavors
# ============================================================================

# Coordinator flavor
resource "openstack_compute_flavor_v2" "trino_coordinator" {
  count = var.trino_enabled ? 1 : 0

  name      = "trino-coord-${var.environment_name}-${var.trino_cpu}vcpu-${var.trino_ram_gb}gb"
  ram       = var.trino_ram_gb * 1024
  vcpus     = var.trino_cpu
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

# Worker flavor (only if cluster mode and different specs)
resource "openstack_compute_flavor_v2" "trino_worker" {
  count = var.trino_enabled && local.trino_is_cluster && (var.trino_worker_cpu != null || var.trino_worker_ram_gb != null) ? 1 : 0

  name      = "trino-worker-${var.environment_name}-${local.trino_worker_actual_cpu}vcpu-${local.trino_worker_actual_ram_gb}gb"
  ram       = local.trino_worker_actual_ram_gb * 1024
  vcpus     = local.trino_worker_actual_cpu
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

resource "openstack_networking_secgroup_rule_v2" "trino_http" {
  count = var.trino_enabled ? 1 : 0

  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 8080
  port_range_max    = 8080
  remote_ip_prefix  = "10.0.0.0/24"
  security_group_id = openstack_networking_secgroup_v2.benchmark.id
}

resource "openstack_networking_secgroup_rule_v2" "nessie" {
  count = var.trino_enabled ? 1 : 0

  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 19120
  port_range_max    = 19120
  remote_ip_prefix  = "10.0.0.0/24"
  security_group_id = openstack_networking_secgroup_v2.benchmark.id
}

resource "openstack_networking_secgroup_rule_v2" "trino_postgres" {
  count = var.trino_enabled ? 1 : 0

  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 5432
  port_range_max    = 5432
  remote_ip_prefix  = "10.0.0.40/32"
  security_group_id = openstack_networking_secgroup_v2.benchmark.id
}

# ============================================================================
# Coordinator Node
# ============================================================================

resource "openstack_blockstorage_volume_v3" "trino_coordinator_boot" {
  count = var.trino_enabled ? 1 : 0

  name              = "trino-coordinator-boot"
  size              = var.trino_disk_size_gb
  image_id          = data.openstack_images_image_v2.ubuntu.id
  volume_type       = "${var.trino_disk_type}.${var.availability_zone}"
  availability_zone = var.availability_zone
}

resource "openstack_blockstorage_volume_v3" "trino_coordinator_data" {
  count = var.trino_enabled ? 1 : 0

  name              = "trino-coordinator-data"
  size              = var.trino_disk_size_gb
  volume_type       = "${var.trino_disk_type}.${var.availability_zone}"
  availability_zone = var.availability_zone
}

resource "openstack_networking_port_v2" "trino_coordinator" {
  count = var.trino_enabled ? 1 : 0

  name           = "trino-coordinator-port"
  network_id     = openstack_networking_network_v2.benchmark.id
  admin_state_up = true

  fixed_ip {
    subnet_id  = openstack_networking_subnet_v2.benchmark.id
    ip_address = local.trino_coordinator_ip
  }

  security_group_ids = [openstack_networking_secgroup_v2.benchmark.id]

  depends_on = [
    selectel_vpc_project_v2.benchmark,
    selectel_iam_serviceuser_v1.benchmark
  ]
}

locals {
  trino_coordinator_cloud_init = var.trino_enabled ? templatefile(
    "${path.module}/../cloud-init/selectel/trino-iceberg.yaml.tftpl",
    {
      trino_ram_gb     = var.trino_ram_gb
      trino_cpu        = var.trino_cpu
      is_coordinator   = true
      is_cluster       = local.trino_is_cluster
      coordinator_ip   = local.trino_coordinator_ip
      worker_ips       = local.trino_worker_ips
      minio_endpoint   = local.trino_minio_endpoint
      minio_internal   = var.minio_enabled
      minio_password   = var.minio_enabled ? var.minio_root_password : "minioadmin"
    }
  ) : ""
}

resource "openstack_compute_instance_v2" "trino_coordinator" {
  count = var.trino_enabled ? 1 : 0

  name              = local.trino_is_cluster ? "trino-coordinator" : "trino"
  flavor_id         = openstack_compute_flavor_v2.trino_coordinator[0].id
  key_pair          = selectel_vpc_keypair_v2.benchmark.name
  availability_zone = var.availability_zone
  user_data         = local.trino_coordinator_cloud_init

  network {
    port = openstack_networking_port_v2.trino_coordinator[0].id
  }

  block_device {
    uuid                  = openstack_blockstorage_volume_v3.trino_coordinator_boot[0].id
    source_type           = "volume"
    destination_type      = "volume"
    boot_index            = 0
    delete_on_termination = true
  }

  lifecycle {
    ignore_changes = [image_id]
  }

  vendor_options {
    ignore_resize_confirmation = true
  }

  depends_on = [openstack_networking_router_interface_v2.benchmark]
}

resource "openstack_compute_volume_attach_v2" "trino_coordinator_data" {
  count = var.trino_enabled ? 1 : 0

  instance_id = openstack_compute_instance_v2.trino_coordinator[0].id
  volume_id   = openstack_blockstorage_volume_v3.trino_coordinator_data[0].id
  device      = "/dev/vdb"
}

# ============================================================================
# Worker Nodes (cluster mode only)
# ============================================================================

resource "openstack_blockstorage_volume_v3" "trino_worker_boot" {
  count = var.trino_enabled && local.trino_is_cluster ? local.trino_worker_count : 0

  name              = "trino-worker-${count.index + 1}-boot"
  size              = var.trino_disk_size_gb
  image_id          = data.openstack_images_image_v2.ubuntu.id
  volume_type       = "${var.trino_disk_type}.${var.availability_zone}"
  availability_zone = var.availability_zone
}

resource "openstack_blockstorage_volume_v3" "trino_worker_data" {
  count = var.trino_enabled && local.trino_is_cluster ? local.trino_worker_count : 0

  name              = "trino-worker-${count.index + 1}-data"
  size              = var.trino_disk_size_gb
  volume_type       = "${var.trino_disk_type}.${var.availability_zone}"
  availability_zone = var.availability_zone
}

resource "openstack_networking_port_v2" "trino_worker" {
  count = var.trino_enabled && local.trino_is_cluster ? local.trino_worker_count : 0

  name           = "trino-worker-${count.index + 1}-port"
  network_id     = openstack_networking_network_v2.benchmark.id
  admin_state_up = true

  fixed_ip {
    subnet_id  = openstack_networking_subnet_v2.benchmark.id
    ip_address = local.trino_worker_ips[count.index]
  }

  security_group_ids = [openstack_networking_secgroup_v2.benchmark.id]

  depends_on = [
    selectel_vpc_project_v2.benchmark,
    selectel_iam_serviceuser_v1.benchmark
  ]
}

locals {
  trino_worker_cloud_init = var.trino_enabled && local.trino_is_cluster ? [
    for i in range(local.trino_worker_count) : templatefile(
      "${path.module}/../cloud-init/selectel/trino-worker.yaml.tftpl",
      {
        trino_ram_gb   = local.trino_worker_actual_ram_gb
        trino_cpu      = local.trino_worker_actual_cpu
        coordinator_ip = local.trino_coordinator_ip
        minio_endpoint = local.trino_minio_endpoint
        minio_password = var.minio_enabled ? var.minio_root_password : "minioadmin"
        worker_index   = i + 1
      }
    )
  ] : []
}

resource "openstack_compute_instance_v2" "trino_worker" {
  count = var.trino_enabled && local.trino_is_cluster ? local.trino_worker_count : 0

  name              = "trino-worker-${count.index + 1}"
  flavor_id         = length(openstack_compute_flavor_v2.trino_worker) > 0 ? openstack_compute_flavor_v2.trino_worker[0].id : openstack_compute_flavor_v2.trino_coordinator[0].id
  key_pair          = selectel_vpc_keypair_v2.benchmark.name
  availability_zone = var.availability_zone
  user_data         = local.trino_worker_cloud_init[count.index]

  network {
    port = openstack_networking_port_v2.trino_worker[count.index].id
  }

  block_device {
    uuid                  = openstack_blockstorage_volume_v3.trino_worker_boot[count.index].id
    source_type           = "volume"
    destination_type      = "volume"
    boot_index            = 0
    delete_on_termination = true
  }

  lifecycle {
    ignore_changes = [image_id]
  }

  vendor_options {
    ignore_resize_confirmation = true
  }

  depends_on = [
    openstack_networking_router_interface_v2.benchmark,
    openstack_compute_instance_v2.trino_coordinator
  ]
}

resource "openstack_compute_volume_attach_v2" "trino_worker_data" {
  count = var.trino_enabled && local.trino_is_cluster ? local.trino_worker_count : 0

  instance_id = openstack_compute_instance_v2.trino_worker[count.index].id
  volume_id   = openstack_blockstorage_volume_v3.trino_worker_data[count.index].id
  device      = "/dev/vdb"
}

# ============================================================================
# Outputs
# ============================================================================

output "trino_vm_ip" {
  description = "Private IP of Trino coordinator"
  value       = var.trino_enabled ? local.trino_coordinator_ip : null
}

output "trino_http" {
  description = "Trino HTTP endpoint"
  value       = var.trino_enabled ? "http://${local.trino_coordinator_ip}:8080" : null
}

output "nessie_url" {
  description = "Nessie REST API endpoint"
  value       = var.trino_enabled ? "http://${local.trino_coordinator_ip}:19120/api/v2" : null
}

output "trino_topology_info" {
  description = "Trino topology information"
  value = var.trino_enabled ? {
    mode               = var.trino_topology
    coordinator_ip     = local.trino_coordinator_ip
    coordinator_cpu    = var.trino_cpu
    coordinator_ram_gb = var.trino_ram_gb
    worker_ips         = local.trino_worker_ips
    worker_cpu         = local.trino_worker_actual_cpu
    worker_ram_gb      = local.trino_worker_actual_ram_gb
    total_nodes        = local.trino_node_count
    total_cpu          = var.trino_cpu + (local.trino_worker_count * local.trino_worker_actual_cpu)
    total_ram_gb       = var.trino_ram_gb + (local.trino_worker_count * local.trino_worker_actual_ram_gb)
  } : null
}
