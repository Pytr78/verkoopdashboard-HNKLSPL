import pandas as pd


def invoices_to_dataframe(invoices: list, partner_emails: dict = None, partner_labels: dict = None) -> pd.DataFrame:
    if not invoices:
        return pd.DataFrame()

    df = pd.DataFrame(invoices)
    df["partner_id_int"] = df["partner_id"].apply(lambda x: x[0] if isinstance(x, list) else x)
    df["commercial_partner_id_int"] = df["commercial_partner_id"].apply(lambda x: x[0] if isinstance(x, list) else x)
    df["partner_name"] = df["commercial_partner_id"].apply(
        lambda x: x[1] if isinstance(x, list) else None
    ).fillna(df["partner_id"].apply(lambda x: x[1] if isinstance(x, list) else x))
    if partner_emails:
        df["email"] = df["commercial_partner_id_int"].map(partner_emails).fillna(
            df["partner_id_int"].map(partner_emails)
        ).fillna("")
    else:
        df["email"] = ""
    if partner_labels:
        df["labels"] = df["commercial_partner_id_int"].map(partner_labels).fillna(
            df["partner_id_int"].map(partner_labels)
        ).apply(lambda x: x if isinstance(x, list) else [])
    else:
        df["labels"] = [[] for _ in range(len(df))]
    df["invoice_date"] = pd.to_datetime(df["invoice_date"])
    df["jaar"] = df["invoice_date"].dt.year
    df["maand"] = df["invoice_date"].dt.to_period("M").astype(str)
    df = df.rename(columns={"amount_untaxed": "omzet", "amount_residual": "openstaand"})
    df["invoice_date_due"] = pd.to_datetime(df["invoice_date_due"], errors="coerce")
    return df[["id", "name", "partner_name", "email", "labels", "invoice_date", "invoice_date_due",
               "jaar", "maand", "omzet", "openstaand", "payment_state",
               "partner_id_int", "commercial_partner_id_int"]]



def omzet_per_partner_per_maand(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.groupby(["partner_name", "maand"])["omzet"]
        .sum()
        .reset_index()
        .sort_values("maand")
    )


def omzet_per_partner_totaal(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.groupby("partner_name")["omzet"]
        .sum()
        .reset_index()
        .sort_values("omzet", ascending=False)
    )
