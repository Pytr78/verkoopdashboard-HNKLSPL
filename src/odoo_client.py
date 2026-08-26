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


def fetch_lonen_bankafschriften() -> list:
    uid = get_uid()
    models = get_models()
    return models.execute_kw(
        ODOO_DB, uid, ODOO_PASSWORD,
        "account.bank.statement.line", "search_read",
        [[["payment_ref", "ilike", "/A/"]]],
        {"fields": ["id", "date", "partner_name", "payment_ref", "amount", "journal_id"]}
    )


def fetch_personeelskosten() -> list:
    uid = get_uid()
    models = get_models()

    accounts = models.execute_kw(
        ODOO_DB, uid, ODOO_PASSWORD,
        "account.account", "search_read",
        [["|", ["name", "ilike", "te betalen lon"], ["name", "ilike", "te betalen bezoldiging"]]],
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
        {"fields": ["id", "date", "name", "ref", "partner_id", "debit", "credit",
                    "account_id", "move_id", "journal_id", "statement_line_id"]}
    )

    # Haal bankafschriftregels op voor counterpartyName en communicatie
    try:
        stmt_ids = list({l["statement_line_id"][0] for l in lines
                         if isinstance(l.get("statement_line_id"), list)})
        stmt_map = {}
        if stmt_ids:
            stmts = models.execute_kw(
                ODOO_DB, uid, ODOO_PASSWORD,
                "account.bank.statement.line", "search_read",
                [[["id", "in", stmt_ids]]],
                {"fields": ["id", "partner_name", "payment_ref", "narration"]}
            )
            stmt_map = {s["id"]: s for s in stmts}
        for line in lines:
            stmt_id = line["statement_line_id"][0] if isinstance(line.get("statement_line_id"), list) else None
            s = stmt_map.get(stmt_id, {})
            line["bank_partner_name"] = s.get("partner_name") or ""
            line["bank_payment_ref"] = s.get("payment_ref") or ""
            line["bank_narration"] = s.get("narration") or ""
    except Exception:
        for line in lines:
            line["bank_partner_name"] = ""
            line["bank_payment_ref"] = ""
            line["bank_narration"] = ""

    return lines


FREELANCER_PARTNER_IDS = [4682, 4858, 4909, 5305]  # Atipica, Cold Mountain, De Cock Gert, Kroketje

# Odoo product category IDs voor eigen productie, per merk
EIGEN_PRODUCTIE_CATEGORIEEN = {
    64: ("Cabriogand",       "Geitenmelk"),
    65: ("Cabriolait",       "Geitenmelk"),
    66: ("Pas de bleu Geit", "Geitenmelk"),
    71: ("Bellie",           "Koemelk"),
    72: ("Dulses",           "Koemelk"),
    73: ("Herbie",           "Koemelk"),
    74: ("Pas de bleu",      "Koemelk"),
    75: ("Pas de rouge",     "Koemelk"),
}

def fetch_leveranciersfacturen() -> list:
    uid = get_uid()
    models = get_models()
    return models.execute_kw(
        ODOO_DB, uid, ODOO_PASSWORD,
        "account.move", "search_read",
        [[
            ["move_type", "=", "in_invoice"],
            ["state", "=", "posted"],
            ["partner_id", "in", FREELANCER_PARTNER_IDS],
        ]],
        {
            "fields": ["name", "partner_id", "invoice_date", "amount_untaxed"],
            "order": "invoice_date asc",
        }
    )


def fetch_omzet_eigen_productie() -> list:
    uid = get_uid()
    models = get_models()

    cat_ids = list(EIGEN_PRODUCTIE_CATEGORIEEN.keys())

    templates = models.execute_kw(
        ODOO_DB, uid, ODOO_PASSWORD,
        "product.template", "search_read",
        [[["categ_id", "in", cat_ids]]],
        {"fields": ["id", "categ_id"]}
    )
    tmpl_cat = {t["id"]: t["categ_id"][0] for t in templates}

    variants = models.execute_kw(
        ODOO_DB, uid, ODOO_PASSWORD,
        "product.product", "search_read",
        [[["product_tmpl_id", "in", list(tmpl_cat.keys())]]],
        {"fields": ["id", "product_tmpl_id"]}
    )
    variant_cat = {
        v["id"]: tmpl_cat[v["product_tmpl_id"][0]]
        for v in variants
        if isinstance(v["product_tmpl_id"], list) and v["product_tmpl_id"][0] in tmpl_cat
    }

    if not variant_cat:
        return []

    lines = models.execute_kw(
        ODOO_DB, uid, ODOO_PASSWORD,
        "account.move.line", "search_read",
        [[
            ["product_id", "in", list(variant_cat.keys())],
            ["move_id.move_type", "=", "out_invoice"],
            ["move_id.state", "=", "posted"],
        ]],
        {"fields": ["id", "product_id", "price_subtotal", "date"]}
    )

    for line in lines:
        prod_id = line["product_id"][0] if isinstance(line["product_id"], list) else None
        cat_id = variant_cat.get(prod_id)
        merk, hogere_cat = EIGEN_PRODUCTIE_CATEGORIEEN.get(cat_id, ("Onbekend", "Onbekend"))
        line["merk"] = merk
        line["hogere_categorie"] = hogere_cat

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
