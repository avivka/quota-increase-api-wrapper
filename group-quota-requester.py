import csv
import time
import datetime
import argparse
from group_quota_common import (
    make_request,
    build_group_quota_base_url,
    add_common_args,
    add_group_quota_name_arg,
    list_group_subscriptions,
    get_compute_usage,
    MGMT_BASE_URL,
)

# Reference: https://learn.microsoft.com/en-us/rest/api/quota/group-quotas
#            https://learn.microsoft.com/en-us/azure/quotas/create-quota-groups
#            https://learn.microsoft.com/en-us/azure/quotas/add-remove-subscriptions-quota-group
#            https://learn.microsoft.com/en-us/azure/quotas/transfer-quota-groups
#            https://learn.microsoft.com/en-us/azure/quotas/quota-group-limit-increase


def read_csv(file_path):
    with open(file_path, mode='r') as file:
        csv_reader = csv.DictReader(file)
        return [row for row in csv_reader]


# --- Subcommand handlers ---

def create_group_quota(args):
    base_url = build_group_quota_base_url(args.management_group_id, args.api_version)
    url = f"{base_url}/{args.group_quota_name}?api-version={args.api_version}"
    payload = {
        "properties": {
            "displayName": args.display_name if args.display_name else args.group_quota_name
        }
    }
    status_code, response = make_request("PUT", url, payload)
    print(f"Create Group Quota '{args.group_quota_name}': Status Code: {status_code}, Response: {response}")


def delete_group_quota(args):
    base_url = build_group_quota_base_url(args.management_group_id, args.api_version)
    url = f"{base_url}/{args.group_quota_name}?api-version={args.api_version}"
    status_code, response = make_request("DELETE", url)
    print(f"Delete Group Quota '{args.group_quota_name}': Status Code: {status_code}, Response: {response}")


def add_subscription(args):
    base_url = build_group_quota_base_url(args.management_group_id, args.api_version)
    url = (
        f"{base_url}/{args.group_quota_name}"
        f"/subscriptions/{args.subscription_id}"
        f"?api-version={args.api_version}"
    )
    payload = {}
    status_code, response = make_request("PUT", url, payload)
    print(f"Add Subscription '{args.subscription_id}' to Group Quota '{args.group_quota_name}': "
          f"Status Code: {status_code}, Response: {response}")


def remove_subscription(args):
    base_url = build_group_quota_base_url(args.management_group_id, args.api_version)
    url = (
        f"{base_url}/{args.group_quota_name}"
        f"/subscriptions/{args.subscription_id}"
        f"?api-version={args.api_version}"
    )
    status_code, response = make_request("DELETE", url)
    print(f"Remove Subscription '{args.subscription_id}' from Group Quota '{args.group_quota_name}': "
          f"Status Code: {status_code}, Response: {response}")


def patch_allocation(subscription_id, group_quota_name, location, resource_name, limit, api_version):
    """PATCH quota allocation for a subscription."""
    url = (
        f"{MGMT_BASE_URL}/subscriptions/{subscription_id}"
        f"/providers/Microsoft.Quota/groupQuotas/{group_quota_name}"
        f"/quotaAllocations/{location}"
        f"?api-version={api_version}"
    )
    payload = {
        "properties": {
            "value": [
                {
                    "resourceName": resource_name,
                    "properties": {
                        "limit": int(limit)
                    }
                }
            ]
        }
    }
    status_code, response = make_request("PATCH", url, payload)
    return status_code, response


def auto_rebalance(args):
    print(f"Starting auto-rebalance loop (interval={args.interval}s, donor threshold={args.donor_threshold}%)")
    print(f"  Management Group: {args.management_group_id}")
    print(f"  Group Quota:      {args.group_quota_name}")
    print(f"  Location:         {args.location}")
    print(f"  Resource:         {args.resource_name}")
    print()

    try:
        while True:
            print(f"=== Rebalance cycle at {datetime.datetime.now().isoformat()} ===")

            # 1. List subscriptions
            sub_ids = list_group_subscriptions(
                args.management_group_id, args.group_quota_name, args.api_version
            )
            if not sub_ids:
                print("No subscriptions found in group quota. Skipping cycle.")
                time.sleep(args.interval)
                continue

            # 2. Gather usage for each subscription
            usage_data = []
            for sub_id in sub_ids:
                result = get_compute_usage(sub_id, args.location, args.resource_name)
                if result is None:
                    continue
                current_value, limit = result
                if limit == 0:
                    print(f"  Skipping {sub_id}: limit is 0")
                    continue
                usage_pct = (current_value / limit) * 100
                usage_data.append({
                    "subscription_id": sub_id,
                    "current_value": current_value,
                    "limit": limit,
                    "usage_pct": usage_pct,
                })

            if not usage_data:
                print("No usage data available. Skipping cycle.")
                time.sleep(args.interval)
                continue

            # 3. Print usage summary table
            print(f"\n{'Subscription':<40} {'Used':>6} {'Limit':>6} {'Usage%':>7}")
            print("-" * 62)
            for entry in sorted(usage_data, key=lambda x: x["usage_pct"], reverse=True):
                print(f"{entry['subscription_id']:<40} {entry['current_value']:>6} {entry['limit']:>6} {entry['usage_pct']:>6.1f}%")
            print()

            # 4. Identify target (highest usage %) and donors (<= threshold)
            target = max(usage_data, key=lambda x: x["usage_pct"])
            donors = [
                e for e in usage_data
                if e["usage_pct"] <= args.donor_threshold
                and e["subscription_id"] != target["subscription_id"]
            ]

            if not donors:
                print("No donor subscriptions available (none at or below threshold). Skipping cycle.")
                time.sleep(args.interval)
                continue

            if target["usage_pct"] <= args.donor_threshold:
                print(f"Target subscription usage ({target['usage_pct']:.1f}%) is at or below threshold. No rebalance needed.")
                time.sleep(args.interval)
                continue

            # 5. Reclaim spare quota from donors
            total_reclaimed = 0
            for donor in donors:
                spare = donor["limit"] - donor["current_value"]
                if spare <= 0:
                    continue
                new_limit = donor["current_value"]
                print(f"Reclaiming {spare} cores from {donor['subscription_id']} (limit {donor['limit']} -> {new_limit})")
                status_code, response = patch_allocation(
                    donor["subscription_id"], args.group_quota_name,
                    args.location, args.resource_name, new_limit, args.api_version
                )
                if status_code == 200:
                    total_reclaimed += spare
                else:
                    print(f"  Failed to reclaim from {donor['subscription_id']}: Status {status_code}, Response: {response}")

            if total_reclaimed == 0:
                print("No quota reclaimed from donors. Skipping allocation to target.")
                time.sleep(args.interval)
                continue

            # 6. Allocate reclaimed quota to target
            new_target_limit = target["limit"] + total_reclaimed
            print(f"\nAllocating {total_reclaimed} reclaimed cores to {target['subscription_id']} "
                  f"(limit {target['limit']} -> {new_target_limit})")
            status_code, response = patch_allocation(
                target["subscription_id"], args.group_quota_name,
                args.location, args.resource_name, new_target_limit, args.api_version
            )
            if status_code != 200:
                print(f"  Failed to allocate to target: Status {status_code}, Response: {response}")

            print(f"\nCycle complete. Reclaimed {total_reclaimed} cores total.\n")
            time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\nAuto-rebalance stopped by user.")


def request_limit_increase_single(args, location, resource_name, limit, comment=None):
    base_url = build_group_quota_base_url(args.management_group_id, args.api_version)
    url = (
        f"{base_url}/{args.group_quota_name}"
        f"/resourceProviders/Microsoft.Compute"
        f"/groupQuotaLimits/{location}"
        f"?api-version={args.api_version}"
    )
    resource_entry = {
        "resourceName": resource_name,
        "properties": {
            "limit": int(limit)
        }
    }
    if comment:
        resource_entry["properties"]["comment"] = comment

    payload = {
        "properties": {
            "value": [resource_entry]
        }
    }
    status_code, response = make_request("PATCH", url, payload)
    print(f"Request Limit Increase (group={args.group_quota_name}, location={location}, "
          f"resource={resource_name}, limit={limit}): "
          f"Status Code: {status_code}, Response: {response}")


def request_limit_increase(args):
    if args.csv_file_path:
        rows = read_csv(args.csv_file_path)
        for row in rows:
            request_limit_increase_single(
                args, row['location'], row['resource_name'],
                row['limit'], row.get('comment')
            )
    else:
        request_limit_increase_single(
            args, args.location, args.resource_name,
            args.limit, args.comment
        )


# --- CLI setup ---

def main():
    parser = argparse.ArgumentParser(
        description='Azure Group Quota write operations (create, delete, manage subscriptions, transfer, increase limits).'
    )
    subparsers = parser.add_subparsers(dest='command', help='Subcommand to run')
    subparsers.required = True

    # create
    create_parser = subparsers.add_parser('create', help='Create a new group quota')
    add_common_args(create_parser)
    add_group_quota_name_arg(create_parser)
    create_parser.add_argument('--display-name', type=str, help='Display name for the group quota (defaults to group-quota-name)')
    create_parser.set_defaults(func=create_group_quota)

    # delete
    delete_parser = subparsers.add_parser('delete', help='Delete a group quota')
    add_common_args(delete_parser)
    add_group_quota_name_arg(delete_parser)
    delete_parser.set_defaults(func=delete_group_quota)

    # add-subscription
    add_sub_parser = subparsers.add_parser('add-subscription', help='Add a subscription to a group quota')
    add_common_args(add_sub_parser)
    add_group_quota_name_arg(add_sub_parser)
    add_sub_parser.add_argument('--subscription-id', type=str, required=True, help='Subscription ID to add')
    add_sub_parser.set_defaults(func=add_subscription)

    # remove-subscription
    rm_sub_parser = subparsers.add_parser('remove-subscription', help='Remove a subscription from a group quota')
    add_common_args(rm_sub_parser)
    add_group_quota_name_arg(rm_sub_parser)
    rm_sub_parser.add_argument('--subscription-id', type=str, required=True, help='Subscription ID to remove')
    rm_sub_parser.set_defaults(func=remove_subscription)

    # auto-rebalance
    rebalance_parser = subparsers.add_parser('auto-rebalance', help='Automatically redistribute quota from low-usage to high-usage subscriptions')
    add_common_args(rebalance_parser)
    add_group_quota_name_arg(rebalance_parser)
    rebalance_parser.add_argument('--location', type=str, required=True, help='Azure region to rebalance (e.g. eastus)')
    rebalance_parser.add_argument('--resource-name', type=str, required=True, help='VM family to rebalance (e.g. standardDSv4Family)')
    rebalance_parser.add_argument('--donor-threshold', type=float, default=40, help='Subs at or below this usage %% are donors (default: 40)')
    rebalance_parser.add_argument('--interval', type=int, default=300, help='Seconds between rebalance cycles (default: 300)')
    rebalance_parser.set_defaults(func=auto_rebalance)

    # request-limit-increase
    increase_parser = subparsers.add_parser('request-limit-increase', help='Request a group quota limit increase')
    add_common_args(increase_parser)
    add_group_quota_name_arg(increase_parser)
    increase_parser.add_argument('--csv-file-path', type=str, help='CSV file with columns: location,resource_name,limit,comment')
    increase_parser.add_argument('--location', type=str, help='Azure region (e.g. eastus)')
    increase_parser.add_argument('--resource-name', type=str, help='Resource/SKU family name (e.g. standardddv4family)')
    increase_parser.add_argument('--limit', type=int, help='Desired quota limit')
    increase_parser.add_argument('--comment', type=str, help='Justification comment')
    increase_parser.set_defaults(func=request_limit_increase)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
