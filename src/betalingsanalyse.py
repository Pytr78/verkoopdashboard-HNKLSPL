import pandas as pd


CATEGORIEEN = [
    ("🟢 Uitstekend", 15),
    ("🔵 Goed",        30),
    ("🟡 Matig",       60),
    ("🔴 Slecht",      9999),
]


def _categorie(dagen: float) -> str:
    for naam, max_d in CATEGORIEEN:
        if dagen <= max_d:
            return naam
    return "🔴 Slecht"


def bereken_betaaldagen(invoices_df: pd.DataFrame, betaalde_facturen: list) -> pd.DataFrame:
    if not betaalde_facturen:
        return pd.DataFrame()

    rijen = []
    for f in betaalde_facturen:
        widget = f.get("invoice_payments_widget")
        if not widget or not isinstance(widget, dict):
            continue
        invoice_date = pd.to_datetime(f["invoice_date"])
        for betaling in widget.get("content", []):
            betaaldatum = pd.to_datetime(betaling.get("date"))
            if betaaldatum and not betaling.get("is_refund") and not betaling.get("is_exchange"):
                rijen.append({
                    "id": f["id"],
                    "invoice_date": invoice_date,
                    "betaaldatum": betaaldatum,
                })
                break  # eerste betaling is voldoende

    if not rijen:
        return pd.DataFrame()

    betaal_df = pd.DataFrame(rijen)
    betaal_df["betaaldagen"] = (betaal_df["betaaldatum"] - betaal_df["invoice_date"]).dt.days.clip(lower=0)

    # Koppel aan partner via invoice ID
    partner_info = invoices_df[["id", "partner_name", "email"]].drop_duplicates("id")
    merged = betaal_df.merge(partner_info, on="id", how="inner")

    if merged.empty:
        return pd.DataFrame()

    resultaat = (
        merged.groupby("partner_name")
        .agg(
            gem_betaaldagen=("betaaldagen", "mean"),
            max_betaaldagen=("betaaldagen", "max"),
            aantal_betaald=("betaaldagen", "count"),
            email=("email", "first"),
        )
        .reset_index()
        .sort_values("gem_betaaldagen", ascending=False)
    )

    resultaat["categorie"] = resultaat["gem_betaaldagen"].apply(_categorie)
    resultaat["gem_betaaldagen"] = resultaat["gem_betaaldagen"].round(1)
    resultaat["max_betaaldagen"] = resultaat["max_betaaldagen"].round(0).astype(int)

    return resultaat
