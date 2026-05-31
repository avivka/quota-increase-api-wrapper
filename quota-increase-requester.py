import csv
import requests
import argparse
from azure.identity import DefaultAzureCredential

# Reference: https://learn.microsoft.com/en-us/rest/api/quota/
#            https://learn.microsoft.com/en-us/rest/api/reserved-vm-instances/quotaapi

# Function to read CSV file
def read_csv(file_path):
    with open(file_path, mode='r') as file:
        csv_reader = csv.DictReader(file)
        # https://stackoverflow.com/questions/37240535/how-to-read-csv-file-in-python no need for delimiter
        requests_data = [row for row in csv_reader]
    return requests_data

# Function to request quota increase
def request_quota_increase(subscription_id, region, sku, amount):
    url = f"https://management.azure.com/subscriptions/{subscription_id}/providers/Microsoft.Compute/locations/{region}/usages/{sku}?api-version=2021-07-01"
    headers = {
        'Content-Type': 'application/json', 
        'Authorization': f'Bearer {get_access_token()}'
    }
    payload = {
        "properties": {
            "limit": amount
        }
    }
    response = requests.put(url, headers=headers, json=payload)
    return response.status_code, response.json()

# Function to get access token
def get_access_token():
    credential = DefaultAzureCredential()
    token = credential.get_token("https://management.azure.com/.default")
    return token.token
    # use managed identity instead of my default token

# Main function
def main():
    parser = argparse.ArgumentParser(description='Request quota increase for Azure subscriptions.')
    parser.add_argument('--subscription-ids', type=str, required=True, help='Comma-separated list of subscription IDs')
    parser.add_argument('--csv-file-path', type=str, required=True, help='Path to the CSV file containing quota requests')
    
    args = parser.parse_args()
    
    subscription_ids = args.subscription_ids.split(',')
    csv_file_path = args.csv_file_path
    
    requests_data = read_csv(csv_file_path)
    
    for subscription_id in subscription_ids:
        for data in requests_data:
            print("Data Keys:", data.keys())
            region = data['region']
            dsv5_sku = data['DSV5']
            dsv4_sku = data['DSV4']
            
            if dsv5_sku:
                status_code, response = request_quota_increase(subscription_id, region, 'DSv5', dsv5_sku)
                print(f"DSv5 Quota Increase Request for {region} (Subscription ID: {subscription_id}): Status Code: {status_code}, Response: {response}")
            
            if dsv4_sku:
                status_code, response = request_quota_increase(subscription_id, region, 'DSv4', dsv4_sku)
                print(f"DSv4 Quota Increase Request for {region} (Subscription ID: {subscription_id}): Status Code: {status_code}, Response: {response}")

if __name__ == "__main__":
    main()