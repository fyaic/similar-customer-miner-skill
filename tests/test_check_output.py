import pandas as pd

from scripts.check_output import check_business_fields


def test_business_fields_pass_with_minimum_live_fields():
    """A valid similar-buyer row: non-seed, has HS, website/domain, source_url,
    and a proxy note alongside estimated shipping spend."""
    df = pd.DataFrame(
        [
            {
                "company_name_value": "Acme Importers",
                "website_value": "https://acmeimporters.com",
                "shipment_frequency_value": "12 shipments (recent)",
                "hs_codes_value": "8517",
                "main_products_value": "",
                "estimated_shipping_spend_value": "Estimated shipping spend: $9,876 (not verified procurement value)",
                "procurement_proxy_notes_value": "Estimated shipping spend (BOL), not verified customs procurement value",
                "email_value": "sales@acmeimporters.com",
                "contact_name_value": "",
                "linkedin_value": "",
                "facebook_value": "",
                "company_name_citation": "https://acmeimporters.com",
                "shipment_frequency_citation": "https://acmeimporters.com",
                "main_products_citation": "",
                "hs_codes_citation": "https://acmeimporters.com",
                "all_citations": "{'source_url': 'https://acmeimporters.com'}",
            }
        ]
    )

    errors, warnings = check_business_fields(df, seed_keys={"ferguson"})

    assert errors == []


def test_business_fields_fail_when_core_live_fields_are_missing():
    df = pd.DataFrame(
        [
            {
                "company_name_value": "Ferguson",  # equals a seed -> discovery invalid
                "website_value": "",               # missing domain -> not reachable
                "shipment_frequency_value": "",
                "hs_codes_value": "",
                "main_products_value": "",
                "estimated_shipping_spend_value": "Estimated shipping spend: $1 (proxy)",
                "procurement_proxy_notes_value": "",  # spend without proxy note -> error
                "email_value": "",
                "contact_name_value": "",
                "linkedin_value": "",
                "facebook_value": "",
                "company_name_citation": "",
                "shipment_frequency_citation": "",
                "main_products_citation": "",
                "hs_codes_citation": "",
                "all_citations": "{}",
            }
        ]
    )

    errors, warnings = check_business_fields(df, seed_keys={"ferguson"})

    assert "Row 2: candidate equals seed/industry-leader (discovery invalid)" in errors
    assert "Row 2: hs_codes_value or main_products_value is required" in errors
    assert "Row 2: source_url citation is required" in errors
    assert "Row 2: website/domain is required for outreach" in errors
    assert "Row 2: estimated_shipping_spend must carry procurement_proxy_notes" in errors
