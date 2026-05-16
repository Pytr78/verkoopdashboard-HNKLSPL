import pandas as pd


SEGMENTEN = {
    "Champion":        {"kleur": "#2ecc71", "omschrijving": "Actief, frequent, hoge omzet"},
    "Trouwe klant":    {"kleur": "#27ae60", "omschrijving": "Frequent en hoge omzet"},
    "Veelbelovend":    {"kleur": "#3498db", "omschrijving": "Recent actief, groeiende frequentie"},
    "Risicovol":       {"kleur": "#e67e22", "omschrijving": "Vroeger frequent, nu minder actief"},
    "Niet verliezen":  {"kleur": "#e74c3c", "omschrijving": "Hoge omzet maar dreigt weg te vallen"},
    "Slapend":         {"kleur": "#95a5a6", "omschrijving": "Weinig actief en lage omzet"},
    "Nieuw":           {"kleur": "#9b59b6", "omschrijving": "Recente eerste aankoop"},
}


def _kwartiel_score(serie: pd.Series, omgekeerd: bool = False) -> pd.Series:
    """Scoort een serie in kwartielgroepen 1-4."""
    labels = [4, 3, 2, 1] if omgekeerd else [1, 2, 3, 4]
    return pd.qcut(serie.rank(method="first"), q=4, labels=labels).astype(int)


def _bepaal_segment(r: int, f: int, m: int) -> str:
    if r >= 4 and f >= 3 and m >= 3:
        return "Champion"
    if f >= 3 and m >= 3:
        return "Trouwe klant"
    if r >= 4 and f == 1:
        return "Nieuw"
    if r >= 3 and f >= 2:
        return "Veelbelovend"
    if r <= 2 and m >= 3:
        return "Niet verliezen"
    if r <= 2 and f >= 3:
        return "Risicovol"
    return "Slapend"


def bereken_rfm(df: pd.DataFrame) -> pd.DataFrame:
    vandaag = pd.Timestamp.now().normalize()

    rfm = df.groupby("partner_name").agg(
        laatste_factuur=("invoice_date", "max"),
        aantal_facturen=("name", "count"),
        totaal_omzet=("omzet", "sum"),
        email=("email", "first"),
    ).reset_index()

    rfm["recency_dagen"] = (vandaag - rfm["laatste_factuur"]).dt.days

    rfm["R"] = _kwartiel_score(rfm["recency_dagen"], omgekeerd=True)
    rfm["F"] = _kwartiel_score(rfm["aantal_facturen"])
    rfm["M"] = _kwartiel_score(rfm["totaal_omzet"])
    rfm["RFM_score"] = rfm["R"].astype(str) + rfm["F"].astype(str) + rfm["M"].astype(str)

    rfm["segment"] = rfm.apply(lambda r: _bepaal_segment(r["R"], r["F"], r["M"]), axis=1)

    return rfm[[
        "partner_name", "email", "segment", "RFM_score",
        "R", "F", "M", "recency_dagen", "aantal_facturen", "totaal_omzet"
    ]].sort_values(["segment", "totaal_omzet"], ascending=[True, False])
