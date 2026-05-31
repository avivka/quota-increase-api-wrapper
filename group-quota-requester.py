import csv
import argparse
from group_quota_common import (
    make_request,
    build_group_quota_base_url,
    add_common_args,
    add_group_quota_name_arg,
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


def transfer_quota_single(args, location, resource_name, limit):
    url = (
        f"{MGMT_BASE_URL}/subscriptions/{args.subscription_id}"
        f"/providers/Microsoft.Quota/groupQuotas/{args.group_quota_name}"
        f"/quotaAllocations/{location}"
        f"?api-version={args.api_version}"
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
    print(f"Transfer Quota (sub={args.subscription_id}, location={location}, "
          f"resource={resource_name}, limit={limit}): "
          f"Status Code: {status_code}, Response: {response}")


def transfer_quota(args):
    if args.csv_file_path:
        rows = read_csv(args.csv_file_path)
        for row in rows:
            transfer_quota_single(args, row['location'], row['resource_name'], row['limit'])
    else:
        transfer_quota_single(args, args.location, args.resource_name, args.limit)


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

    # transfer-quota
    transfer_parser = subparsers.add_parser('transfer-quota', help='Transfer quota to a subscription')
    add_common_args(transfer_parser)
    add_group_quota_name_arg(transfer_parser)
    transfer_parser.add_argument('--subscription-id', type=str, required=True, help='Target subscription ID')
    transfer_parser.add_argument('--csv-file-path', type=str, help='CSV file with columns: location,resource_name,limit')
    transfer_parser.add_argument('--location', type=str, help='Azure region (e.g. eastus)')
    transfer_parser.add_argument('--resource-name', type=str, help='Resource/SKU family name (e.g. standardddv4family)')
    transfer_parser.add_argument('--limit', type=int, help='Quota limit to transfer')
    transfer_parser.set_defaults(func=transfer_quota)

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
