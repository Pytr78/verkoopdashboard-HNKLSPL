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
from src.doelstellingen import laad_doelstellingen, sla_doelstellingen_op
from src.betalingsanalyse import bereken_betaaldagen, CATEGORIEEN
from src.odoo_client import fetch_betaalde_facturen

st.set_page_config(
    page_title="Verkoopdashboard HNKLSPL",
    page_icon="📊",
    layout="wide",
)

st.title("Verkoopdashboard")

@st.cache_data(ttl=3600)
def laad_betalingen():
    return fetch_betaalde_facturen()

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

# --- Omzetdoelstellingen ---
st.header("Omzetdoelstellingen")

doelstellingen = laad_doelstellingen()
huidig_jaar = pd.Timestamp.now().year
df_huidig_jaar = df[df["jaar"] == huidig_jaar]
omzet_huidig_jaar = df_huidig_jaar["omzet"].sum()

totaal_doel = doelstellingen.get("totaal", 0)

# Datumberekeningen
vandaag = pd.Timestamp.now().normalize()
jaar_start = vandaag.replace(month=1, day=1)
jaar_eind = vandaag.replace(month=12, day=31)
verstreken_dagen = max((vandaag - jaar_start).days, 1)
resterende_dagen = max((jaar_eind - vandaag).days, 1)
dagen_in_jaar = 365

# Huidige pace
gem_per_dag = omzet_huidig_jaar / verstreken_dagen
gem_per_week = gem_per_dag * 7
gem_per_maand = gem_per_dag * 30
prognose_einde_jaar = gem_per_dag * dagen_in_jaar

# Totale doelstelling bovenaan
col1, col2 = st.columns([2, 1])
with col1:
    if totaal_doel > 0:
        voortgang = min(omzet_huidig_jaar / totaal_doel, 1.0)
        st.metric(
            f"Totale omzet {huidig_jaar}",
            f"€ {omzet_huidig_jaar:,.0f}",
            delta=f"€ {omzet_huidig_jaar - totaal_doel:,.0f} t.o.v. doel",
        )
        st.progress(voortgang, text=f"{voortgang*100:.1f}% van € {totaal_doel:,.0f}")
    else:
        st.metric(f"Totale omzet {huidig_jaar}", f"€ {omzet_huidig_jaar:,.0f}")
        st.info("Nog geen totale doelstelling ingesteld.")

with col2:
    with st.expander("Totale doelstelling instellen"):
        nieuw_totaal = st.number_input(
            f"Jaardoelstelling {huidig_jaar} (€)",
            min_value=0,
            value=int(totaal_doel),
            step=10000,
        )
        if st.button("Opslaan", key="totaal_opslaan"):
            doelstellingen["totaal"] = nieuw_totaal
            sla_doelstellingen_op(doelstellingen)
            st.success("Opgeslagen!")
            st.rerun()

# Pace KPI's
st.subheader("Huidige pace")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Gem. per dag", f"€ {gem_per_dag:,.0f}")
c2.metric("Gem. per week", f"€ {gem_per_week:,.0f}")
c3.metric("Gem. per maand", f"€ {gem_per_maand:,.0f}")
c4.metric("Prognose einde jaar", f"€ {prognose_einde_jaar:,.0f}",
          delta=f"€ {prognose_einde_jaar - totaal_doel:,.0f}" if totaal_doel > 0 else None)

if totaal_doel > 0:
    resterend = max(totaal_doel - omzet_huidig_jaar, 0)
    benodigde_dag = resterend / resterende_dagen
    benodigde_week = benodigde_dag * 7
    benodigde_maand = benodigde_dag * 30

    st.subheader(f"Benodigde pace om doel te halen ({resterende_dagen} dagen resterend)")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Nog te realiseren", f"€ {resterend:,.0f}")
    c2.metric("Benodigd per dag", f"€ {benodigde_dag:,.0f}",
              delta=f"€ {gem_per_dag - benodigde_dag:,.0f} vs huidige pace",
              delta_color="normal")
    c3.metric("Benodigd per week", f"€ {benodigde_week:,.0f}")
    c4.metric("Benodigd per maand", f"€ {benodigde_maand:,.0f}")

st.divider()

# Doelstellingen per klant
with st.expander("Doelstellingen per klant", expanded=True):
    omzet_per_klant = df_huidig_jaar.groupby("partner_name")["omzet"].sum()
    alle_klanten = sorted(df["partner_name"].unique().tolist())

    tab1, tab2 = st.tabs(["Voortgang", "Instellen"])

    with tab1:
        klanten_met_doel = {k: v for k, v in doelstellingen.get("per_klant", {}).items() if v > 0}
        if not klanten_met_doel:
            st.info("Nog geen doelstellingen per klant ingesteld. Gebruik het tabblad 'Instellen'.")
        else:
            for klant, doel in sorted(klanten_met_doel.items(), key=lambda x: -x[1]):
                gerealiseerd = omzet_per_klant.get(klant, 0)
                voortgang = min(gerealiseerd / doel, 1.0)
                kleur = "normal" if voortgang >= 0.8 else "off"
                col_a, col_b = st.columns([3, 1])
                with col_a:
                    st.write(f"**{klant}**")
                    st.progress(voortgang, text=f"€ {gerealiseerd:,.0f} / € {doel:,.0f} ({voortgang*100:.1f}%)")
                with col_b:
                    verschil = gerealiseerd - doel
                    st.metric("", f"€ {gerealiseerd:,.0f}", delta=f"€ {verschil:,.0f}")

    with tab2:
        st.caption("Stel een jaardoelstelling in per klant (0 = geen doel)")
        per_klant = doelstellingen.get("per_klant", {})
        gewijzigd = False
        for klant in alle_klanten:
            huidig_doel = int(per_klant.get(klant, 0))
            nieuw_doel = st.number_input(klant, min_value=0, value=huidig_doel, step=1000, key=f"doel_{klant}")
            if nieuw_doel != huidig_doel:
                per_klant[klant] = nieuw_doel
                gewijzigd = True
        if gewijzigd:
            doelstellingen["per_klant"] = per_klant
            sla_doelstellingen_op(doelstellingen)
            st.success("Doelstellingen opgeslagen!")

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

# --- Betalingsgedrag ---
st.header("Betalingsgedrag")

vandaag_ts = pd.Timestamp.now().normalize()

openstaand_df = df[df["payment_state"].isin(["not_paid", "partial"])].copy()
openstaand_df["vervallen_dagen"] = (vandaag_ts - openstaand_df["invoice_date_due"]).dt.days.clip(lower=0)
openstaand_df["vervallen"] = openstaand_df["vervallen_dagen"] > 0

totaal_openstaand = openstaand_df["openstaand"].sum()
totaal_vervallen = openstaand_df[openstaand_df["vervallen"]]["openstaand"].sum()
aantal_vervallen = int(openstaand_df["vervallen"].sum())

col1, col2, col3 = st.columns(3)
col1.metric("Totaal openstaand", f"€ {totaal_openstaand:,.0f}")
col2.metric("Waarvan vervallen", f"€ {totaal_vervallen:,.0f}")
col3.metric("Aantal vervallen facturen", aantal_vervallen)

with st.expander("Vervallen facturen per klant", expanded=True):
    vervallen = openstaand_df[openstaand_df["vervallen"]].copy()
    if vervallen.empty:
        st.success("Geen vervallen facturen.")
    else:
        vervallen_per_klant = (
            vervallen.groupby("partner_name")
            .agg(
                openstaand=("openstaand", "sum"),
                aantal=("name", "count"),
                max_vervallen_dagen=("vervallen_dagen", "max"),
                email=("email", "first"),
            )
            .reset_index()
            .sort_values("openstaand", ascending=False)
            .rename(columns={
                "partner_name": "Klant",
                "openstaand": "Openstaand (€)",
                "aantal": "Facturen",
                "max_vervallen_dagen": "Max. vervallen (dagen)",
                "email": "E-mail",
            })
        )
        st.dataframe(
            vervallen_per_klant.style.format({"Openstaand (€)": "€ {:,.0f}"}),
            use_container_width=True,
        )

with st.expander("Alle openstaande facturen"):
    if openstaand_df.empty:
        st.success("Geen openstaande facturen.")
    else:
        weergave = openstaand_df[[
            "name", "partner_name", "email", "invoice_date",
            "invoice_date_due", "openstaand", "vervallen_dagen", "payment_state"
        ]].rename(columns={
            "name": "Factuur",
            "partner_name": "Klant",
            "email": "E-mail",
            "invoice_date": "Factuurdatum",
            "invoice_date_due": "Vervaldatum",
            "openstaand": "Openstaand (€)",
            "vervallen_dagen": "Vervallen (dagen)",
            "payment_state": "Status",
        }).sort_values("Vervallen (dagen)", ascending=False)
        st.dataframe(
            weergave.style.format({"Openstaand (€)": "€ {:,.0f}"}),
            use_container_width=True,
        )

# Gemiddelde betaaldagen per klant
st.subheader("Gemiddelde betaaltermijn per klant")

with st.spinner("Betalingshistoriek ophalen..."):
    betalingen = laad_betalingen()

betaal_analyse = bereken_betaaldagen(df, betalingen)

if betaal_analyse.empty:
    st.info("Geen betalingsdata beschikbaar.")
else:
    totaal_gem = betaal_analyse["gem_betaaldagen"].mean()
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Gemiddeld alle klanten", f"{totaal_gem:.1f} dagen")
    for i, (naam, _) in enumerate(CATEGORIEEN):
        aantal = len(betaal_analyse[betaal_analyse["categorie"] == naam])
        [col2, col3, col4, col5][i].metric(naam, f"{aantal} klanten")

    filter_cat = st.selectbox(
        "Filter op categorie",
        options=["Alle"] + [naam for naam, _ in CATEGORIEEN],
    )

    weergave = betaal_analyse if filter_cat == "Alle" else betaal_analyse[betaal_analyse["categorie"] == filter_cat]

    st.dataframe(
        weergave.rename(columns={
            "partner_name": "Klant",
            "email": "E-mail",
            "categorie": "Categorie",
            "gem_betaaldagen": "Gem. betaaldagen",
            "max_betaaldagen": "Max. betaaldagen",
            "aantal_betaald": "Betaalde facturen",
        }).style.format({"Gem. betaaldagen": "{:.1f}"}),
        use_container_width=True,
    )

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
