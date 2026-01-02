# Firma.dev Agreement Signing System

An end-to-end API-based agreement signing system using Firma.dev e-signature platform.

## Why Firma.dev UI Looks Empty

Firma.dev dashboard is intentionally minimal - it only provides:
- API key management
- Credit balance viewing
- Basic envelope tracking

**Template creation is API-only** - this is by design to enable programmatic template management at scale.

## Why Templates Are API-Created

Templates must be created via API because:
1. **Programmatic Control**: Templates can be generated dynamically based on business logic
2. **Version Management**: API allows automated template updates and versioning
3. **Integration**: Templates can be created as part of your application workflow
4. **Scalability**: Bulk template creation without manual UI interaction

## Quick Start

### 1. Set API Key
```bash
# Set your Firma.dev API key
export FIRMA_API_KEY=your_api_key_here
```

### 2. Create Template
```bash
# Create the agreement template
python create_template.py
```
**Output**: Template ID (save this for next step)

### 3. Send Agreement
```bash
# Send agreement to client
python send_agreement.py
```
**Prompts for**: Template ID, client email, and company details

## High-Level Flow

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│ create_template │───▶│ Firma.dev API    │───▶│ Template ID     │
│ .py             │    │ (POST /templates)│    │ (saved)         │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                                        │
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│ send_agreement  │───▶│ Firma.dev API    │───▶│ Email to Client │
│ .py             │    │ (POST /envelopes)│    │ (signing link)  │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## Template Field Types

### Client-Filled Fields (Required & Editable)
- `client_name`: Client's full name
- `client_address`: Client's address
- `sign_date`: Date of signature
- `client_signature`: Digital signature

### API-Filled Fields (Prefilled & Read-Only)
- `agreement_id`: Unique agreement identifier
- `company_name`: Your company name
- `service_plan`: Service plan description
- `pricing`: Pricing information
- `start_date`: Service start date
- `end_date`: Service end date

## File Structure

```
├── create_template.py    # Creates reusable agreement template
├── send_agreement.py     # Sends agreements using template
└── README.md             # This documentation
```

## Security Notes

- ✅ API key stored in environment variable
- ✅ No hardcoded secrets in code
- ✅ HTTPS-only API communication
- ✅ Error handling for API failures

## Error Handling

Both scripts include comprehensive error handling:
- Missing API key detection
- Network connectivity issues
- API response validation
- JSON parsing errors
- User input validation

## Next Steps

1. **Customize Template**: Modify `create_template.py` to match your agreement content
2. **Automate**: Integrate scripts into your application workflow
3. **Monitor**: Use envelope IDs to track signing progress
4. **Scale**: Create multiple templates for different agreement types

## Support

- Firma.dev API documentation: https://docs.firma.dev
- For API key issues: Check your Firma.dev dashboard
- For template errors: Verify field configurations match API requirements
