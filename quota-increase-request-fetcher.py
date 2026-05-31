import requests
import argparse
from azure.identity import DefaultAzureCredential
from azure.mgmt.resource import ResourceManagementClient

# Reference: https://learn.microsoft.com/en-us/rest/api/quota/
#            https://learn.microsoft.com/en-us/rest/api/reserved-vm-instances/quotaapi

def assure_provider_registration(subscription_id):
    resource_client = ResourceManagementClient(credential=DefaultAzureCredential(),subscription_id=subscription_id)
    provider_namespace = 'Microsoft.Capacity'
    provider = resource_client.providers.get(provider_namespace)
    if provider.registration_state == 'Registered':
        print(f'{provider_namespace} is registered.')
    else:
        print(f'{provider_namespace} is not registered.')
        print(f'Registering {provider_namespace}...')
        response = resource_client.providers.register(provider_namespace)
        print(f'Registration status: {response.registration_state}')

# Function to request quota increase
def get_quota_usage(subscription_id):
    url = f"https://management.azure.com/subscriptions/{subscription_id}/providers/Microsoft.Capacity/resourceProviders/Microsoft.Compute/locations/eastus/serviceLimits/standardDSv4Family?api-version=2020-10-25"
    headers = {
        'Content-Type': 'application/json', 
        'Authorization': f'Bearer {get_access_token()}'
    }
    response = requests.get(url, headers=headers)
    return response.status_code, response.json()

# Function to get access token
def get_access_token():
    credential = DefaultAzureCredential()
    token = credential.get_token("https://management.azure.com/.default")
    return token.token
    # use managed identity instead of my default token

def main():
    parser = argparse.ArgumentParser(description='Fetch quota usage for Azure subscriptions.')
    parser.add_argument('--subscription-ids', type=str, required=True, help='Comma-separated list of subscription IDs')
    
    args = parser.parse_args()
    
    subscription_ids = args.subscription_ids.split(',')
    
    for subscription_id in subscription_ids:
        status_code, response = assure_provider_registration(subscription_id)
        print(f"Assure Provider Registration for (Subscription ID: {subscription_id}): Status Code: {status_code}, Response: {response}")
        status_code, response = get_quota_usage(subscription_id)   
        print(f"DSv5 Quota Fetcher Request for eastus (Subscription ID: {subscription_id}): Status Code: {status_code}, Response: {response}")

if __name__ == "__main__":
    main()