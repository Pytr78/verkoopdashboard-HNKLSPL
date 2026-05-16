import pandas as pd
from datetime import timedelta


def genereer_actiepunten(df: pd.DataFrame, samenvatting: dict, rfm_df: pd.DataFrame,
                          betaal_analyse: pd.DataFrame, doelstellingen: dict) -> list:
    acties = []
    vandaag = pd.Timestamp.now().normalize()

    # --- URGENT: Vervallen facturen ---
    openstaand = df[df["payment_state"].isin(["not_paid", "partial"])].copy()
    openstaand["vervallen_dagen"] = (vandaag - openstaand["invoice_date_due"]).dt.days.clip(lower=0)
    vervallen = openstaand[openstaand["vervallen_dagen"] > 0]
    if not vervallen.empty:
        totaal = vervallen["openstaand"].sum()
        klanten = vervallen["partner_name"].nunique()
        acties.append({
            "prioriteit": "🔴 Urgent",
            "categorie": "Betalingen",
            "actie": f"Opvolgen vervallen facturen",
            "detail": f"{klanten} klanten | € {totaal:,.0f} openstaand",
            "klanten": sorted(vervallen["partner_name"].unique().tolist()),
        })

    # --- URGENT: Slechte betalers ---
    if not betaal_analyse.empty:
        slecht = betaal_analyse[betaal_analyse["categorie"] == "🔴 Slecht"]
        if not slecht.empty:
            acties.append({
                "prioriteit": "🔴 Urgent",
                "categorie": "Betalingen",
                "actie": f"Betalingsafspraken maken met slechte betalers",
                "detail": f"{len(slecht)} klanten met gem. betaaltermijn > 60 dagen",
                "klanten": sorted(slecht["partner_name"].tolist()),
            })

    # --- URGENT: "Niet verliezen" segment ---
    if not rfm_df.empty:
        niet_verliezen = rfm_df[rfm_df["segment"] == "🔴 Niet verliezen"]
        if not niet_verliezen.empty:
            omzet = niet_verliezen["totaal_omzet"].sum()
            acties.append({
                "prioriteit": "🔴 Urgent",
                "categorie": "Klantbehoud",
                "actie": "Proactief contact met 'Niet verliezen' klanten",
                "detail": f"{len(niet_verliezen)} klanten | € {omzet:,.0f} omzet op het spel",
                "klanten": sorted(niet_verliezen["partner_name"].tolist()),
            })

    # --- ATTENTIE: Sterke dalers ---
    if not samenvatting["dalers"].empty:
        dalers = samenvatting["dalers"]
        acties.append({
            "prioriteit": "🟡 Attentie",
            "categorie": "Omzettrend",
            "actie": "Contact opnemen met klanten met dalende omzet",
            "detail": f"{len(dalers)} klanten met dalende trend (> 10%/maand)",
            "klanten": sorted(dalers.index.tolist()),
        })

    # --- ATTENTIE: Inactieve klanten ---
    if samenvatting["inactief"]:
        acties.append({
            "prioriteit": "🟡 Attentie",
            "categorie": "Reactivatie",
            "actie": "Inactieve klanten reactiveren",
            "detail": f"{len(samenvatting['inactief'])} klanten zonder factuur in laatste 90 dagen",
            "klanten": samenvatting["inactief"],
        })

    # --- ATTENTIE: Doelstelling achterstand ---
    totaal_doel = doelstellingen.get("totaal", 0)
    if totaal_doel > 0:
        huidig_jaar = vandaag.year
        omzet_huidig = df[df["jaar"] == huidig_jaar]["omzet"].sum()
        verstreken_dagen = max((vandaag - vandaag.replace(month=1, day=1)).days, 1)
        resterende_dagen = max((vandaag.replace(month=12, day=31) - vandaag).days, 1)
        gem_per_dag = omzet_huidig / verstreken_dagen
        prognose = gem_per_dag * 365
        if prognose < totaal_doel * 0.9:
            tekort = totaal_doel - prognose
            acties.append({
                "prioriteit": "🟡 Attentie",
                "categorie": "Doelstelling",
                "actie": "Verkoopinspanning verhogen om jaardoel te halen",
                "detail": f"Prognose € {prognose:,.0f} vs doel € {totaal_doel:,.0f} (tekort € {tekort:,.0f})",
                "klanten": [],
            })

    # --- ATTENTIE: Matige betalers ---
    if not betaal_analyse.empty:
        matig = betaal_analyse[betaal_analyse["categorie"] == "🟡 Matig"]
        if not matig.empty:
            acties.append({
                "prioriteit": "🟡 Attentie",
                "categorie": "Betalingen",
                "actie": "Betalingsherinnering sturen naar matige betalers",
                "detail": f"{len(matig)} klanten met gem. betaaltermijn 31–60 dagen",
                "klanten": sorted(matig["partner_name"].tolist()),
            })

    # --- INFO: Concentratierisico ---
    if samenvatting["concentratie_pct"] > 50:
        top3 = samenvatting["top3"]
        acties.append({
            "prioriteit": "🔵 Info",
            "categorie": "Risico",
            "actie": "Concentratierisico verminderen",
            "detail": f"Top 3 klanten = {samenvatting['concentratie_pct']:.1f}% van totale omzet",
            "klanten": top3.index.tolist(),
        })

    # --- INFO: Stijgende trends ---
    if not samenvatting["stijgers"].empty:
        stijgers = samenvatting["stijgers"]
        acties.append({
            "prioriteit": "🔵 Info",
            "categorie": "Kansen",
            "actie": "Groeikansen benutten bij stijgende klanten",
            "detail": f"{len(stijgers)} klanten met stijgende omzettrend",
            "klanten": sorted(stijgers.index.tolist()),
        })

    return acties
