#!/usr/bin/env python3
"""
Create Agreement Template for Firma.dev

This script creates a template via API since Firma.dev dashboard doesn't support template creation.
Templates are reusable agreement structures that define which fields clients fill vs API prefills.

NOTE: Firma.dev requires a base64-encoded PDF document for template creation.
This script creates a simple PDF and encodes it for the API.
"""

import os
import requests
import json
import base64
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from io import BytesIO

def create_pdf_document():
    """
    Create a simple PDF document with placeholders for the agreement.
    This PDF will be used as the base document for the template.
    """
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    
    # Add content to PDF
    p.setFont("Helvetica-Bold", 16)
    p.drawString(100, 750, "CLIENT SERVICE AGREEMENT")
    
    p.setFont("Helvetica", 12)
    p.drawString(100, 700, "This agreement is made between:")
    p.drawString(100, 680, "Company: {{company_name}}")
    p.drawString(100, 660, "Client: {{client_name}}")
    
    p.drawString(100, 620, "Client Information:")
    p.drawString(100, 600, "Name: {{client_name}}")
    p.drawString(100, 580, "Address: {{client_address}}")
    p.drawString(100, 560, "Date: {{sign_date}}")
    
    p.drawString(100, 520, "Service Details:")
    p.drawString(100, 500, "Agreement ID: {{agreement_id}}")
    p.drawString(100, 480, "Service Plan: {{service_plan}}")
    p.drawString(100, 460, "Pricing: {{pricing}}")
    p.drawString(100, 440, "Service Period: {{start_date}} to {{end_date}}")
    
    p.drawString(100, 380, "Client Signature: {{client_signature}}")
    
    p.drawString(100, 320, "By signing below, the Client agrees to the terms")
    p.drawString(100, 300, "outlined in this agreement.")
    
    p.save()
    
    # Get PDF bytes and encode to base64
    pdf_bytes = buffer.getvalue()
    buffer.close()
    base64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
    
    return base64_pdf

def create_template():
    """
    Create a new agreement template on Firma.dev
    
    Template structure:
    - Client-filled fields: required, editable (client_name, client_address, sign_date, client_signature)
    - API-filled fields: prefilled, read-only (agreement_id, company_name, service_plan, pricing, start_date, end_date)
    """
    
    # Get API key from environment variable (never hardcode secrets)
    api_key = os.getenv("FIRMA_API_KEY")
    if not api_key:
        print("ERROR: FIRMA_API_KEY environment variable not set")
        print("Set it with: export FIRMA_API_KEY=your_api_key")
        return None
    
    # Create PDF document for template
    print("Creating PDF document...")
    base64_pdf = create_pdf_document()
    
    # Correct API endpoint for Firma.dev
    url = "https://api.firma.dev/functions/v1/signing-request-api/templates"
    
    # Headers with authentication (Firma.dev uses API key directly, no Bearer prefix needed)
    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json"
    }
    
    # Template data according to Firma.dev API specification
    template_data = {
        "name": "Client Service Agreement – API",
        "description": "Standard client service agreement with API-prefilled company details",
        "document": base64_pdf,
        "expiration_hours": 168,  # 7 days
        "settings": {
            "allow_editing_before_sending": False,
            "attach_pdf_on_finish": True,
            "allow_download": True
        }
    }
    
    try:
        print("Creating template...")
        response = requests.post(url, headers=headers, json=template_data)
        
        # Check if request was successful
        if response.status_code == 201:
            template_result = response.json()
            template_id = template_result.get("id")
            print(f"✅ Template created successfully!")
            print(f"Template ID: {template_id}")
            print(f"Template Name: {template_result.get('name')}")
            return template_id
        else:
            print(f"❌ Failed to create template")
            print(f"Status Code: {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Network error occurred: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"❌ Failed to parse response: {e}")
        return None

if __name__ == "__main__":
    template_id = create_template()
    if template_id:
        print(f"\nNext step: Use this template_id ({template_id}) in send_agreement.py")
    else:
        print("\nTemplate creation failed. Check your API key and connection.")
