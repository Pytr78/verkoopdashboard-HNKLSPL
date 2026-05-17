import pandas as pd


BUCKETS = [
    ("0–30 dagen",   0,  30),
    ("31–60 dagen", 31,  60),
    ("61–90 dagen", 61,  90),
    ("> 90 dagen",  91, 9999),
]


def bereken_cashflow_prognose(df: pd.DataFrame, betaal_analyse: pd.DataFrame) -> pd.DataFrame:
    vandaag = pd.Timestamp.now().normalize()

    openstaand = df[df["payment_state"].isin(["not_paid", "partial"])].copy()
    if openstaand.empty:
        return pd.DataFrame()

    betaal_lookup = (
        betaal_analyse.set_index("partner_name")["gem_betaaldagen"].to_dict()
        if not betaal_analyse.empty else {}
    )

    def _verwachte_datum(row):
        gem = betaal_lookup.get(row["partner_name"])
        if gem and not pd.isna(gem):
            verwacht = row["invoice_date"] + pd.Timedelta(days=int(gem))
        elif pd.notna(row.get("invoice_date_due")):
            verwacht = row["invoice_date_due"]
        else:
            verwacht = vandaag + pd.Timedelta(days=30)
        return max(verwacht, vandaag)

    openstaand["verwachte_betaaldatum"] = openstaand.apply(_verwachte_datum, axis=1)
    openstaand["dagen_tot_betaling"] = (openstaand["verwachte_betaaldatum"] - vandaag).dt.days

    def _bucket(dagen):
        for label, lo, hi in BUCKETS:
            if lo <= dagen <= hi:
                return label
        return "> 90 dagen"

    openstaand["periode"] = openstaand["dagen_tot_betaling"].apply(_bucket)
    openstaand["bron"] = openstaand["partner_name"].apply(
        lambda p: "historisch gemiddelde" if p in betaal_lookup else "vervaldatum"
    )

    return openstaand[[
        "name", "partner_name", "email", "invoice_date", "invoice_date_due",
        "openstaand", "verwachte_betaaldatum", "dagen_tot_betaling", "periode", "bron",
    ]]


def cashflow_per_periode(prognose_df: pd.DataFrame) -> pd.DataFrame:
    volgorde = [b[0] for b in BUCKETS]
    return (
        prognose_df.groupby("periode")["openstaand"]
        .sum()
        .reindex(volgorde)
        .fillna(0)
        .reset_index()
        .rename(columns={"openstaand": "verwacht_bedrag"})
    )