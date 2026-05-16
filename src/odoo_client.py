import xmlrpc.client
import os
from dotenv import load_dotenv

load_dotenv()

ODOO_URL = os.getenv("ODOO_URL")
ODOO_DB = os.getenv("ODOO_DB")
ODOO_USERNAME = os.getenv("ODOO_USERNAME")
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD")


def get_uid():
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
    return common.authenticate(ODOO_DB, ODOO_USERNAME, ODOO_PASSWORD, {})


def get_models():
    return xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")


def fetch_invoices():
    uid = get_uid()
    models = get_models()

    invoices = models.execute_kw(
        ODOO_DB, uid, ODOO_PASSWORD,
        "account.move", "search_read",
        [[
            ["move_type", "=", "out_invoice"],
            ["state", "=", "posted"],
        ]],
        {
            "fields": [
                "name", "partner_id", "commercial_partner_id",
                "invoice_date", "amount_untaxed", "state"
            ],
            "order": "invoice_date asc",
        }
    )
    return invoices


def fetch_partner_emails(partner_ids: list) -> dict:
    uid = get_uid()
    models = get_models()

    partners = models.execute_kw(
        ODOO_DB, uid, ODOO_PASSWORD,
        "res.partner", "search_read",
        [[["id", "in", partner_ids]]],
        {"fields": ["id", "name", "email"]}
    )
    return {p["id"]: p.get("email") or "" for p in partners}
