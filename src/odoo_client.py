import xmlrpc.client
import os
from dotenv import load_dotenv
import streamlit as st

load_dotenv()

def _get_secret(key: str) -> str:
    try:
        return st.secrets["odoo"][key]
    except Exception:
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
                "id", "name", "partner_id", "commercial_partner_id",
                "invoice_date", "invoice_date_due", "amount_untaxed",
                "amount_residual", "payment_state", "state"
            ],
            "order": "invoice_date asc",
        }
    )
    return invoices


def fetch_betaalde_facturen():
    uid = get_uid()
    models = get_models()

    facturen = models.execute_kw(
        ODOO_DB, uid, ODOO_PASSWORD,
        "account.move", "search_read",
        [[
            ["move_type", "=", "out_invoice"],
            ["state", "=", "posted"],
            ["payment_state", "in", ["paid", "in_payment", "partial"]],
        ]],
        {
            "fields": ["id", "invoice_date", "invoice_payments_widget"],
        }
    )
    return facturen


def fetch_partner_info(partner_ids: list) -> tuple:
    uid = get_uid()
    models = get_models()

    partners = models.execute_kw(
        ODOO_DB, uid, ODOO_PASSWORD,
        "res.partner", "search_read",
        [[["id", "in", partner_ids]]],
        {"fields": ["id", "name", "email", "category_id"]}
    )
    emails = {p["id"]: p.get("email") or "" for p in partners}

    all_cat_ids = list({cat_id for p in partners for cat_id in p.get("category_id", [])})
    cat_names = {}
    if all_cat_ids:
        cats = models.execute_kw(
            ODOO_DB, uid, ODOO_PASSWORD,
            "res.partner.category", "search_read",
            [[["id", "in", all_cat_ids]]],
            {"fields": ["id", "name"]}
        )
        cat_names = {c["id"]: c["name"] for c in cats}

    labels = {
        p["id"]: [cat_names[cid] for cid in p.get("category_id", []) if cid in cat_names]
        for p in partners
    }
    return emails, labels


def fetch_partner_emails(partner_ids: list) -> dict:
    emails, _ = fetch_partner_info(partner_ids)
    return emails


def fetch_personeelskosten() -> list:
    uid = get_uid()
    models = get_models()

    lonen = "te betalen lonen"
    bezoldigingen = "te betalen bezoldigingen"
    accounts = models.execute_kw(
        ODOO_DB, uid, ODOO_PASSWORD,
        "account.account", "search_read",
        [["|", ["name", "ilike", lonen], ["name", "ilike", bezoldigingen]]],
        {"fields": ["id", "name", "code"]}
    )
    if not accounts:
        return []

    account_ids = [a["id"] for a in accounts]
    lines = models.execute_kw(
        ODOO_DB, uid, ODOO_PASSWORD,
        "account.move.line", "search_read",
        [[
            ["account_id", "in", account_ids],
            ["move_id.state", "=", "posted"],
        ]],
        {"fields": ["id", "date", "name", "partner_id", "debit", "credit", "account_id", "move_id"]}
    )
    return lines


def fetch_employees() -> list:
    uid = get_uid()
    models = get_models()
    return models.execute_kw(
        ODOO_DB, uid, ODOO_PASSWORD,
        "hr.employee", "search_read",
        [[["active", "=", True]]],
        {"fields": ["id", "name", "job_id", "job_title", "department_id"]}
    )


def fetch_payslips() -> list:
    uid = get_uid()
    models = get_models()
    return models.execute_kw(
        ODOO_DB, uid, ODOO_PASSWORD,
        "hr.payslip", "search_read",
        [[["state", "in", ["done", "paid"]]]],
        {"fields": ["id", "employee_id", "date_from", "date_to", "net_wage", "basic_wage"]}
    )
