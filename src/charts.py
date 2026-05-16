import plotly.express as px
import pandas as pd


def lijndiagram(df: pd.DataFrame, geselecteerde_partners: list) -> px.line:
    gefilterd = df[df["partner_name"].isin(geselecteerde_partners)]
    fig = px.line(
        gefilterd,
        x="maand",
        y="omzet",
        color="partner_name",
        markers=True,
        title="Omzetevolutie per klant per maand",
        labels={"maand": "Maand", "omzet": "Omzet (€)", "partner_name": "Klant"},
    )
    fig.update_layout(xaxis_tickangle=-45, legend_title_text="Klant")
    return fig


def staafdiagram(df: pd.DataFrame, geselecteerde_partners: list) -> px.bar:
    gefilterd = df[df["partner_name"].isin(geselecteerde_partners)]
    fig = px.bar(
        gefilterd,
        x="partner_name",
        y="omzet",
        title="Totale omzet per klant",
        labels={"partner_name": "Klant", "omzet": "Omzet (€)"},
        color="partner_name",
    )
    fig.update_layout(showlegend=False, xaxis_tickangle=-45)
    return fig
