# api/mpesa_api.py

import requests
import base64
from datetime import datetime
from django.conf import settings
from django.core.cache import cache 

def get_mpesa_access_token():
    """
    Fetches M-Pesa access token and caches it.
    """
    cached_token = cache.get('mpesa_access_token')
    if cached_token:
        return cached_token

    if settings.MPESA_ENVIRONMENT == 'production':
        url = 'https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials'
    else:
        url = 'https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials'

    try:
        response = requests.get(url, auth=(settings.MPESA_CONSUMER_KEY, settings.MPESA_CONSUMER_SECRET), timeout=10)
        response.raise_for_status() 
    except requests.exceptions.RequestException as e:
        print(f"Error getting access token: {e}")
        return None

    try:
        token = response.json()['access_token']
        cache.set('mpesa_access_token', token, timeout=3500) # Cache for just under an hour
        return token
    except KeyError:
        print("Could not find 'access_token' in the response.")
        return None

# --- THIS IS THE CORRECTED FUNCTION ---
# It now correctly accepts the 'transaction_desc' argument
def initiate_stk_push(phone_number, amount, order_id, transaction_desc):
    """Initiates a secure and robust STK push request."""
    access_token = get_mpesa_access_token()
    if not access_token:
        return {'error': 'Could not obtain access token.'}

    if settings.MPESA_ENVIRONMENT == 'production':
        process_request_url = 'https://api.safaricom.co.ke/mpesa/stkpush/v1/processrequest'
    else:
        process_request_url = 'https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest'

    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    password = base64.b64encode((settings.MPESA_SHORTCODE + settings.MPESA_PASSKEY + timestamp).encode()).decode()

    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }

    payload = {
        'BusinessShortCode': settings.MPESA_SHORTCODE,
        'Password': password,
        'Timestamp': timestamp,
        'TransactionType': settings.MPESA_TRANSACTION_TYPE,
        'Amount': str(amount),
        'PartyA': phone_number,
        'PartyB': settings.MPESA_SHORTCODE,
        'PhoneNumber': phone_number,
        'CallBackURL': settings.MPESA_CALLBACK_URL,
        'AccountReference': str(order_id),  
        'TransactionDesc': transaction_desc # Using the custom description
    }

    print("--- SENDING PAYLOAD TO M-PESA ---")
    print(payload)
    print("---------------------------------")

    try:
        response = requests.post(process_request_url, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"M-Pesa request failed. Status Code: {e.response.status_code if e.response else 'N/A'}")
        print(f"Response Body: {e.response.text if e.response else 'No response body'}")
        return {'error': 'Request to M-Pesa failed.', 'details': str(e)}
