import xmlrpc.client
import os
from dotenv import load_dotenv
import streamlit as st

load_dotenv()

def _get_secret(key: str) -> str:
    try:
        return st.secrets["odoo"][key]
    except (KeyError, AttributeError):
        return os.getenv(key)

ODOO_URL = _get_secret("ODOO_URL")
ODOO_DB = _get_secret("ODOO_DB")
ODOO_USERNAME = _get_secret("ODOO_USERNAME")
ODOO_PASSWORD = _get_secret("ODOO_PASSWORD")


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
