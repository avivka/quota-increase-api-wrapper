import time
import requests
import argparse
from azure.identity import DefaultAzureCredential

# Reference: https://learn.microsoft.com/en-us/rest/api/quota/group-quotas
#            https://learn.microsoft.com/en-us/azure/quotas/quota-groups

DEFAULT_API_VERSION = "2025-03-01"
MGMT_BASE_URL = "https://management.azure.com"
POLL_INTERVAL_SECONDS = 5
POLL_MAX_ATTEMPTS = 60


def get_access_token():
    credential = DefaultAzureCredential()
    token = credential.get_token("https://management.azure.com/.default")
    return token.token


def build_headers():
    return {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {get_access_token()}'
    }


def poll_async_operation(async_url):
    """Poll an Azure async operation URL until it reaches a terminal state."""
    headers = build_headers()
    for attempt in range(POLL_MAX_ATTEMPTS):
        response = requests.get(async_url, headers=headers)
        if response.status_code != 200:
            print(f"Polling error: Status {response.status_code}, Response: {response.text}")
            return response.status_code, response.json() if response.text else {}

        result = response.json()
        status = result.get("status", "").lower()
        print(f"  Poll attempt {attempt + 1}: status = {result.get('status', 'unknown')}")

        if status in ("succeeded", "failed", "canceled", "cancelled"):
            return response.status_code, result

        time.sleep(POLL_INTERVAL_SECONDS)

    print("Polling timed out.")
    return 408, {"error": "Polling timed out after max attempts"}


def make_request(method, url, payload=None):
    """Execute an HTTP request and handle 202 async polling."""
    headers = build_headers()

    if method.upper() == "GET":
        response = requests.get(url, headers=headers)
    elif method.upper() == "PUT":
        response = requests.put(url, headers=headers, json=payload)
    elif method.upper() == "PATCH":
        response = requests.patch(url, headers=headers, json=payload)
    elif method.upper() == "DELETE":
        response = requests.delete(url, headers=headers)
    else:
        raise ValueError(f"Unsupported HTTP method: {method}")

    status_code = response.status_code
    response_body = response.json() if response.text else {}

    if status_code == 202:
        async_url = response.headers.get("Azure-AsyncOperation")
        if async_url:
            print(f"Accepted (202). Polling async operation...")
            return poll_async_operation(async_url)
        else:
            print("Accepted (202) but no Azure-AsyncOperation header found.")

    return status_code, response_body


def build_group_quota_base_url(management_group_id, api_version):
    return (
        f"{MGMT_BASE_URL}/providers/Microsoft.Management"
        f"/managementGroups/{management_group_id}"
        f"/providers/Microsoft.Quota/groupQuotas"
    )


def add_common_args(parser):
    parser.add_argument(
        '--management-group-id', type=str, required=True,
        help='Management group ID'
    )
    parser.add_argument(
        '--api-version', type=str, default=DEFAULT_API_VERSION,
        help=f'API version (default: {DEFAULT_API_VERSION})'
    )


def add_group_quota_name_arg(parser):
    parser.add_argument(
        '--group-quota-name', type=str, required=True,
        help='Name of the group quota'
    )


def list_group_subscriptions(management_group_id, group_quota_name, api_version=DEFAULT_API_VERSION):
    """List all subscription IDs enrolled in a group quota."""
    url = (
        f"{MGMT_BASE_URL}/providers/Microsoft.Management"
        f"/managementGroups/{management_group_id}"
        f"/providers/Microsoft.Quota/groupQuotas/{group_quota_name}"
        f"/subscriptions?api-version={api_version}"
    )
    status_code, response = make_request("GET", url)
    if status_code != 200:
        print(f"Failed to list group subscriptions: Status {status_code}, Response: {response}")
        return []
    return [
        entry["properties"]["subscriptionId"]
        for entry in response.get("value", [])
    ]


def get_compute_usage(subscription_id, location, resource_name):
    """Get current usage and limit for a specific compute resource in a subscription."""
    url = (
        f"{MGMT_BASE_URL}/subscriptions/{subscription_id}"
        f"/providers/Microsoft.Compute/locations/{location}"
        f"/usages?api-version=2024-07-01"
    )
    status_code, response = make_request("GET", url)
    if status_code != 200:
        print(f"Failed to get compute usage for {subscription_id}: Status {status_code}, Response: {response}")
        return None
    for entry in response.get("value", []):
        if entry.get("name", {}).get("value", "").lower() == resource_name.lower():
            return (entry["currentValue"], entry["limit"])
    print(f"Resource '{resource_name}' not found in usage data for subscription {subscription_id}")
    return None
