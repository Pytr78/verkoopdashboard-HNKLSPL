import os
import re
import streamlit as st
import pandas as pd
import io
import plotly.express as px
from src.odoo_client import fetch_invoices, fetch_partner_info, fetch_betaalde_facturen, fetch_employees, fetch_personeelskosten, fetch_lonen_bankafschriften, fetch_leveranciersfacturen, fetch_omzet_eigen_productie
from src.data_processing import invoices_to_dataframe, omzet_per_partner_per_maand, omzet_per_partner_totaal
from src.charts import lijndiagram, staafdiagram
from src.management_summary import bereken_samenvatting
from src.rfm import bereken_rfm, SEGMENTEN
from src.doelstellingen import laad_doelstellingen, sla_doelstellingen_op
from src.betalingsanalyse import bereken_betaaldagen, CATEGORIEEN
from src.actiepunten import genereer_actiepunten
from src.cashflow import bereken_cashflow_prognose, cashflow_per_periode

st.set_page_config(page_title="Verkoopdashboard HNKLSPL", page_icon="📊", layout="wide")


st.title("Verkoopdashboard")

# --- Data laden ---
@st.cache_data(ttl=86400)
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
    emails, labels = fetch_partner_info(partner_ids)
    return invoices_to_dataframe(invoices, emails, labels)

@st.cache_data(ttl=86400)
def laad_betalingen():
    return fetch_betaalde_facturen()

@st.cache_data(ttl=86400)
def laad_werknemers():
    return fetch_employees()

@st.cache_data(ttl=86400)
def laad_personeelskosten():
    return fetch_personeelskosten()

@st.cache_data(ttl=86400)
def laad_lonen_bankafschriften():
    return fetch_lonen_bankafschriften()

@st.cache_data(ttl=86400)
def laad_leveranciersfacturen():
    return fetch_leveranciersfacturen()

@st.cache_data(ttl=86400)
def laad_omzet_eigen_productie():
    return fetch_omzet_eigen_productie()


with st.spinner("Data ophalen uit Odoo..."):
    df = laad_data()

if df.empty:
    st.error("Geen data gevonden. Controleer je Odoo verbindingsinstellingen in het .env bestand.")
    st.stop()

# --- Sidebar ---
st.sidebar.header("Filters")

if st.sidebar.button("🔄 Data verversen"):
    st.cache_data.clear()
    st.rerun()
st.sidebar.caption("Data wordt automatisch ververst om de 24 uur.")
st.sidebar.divider()

alle_partners = sorted(df["partner_name"].unique().tolist())
geselecteerde_partners = st.sidebar.multiselect("Selecteer klanten", options=alle_partners, default=alle_partners)

alle_jaren = sorted(df["jaar"].unique().tolist(), reverse=True)
geselecteerde_jaren = st.sidebar.multiselect("Selecteer jaar", options=alle_jaren, default=alle_jaren)

df_gefilterd = df[df["partner_name"].isin(geselecteerde_partners) & df["jaar"].isin(geselecteerde_jaren)]

if df_gefilterd.empty:
    st.warning("Geen data voor de geselecteerde filters.")
    st.stop()

# --- Gemeenschappelijke berekeningen ---
samenvatting = bereken_samenvatting(df)
rfm_df = bereken_rfm(df)
betalingen = laad_betalingen()
betaal_analyse = bereken_betaaldagen(df, betalingen)
doelstellingen = laad_doelstellingen()

# --- KPI's bovenaan ---
huidig_jaar = pd.Timestamp.now().year
df_huidig_jaar = df[df["jaar"] == huidig_jaar]
col1, col2, col3, col4 = st.columns(4)
col1.metric("Totale omzet (gefilterd)", f"€ {df_gefilterd['omzet'].sum():,.0f}")
col2.metric(f"Omzet {huidig_jaar}", f"€ {df_huidig_jaar['omzet'].sum():,.0f}")
col3.metric("Aantal klanten", df_gefilterd["partner_name"].nunique())
col4.metric("Aantal facturen", len(df_gefilterd))

st.divider()

# --- Tabs ---
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10 = st.tabs([
    "🚨 Actiepunten",
    "🎯 Doelstellingen",
    "📊 Grafieken",
    "📈 Omzettrends",
    "👥 Klantsegmentatie",
    "💳 Betalingsgedrag",
    "💰 Cashflow",
    "🏷️ Segmentatie per label",
    "👷 Personeelskosten",
    "🧀 Eigen Productie",
])

# ── Tab 1: Actiepunten ──────────────────────────────────────────────────────
with tab1:
    st.header("Actiepunten")
    st.caption("Automatisch gegenereerd op basis van alle analyses")

    actiepunten = genereer_actiepunten(df, samenvatting, rfm_df, betaal_analyse, doelstellingen)

    if not actiepunten:
        st.success("Geen actiepunten — alles ziet er goed uit!")
    else:
        for actie in actiepunten:
            with st.expander(f"{actie['prioriteit']} — {actie['categorie']}: {actie['actie']}"):
                st.write(f"**{actie['detail']}**")
                if actie["klanten"]:
                    st.write("**Betrokken klanten:**")
                    st.dataframe(pd.DataFrame({"Klant": actie["klanten"]}), hide_index=True, use_container_width=True)

# ── Tab 2: Doelstellingen ───────────────────────────────────────────────────
with tab2:
    st.header("Omzetdoelstellingen")

    vandaag = pd.Timestamp.now().normalize()
    omzet_huidig_jaar = df_huidig_jaar["omzet"].sum()
    totaal_doel = doelstellingen.get("totaal", 0)
    verstreken_dagen = max((vandaag - vandaag.replace(month=1, day=1)).days, 1)
    resterende_dagen = max((vandaag.replace(month=12, day=31) - vandaag).days, 1)
    gem_per_dag = omzet_huidig_jaar / verstreken_dagen

    col1, col2 = st.columns([2, 1])
    with col1:
        if totaal_doel > 0:
            voortgang = min(omzet_huidig_jaar / totaal_doel, 1.0)
            st.metric(f"Totale omzet {huidig_jaar}", f"€ {omzet_huidig_jaar:,.0f}",
                      delta=f"€ {omzet_huidig_jaar - totaal_doel:,.0f} t.o.v. doel")
            st.progress(voortgang, text=f"{voortgang*100:.1f}% van € {totaal_doel:,.0f}")
        else:
            st.metric(f"Totale omzet {huidig_jaar}", f"€ {omzet_huidig_jaar:,.0f}")
            st.info("Nog geen totale doelstelling ingesteld.")
    with col2:
        with st.expander("Totale doelstelling instellen"):
            nieuw_totaal = st.number_input(f"Jaardoelstelling {huidig_jaar} (€)", min_value=0, value=int(totaal_doel), step=10000)
            if st.button("Opslaan", key="totaal_opslaan"):
                doelstellingen["totaal"] = nieuw_totaal
                sla_doelstellingen_op(doelstellingen)
                st.success("Opgeslagen!")
                st.rerun()

    st.subheader("Huidige pace")
    c1, c2, c3, c4 = st.columns(4)
    prognose = gem_per_dag * 365
    c1.metric("Gem. per dag", f"€ {gem_per_dag:,.0f}")
    c2.metric("Gem. per week", f"€ {gem_per_dag * 7:,.0f}")
    c3.metric("Gem. per maand", f"€ {gem_per_dag * 30:,.0f}")
    c4.metric("Prognose einde jaar", f"€ {prognose:,.0f}",
              delta=f"€ {prognose - totaal_doel:,.0f}" if totaal_doel > 0 else None)

    if totaal_doel > 0:
        resterend = max(totaal_doel - omzet_huidig_jaar, 0)
        benodigde_dag = resterend / resterende_dagen
        st.subheader(f"Benodigde pace ({resterende_dagen} dagen resterend)")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Nog te realiseren", f"€ {resterend:,.0f}")
        c2.metric("Benodigd per dag", f"€ {benodigde_dag:,.0f}",
                  delta=f"€ {gem_per_dag - benodigde_dag:,.0f} vs huidige pace", delta_color="normal")
        c3.metric("Benodigd per week", f"€ {benodigde_dag * 7:,.0f}")
        c4.metric("Benodigd per maand", f"€ {benodigde_dag * 30:,.0f}")

    st.subheader("Doelstellingen per klant")
    omzet_per_klant = df_huidig_jaar.groupby("partner_name")["omzet"].sum()
    alle_klanten = sorted(df["partner_name"].unique().tolist())
    subtab1, subtab2 = st.tabs(["Voortgang", "Instellen"])

    with subtab1:
        klanten_met_doel = {k: v for k, v in doelstellingen.get("per_klant", {}).items() if v > 0}
        if not klanten_met_doel:
            st.info("Nog geen doelstellingen per klant ingesteld. Gebruik het tabblad 'Instellen'.")
        else:
            for klant, doel in sorted(klanten_met_doel.items(), key=lambda x: -x[1]):
                gerealiseerd = omzet_per_klant.get(klant, 0)
                vrtg = min(gerealiseerd / doel, 1.0)
                col_a, col_b = st.columns([3, 1])
                with col_a:
                    st.write(f"**{klant}**")
                    st.progress(vrtg, text=f"€ {gerealiseerd:,.0f} / € {doel:,.0f} ({vrtg*100:.1f}%)")
                with col_b:
                    st.metric("", f"€ {gerealiseerd:,.0f}", delta=f"€ {gerealiseerd - doel:,.0f}")

    with subtab2:
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

# ── Tab 3: Grafieken ────────────────────────────────────────────────────────
with tab3:
    st.header("Grafieken")
    maand_df = omzet_per_partner_per_maand(df_gefilterd)
    totaal_df = omzet_per_partner_totaal(df_gefilterd)
    st.plotly_chart(lijndiagram(maand_df, geselecteerde_partners), use_container_width=True)
    st.plotly_chart(staafdiagram(totaal_df, geselecteerde_partners), use_container_width=True)

    st.subheader("Export")
    def maak_excel(df, omzet_per_maand, omzet_totaal, samenvatting, df_alle=None, rfm_df=None):
        email_lookup = (df_alle if df_alle is not None else df).drop_duplicates("partner_name")[["partner_name", "email"]]
        def voeg_email_toe(bron_df):
            return bron_df.merge(email_lookup, left_on="Klant", right_on="partner_name", how="left").drop(columns="partner_name")
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.sort_values("invoice_date", ascending=False).to_excel(writer, sheet_name="Facturen", index=False)
            omzet_per_maand.to_excel(writer, sheet_name="Omzet per maand", index=False)
            omzet_totaal.to_excel(writer, sheet_name="Omzet per klant", index=False)
            for _, sleutel, sheet in [("Dalers", "dalers", "Dalers"), ("Stijgers", "stijgers", "Stijgers")]:
                trend = samenvatting[sleutel][["gemiddeld_per_maand", "slope", "slope_pct", "aantal_maanden"]].copy()
                trend.index.name = "Klant"
                trend.columns = ["Gem. omzet/maand (€)", "Trend (€/maand)", "Trend (%/maand)", "Maanden data"]
                voeg_email_toe(trend.reset_index()).to_excel(writer, sheet_name=sheet, index=False)
            voeg_email_toe(pd.DataFrame({"Klant": samenvatting["inactief"]})).to_excel(writer, sheet_name="Inactieve klanten", index=False)
            top3_df = samenvatting["top3"].reset_index()
            top3_df.columns = ["Klant", "Omzet (€)"]
            top3_df["Aandeel (%)"] = top3_df["Omzet (€)"] / samenvatting["totaal_omzet"] * 100
            top3_df.to_excel(writer, sheet_name="Concentratierisico", index=False)
            if rfm_df is not None:
                rfm_df.rename(columns={"partner_name": "Klant", "email": "E-mail", "segment": "Segment",
                    "RFM_score": "Score", "recency_dagen": "Dagen sinds laatste factuur",
                    "aantal_facturen": "Aantal facturen", "totaal_omzet": "Totale omzet (€)"
                }).to_excel(writer, sheet_name="RFM Segmentatie", index=False)
        return buffer.getvalue()

    excel_data = maak_excel(df_gefilterd, maand_df, totaal_df, samenvatting, df_alle=df, rfm_df=rfm_df)
    st.download_button(label="📥 Download Excel", data=excel_data, file_name="verkoopdashboard.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    with st.expander("Ruwe data bekijken"):
        st.dataframe(df_gefilterd.sort_values("invoice_date", ascending=False), use_container_width=True)

# ── Tab 4: Omzettrends ──────────────────────────────────────────────────────
with tab4:
    st.header("Omzettrends")
    st.caption("Trend berekend via lineaire regressie over alle beschikbare maanden")

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

    with st.expander("Dalende trend (> 10%/maand)", expanded=True):
        if samenvatting["dalers"].empty:
            st.info("Geen klanten met duidelijk dalende trend.")
        else:
            d = samenvatting["dalers"][["gemiddeld_per_maand", "slope", "slope_pct", "aantal_maanden"]].copy()
            d.columns = ["Gem. omzet/maand (€)", "Trend (€/maand)", "Trend (%/maand)", "Maanden data"]
            st.dataframe(d.style.format({"Gem. omzet/maand (€)": "€ {:,.0f}", "Trend (€/maand)": "€ {:,.0f}", "Trend (%/maand)": "{:.1f}%", "Maanden data": "{:.0f}"}), use_container_width=True)

    with st.expander("Stijgende trend (> 10%/maand)"):
        if samenvatting["stijgers"].empty:
            st.info("Geen klanten met duidelijk stijgende trend.")
        else:
            s = samenvatting["stijgers"][["gemiddeld_per_maand", "slope", "slope_pct", "aantal_maanden"]].copy()
            s.columns = ["Gem. omzet/maand (€)", "Trend (€/maand)", "Trend (%/maand)", "Maanden data"]
            st.dataframe(s.style.format({"Gem. omzet/maand (€)": "€ {:,.0f}", "Trend (€/maand)": "€ {:,.0f}", "Trend (%/maand)": "{:.1f}%", "Maanden data": "{:.0f}"}), use_container_width=True)

    with st.expander("Inactieve klanten (geen factuur in laatste 90 dagen)"):
        if not samenvatting["inactief"]:
            st.info("Geen inactieve klanten gevonden.")
        else:
            st.dataframe(pd.DataFrame({"Klant": samenvatting["inactief"]}), use_container_width=True)

    with st.expander("Concentratierisico — top 3 klanten"):
        top3_df = samenvatting["top3"].reset_index()
        top3_df.columns = ["Klant", "Omzet (€)"]
        top3_df["Aandeel (%)"] = top3_df["Omzet (€)"] / samenvatting["totaal_omzet"] * 100
        st.dataframe(top3_df.style.format({"Omzet (€)": "€ {:,.0f}", "Aandeel (%)": "{:.1f}%"}), use_container_width=True)

# ── Tab 5: Klantsegmentatie ─────────────────────────────────────────────────
with tab5:
    st.header("Klantsegmentatie (RFM)")
    st.caption("Scores 1 (laag) tot 4 (hoog) op Recency, Frequency en Monetary")

    cols = st.columns(len(SEGMENTEN))
    for col, (segment, info) in zip(cols, SEGMENTEN.items()):
        col.metric(segment, len(rfm_df[rfm_df["segment"] == segment]))
        col.caption(info["omschrijving"])

    st.divider()
    geselecteerd_segment = st.selectbox("Bekijk klanten per segment", options=["Alle segmenten"] + list(SEGMENTEN.keys()))
    rfm_weergave = rfm_df if geselecteerd_segment == "Alle segmenten" else rfm_df[rfm_df["segment"] == geselecteerd_segment]
    st.dataframe(rfm_weergave.rename(columns={
        "partner_name": "Klant", "email": "E-mail", "segment": "Segment", "RFM_score": "Score",
        "recency_dagen": "Dagen sinds laatste factuur", "aantal_facturen": "Aantal facturen", "totaal_omzet": "Totale omzet (€)",
    }).style.format({"Totale omzet (€)": "€ {:,.0f}"}), use_container_width=True)

# ── Tab 6: Betalingsgedrag ──────────────────────────────────────────────────
with tab6:
    st.header("Betalingsgedrag")

    vandaag_ts = pd.Timestamp.now().normalize()
    openstaand_df = df[df["payment_state"].isin(["not_paid", "partial"])].copy()
    openstaand_df["vervallen_dagen"] = (vandaag_ts - openstaand_df["invoice_date_due"]).dt.days.clip(lower=0)
    openstaand_df["vervallen"] = openstaand_df["vervallen_dagen"] > 0

    col1, col2, col3 = st.columns(3)
    col1.metric("Totaal openstaand", f"€ {openstaand_df['openstaand'].sum():,.0f}")
    col2.metric("Waarvan vervallen", f"€ {openstaand_df[openstaand_df['vervallen']]['openstaand'].sum():,.0f}")
    col3.metric("Aantal vervallen facturen", int(openstaand_df["vervallen"].sum()))

    with st.expander("Vervallen facturen per klant", expanded=True):
        vervallen = openstaand_df[openstaand_df["vervallen"]].copy()
        if vervallen.empty:
            st.success("Geen vervallen facturen.")
        else:
            st.dataframe(vervallen.groupby("partner_name").agg(
                openstaand=("openstaand", "sum"), aantal=("name", "count"),
                max_vervallen_dagen=("vervallen_dagen", "max"), email=("email", "first")
            ).reset_index().sort_values("openstaand", ascending=False).rename(columns={
                "partner_name": "Klant", "openstaand": "Openstaand (€)",
                "aantal": "Facturen", "max_vervallen_dagen": "Max. vervallen (dagen)", "email": "E-mail"
            }).style.format({"Openstaand (€)": "€ {:,.0f}"}), use_container_width=True)

    with st.expander("Alle openstaande facturen"):
        if openstaand_df.empty:
            st.success("Geen openstaande facturen.")
        else:
            st.dataframe(openstaand_df[[
                "name", "partner_name", "email", "invoice_date", "invoice_date_due", "openstaand", "vervallen_dagen", "payment_state"
            ]].rename(columns={
                "name": "Factuur", "partner_name": "Klant", "email": "E-mail", "invoice_date": "Factuurdatum",
                "invoice_date_due": "Vervaldatum", "openstaand": "Openstaand (€)", "vervallen_dagen": "Vervallen (dagen)", "payment_state": "Status"
            }).sort_values("Vervallen (dagen)", ascending=False).style.format({"Openstaand (€)": "€ {:,.0f}"}), use_container_width=True)

    st.subheader("Gemiddelde betaaltermijn per klant")
    if betaal_analyse.empty:
        st.info("Geen betalingsdata beschikbaar.")
    else:
        totaal_gem = betaal_analyse["gem_betaaldagen"].mean()
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Gemiddeld alle klanten", f"{totaal_gem:.1f} dagen")
        for i, (naam, _) in enumerate(CATEGORIEEN):
            [col2, col3, col4, col5][i].metric(naam, f"{len(betaal_analyse[betaal_analyse['categorie'] == naam])} klanten")

        filter_cat = st.selectbox("Filter op categorie", options=["Alle"] + [naam for naam, _ in CATEGORIEEN])
        weergave = betaal_analyse if filter_cat == "Alle" else betaal_analyse[betaal_analyse["categorie"] == filter_cat]
        st.dataframe(weergave.rename(columns={
            "partner_name": "Klant", "email": "E-mail", "categorie": "Categorie",
            "gem_betaaldagen": "Gem. betaaldagen", "max_betaaldagen": "Max. betaaldagen", "aantal_betaald": "Betaalde facturen"
        }).style.format({"Gem. betaaldagen": "{:.1f}"}), use_container_width=True)

# ── Tab 7: Cashflow ─────────────────────────────────────────────────────────
with tab7:
    st.header("Cashflow prognose")
    st.caption("Verwachte inkomsten op basis van openstaande facturen en historisch betalingsgedrag per klant")

    prognose_df = bereken_cashflow_prognose(df, betaal_analyse)

    if prognose_df.empty:
        st.success("Geen openstaande facturen.")
    else:
        periode_df = cashflow_per_periode(prognose_df)
        totaal_openstaand = prognose_df["openstaand"].sum()
        binnen_30 = prognose_df[prognose_df["dagen_tot_betaling"] <= 30]["openstaand"].sum()
        binnen_60 = prognose_df[prognose_df["dagen_tot_betaling"] <= 60]["openstaand"].sum()
        binnen_90 = prognose_df[prognose_df["dagen_tot_betaling"] <= 90]["openstaand"].sum()

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Totaal openstaand", f"€ {totaal_openstaand:,.0f}")
        col2.metric("Verwacht binnen 30 dagen", f"€ {binnen_30:,.0f}")
        col3.metric("Verwacht binnen 60 dagen", f"€ {binnen_60:,.0f}")
        col4.metric("Verwacht binnen 90 dagen", f"€ {binnen_90:,.0f}")

        st.plotly_chart(
            px.bar(
                periode_df,
                x="periode",
                y="verwacht_bedrag",
                labels={"periode": "Periode", "verwacht_bedrag": "Verwacht bedrag (€)"},
                title="Verwachte cashflow per periode",
                color="periode",
                color_discrete_sequence=["#2ecc71", "#3498db", "#e67e22", "#e74c3c"],
            ).update_layout(showlegend=False).update_yaxes(tickprefix="€ ", tickformat=",.0f"),
            use_container_width=True,
        )

        with st.expander("Detail per klant"):
            per_klant = (
                prognose_df.groupby(["partner_name", "periode"])
                .agg(verwacht=("openstaand", "sum"), facturen=("name", "count"), email=("email", "first"))
                .reset_index()
                .sort_values(["periode", "verwacht"], ascending=[True, False])
                .rename(columns={"partner_name": "Klant", "email": "E-mail", "periode": "Periode",
                                 "verwacht": "Verwacht (€)", "facturen": "Facturen"})
            )
            st.dataframe(per_klant.style.format({"Verwacht (€)": "€ {:,.0f}"}), use_container_width=True)

        with st.expander("Detail per factuur"):
            st.dataframe(
                prognose_df.rename(columns={
                    "name": "Factuur", "partner_name": "Klant", "email": "E-mail",
                    "invoice_date": "Factuurdatum", "invoice_date_due": "Vervaldatum",
                    "openstaand": "Openstaand (€)", "verwachte_betaaldatum": "Verwachte betaling",
                    "dagen_tot_betaling": "Dagen", "periode": "Periode", "bron": "Schatting op basis van",
                }).sort_values("Dagen").style.format({"Openstaand (€)": "€ {:,.0f}"}),
                use_container_width=True,
            )

# ── Tab 8: Segmentatie per label ────────────────────────────────────────────
with tab8:
    st.header("Segmentatie per label")
    st.caption("Omzet per klantengroep op basis van Odoo-labels (winkelier, horeca, ...)")

    df_labels = df_gefilterd.copy()
    df_labels["labels"] = df_labels["labels"].apply(
        lambda xs: [x[len("klant:"):].strip() for x in xs if x.lower().startswith("klant:")]
    )

    EIGEN_SEGMENTEN = {"hinkelspelwinkels", "hinkelspel markten"}
    klanten_zonder_label = (
        df_labels[
            df_labels["labels"].apply(lambda x: len(x) == 0) &
            ~df_labels["partner_name"].str.lower().isin(EIGEN_SEGMENTEN)
        ]
        .groupby("partner_name")
        .agg(omzet=("omzet", "sum"), email=("email", "first"))
        .reset_index()
        .sort_values("omzet", ascending=False)
        .rename(columns={"partner_name": "Klant", "omzet": "Omzet (€)", "email": "E-mail"})
    )
    if not klanten_zonder_label.empty:
        with st.expander(f"⚠️ {len(klanten_zonder_label)} klanten zonder 'klant:'-label", expanded=False):
            st.caption("Deze klanten hebben geen label dat begint met 'klant:' in Odoo en zijn nog niet ingedeeld in een segment.")
            st.dataframe(
                klanten_zonder_label.style.format({"Omzet (€)": "€ {:,.0f}"}),
                use_container_width=True,
                hide_index=True,
            )

    df_labels = df_labels[df_labels["labels"].apply(lambda x: len(x) > 0)]

    if df_labels.empty:
        st.info("Geen 'klant:'-labels gevonden op de gefilterde klanten. Voeg labels toe in Odoo die beginnen met 'klant:'.")
    else:
        df_exploded = df_labels.explode("labels").rename(columns={"labels": "label"})

        alle_labels = sorted(df_exploded["label"].unique().tolist())
        geselecteerde_labels = st.multiselect("Filter op label", options=alle_labels, default=alle_labels)
        df_exploded = df_exploded[df_exploded["label"].isin(geselecteerde_labels)]

        omzet_per_label = (
            df_exploded.groupby("label")
            .agg(omzet=("omzet", "sum"), klanten=("partner_name", "nunique"), facturen=("name", "count"))
            .reset_index()
            .sort_values("omzet", ascending=False)
        )

        cols = st.columns(min(len(omzet_per_label), 4))
        for i, row in omzet_per_label.iterrows():
            cols[i % len(cols)].metric(row["label"], f"€ {row['omzet']:,.0f}", f"{row['klanten']} klanten")

        st.divider()

        st.plotly_chart(
            px.bar(
                omzet_per_label,
                x="label",
                y="omzet",
                text_auto=".3s",
                labels={"label": "Label", "omzet": "Omzet (€)"},
                title="Omzet per klantengroep (totaal)",
                color="label",
            ).update_layout(showlegend=False).update_yaxes(tickprefix="€ ", tickformat=",.0f"),
            use_container_width=True,
        )

        omzet_per_label_jaar = (
            df_exploded.groupby(["label", "jaar"])["omzet"]
            .sum()
            .reset_index()
            .sort_values(["jaar", "label"])
        )
        omzet_per_label_jaar["jaar"] = omzet_per_label_jaar["jaar"].astype(str)
        st.plotly_chart(
            px.bar(
                omzet_per_label_jaar,
                x="jaar",
                y="omzet",
                color="label",
                barmode="group",
                text_auto=".3s",
                labels={"jaar": "Jaar", "omzet": "Omzet (€)", "label": "Label"},
                title="Omzet per label per jaar",
            ).update_yaxes(tickprefix="€ ", tickformat=",.0f"),
            use_container_width=True,
        )

        with st.expander("Tabel omzet per label per jaar"):
            pivot = omzet_per_label_jaar.pivot(index="label", columns="jaar", values="omzet").fillna(0)
            st.dataframe(
                pivot.style.format("€ {:,.0f}"),
                use_container_width=True,
            )

        st.subheader("Detail per label")
        geselecteerd_label = st.selectbox("Bekijk klanten van label", options=alle_labels)
        df_label_detail = (
            df_exploded[df_exploded["label"] == geselecteerd_label]
            .groupby("partner_name")
            .agg(omzet=("omzet", "sum"), facturen=("name", "count"), email=("email", "first"))
            .reset_index()
            .sort_values("omzet", ascending=False)
            .rename(columns={"partner_name": "Klant", "omzet": "Omzet (€)", "facturen": "Facturen", "email": "E-mail"})
        )
        st.dataframe(
            df_label_detail.style.format({"Omzet (€)": "€ {:,.0f}"}),
            use_container_width=True,
            hide_index=True,
        )

# ── Tab 9: Personeelskosten ─────────────────────────────────────────────────
with tab9:
    st.header("Personeelskosten")

    # ── SD Worx upload ──────────────────────────────────────────────────────
    st.subheader("Loonkosten (SD Worx export)")

    LOONKOST_PAD = os.path.join(os.path.dirname(__file__), "data", "loonkost.xlsx")
    VENNOTEN_PAD = os.path.join(os.path.dirname(__file__), "data", "loonkost_vennoten.xlsx")

    def _upload_widget(label, pad, key):
        expanded = not os.path.exists(pad)
        with st.expander(f"Excel uploaden — {label}", expanded=expanded):
            st.caption("Het bestand wordt opgeslagen en automatisch geladen bij elk volgend bezoek.")
            geupload = st.file_uploader(f"{label} (.xlsx)", type=["xlsx"], key=key)
            if geupload:
                with open(pad, "wb") as f:
                    f.write(geupload.read())
                st.success("Bestand opgeslagen.")
                st.rerun()
            if os.path.exists(pad):
                mtime = os.path.getmtime(pad)
                st.info(f"Huidig bestand geüpload op {pd.Timestamp(mtime, unit='s').strftime('%d/%m/%Y %H:%M')}")
                if st.button("Verwijderen", key=f"del_{key}"):
                    os.remove(pad)
                    st.rerun()

    col_up1, col_up2 = st.columns(2)
    with col_up1:
        _upload_widget("Werknemers (derde tabblad)", LOONKOST_PAD, "loonkost_upload")
    with col_up2:
        _upload_widget("Vennoten (tweede tabblad, looncode 001.48)", VENNOTEN_PAD, "vennoten_upload")

    def _laad_werknemers_excel(pad):
        sdw = pd.read_excel(pad, sheet_name=2)
        sdw = sdw.rename(columns={
            "Naam": "partner_name",
            "Functie": "functie",
            "Start loonperiode": "start_periode",
            "Einde loonperiode": "einde_periode",
            "Totaal Loonkoste": "bedrag",
        })
        start = pd.to_datetime(sdw["start_periode"], errors="coerce")
        einde = pd.to_datetime(sdw["einde_periode"], errors="coerce")
        sdw["maand"] = start.fillna(einde).dt.to_period("M").astype(str)
        sdw["bedrag"] = pd.to_numeric(sdw["bedrag"], errors="coerce").fillna(0)
        return sdw[sdw["maand"].notna()][["maand", "partner_name", "functie", "bedrag"]].copy()

    def _laad_vennoten_excel(pad):
        sdw = pd.read_excel(pad, sheet_name=1)
        looncode_col = next((c for c in sdw.columns if c.strip().lower() == "looncode"), None)
        if looncode_col is None:
            raise ValueError(f"Kolom 'Looncode' niet gevonden. Beschikbare kolommen: {list(sdw.columns)}")
        unieke_codes = sdw[looncode_col].dropna().unique().tolist()
        sdw = sdw[sdw[looncode_col].apply(
            lambda v: str(v).strip().lstrip("0") == "1.48" or str(v).strip() == "001.48"
        )]
        if len(sdw) == 0:
            raise ValueError(f"Geen rijen met looncode 001.48. Gevonden codes: {unieke_codes[:20]}")
        sdw = sdw.rename(columns={
            "Naam": "partner_name",
            "Type werknemer": "functie",
            "Start loonperiode": "start_periode",
            "Einde loonperiode": "einde_periode",
            "Bedrag": "bedrag",
        })
        start = pd.to_datetime(sdw["start_periode"], errors="coerce")
        einde = pd.to_datetime(sdw["einde_periode"], errors="coerce")
        sdw["maand"] = start.fillna(einde).dt.to_period("M").astype(str)
        sdw["bedrag"] = pd.to_numeric(sdw["bedrag"], errors="coerce").fillna(0)
        return sdw[sdw["maand"].notna()][["maand", "partner_name", "functie", "bedrag"]].copy()

    lonen_bank_df = None
    frames = []

    if os.path.exists(LOONKOST_PAD):
        try:
            df_w = _laad_werknemers_excel(LOONKOST_PAD)
            frames.append(df_w)
            st.caption(f"✅ Werknemersbestand geladen: {len(df_w)} rijen, {df_w['partner_name'].nunique()} personen")
        except Exception as e:
            st.error(f"Fout bij inladen werknemersbestand: {e}")
    else:
        st.warning("Werknemersbestand niet gevonden — upload het via het paneel hierboven.")

    if os.path.exists(VENNOTEN_PAD):
        try:
            df_v = _laad_vennoten_excel(VENNOTEN_PAD)
            frames.append(df_v)
            st.caption(f"✅ Vennotenbestand geladen: {len(df_v)} rijen, {df_v['partner_name'].nunique()} personen")
        except Exception as e:
            st.error(f"Fout bij inladen vennotenbestand: {e}")
    else:
        st.warning("Vennotenbestand niet gevonden — upload het via het paneel hierboven.")

    if frames:
        lonen_bank_df = pd.concat(frames, ignore_index=True)
    else:
        st.info("Upload minstens één SD Worx Excel-bestand via de panelen hierboven.")

    # ── Leveranciersfacturen uit Odoo ───────────────────────────────────────
    try:
        facturen_raw = laad_leveranciersfacturen()
        if facturen_raw:
            # Drempel per partner: dag ≤ drempel → factuur hoort bij vorige maand
            # De Cock Gert: factureert altijd begin volgende maand (t/m dag 25)
            # Atipica: factureert op de 1e van de volgende maand
            PARTNER_DREMPEL = {"De Cock Gert": 25, "Atipica": 1}

            items_per_partner = {}
            for fac in sorted(facturen_raw, key=lambda x: (x["partner_id"][1] if isinstance(x["partner_id"], list) else "", x["invoice_date"])):
                d = pd.Timestamp(fac["invoice_date"])
                partner = fac["partner_id"][1] if isinstance(fac["partner_id"], list) else ""
                drempel = PARTNER_DREMPEL.get(partner, 0)
                if d.day <= drempel:
                    maand = pd.Period((d - pd.offsets.MonthEnd(1)).strftime("%Y-%m"), freq="M")
                else:
                    maand = pd.Period(d.strftime("%Y-%m"), freq="M")
                items_per_partner.setdefault(partner, []).append({
                    "d": d, "maand": maand, "partner_name": partner,
                    "functie": "Freelancer", "bedrag": float(fac["amount_untaxed"]),
                })

            # Sequentieel: resterende conflicten oplossen door latere factuur door te schuiven
            facturen_rows = []
            for partner, pinv in items_per_partner.items():
                for i in range(1, len(pinv)):
                    if pinv[i]["maand"] <= pinv[i - 1]["maand"]:
                        pinv[i]["maand"] = pinv[i - 1]["maand"] + 1
                facturen_rows.extend(pinv)

            df_fact = pd.DataFrame([{"maand": str(r["maand"]), "partner_name": r["partner_name"],
                                     "functie": r["functie"], "bedrag": r["bedrag"]} for r in facturen_rows])
            personen_fact = df_fact["partner_name"].nunique()
            st.caption(f"✅ Leveranciersfacturen (Odoo): {len(df_fact)} rijen, {personen_fact} personen")
            lonen_bank_df = pd.concat([lonen_bank_df, df_fact], ignore_index=True) if lonen_bank_df is not None else df_fact
    except Exception as e:
        st.error(f"Fout bij laden leveranciersfacturen: {e}")

    if lonen_bank_df is not None:
        st.divider()
        st.subheader("Rendabiliteit per segment vs. personeelskost")

        def _naar_periode(maand_str: str, granulariteit: str) -> str:
            p = pd.Period(maand_str, freq="M")
            if granulariteit == "Kwartaal":
                return f"{p.year}-K{p.quarter}"
            if granulariteit == "Jaar":
                return str(p.year)
            return maand_str

        alle_jaren = sorted(lonen_bank_df["maand"].str[:4].unique(), reverse=True)
        cg1, cg2 = st.columns([1, 2])
        with cg1:
            granulariteit = st.selectbox("Toon per", ["Maand", "Kwartaal", "Jaar"], key="rend_gran")
        with cg2:
            gekozen_jaren = st.multiselect("Jaar(en)", options=alle_jaren, default=alle_jaren, key="rend_jaren")

        alle_labels = sorted({
            lbl[len("klant:"):].strip()
            for rij in df["labels"]
            for lbl in rij
            if lbl.lower().startswith("klant:")
        }) + ["Hinkelspelwinkels", "Hinkelspel Markten"]
        alle_medewerkers = sorted(lonen_bank_df["partner_name"].dropna().unique())

        col_l, col_r = st.columns(2)
        with col_l:
            gekozen_labels = st.multiselect("Klantsegment(en)", options=alle_labels, default=alle_labels)
        with col_r:
            gekozen_medewerkers = st.multiselect("Medewerker(s)", options=alle_medewerkers, default=alle_medewerkers[:1] if alle_medewerkers else [])

        if gekozen_labels and gekozen_medewerkers and gekozen_jaren:
            hinkel = "Hinkelspelwinkels" in gekozen_labels
            hinkel_markten = "Hinkelspel Markten" in gekozen_labels
            label_selectie = [l for l in gekozen_labels if l not in ("Hinkelspelwinkels", "Hinkelspel Markten")]
            masker = df["labels"].apply(
                lambda lbls: any(
                    lbl[len("klant:"):].strip() in label_selectie
                    for lbl in lbls
                    if lbl.lower().startswith("klant:")
                )
            )
            if hinkel:
                masker = masker | df["partner_name"].str.lower().str.contains("hinkelspelwinkels", na=False)
            if hinkel_markten:
                masker = masker | df["partner_name"].str.lower().str.contains("hinkelspel markten", na=False)
            df_jaar_filter = df["maand"].str[:4].isin(gekozen_jaren)
            omzet_seg = df[masker & df_jaar_filter].copy()
            omzet_seg["Periode"] = omzet_seg["maand"].apply(lambda m: _naar_periode(m, granulariteit))
            omzet_seg = omzet_seg.groupby("Periode")["omzet"].sum().reset_index().rename(columns={"omzet": "Omzet (€)"})

            loon_jaar_filter = lonen_bank_df["maand"].str[:4].isin(gekozen_jaren)
            loon_gefilterd = lonen_bank_df[lonen_bank_df["partner_name"].isin(gekozen_medewerkers) & loon_jaar_filter].copy()
            loon_gefilterd["Periode"] = loon_gefilterd["maand"].apply(lambda m: _naar_periode(m, granulariteit))
            loon_seg = loon_gefilterd.groupby("Periode")["bedrag"].sum().reset_index().rename(columns={"bedrag": "Personeelskost (€)"})

            vergelijk = omzet_seg.merge(loon_seg, on="Periode", how="outer").fillna(0).sort_values("Periode")
            vergelijk["Marge (€)"] = vergelijk["Omzet (€)"] - vergelijk["Personeelskost (€)"]
            totaal_omzet = vergelijk["Omzet (€)"].sum()
            totaal_kost = vergelijk["Personeelskost (€)"].sum()
            totaal_marge = vergelijk["Marge (€)"].sum()

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Omzet", f"€ {totaal_omzet:,.0f}")
            c2.metric("Personeelskost", f"€ {totaal_kost:,.0f}")
            c3.metric("Marge", f"€ {totaal_marge:,.0f}")
            c4.metric("Rendabiliteit", f"{totaal_marge / totaal_omzet * 100:.1f}%" if totaal_omzet else "—")

            st.plotly_chart(
                px.bar(
                    vergelijk.melt(id_vars="Periode", value_vars=["Omzet (€)", "Personeelskost (€)", "Marge (€)"]),
                    x="Periode", y="value", color="variable", barmode="group",
                    labels={"value": "Bedrag (€)", "variable": ""},
                    title=f"Omzet [{', '.join(gekozen_labels)}] vs. loonkost [{', '.join(gekozen_medewerkers)}]",
                ).update_yaxes(tickprefix="€ ", tickformat=",.0f"),
                use_container_width=True,
            )

            vergelijk["Kost/Omzet (%)"] = vergelijk.apply(lambda r: r["Personeelskost (€)"] / r["Omzet (€)"] * 100 if r["Omzet (€)"] else 0, axis=1)
            vergelijk["Rendabiliteit (%)"] = vergelijk.apply(lambda r: r["Marge (€)"] / r["Omzet (€)"] * 100 if r["Omzet (€)"] else 0, axis=1)
            st.dataframe(
                vergelijk.style.format({"Omzet (€)": "€ {:,.0f}", "Personeelskost (€)": "€ {:,.0f}", "Marge (€)": "€ {:,.0f}", "Kost/Omzet (%)": "{:.1f}%", "Rendabiliteit (%)": "{:.1f}%"}),
                use_container_width=True, hide_index=True,
            )
        else:
            st.info("Selecteer minstens één segment, één medewerker en één jaar.")

        st.divider()
        with st.expander("Totaal per maand"):
            maand_ovz = lonen_bank_df.groupby("maand").agg(totaal=("bedrag", "sum"), werknemers=("partner_name", lambda x: ", ".join(sorted(x.dropna().unique())))).reset_index().sort_values("maand").rename(columns={"maand": "Maand", "totaal": "Totaal (€)", "werknemers": "Werknemers"})
            st.dataframe(maand_ovz.style.format({"Totaal (€)": "€ {:,.0f}"}), use_container_width=True, hide_index=True)

        with st.expander("Totaal per functie per maand"):
            fovz = lonen_bank_df.groupby(["functie", "maand"])["bedrag"].sum().reset_index().pivot(index="functie", columns="maand", values="bedrag").fillna(0)
            fovz["Totaal"] = fovz.sum(axis=1)
            st.dataframe(fovz.sort_values("Totaal", ascending=False).style.format("€ {:,.0f}"), use_container_width=True)

        with st.expander("Detail per werknemer"):
            st.dataframe(
                lonen_bank_df.rename(columns={"maand": "Maand", "partner_name": "Werknemer", "functie": "Functie", "bedrag": "Bedrag (€)"})
                .sort_values(["Maand", "Functie", "Werknemer"]).style.format({"Bedrag (€)": "€ {:,.0f}"}),
                use_container_width=True, hide_index=True,
            )

    st.divider()
    werknemers_raw = laad_werknemers()

    if not werknemers_raw:
        st.warning("Geen werknemers gevonden. Controleer of de HR-module actief is in Odoo.")
    else:
        wdf = pd.DataFrame(werknemers_raw)
        wdf["functie"] = wdf["job_id"].apply(lambda x: x[1] if isinstance(x, list) else (x or ""))
        wdf["afdeling"] = wdf["department_id"].apply(lambda x: x[1] if isinstance(x, list) else (x or ""))
        wdf["functietitel"] = wdf["job_title"].apply(lambda x: x if isinstance(x, str) else "")
        wdf = wdf[["name", "functie", "functietitel", "afdeling"]].rename(columns={
            "name": "Werknemer", "functie": "Functie", "functietitel": "Functietitel", "afdeling": "Afdeling"
        })

        col1, col2, col3 = st.columns(3)
        col1.metric("Aantal werknemers", len(wdf))
        col2.metric("Aantal functies", wdf["Functie"].nunique())
        col3.metric("Aantal afdelingen", wdf["Afdeling"].nunique())

        st.divider()

        filter_afd = st.selectbox("Filter op afdeling", options=["Alle"] + sorted(wdf["Afdeling"].unique().tolist()))
        weergave = wdf if filter_afd == "Alle" else wdf[wdf["Afdeling"] == filter_afd]
        st.dataframe(weergave.sort_values(["Afdeling", "Functie", "Werknemer"]), use_container_width=True, hide_index=True)

        with st.expander("Werknemers per afdeling"):
            st.dataframe(
                wdf.groupby("Afdeling").agg(werknemers=("Werknemer", "count")).reset_index()
                .rename(columns={"werknemers": "Werknemers"})
                .sort_values("Werknemers", ascending=False),
                use_container_width=True, hide_index=True,
            )

# ── Tab 10: Eigen Productie ─────────────────────────────────────────────────
with tab10:
    st.header("Omzet Eigen Productie")

    try:
        ep_raw = laad_omzet_eigen_productie()
    except Exception as e:
        st.error(f"Fout bij laden eigen productie data: {e}")
        ep_raw = []

    if not ep_raw:
        st.info("Geen data beschikbaar.")
    else:
        ep_df = pd.DataFrame([{
            "maand": r["date"][:7],
            "merk": r["merk"],
            "hogere_categorie": r["hogere_categorie"],
            "omzet": float(r["price_subtotal"]),
        } for r in ep_raw if r.get("date")])

        alle_ep_jaren = sorted(ep_df["maand"].str[:4].unique(), reverse=True)
        cep1, cep2 = st.columns([1, 2])
        with cep1:
            ep_gran = st.selectbox("Toon per", ["Maand", "Kwartaal", "Jaar"], key="ep_gran")
        with cep2:
            ep_jaren = st.multiselect("Jaar(en)", alle_ep_jaren, default=alle_ep_jaren, key="ep_jaren")

        def _ep_periode(maand_str, gran):
            p = pd.Period(maand_str, freq="M")
            if gran == "Kwartaal":
                return f"{p.year}-K{p.quarter}"
            if gran == "Jaar":
                return str(p.year)
            return maand_str

        ep_filtered = ep_df[ep_df["maand"].str[:4].isin(ep_jaren)].copy()
        ep_filtered["Periode"] = ep_filtered["maand"].apply(lambda m: _ep_periode(m, ep_gran))

        # Totaalcijfers
        totaal_ep = ep_filtered["omzet"].sum()
        totaal_geit = ep_filtered[ep_filtered["hogere_categorie"] == "Geitenmelk"]["omzet"].sum()
        totaal_koe = ep_filtered[ep_filtered["hogere_categorie"] == "Koemelk"]["omzet"].sum()
        mc1, mc2, mc3 = st.columns(3)
        mc1.metric("Totaal eigen productie", f"€ {totaal_ep:,.0f}")
        mc2.metric("Geitenmelk", f"€ {totaal_geit:,.0f}")
        mc3.metric("Koemelk", f"€ {totaal_koe:,.0f}")

        st.divider()

        # Hogere categorie
        st.subheader("Per hogere categorie")
        cat_df = ep_filtered.groupby(["Periode", "hogere_categorie"])["omzet"].sum().reset_index()
        st.plotly_chart(
            px.bar(
                cat_df, x="Periode", y="omzet", color="hogere_categorie", barmode="stack",
                labels={"omzet": "Omzet (€)", "hogere_categorie": "Categorie"},
                title="Omzet eigen productie per hogere categorie",
            ).update_yaxes(tickprefix="€ ", tickformat=",.0f"),
            use_container_width=True,
        )

        st.divider()

        # Per merk
        st.subheader("Per merk")
        merk_df = ep_filtered.groupby(["Periode", "merk", "hogere_categorie"])["omzet"].sum().reset_index()
        st.plotly_chart(
            px.bar(
                merk_df, x="Periode", y="omzet", color="merk", barmode="stack",
                facet_row="hogere_categorie",
                labels={"omzet": "Omzet (€)", "merk": "Merk", "hogere_categorie": ""},
                title="Omzet per merk",
            ).update_yaxes(tickprefix="€ ", tickformat=",.0f"),
            use_container_width=True,
        )

        st.divider()

        with st.expander("Overzicht per merk per periode"):
            pivot_ep = ep_filtered.pivot_table(
                index="merk", columns="Periode", values="omzet", aggfunc="sum", fill_value=0
            )
            pivot_ep.insert(0, "Categorie", ep_filtered.groupby("merk")["hogere_categorie"].first())
            pivot_ep["Totaal"] = pivot_ep.drop(columns="Categorie").sum(axis=1)
            st.dataframe(
                pivot_ep.sort_values(["Categorie", "Totaal"], ascending=[True, False])
                .style.format({c: "€ {:,.0f}" for c in pivot_ep.columns if c != "Categorie"}),
                use_container_width=True,
            )

        st.divider()
        st.subheader("Rendabiliteit eigen productie vs. personeelskost")

        if lonen_bank_df is None:
            st.info("Upload SD Worx loonbestanden in het tabblad 'Personeelskosten' om personeelskosten te vergelijken.")
        else:
            alle_ep_mw = sorted(lonen_bank_df["partner_name"].dropna().unique())
            gekozen_ep_mw = st.multiselect("Medewerker(s)", options=alle_ep_mw, default=[], key="ep_mw")

            if gekozen_ep_mw:
                omzet_agg = ep_filtered.groupby("Periode")["omzet"].sum().reset_index().rename(columns={"omzet": "Omzet (€)"})

                loon_ep = lonen_bank_df[
                    lonen_bank_df["partner_name"].isin(gekozen_ep_mw) &
                    lonen_bank_df["maand"].str[:4].isin(ep_jaren)
                ].copy()
                loon_ep["Periode"] = loon_ep["maand"].apply(lambda m: _ep_periode(m, ep_gran))
                loon_agg = loon_ep.groupby("Periode")["bedrag"].sum().reset_index().rename(columns={"bedrag": "Personeelskost (€)"})

                vgl_ep = omzet_agg.merge(loon_agg, on="Periode", how="outer").fillna(0).sort_values("Periode")
                vgl_ep["Marge (€)"] = vgl_ep["Omzet (€)"] - vgl_ep["Personeelskost (€)"]

                tot_o = vgl_ep["Omzet (€)"].sum()
                tot_k = vgl_ep["Personeelskost (€)"].sum()
                tot_m = vgl_ep["Marge (€)"].sum()

                r1, r2, r3, r4 = st.columns(4)
                r1.metric("Omzet EP", f"€ {tot_o:,.0f}")
                r2.metric("Personeelskost", f"€ {tot_k:,.0f}")
                r3.metric("Marge", f"€ {tot_m:,.0f}")
                r4.metric("Rendabiliteit", f"{tot_m / tot_o * 100:.1f}%" if tot_o else "—")

                st.plotly_chart(
                    px.bar(
                        vgl_ep.melt(id_vars="Periode", value_vars=["Omzet (€)", "Personeelskost (€)", "Marge (€)"]),
                        x="Periode", y="value", color="variable", barmode="group",
                        labels={"value": "Bedrag (€)", "variable": ""},
                        title=f"Eigen productie omzet vs. loonkost [{', '.join(gekozen_ep_mw)}]",
                    ).update_yaxes(tickprefix="€ ", tickformat=",.0f"),
                    use_container_width=True,
                )

                vgl_ep["Kost/Omzet (%)"] = vgl_ep.apply(
                    lambda r: r["Personeelskost (€)"] / r["Omzet (€)"] * 100 if r["Omzet (€)"] else 0, axis=1
                )
                vgl_ep["Rendabiliteit (%)"] = vgl_ep.apply(
                    lambda r: r["Marge (€)"] / r["Omzet (€)"] * 100 if r["Omzet (€)"] else 0, axis=1
                )
                st.dataframe(
                    vgl_ep.style.format({
                        "Omzet (€)": "€ {:,.0f}",
                        "Personeelskost (€)": "€ {:,.0f}",
                        "Marge (€)": "€ {:,.0f}",
                        "Kost/Omzet (%)": "{:.1f}%",
                        "Rendabiliteit (%)": "{:.1f}%",
                    }),
                    use_container_width=True, hide_index=True,
                )
            else:
                st.info("Selecteer minstens één medewerker.")


