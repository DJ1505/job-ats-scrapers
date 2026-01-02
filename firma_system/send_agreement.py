#!/usr/bin/env python3
"""
Send Agreement Using Template

This script sends an agreement to a client using a pre-created template.
The template defines which fields are filled by API vs client.
Client receives email to fill their required fields and sign.

NOTE: Updated to use Firma.dev's correct API structure with signing requests.
"""

import os
import requests
import json
from datetime import datetime

def send_agreement(template_id, client_email, api_fields):
    """
    Send agreement for client signature using existing template
    
    Args:
        template_id: ID of template created via create_template.py
        client_email: Email address where signing invitation will be sent
        api_fields: Dictionary containing API-prefilled field values
    """
    
    # Get API key from environment variable (never hardcode secrets)
    api_key = os.getenv("FIRMA_API_KEY")
    if not api_key:
        print("ERROR: FIRMA_API_KEY environment variable not set")
        print("Set it with: export FIRMA_API_KEY=your_api_key")
        return None
    
    # Correct API endpoint for Firma.dev signing requests
    url = "https://api.firma.dev/functions/v1/signing-request-api/signing-requests"
    
    # Headers with authentication (Firma.dev uses API key directly, no Bearer prefix needed)
    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json"
    }
    
    # Split client name into first and last name
    client_name_parts = api_fields.get('client_name', 'Valued Client').split()
    first_name = client_name_parts[0] if client_name_parts else "Valued"
    last_name = " ".join(client_name_parts[1:]) if len(client_name_parts) > 1 else "Client"
    
    # Signing request data according to Firma.dev API specification
    signing_request_data = {
        "name": f"Service Agreement - {api_fields.get('client_name', 'Client')}",
        "description": f"Service agreement for {api_fields.get('client_name', 'Client')} with agreement ID: {api_fields.get('agreement_id', 'N/A')}",
        "template_id": template_id,
        "expiration_hours": 168,  # 7 days
        "recipients": [
            {
                "id": "temp_1",  # Temporary ID pattern required by Firma.dev
                "first_name": first_name,
                "last_name": last_name,
                "email": client_email,
                "role": "signer"
            }
        ],
        "settings": {
            "allow_download": True,
            "attach_pdf_on_finish": True,
            "allow_editing_before_sending": False,
            "send_signing_email": True,
            "send_finish_email": True,
            "send_expiration_email": True,
            "send_cancellation_email": True
        }
    }
    
    try:
        print(f"Sending agreement to {client_email}...")
        response = requests.post(url, headers=headers, json=signing_request_data)
        
        # Check if request was successful
        if response.status_code == 201:
            signing_request_result = response.json()
            signing_request_id = signing_request_result.get("id")
            print(f"✅ Agreement sent successfully!")
            print(f"Signing Request ID: {signing_request_id}")
            print(f"Client Email: {client_email}")
            print(f"Template Used: {template_id}")
            print(f"Status: {signing_request_result.get('status', 'not_sent')}")
            
            # Send the signing request (separate API call)
            send_url = f"https://api.firma.dev/functions/v1/signing-request-api/signing-requests/{signing_request_id}/send"
            send_response = requests.post(send_url, headers=headers)
            
            if send_response.status_code == 200:
                print(f"✅ Signing request sent to client!")
                return signing_request_id
            else:
                print(f"⚠️  Signing request created but failed to send: {send_response.text}")
                return signing_request_id
        else:
            print(f"❌ Failed to send agreement")
            print(f"Status Code: {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Network error occurred: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"❌ Failed to parse response: {e}")
        return None

def main():
    """
    Example usage with sample data
    In production, you'd get these values from your application/database
    """
    
    # Template ID from create_template.py output
    template_id = input("Enter template ID: ").strip()
    if not template_id:
        print("ERROR: Template ID is required")
        return
    
    # Client email for signing invitation
    client_email = input("Enter client email: ").strip()
    if not client_email or "@" not in client_email:
        print("ERROR: Valid client email is required")
        return
    
    # API-filled fields (these will be prefilled and read-only for client)
    api_fields = {
        "agreement_id": input("Enter agreement ID (or press Enter for auto-generated): ").strip() or f"AGR-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "company_name": input("Enter company name: ").strip() or "Your Company Name",
        "service_plan": input("Enter service plan: ").strip() or "Standard Plan",
        "pricing": input("Enter pricing: ").strip() or "$999/month",
        "start_date": input("Enter start date (YYYY-MM-DD): ").strip() or datetime.now().strftime('%Y-%m-%d'),
        "client_name": input("Enter client name: ").strip() or "Valued Client"
    }
    
    # Calculate end date if not provided (1 year from start)
    if not api_fields.get('end_date'):
        try:
            start_dt = datetime.strptime(api_fields['start_date'], '%Y-%m-%d')
            api_fields['end_date'] = start_dt.replace(year=start_dt.year + 1).strftime('%Y-%m-%d')
        except ValueError:
            api_fields['end_date'] = datetime.now().replace(year=datetime.now().year + 1).strftime('%Y-%m-%d')
    
    # Send the agreement
    signing_request_id = send_agreement(template_id, client_email, api_fields)
    
    if signing_request_id:
        print(f"\n🎉 Success! Agreement sent for signature.")
        print(f"📧 Client will receive email at: {client_email}")
        print(f"📋 Track progress with Signing Request ID: {signing_request_id}")
        print(f"📄 Agreement ID: {api_fields['agreement_id']}")
        print(f"🔗 Client can sign at: https://app.firma.dev/signing/{signing_request_id}")
    else:
        print("\n❌ Failed to send agreement. Check your API key and template ID.")

if __name__ == "__main__":
    main()
