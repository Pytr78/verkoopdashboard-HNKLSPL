import os
import streamlit as st
import pandas as pd
import io
import plotly.express as px
from src.odoo_client import fetch_invoices, fetch_partner_info, fetch_betaalde_facturen, fetch_employees, fetch_personeelskosten
from src.data_processing import invoices_to_dataframe, omzet_per_partner_per_maand, omzet_per_partner_totaal
from src.charts import lijndiagram, staafdiagram
from src.management_summary import bereken_samenvatting
from src.rfm import bereken_rfm, SEGMENTEN
from src.doelstellingen import laad_doelstellingen, sla_doelstellingen_op
from src.betalingsanalyse import bereken_betaaldagen, CATEGORIEEN
from src.actiepunten import genereer_actiepunten
from src.cashflow import bereken_cashflow_prognose, cashflow_per_periode

st.set_page_config(page_title="Verkoopdashboard HNKLSPL", page_icon="📊", layout="wide")

# --- Toegangsbeveiliging ---
def check_wachtwoord():
    juist_wachtwoord = st.secrets.get("auth", {}).get("password") or os.getenv("DASHBOARD_PASSWORD", "")
    if not juist_wachtwoord:
        return True  # geen wachtwoord ingesteld, vrije toegang
    if st.session_state.get("ingelogd"):
        return True
    st.title("Verkoopdashboard HNKLSPL")
    with st.form("login"):
        ww = st.text_input("Wachtwoord", type="password")
        if st.form_submit_button("Inloggen"):
            if ww == juist_wachtwoord:
                st.session_state["ingelogd"] = True
                st.rerun()
            else:
                st.error("Ongeldig wachtwoord.")
    return False

if not check_wachtwoord():
    st.stop()

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
geselecteerde_partners = st.sidebar.multiselect("Selecteer klanten", options=alle_partners, default=alle_partners[:10])

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
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = st.tabs([
    "🚨 Actiepunten",
    "🎯 Doelstellingen",
    "📊 Grafieken",
    "📈 Omzettrends",
    "👥 Klantsegmentatie",
    "💳 Betalingsgedrag",
    "💰 Cashflow",
    "🏷️ Segmentatie per label",
    "👷 Personeelskosten",
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

    klanten_zonder_label = (
        df_labels[df_labels["labels"].apply(lambda x: len(x) == 0)]
        .groupby("partner_name")
        .agg(omzet=("omzet", "sum"), email=("email", "first"))
        .reset_index()
        .sort_values("omzet", ascending=False)
        .rename(columns={"partner_name": "Klant", "omzet": "Omzet (€)", "email": "E-mail"})
    )
    if not klanten_zonder_label.empty:
        with st.expander(f"⚠️ {len(klanten_zonder_label)} klanten zonder 'klant:'-label", expanded=True):
            st.caption("Deze klanten hebben geen label dat begint met 'klant:' in Odoo.")
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
    st.caption("Overzicht werknemers per functie en loonkosten via rekening 'Te betalen Lonen'")

    loon_raw = laad_personeelskosten()
    if loon_raw:
        loon_df = pd.DataFrame(loon_raw)
        loon_df["date"] = pd.to_datetime(loon_df["date"])
        loon_df["jaar"] = loon_df["date"].dt.year
        loon_df["maand"] = loon_df["date"].dt.to_period("M").astype(str)
        loon_df["partner"] = loon_df["partner_id"].apply(lambda x: x[1] if isinstance(x, list) else "")
        loon_df["rekening"] = loon_df["account_id"].apply(lambda x: x[1] if isinstance(x, list) else "")
        loon_df["type"] = loon_df["rekening"].apply(
            lambda r: "Bezoldigingen vennoten" if "bezoldiging" in r.lower() else "Lonen personeel"
        )

        huidig_jaar = pd.Timestamp.now().year
        totaal = loon_df["debit"].sum()
        lonen = loon_df[loon_df["type"] == "Lonen personeel"]["debit"].sum()
        bezoldigingen = loon_df[loon_df["type"] == "Bezoldigingen vennoten"]["debit"].sum()
        huidig_jaar_totaal = loon_df[loon_df["jaar"] == huidig_jaar]["debit"].sum()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Totaal personeelskosten", f"€ {totaal:,.0f}")
        c2.metric(f"Totaal {huidig_jaar}", f"€ {huidig_jaar_totaal:,.0f}")
        c3.metric("Lonen personeel", f"€ {lonen:,.0f}")
        c4.metric("Bezoldigingen vennoten", f"€ {bezoldigingen:,.0f}")

        st.divider()

        kost_per_jaar = (
            loon_df.groupby(["jaar", "type"])["debit"].sum().reset_index()
            .rename(columns={"jaar": "Jaar", "type": "Type", "debit": "Bedrag (€)"})
        )
        kost_per_jaar["Jaar"] = kost_per_jaar["Jaar"].astype(str)
        st.plotly_chart(
            px.bar(kost_per_jaar, x="Jaar", y="Bedrag (€)", color="Type", barmode="group",
                   text_auto=".3s", title="Personeelskosten per jaar"
                   ).update_yaxes(tickprefix="€ ", tickformat=",.0f"),
            use_container_width=True,
        )

        with st.expander("Detail boekingen"):
            st.dataframe(
                loon_df[["date", "maand", "type", "partner", "name", "debit", "rekening"]]
                .rename(columns={"date": "Datum", "maand": "Maand", "type": "Type", "partner": "Tegenpartij",
                                 "name": "Omschrijving", "debit": "Bedrag (€)", "rekening": "Rekening"})
                .sort_values("Datum", ascending=False)
                .style.format({"Bedrag (€)": "€ {:,.0f}"}),
                use_container_width=True, hide_index=True,
            )
    else:
        st.info("Geen boekingen gevonden op 'Te betalen Lonen' of 'Te betalen Bezoldigingen'. Controleer de rekeningnamen in Odoo.")

    st.divider()
    werknemers_raw = laad_werknemers()

    if not werknemers_raw:
        st.warning("Geen werknemers gevonden. Controleer of de HR-module actief is in Odoo.")
    else:
        wdf = pd.DataFrame(werknemers_raw)
        wdf["functie"] = wdf["job_id"].apply(lambda x: x[1] if isinstance(x, list) else (x or ""))
        wdf["afdeling"] = wdf["department_id"].apply(lambda x: x[1] if isinstance(x, list) else (x or ""))
        wdf["functietitel"] = wdf["job_title"].fillna("")
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

    st.divider()
    st.subheader("Rendabiliteit winkelpersoneel vs. Hinkelspelwinkels")
    st.caption("Personeelskost = netto loon uit banktransacties, verdeeld naar aandeel van de geselecteerde functie in het totaal personeelsbestand")

    if not loon_raw or not werknemers_raw:
        st.info("Loondata of werknemersdata ontbreekt.")
    else:
        # Klantsegmenten op basis van klant:-labels
        df_labels = df.copy()
        df_labels["klant_label"] = df_labels["labels"].apply(
            lambda xs: [x[len("klant:"):].strip() for x in xs if x.lower().startswith("klant:")]
        )
        alle_labels = sorted({l for ls in df_labels["klant_label"] for l in ls})

        alle_functies = sorted({
            e["job_id"][1] for e in werknemers_raw if isinstance(e.get("job_id"), list)
        })

        col_l, col_r = st.columns(2)
        gekozen_label = col_l.selectbox("Klantsegment (label)", options=alle_labels)
        gekozen_functie = col_r.selectbox("Personeelsfunctie", options=alle_functies)

        totaal_werknemers = len(werknemers_raw)
        aantal_functie = sum(
            1 for e in werknemers_raw
            if isinstance(e.get("job_id"), list) and e["job_id"][1] == gekozen_functie
        )
        ratio = aantal_functie / totaal_werknemers if totaal_werknemers > 0 else 0
        st.caption(f"{aantal_functie} van {totaal_werknemers} werknemers = **{ratio*100:.1f}%** van totale loonskost")

        # Maandelijkse loonkost enkel uit "Te betalen Lonen" (niet bezoldigingen vennoten)
        loon_personeel = [r for r in loon_raw if "bezoldiging" not in (
            r["account_id"][1] if isinstance(r.get("account_id"), list) else ""
        ).lower()]
        loon_maand = (
            pd.DataFrame(loon_personeel)
            .assign(maand=lambda d: pd.to_datetime(d["date"]).dt.to_period("M").astype(str))
            .groupby("maand")["debit"].sum()
            .reset_index()
        )
        loon_maand["Personeelskost (€)"] = loon_maand["debit"] * ratio
        loon_maand = loon_maand[["maand", "Personeelskost (€)"]].rename(columns={"maand": "Maand"})

        # Omzet voor gekozen klantsegment
        df_segment = df_labels[df_labels["klant_label"].apply(lambda ls: gekozen_label in ls)]
        omzet_segment = (
            df_segment.groupby("maand")["omzet"].sum()
            .reset_index()
            .rename(columns={"maand": "Maand", "omzet": "Omzet (€)"})
        )

        vergelijk_df = loon_maand.merge(omzet_segment, on="Maand", how="outer").fillna(0).sort_values("Maand")
        vergelijk_df["Marge (€)"] = vergelijk_df["Omzet (€)"] - vergelijk_df["Personeelskost (€)"]

        totaal_omzet = vergelijk_df["Omzet (€)"].sum()
        totaal_kost = vergelijk_df["Personeelskost (€)"].sum()
        totaal_marge = vergelijk_df["Marge (€)"].sum()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric(f"Omzet {gekozen_label}", f"€ {totaal_omzet:,.0f}")
        c2.metric(f"Loonskost {gekozen_functie}", f"€ {totaal_kost:,.0f}")
        c3.metric("Marge", f"€ {totaal_marge:,.0f}")
        c4.metric("Rendabiliteit", f"{totaal_marge / totaal_omzet * 100:.1f}%" if totaal_omzet else "—")

        st.plotly_chart(
            px.bar(
                vergelijk_df.melt(id_vars="Maand", value_vars=["Omzet (€)", "Personeelskost (€)", "Marge (€)"]),
                x="Maand", y="value", color="variable", barmode="group",
                labels={"value": "Bedrag (€)", "variable": "", "Maand": "Maand"},
                title=f"Omzet {gekozen_label} vs. loonskost {gekozen_functie}",
            ).update_yaxes(tickprefix="€ ", tickformat=",.0f"),
            use_container_width=True,
        )

        with st.expander("Detail per maand"):
            detail_df = vergelijk_df.copy()
            detail_df["Kost/Omzet (%)"] = detail_df.apply(
                lambda r: r["Personeelskost (€)"] / r["Omzet (€)"] * 100 if r["Omzet (€)"] != 0 else 0, axis=1
            )
            detail_df["Rendabiliteit (%)"] = detail_df.apply(
                lambda r: r["Marge (€)"] / r["Omzet (€)"] * 100 if r["Omzet (€)"] != 0 else 0, axis=1
            )
            st.dataframe(
                detail_df.style.format({
                    "Omzet (€)": "€ {:,.0f}",
                    "Personeelskost (€)": "€ {:,.0f}",
                    "Marge (€)": "€ {:,.0f}",
                    "Kost/Omzet (%)": "{:.1f}%",
                    "Rendabiliteit (%)": "{:.1f}%",
                }),
                use_container_width=True, hide_index=True,
            )
