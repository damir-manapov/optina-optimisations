# Selectel Account Credentials
# Set via environment variables:
#   export TF_VAR_selectel_domain="123456"
#   export TF_VAR_selectel_username="your-username"
#   export TF_VAR_selectel_password="your-password"
#   export TF_VAR_selectel_openstack_password="your-openstack-password"

variable "selectel_domain" {
  description = "Selectel account domain (account ID)"
  type        = string
  default     = null
}

variable "selectel_username" {
  description = "Selectel username"
  type        = string
  default     = null
}

variable "selectel_password" {
  description = "Selectel password"
  type        = string
  sensitive   = true
  default     = null
}

variable "selectel_openstack_password" {
  description = "Password for OpenStack service user"
  type        = string
  sensitive   = true
  default     = null
}

# Environment
variable "environment_name" {
  description = "Name suffix for resources (e.g., 'fast-ssd-96gb')"
  type        = string
  default     = "test"
}

variable "region" {
  description = "Selectel region"
  type        = string
  default     = "ru-7"
}

variable "availability_zone" {
  description = "Availability zone"
  type        = string
  default     = "ru-7b"
}

# VM Configuration
variable "cpu_count" {
  description = "Number of vCPUs for benchmark VM"
  type        = number
  default     = 16
}

variable "ram_gb" {
  description = "RAM in GB for benchmark VM (Selectel requires 32GB min for 16 vCPUs)"
  type        = number
  default     = 32
}

variable "disk_size_gb" {
  description = "Boot disk size in GB"
  type        = number
  default     = 200
}

variable "disk_type" {
  description = "Disk type: fast, universal2, universal, basicssd, basic"
  type        = string
  default     = "fast"

  validation {
    condition     = contains(["fast", "universal2", "universal", "basicssd", "basic"], var.disk_type)
    error_message = "disk_type must be one of: fast, universal2, universal, basicssd, basic"
  }
}

variable "ssh_public_key_path" {
  description = "Path to SSH public key file"
  type        = string
  default     = "~/.ssh/id_ed25519.pub"
}

# ============================================================================
# Cluster Topology Configuration
# ============================================================================

# --- Trino Topology ---
variable "trino_topology" {
  description = "Trino deployment: solo (all-in-one) or cluster (coordinator + workers)"
  type        = string
  default     = "solo"

  validation {
    condition     = contains(["solo", "cluster"], var.trino_topology)
    error_message = "trino_topology must be: solo or cluster"
  }
}

variable "trino_workers" {
  description = "Number of Trino worker nodes (cluster mode only)"
  type        = number
  default     = 2

  validation {
    condition     = var.trino_workers >= 1 && var.trino_workers <= 8
    error_message = "trino_workers must be between 1 and 8"
  }
}

variable "trino_worker_cpu" {
  description = "CPU cores per Trino worker (cluster mode). If null, uses trino_cpu"
  type        = number
  default     = null
}

variable "trino_worker_ram_gb" {
  description = "RAM in GB per Trino worker (cluster mode). If null, uses trino_ram_gb"
  type        = number
  default     = null
}

# --- MinIO Topology ---
variable "minio_topology" {
  description = "MinIO deployment: solo (single node) or cluster (distributed erasure)"
  type        = string
  default     = "solo"

  validation {
    condition     = contains(["solo", "cluster"], var.minio_topology)
    error_message = "minio_topology must be: solo or cluster"
  }
}

variable "minio_nodes" {
  description = "Number of MinIO nodes (cluster mode only, min 4 for erasure coding)"
  type        = number
  default     = 4

  validation {
    condition     = var.minio_nodes >= 1 && var.minio_nodes <= 16
    error_message = "minio_nodes must be between 1 and 16"
  }
}

variable "minio_cpu" {
  description = "CPU cores per MinIO node"
  type        = number
  default     = 4
}

variable "minio_ram_gb" {
  description = "RAM in GB per MinIO node"
  type        = number
  default     = 16
}

variable "minio_disk_size_gb" {
  description = "Disk size in GB per MinIO drive"
  type        = number
  default     = 100
}

variable "minio_disk_type" {
  description = "Disk type for MinIO drives"
  type        = string
  default     = "fast"
}

variable "minio_drives_per_node" {
  description = "Number of data drives per MinIO node"
  type        = number
  default     = 2

  validation {
    condition     = var.minio_drives_per_node >= 1 && var.minio_drives_per_node <= 8
    error_message = "minio_drives_per_node must be between 1 and 8"
  }
}
