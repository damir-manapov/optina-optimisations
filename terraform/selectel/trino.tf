# Trino + Nessie + PostgreSQL Configuration for Selectel
# Single-node setup with all services co-located

# Variables for Trino
variable "trino_enabled" {
  description = "Enable Trino-Iceberg deployment"
  type        = bool
  default     = false
}

variable "trino_cpu" {
  description = "CPU cores for Trino node"
  type        = number
  default     = 8
}

variable "trino_ram_gb" {
  description = "RAM in GB for Trino node"
  type        = number
  default     = 32
}

variable "trino_disk_size_gb" {
  description = "Disk size in GB for Trino node"
  type        = number
  default     = 200
}

variable "trino_disk_type" {
  description = "Disk type: fast or universal"
  type        = string
  default     = "fast"
}

# Trino flavor
resource "openstack_compute_flavor_v2" "trino" {
  count = var.trino_enabled ? 1 : 0

  name      = "trino-${var.environment_name}-${var.trino_cpu}vcpu-${var.trino_ram_gb}gb"
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

# Security group rules for Trino
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

# Nessie REST API
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

# PostgreSQL for Nessie metadata (internal)
resource "openstack_networking_secgroup_rule_v2" "trino_postgres" {
  count = var.trino_enabled ? 1 : 0

  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 5432
  port_range_max    = 5432
  remote_ip_prefix  = "10.0.0.40/32" # Only from Trino node itself
  security_group_id = openstack_networking_secgroup_v2.benchmark.id
}

# Boot volume for Trino
resource "openstack_blockstorage_volume_v3" "trino_boot" {
  count = var.trino_enabled ? 1 : 0

  name              = "trino-boot"
  size              = var.trino_disk_size_gb
  image_id          = data.openstack_images_image_v2.ubuntu.id
  volume_type       = "${var.trino_disk_type}.${var.availability_zone}"
  availability_zone = var.availability_zone
}

# Data volume for Iceberg warehouse
resource "openstack_blockstorage_volume_v3" "trino_data" {
  count = var.trino_enabled ? 1 : 0

  name              = "trino-data"
  size              = var.trino_disk_size_gb
  volume_type       = "${var.trino_disk_type}.${var.availability_zone}"
  availability_zone = var.availability_zone
}

# Network port for Trino (10.0.0.40)
resource "openstack_networking_port_v2" "trino" {
  count = var.trino_enabled ? 1 : 0

  name           = "trino-port"
  network_id     = openstack_networking_network_v2.benchmark.id
  admin_state_up = true

  fixed_ip {
    subnet_id  = openstack_networking_subnet_v2.benchmark.id
    ip_address = "10.0.0.40"
  }

  security_group_ids = [openstack_networking_secgroup_v2.benchmark.id]

  depends_on = [
    selectel_vpc_project_v2.benchmark,
    selectel_iam_serviceuser_v1.benchmark
  ]
}

# Cloud-init for Trino node
locals {
  trino_cloud_init = var.trino_enabled ? templatefile("${path.module}/../cloud-init/selectel/trino-iceberg.yaml.tftpl", {
    trino_ram_gb = var.trino_ram_gb
    trino_cpu    = var.trino_cpu
  }) : ""
}

# Trino compute instance
resource "openstack_compute_instance_v2" "trino" {
  count = var.trino_enabled ? 1 : 0

  name              = "trino"
  flavor_id         = openstack_compute_flavor_v2.trino[0].id
  key_pair          = selectel_vpc_keypair_v2.benchmark.name
  availability_zone = var.availability_zone
  user_data         = local.trino_cloud_init

  network {
    port = openstack_networking_port_v2.trino[0].id
  }

  block_device {
    uuid                  = openstack_blockstorage_volume_v3.trino_boot[0].id
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

# Attach data volume to Trino instance
resource "openstack_compute_volume_attach_v2" "trino_data" {
  count = var.trino_enabled ? 1 : 0

  instance_id = openstack_compute_instance_v2.trino[0].id
  volume_id   = openstack_blockstorage_volume_v3.trino_data[0].id
  device      = "/dev/vdb"
}

# Outputs
output "trino_vm_ip" {
  description = "Private IP of Trino node (access via benchmark VM)"
  value       = var.trino_enabled ? "10.0.0.40" : null
}

output "trino_http" {
  description = "Trino HTTP endpoint (private)"
  value       = var.trino_enabled ? "http://10.0.0.40:8080" : null
}

output "nessie_url" {
  description = "Nessie REST API endpoint (private)"
  value       = var.trino_enabled ? "http://10.0.0.40:19120/api/v2" : null
}

output "trino_config" {
  description = "Trino configuration summary"
  value = var.trino_enabled ? {
    cpu       = var.trino_cpu
    ram_gb    = var.trino_ram_gb
    disk_gb   = var.trino_disk_size_gb
    disk_type = var.trino_disk_type
  } : null
}
