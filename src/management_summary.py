import pandas as pd
import numpy as np
from datetime import timedelta


def _bereken_trend(df: pd.DataFrame, drempel_pct: float = 10.0) -> pd.DataFrame:
    """Berekent de lineaire trend (helling) per klant over alle beschikbare maanden."""
    maand_df = (
        df.groupby(["partner_name", "maand"])["omzet"]
        .sum()
        .reset_index()
    )

    resultaten = []
    for partner, groep in maand_df.groupby("partner_name"):
        if len(groep) < 2:
            continue
        groep = groep.sort_values("maand")
        x = np.arange(len(groep))
        y = groep["omzet"].values
        slope, _ = np.polyfit(x, y, 1)
        gemiddeld = y.mean()
        slope_pct = (slope / gemiddeld * 100) if gemiddeld > 0 else 0
        resultaten.append({
            "partner_name": partner,
            "slope": slope,
            "slope_pct": slope_pct,
            "gemiddeld_per_maand": gemiddeld,
            "aantal_maanden": len(groep),
        })

    trend_df = pd.DataFrame(resultaten).set_index("partner_name")
    dalers = trend_df[trend_df["slope_pct"] < -drempel_pct].sort_values("slope_pct")
    stijgers = trend_df[trend_df["slope_pct"] > drempel_pct].sort_values("slope_pct", ascending=False)
    return trend_df, dalers, stijgers


def bereken_samenvatting(df: pd.DataFrame, drempel_trend_pct: float = 10.0, inactief_dagen: int = 90) -> dict:
    vandaag = pd.Timestamp.now().normalize()

    trend_df, dalers, stijgers = _bereken_trend(df, drempel_pct=drempel_trend_pct)

    # Inactieve klanten: ooit gefactureerd maar niet in laatste X dagen
    grens_inactief = vandaag - timedelta(days=inactief_dagen)
    recent_actief = set(df[df["invoice_date"] >= grens_inactief]["partner_name"].unique())
    ooit_actief = set(df[df["invoice_date"] < grens_inactief]["partner_name"].unique())
    inactief = sorted(ooit_actief - recent_actief)

    # Concentratierisico: top 3 klanten
    totaal_omzet = df["omzet"].sum()
    omzet_per_partner = df.groupby("partner_name")["omzet"].sum().sort_values(ascending=False)
    top3 = omzet_per_partner.head(3)
    concentratie_pct = (top3.sum() / totaal_omzet * 100) if totaal_omzet > 0 else 0

    return {
        "dalers": dalers,
        "stijgers": stijgers,
        "trend_df": trend_df,
        "inactief": inactief,
        "concentratie_pct": concentratie_pct,
        "top3": top3,
        "totaal_omzet": totaal_omzet,
    }
