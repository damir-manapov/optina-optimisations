# Terraform Infrastructure

Deploy benchmark VMs on Selectel or Timeweb Cloud.

## Prerequisites

- [Terraform](https://terraform.io/downloads) >= 1.0
- [tflint](https://github.com/terraform-linters/tflint) - linting
- [trivy](https://github.com/aquasecurity/trivy) - security scanning
- Cloud account (Selectel or Timeweb)

## Cloud Setup

### Selectel

1. **Create a service user** at https://my.selectel.ru/iam/service-users:
   - Assign role `member` in Account access area
   - Assign role `iam_admin` for project management
   - Note the username and password

2. **Get your account number** (domain) from the upper right corner of https://my.selectel.ru/

3. **Set environment variables:**

```bash
export TF_VAR_selectel_domain="123456"              # Account number
export TF_VAR_selectel_username="service-user"      # Service user name
export TF_VAR_selectel_password="service-password"  # Service user password
# Random password for OpenStack user that Terraform will create:
export TF_VAR_selectel_openstack_password="$(openssl rand -base64 24)"

cd terraform/selectel
cp terraform.tfvars.example terraform.tfvars
terraform init
```

### Timeweb

Get API token from https://timeweb.cloud/my/api-keys

```bash
export TWC_TOKEN="your-api-token"

cd terraform/timeweb
cp terraform.tfvars.example terraform.tfvars
terraform init
```

## Usage

```bash
terraform plan
terraform apply

# Get SSH command
terraform output ssh_command

# Wait for cloud-init to complete (~3-5 min)
eval $(terraform output -raw wait_for_ready)

# Destroy when done
terraform destroy
```

## Configuration

Edit `terraform.tfvars`:

| Variable           | Default      | Description           |
| ------------------ | ------------ | --------------------- |
| `environment_name` | `test`       | Resource name suffix  |
| `cpu_count`        | `8`          | vCPUs                 |
| `ram_gb`           | `8`          | RAM in GB             |
| `disk_size_gb`     | `200`        | Disk size in GB       |
| `disk_type`        | `fast`/`nvme`| Disk type (see below) |

### Disk Types

**Selectel:**
| Type        | IOPS (r/w)  | Throughput |
| ----------- | ----------- | ---------- |
| `fast`      | 25k/15k     | 500 MB/s   |
| `universal` | up to 16k   | 200 MB/s   |
| `basic`     | 640/320     | 150 MB/s   |

**Timeweb:**
| Type   | Description           |
| ------ | --------------------- |
| `nvme` | NVMe SSD (fastest)    |
| `ssd`  | Standard SSD          |
| `hdd`  | HDD (cheapest)        |

## MinIO Cluster (Optional)

Add to `terraform.tfvars`:

```hcl
minio_enabled       = true
minio_root_password = "your-secure-password"
minio_node_cpu      = 4
minio_node_ram_gb   = 16
minio_drives_per_node = 2
minio_drive_size_gb = 100
```

Access via SSH tunnel:
```bash
ssh -L 9001:10.0.0.10:9001 -L 9000:10.0.0.10:9000 root@<vm-ip>
# Console: http://localhost:9001
# S3 API: http://localhost:9000
```

## Cloud-init

VMs are automatically configured with:
- Docker, Node.js 24, pnpm
- warp (MinIO benchmark tool)
- Benchmark repo cloned and installed
- `/root/benchmark-ready` marker when complete

## Checks

```bash
./terraform/check.sh
```

Runs: `terraform fmt`, `terraform validate`, `tflint`, `trivy`

## OpenStack CLI (Selectel)

For debugging and cleanup. Install OpenStack CLI first:

```bash
pip install python-openstackclient
```

Set environment variables:

```bash
export OS_AUTH_URL="https://cloud.api.selcloud.ru/identity/v3"
export OS_IDENTITY_API_VERSION=3
export OS_PROJECT_DOMAIN_NAME="$TF_VAR_selectel_domain"
export OS_USER_DOMAIN_NAME="$TF_VAR_selectel_domain"
export OS_USERNAME="$TF_VAR_selectel_username"
export OS_PASSWORD="$TF_VAR_selectel_password"
export OS_REGION_NAME="ru-7"
```

### Cleanup Stale Flavors

When terraform state gets corrupted, flavors may become orphaned. Delete them manually:

```bash
# List all benchmark flavors
openstack flavor list | grep -E 'benchmark|minio|trino'

# Delete specific flavor by name
openstack flavor delete benchmark-optuna-16vcpu-32gb

# Delete all stale benchmark flavors (careful!)
openstack flavor list -f value -c ID -c Name | grep benchmark | awk '{print $1}' | xargs -r openstack flavor delete
```

### Cleanup Stale Volumes

```bash
# List volumes
openstack volume list

# Delete orphaned volumes
openstack volume delete <volume-id>
```

### Cleanup Stale VMs

```bash
# List servers
openstack server list

# Delete orphaned servers
openstack server delete <server-id>
```

### Full Reset

When things go wrong, do a full reset:

```bash
cd terraform/selectel

# 1. Try terraform destroy first (may fail if state is corrupted)
terraform destroy -auto-approve

# 2. Reset terraform state
rm -rf .terraform terraform.tfstate* .terraform.lock.hcl
terraform init

# 3. Manually cleanup orphaned resources via OpenStack CLI
openstack flavor list | grep benchmark | awk '{print $1}' | xargs -r openstack flavor delete
openstack server list | grep -E 'benchmark|minio|trino' | awk '{print $2}' | xargs -r openstack server delete
openstack volume list | grep -E 'benchmark|minio|trino' | awk '{print $2}' | xargs -r openstack volume delete

# 4. Delete Optuna study (optional, to start fresh)
rm -f optimizers/trino_iceberg/study.db
rm -f optimizers/minio/study.db
```

### Useful Commands

```bash
openstack flavor list
openstack volume type list
openstack server list
openstack volume list
openstack network list
```
