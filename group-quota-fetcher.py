import json
import argparse
from azure.identity import DefaultAzureCredential
from azure.mgmt.resource import ResourceManagementClient
from group_quota_common import (
    make_request,
    build_group_quota_base_url,
    add_common_args,
    add_group_quota_name_arg,
    MGMT_BASE_URL,
)

# Reference: https://learn.microsoft.com/en-us/rest/api/quota/group-quotas
#            https://learn.microsoft.com/en-us/azure/quotas/quota-groups


# --- Subcommand handlers ---

def get_group_quota(args):
    base_url = build_group_quota_base_url(args.management_group_id, args.api_version)
    url = f"{base_url}/{args.group_quota_name}?api-version={args.api_version}"
    status_code, response = make_request("GET", url)
    print(f"Get Group Quota '{args.group_quota_name}': Status Code: {status_code}")
    print(json.dumps(response, indent=2))


def list_group_quotas(args):
    base_url = build_group_quota_base_url(args.management_group_id, args.api_version)
    url = f"{base_url}?api-version={args.api_version}"
    status_code, response = make_request("GET", url)
    print(f"List Group Quotas: Status Code: {status_code}")
    print(json.dumps(response, indent=2))


def allocation_snapshot(args):
    base_url = build_group_quota_base_url(args.management_group_id, args.api_version)
    url = (
        f"{base_url}/{args.group_quota_name}"
        f"/subscriptions/{args.subscription_id}"
        f"/resourceProviders/Microsoft.Compute"
        f"/quotaAllocations/{args.location}"
        f"?api-version={args.api_version}"
    )
    status_code, response = make_request("GET", url)
    print(f"Allocation Snapshot (sub={args.subscription_id}, location={args.location}): "
          f"Status Code: {status_code}")
    print(json.dumps(response, indent=2))


def group_limit_snapshot(args):
    base_url = build_group_quota_base_url(args.management_group_id, args.api_version)
    url = (
        f"{base_url}/{args.group_quota_name}"
        f"/resourceProviders/Microsoft.Compute"
        f"/groupQuotaLimits/{args.location}"
        f"?api-version={args.api_version}"
    )
    status_code, response = make_request("GET", url)
    print(f"Group Limit Snapshot (location={args.location}): Status Code: {status_code}")
    print(json.dumps(response, indent=2))


def request_status(args):
    base_url = build_group_quota_base_url(args.management_group_id, args.api_version)
    url = (
        f"{base_url}/{args.group_quota_name}"
        f"/groupQuotaRequests/{args.request_id}"
        f"?api-version={args.api_version}"
    )
    status_code, response = make_request("GET", url)
    print(f"Request Status (request={args.request_id}): Status Code: {status_code}")
    print(json.dumps(response, indent=2))


def usages(args):
    # Usages endpoint uses a newer API version
    api_version = "2025-09-01"
    base_url = build_group_quota_base_url(args.management_group_id, api_version)
    url = (
        f"{base_url}/{args.group_quota_name}"
        f"/resourceProviders/Microsoft.Compute"
        f"/groupQuotaUsages/{args.location}"
        f"?api-version={api_version}"
    )
    status_code, response = make_request("GET", url)
    print(f"Group Quota Usages (location={args.location}, api-version={api_version}): "
          f"Status Code: {status_code}")
    print(json.dumps(response, indent=2))


def register_providers(args):
    credential = DefaultAzureCredential()
    subscription_ids = args.subscription_ids.split(',')
    providers = ['Microsoft.Quota', 'Microsoft.Compute']

    for subscription_id in subscription_ids:
        resource_client = ResourceManagementClient(
            credential=credential,
            subscription_id=subscription_id
        )
        for provider_namespace in providers:
            provider = resource_client.providers.get(provider_namespace)
            if provider.registration_state == 'Registered':
                print(f"[{subscription_id}] {provider_namespace} is already registered.")
            else:
                print(f"[{subscription_id}] Registering {provider_namespace}...")
                result = resource_client.providers.register(provider_namespace)
                print(f"[{subscription_id}] {provider_namespace} registration status: {result.registration_state}")


# --- CLI setup ---

def main():
    parser = argparse.ArgumentParser(
        description='Azure Group Quota read operations (get, list, snapshots, status, usages, provider registration).'
    )
    subparsers = parser.add_subparsers(dest='command', help='Subcommand to run')
    subparsers.required = True

    # get
    get_parser = subparsers.add_parser('get', help='Get a specific group quota')
    add_common_args(get_parser)
    add_group_quota_name_arg(get_parser)
    get_parser.set_defaults(func=get_group_quota)

    # list
    list_parser = subparsers.add_parser('list', help='List all group quotas under a management group')
    add_common_args(list_parser)
    list_parser.set_defaults(func=list_group_quotas)

    # allocation-snapshot
    alloc_parser = subparsers.add_parser('allocation-snapshot', help='Get quota allocation snapshot for a subscription/location')
    add_common_args(alloc_parser)
    add_group_quota_name_arg(alloc_parser)
    alloc_parser.add_argument('--subscription-id', type=str, required=True, help='Subscription ID')
    alloc_parser.add_argument('--location', type=str, required=True, help='Azure region (e.g. eastus)')
    alloc_parser.set_defaults(func=allocation_snapshot)

    # group-limit-snapshot
    limit_parser = subparsers.add_parser('group-limit-snapshot', help='Get group-level limit snapshot for a location')
    add_common_args(limit_parser)
    add_group_quota_name_arg(limit_parser)
    limit_parser.add_argument('--location', type=str, required=True, help='Azure region (e.g. eastus)')
    limit_parser.set_defaults(func=group_limit_snapshot)

    # request-status
    status_parser = subparsers.add_parser('request-status', help='Check async request status by request ID')
    add_common_args(status_parser)
    add_group_quota_name_arg(status_parser)
    status_parser.add_argument('--request-id', type=str, required=True, help='Request ID to check')
    status_parser.set_defaults(func=request_status)

    # usages
    usages_parser = subparsers.add_parser('usages', help='Get group quota usage info per location (API 2025-09-01)')
    add_common_args(usages_parser)
    add_group_quota_name_arg(usages_parser)
    usages_parser.add_argument('--location', type=str, required=True, help='Azure region (e.g. eastus)')
    usages_parser.set_defaults(func=usages)

    # register-providers
    reg_parser = subparsers.add_parser('register-providers', help='Register Microsoft.Quota + Microsoft.Compute on subscriptions')
    reg_parser.add_argument('--subscription-ids', type=str, required=True, help='Comma-separated list of subscription IDs')
    reg_parser.set_defaults(func=register_providers)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
