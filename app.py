import streamlit as st
import pandas as pd
import io
from src.odoo_client import fetch_invoices, fetch_partner_emails
from src.data_processing import (
    invoices_to_dataframe,
    omzet_per_partner_per_maand,
    omzet_per_partner_totaal,
)
from src.charts import lijndiagram, staafdiagram
from src.management_summary import bereken_samenvatting
from src.rfm import bereken_rfm, SEGMENTEN

st.set_page_config(
    page_title="Verkoopdashboard HNKLSPL",
    page_icon="📊",
    layout="wide",
)

st.title("Verkoopdashboard")

@st.cache_data(ttl=3600)
def laad_data():
    invoices = fetch_invoices()
    if not invoices:
        return invoices_to_dataframe([])
    partner_ids = list({
        id
        for inv in invoices
        for id in [
            inv["partner_id"][0] if isinstance(inv["partner_id"], list) else None,
            inv["commercial_partner_id"][0] if isinstance(inv.get("commercial_partner_id"), list) else None,
        ]
        if id is not None
    })
    emails = fetch_partner_emails(partner_ids)
    return invoices_to_dataframe(invoices, emails)

with st.spinner("Data ophalen uit Odoo..."):
    df = laad_data()

if df.empty:
    st.error("Geen data gevonden. Controleer je Odoo verbindingsinstellingen in het .env bestand.")
    st.stop()

# --- Sidebar filters ---
st.sidebar.header("Filters")

alle_partners = sorted(df["partner_name"].unique().tolist())
geselecteerde_partners = st.sidebar.multiselect(
    "Selecteer klanten",
    options=alle_partners,
    default=alle_partners[:10],
)

alle_jaren = sorted(df["jaar"].unique().tolist(), reverse=True)
geselecteerde_jaren = st.sidebar.multiselect(
    "Selecteer jaar",
    options=alle_jaren,
    default=alle_jaren,
)

df_gefilterd = df[
    df["partner_name"].isin(geselecteerde_partners) &
    df["jaar"].isin(geselecteerde_jaren)
]

if df_gefilterd.empty:
    st.warning("Geen data voor de geselecteerde filters.")
    st.stop()

# --- KPI's ---
col1, col2, col3 = st.columns(3)
col1.metric("Totale omzet", f"€ {df_gefilterd['omzet'].sum():,.0f}")
col2.metric("Aantal klanten", df_gefilterd["partner_name"].nunique())
col3.metric("Aantal facturen", len(df_gefilterd))

st.divider()

# --- Managementsamenvatting ---
st.header("Managementsamenvatting")
st.caption("Trend berekend via lineaire regressie over alle beschikbare maanden")

samenvatting = bereken_samenvatting(df)

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.error(f"**Dalende trend**\n\n{len(samenvatting['dalers'])} klanten")
with col2:
    st.success(f"**Stijgende trend**\n\n{len(samenvatting['stijgers'])} klanten")
with col3:
    st.warning(f"**Inactief (>90 dagen)**\n\n{len(samenvatting['inactief'])} klanten")
with col4:
    kleur = st.error if samenvatting["concentratie_pct"] > 50 else st.info
    kleur(f"**Concentratierisico**\n\nTop 3 = {samenvatting['concentratie_pct']:.1f}% van omzet")

with st.expander("Dalende trend (> 10% daling per maand t.o.v. gemiddelde)", expanded=True):
    if samenvatting["dalers"].empty:
        st.info("Geen klanten met duidelijk dalende trend.")
    else:
        dalers_display = samenvatting["dalers"][["gemiddeld_per_maand", "slope", "slope_pct", "aantal_maanden"]].copy()
        dalers_display.columns = ["Gem. omzet/maand (€)", "Trend (€/maand)", "Trend (%/maand)", "Maanden data"]
        st.dataframe(dalers_display.style.format({
            "Gem. omzet/maand (€)": "€ {:,.0f}",
            "Trend (€/maand)": "€ {:,.0f}",
            "Trend (%/maand)": "{:.1f}%",
            "Maanden data": "{:.0f}",
        }), use_container_width=True)

with st.expander("Stijgende trend (> 10% stijging per maand t.o.v. gemiddelde)"):
    if samenvatting["stijgers"].empty:
        st.info("Geen klanten met duidelijk stijgende trend.")
    else:
        stijgers_display = samenvatting["stijgers"][["gemiddeld_per_maand", "slope", "slope_pct", "aantal_maanden"]].copy()
        stijgers_display.columns = ["Gem. omzet/maand (€)", "Trend (€/maand)", "Trend (%/maand)", "Maanden data"]
        st.dataframe(stijgers_display.style.format({
            "Gem. omzet/maand (€)": "€ {:,.0f}",
            "Trend (€/maand)": "€ {:,.0f}",
            "Trend (%/maand)": "{:.1f}%",
            "Maanden data": "{:.0f}",
        }), use_container_width=True)

with st.expander("Inactieve klanten (geen factuur in laatste 90 dagen)"):
    if not samenvatting["inactief"]:
        st.info("Geen inactieve klanten gevonden.")
    else:
        st.dataframe(pd.DataFrame({"Klant": samenvatting["inactief"]}), use_container_width=True)

with st.expander("Concentratierisico — top 3 klanten"):
    top3_df = samenvatting["top3"].reset_index()
    top3_df.columns = ["Klant", "Omzet (€)"]
    top3_df["Aandeel (%)"] = top3_df["Omzet (€)"] / samenvatting["totaal_omzet"] * 100
    st.dataframe(top3_df.style.format({
        "Omzet (€)": "€ {:,.0f}",
        "Aandeel (%)": "{:.1f}%",
    }), use_container_width=True)

st.divider()

# --- Grafieken ---
maand_df = omzet_per_partner_per_maand(df_gefilterd)
totaal_df = omzet_per_partner_totaal(df_gefilterd)

st.plotly_chart(
    lijndiagram(maand_df, geselecteerde_partners),
    use_container_width=True,
)

st.plotly_chart(
    staafdiagram(totaal_df, geselecteerde_partners),
    use_container_width=True,
)

# --- RFM Segmentatie ---
st.divider()
st.header("Klantsegmentatie (RFM)")
st.caption("Gebaseerd op Recency (recentheid), Frequency (frequentie) en Monetary (omzet) — scores 1 (laag) tot 4 (hoog)")

rfm_df = bereken_rfm(df)

# Overzicht per segment
segment_counts = rfm_df["segment"].value_counts().reset_index()
segment_counts.columns = ["Segment", "Aantal klanten"]

cols = st.columns(len(SEGMENTEN))
for col, (segment, info) in zip(cols, SEGMENTEN.items()):
    aantal = len(rfm_df[rfm_df["segment"] == segment])
    col.metric(segment, aantal)
    col.caption(info["omschrijving"])

st.divider()

# Filter op segment
geselecteerd_segment = st.selectbox(
    "Bekijk klanten per segment",
    options=["Alle segmenten"] + list(SEGMENTEN.keys()),
)

rfm_weergave = rfm_df if geselecteerd_segment == "Alle segmenten" else rfm_df[rfm_df["segment"] == geselecteerd_segment]

st.dataframe(
    rfm_weergave.rename(columns={
        "partner_name": "Klant",
        "email": "E-mail",
        "segment": "Segment",
        "RFM_score": "Score",
        "R": "R",
        "F": "F",
        "M": "M",
        "recency_dagen": "Dagen sinds laatste factuur",
        "aantal_facturen": "Aantal facturen",
        "totaal_omzet": "Totale omzet (€)",
    }).style.format({"Totale omzet (€)": "€ {:,.0f}"}),
    use_container_width=True,
)

# --- Export ---
st.divider()
st.subheader("Export")

def maak_excel(df: pd.DataFrame, omzet_per_maand: pd.DataFrame, omzet_totaal: pd.DataFrame, samenvatting: dict, df_alle: pd.DataFrame = None, rfm_df: pd.DataFrame = None) -> bytes:
    email_lookup = (df_alle if df_alle is not None else df).drop_duplicates("partner_name")[["partner_name", "email"]]

    def voeg_email_toe(bron_df: pd.DataFrame) -> pd.DataFrame:
        return bron_df.merge(email_lookup, left_on="Klant", right_on="partner_name", how="left").drop(columns="partner_name")

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.sort_values("invoice_date", ascending=False).to_excel(writer, sheet_name="Facturen", index=False)
        omzet_per_maand.to_excel(writer, sheet_name="Omzet per maand", index=False)
        omzet_totaal.to_excel(writer, sheet_name="Omzet per klant", index=False)

        for label, sleutel, sheet in [("Dalers", "dalers", "Dalers"), ("Stijgers", "stijgers", "Stijgers")]:
            trend = samenvatting[sleutel][["gemiddeld_per_maand", "slope", "slope_pct", "aantal_maanden"]].copy()
            trend.index.name = "Klant"
            trend.columns = ["Gem. omzet/maand (€)", "Trend (€/maand)", "Trend (%/maand)", "Maanden data"]
            voeg_email_toe(trend.reset_index()).to_excel(writer, sheet_name=sheet, index=False)

        inactief_df = pd.DataFrame({"Klant": samenvatting["inactief"]})
        voeg_email_toe(inactief_df).to_excel(writer, sheet_name="Inactieve klanten", index=False)

        top3_df = samenvatting["top3"].reset_index()
        top3_df.columns = ["Klant", "Omzet (€)"]
        top3_df["Aandeel (%)"] = top3_df["Omzet (€)"] / samenvatting["totaal_omzet"] * 100
        top3_df.to_excel(writer, sheet_name="Concentratierisico", index=False)

        if rfm_df is not None:
            rfm_export = rfm_df.rename(columns={
                "partner_name": "Klant", "email": "E-mail", "segment": "Segment",
                "RFM_score": "Score", "recency_dagen": "Dagen sinds laatste factuur",
                "aantal_facturen": "Aantal facturen", "totaal_omzet": "Totale omzet (€)",
            })
            rfm_export.to_excel(writer, sheet_name="RFM Segmentatie", index=False)

    return buffer.getvalue()

excel_data = maak_excel(df_gefilterd, maand_df, totaal_df, samenvatting, df_alle=df, rfm_df=rfm_df)
st.download_button(
    label="Download Excel",
    data=excel_data,
    file_name="verkoopdashboard.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

# --- Ruwe data ---
with st.expander("Ruwe data bekijken"):
    st.dataframe(df_gefilterd.sort_values("invoice_date", ascending=False), use_container_width=True)
