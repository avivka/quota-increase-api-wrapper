# Azure Quota Increase API Wrapper

CLI tools for managing Azure compute quotas — both per-subscription quotas and the newer **Group Quota API** (`Microsoft.Quota/groupQuotas`) that enables sharing quota across multiple subscriptions via a Management Group.

## Prerequisites

- Python 3.8+
- Azure CLI authenticated (`az login`) or a configured managed identity
- **Roles**: Quota Request Operator (or Contributor) on the management group and target subscriptions
- **Subscription types**: Enterprise Agreement (EA), MCA, or CSP (Pay-as-you-go is not supported for group quotas)
- **Resource providers**: `Microsoft.Quota` and `Microsoft.Compute` must be registered on each subscription

## Installation

```bash
pip install -r requirements.txt
```

## Scripts Overview

| Script | Purpose |
|---|---|
| `quota-increase-requester.py` | Per-subscription quota increase requests (legacy) |
| `quota-increase-request-fetcher.py` | Per-subscription quota usage fetcher (legacy) |
| `group-quota-requester.py` | Group Quota write operations |
| `group-quota-fetcher.py` | Group Quota read operations |

## Group Quota Requester — Write Operations

```bash
python group-quota-requester.py <subcommand> [options]
```

### Subcommands

#### `create` — Create a group quota

```bash
python group-quota-requester.py create \
  --management-group-id myMgmtGroup \
  --group-quota-name myGroupQuota \
  --display-name "My Group Quota"
```

#### `delete` — Delete a group quota

```bash
python group-quota-requester.py delete \
  --management-group-id myMgmtGroup \
  --group-quota-name myGroupQuota
```

#### `add-subscription` — Add a subscription to a group quota

```bash
python group-quota-requester.py add-subscription \
  --management-group-id myMgmtGroup \
  --group-quota-name myGroupQuota \
  --subscription-id 00000000-0000-0000-0000-000000000000
```

#### `remove-subscription` — Remove a subscription from a group quota

```bash
python group-quota-requester.py remove-subscription \
  --management-group-id myMgmtGroup \
  --group-quota-name myGroupQuota \
  --subscription-id 00000000-0000-0000-0000-000000000000
```

#### `auto-rebalance` — Automatically redistribute quota across subscriptions

Runs a continuous loop that scans all subscriptions in the group, identifies which subscription needs quota most (highest usage %), reclaims spare quota from low-usage donor subscriptions (at or below the donor threshold), and allocates it to the target.

```bash
python group-quota-requester.py auto-rebalance \
  --management-group-id myMgmtGroup \
  --group-quota-name myGroupQuota \
  --location eastus \
  --resource-name standardDSv4Family \
  --donor-threshold 40 \
  --interval 300
```

**How it works (each cycle):**

1. Lists all subscriptions in the group quota
2. Queries compute usage (`currentValue` / `limit`) for the specified resource in each subscription
3. Prints a usage summary table
4. Identifies the **target** — subscription with the highest usage %
5. Identifies **donors** — subscriptions at or below the `--donor-threshold` usage %
6. Reclaims spare cores from each donor (PATCHes their allocation down to their current usage)
7. Allocates the total reclaimed cores to the target (PATCHes its allocation up)
8. Sleeps for `--interval` seconds before the next cycle

Press `Ctrl+C` to stop the loop.

| Option | Description | Default |
|---|---|---|
| `--location` | Azure region to rebalance | Required |
| `--resource-name` | VM family to rebalance (e.g. `standardDSv4Family`) | Required |
| `--donor-threshold` | Subs at or below this usage % are donors | `40` |
| `--interval` | Seconds between rebalance cycles | `300` |

#### `request-limit-increase` — Request a group quota limit increase

Single operation:

```bash
python group-quota-requester.py request-limit-increase \
  --management-group-id myMgmtGroup \
  --group-quota-name myGroupQuota \
  --location eastus \
  --resource-name standardddv4family \
  --limit 100 \
  --comment "Q2 scaling"
```

Batch mode (CSV):

```bash
python group-quota-requester.py request-limit-increase \
  --management-group-id myMgmtGroup \
  --group-quota-name myGroupQuota \
  --csv-file-path limits.csv
```

CSV format (`limits.csv`):

```csv
location,resource_name,limit,comment
eastus,standardddv4family,100,Q2 scaling
westus2,standarddsv5family,200,New workload
```

## Group Quota Fetcher — Read Operations

```bash
python group-quota-fetcher.py <subcommand> [options]
```

### Subcommands

#### `get` — Get a specific group quota

```bash
python group-quota-fetcher.py get \
  --management-group-id myMgmtGroup \
  --group-quota-name myGroupQuota
```

#### `list` — List all group quotas under a management group

```bash
python group-quota-fetcher.py list \
  --management-group-id myMgmtGroup
```

#### `allocation-snapshot` — Get quota allocation snapshot

```bash
python group-quota-fetcher.py allocation-snapshot \
  --management-group-id myMgmtGroup \
  --group-quota-name myGroupQuota \
  --subscription-id 00000000-0000-0000-0000-000000000000 \
  --location eastus
```

#### `group-limit-snapshot` — Get group-level limit snapshot

```bash
python group-quota-fetcher.py group-limit-snapshot \
  --management-group-id myMgmtGroup \
  --group-quota-name myGroupQuota \
  --location eastus
```

#### `request-status` — Check async request status

```bash
python group-quota-fetcher.py request-status \
  --management-group-id myMgmtGroup \
  --group-quota-name myGroupQuota \
  --request-id 00000000-0000-0000-0000-000000000000
```

#### `usages` — Get group quota usage info (API 2025-09-01)

```bash
python group-quota-fetcher.py usages \
  --management-group-id myMgmtGroup \
  --group-quota-name myGroupQuota \
  --location eastus
```

#### `register-providers` — Register resource providers on subscriptions

```bash
python group-quota-fetcher.py register-providers \
  --subscription-ids sub1,sub2,sub3
```

## Typical End-to-End Workflow

```bash
# 1. Register providers on target subscriptions
python group-quota-fetcher.py register-providers \
  --subscription-ids sub-id-1,sub-id-2

# 2. Create a group quota
python group-quota-requester.py create \
  --management-group-id myMgmtGroup \
  --group-quota-name myGroupQuota \
  --display-name "Production Quota Pool"

# 3. Add subscriptions
python group-quota-requester.py add-subscription \
  --management-group-id myMgmtGroup \
  --group-quota-name myGroupQuota \
  --subscription-id sub-id-1

python group-quota-requester.py add-subscription \
  --management-group-id myMgmtGroup \
  --group-quota-name myGroupQuota \
  --subscription-id sub-id-2

# 4. Request a group-level limit increase
python group-quota-requester.py request-limit-increase \
  --management-group-id myMgmtGroup \
  --group-quota-name myGroupQuota \
  --location eastus \
  --resource-name standardddv4family \
  --limit 200 \
  --comment "Production scaling"

# 5. Auto-rebalance quota across subscriptions
python group-quota-requester.py auto-rebalance \
  --management-group-id myMgmtGroup \
  --group-quota-name myGroupQuota \
  --location eastus \
  --resource-name standardDSv4Family

# 6. Check allocation snapshot
python group-quota-fetcher.py allocation-snapshot \
  --management-group-id myMgmtGroup \
  --group-quota-name myGroupQuota \
  --subscription-id sub-id-1 \
  --location eastus

# 7. View group-level limits
python group-quota-fetcher.py group-limit-snapshot \
  --management-group-id myMgmtGroup \
  --group-quota-name myGroupQuota \
  --location eastus
```

## Common Options

| Flag | Description | Default |
|---|---|---|
| `--management-group-id` | Azure Management Group ID | Required |
| `--group-quota-name` | Name of the group quota resource | Required (most subcommands) |
| `--api-version` | ARM API version | `2025-03-01` |

## References

- [Group Quotas REST API](https://learn.microsoft.com/en-us/rest/api/quota/group-quotas)
- [Share Quota Across Subscriptions](https://learn.microsoft.com/en-us/azure/quotas/quota-groups)
- [Create/Delete Quota Groups](https://learn.microsoft.com/en-us/azure/quotas/create-quota-groups)
- [Add/Remove Subscriptions](https://learn.microsoft.com/en-us/azure/quotas/add-remove-subscriptions-quota-group)
- [Transfer Quota](https://learn.microsoft.com/en-us/azure/quotas/transfer-quota-groups)
- [Group Limit Increase](https://learn.microsoft.com/en-us/azure/quotas/quota-group-limit-increase)
