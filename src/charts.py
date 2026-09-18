import plotly.express as px
import pandas as pd

PLOTLY_KLEUREN = px.colors.qualitative.Plotly


def _stijl(fig):
    return (
        fig.update_layout(
            template="plotly_white",
            font_family="Arial, sans-serif",
            title_font_size=15,
            hoverlabel=dict(bgcolor="white", font_size=13),
            margin=dict(t=60, b=50, l=60, r=20),
        )
        .update_yaxes(gridcolor="#efefef")
        .update_xaxes(showgrid=False)
    )


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
        color_discrete_sequence=PLOTLY_KLEUREN,
    )
    fig.update_layout(xaxis_tickangle=-45, legend_title_text="Klant")
    fig.update_yaxes(tickprefix="€ ", tickformat=",.0f")
    return _stijl(fig)


def staafdiagram(df: pd.DataFrame, geselecteerde_partners: list) -> px.bar:
    gefilterd = df[df["partner_name"].isin(geselecteerde_partners)]
    fig = px.bar(
        gefilterd,
        x="partner_name",
        y="omzet",
        title="Totale omzet per klant",
        labels={"partner_name": "Klant", "omzet": "Omzet (€)"},
        color="partner_name",
        color_discrete_sequence=PLOTLY_KLEUREN,
        text_auto=".3s",
    )
    fig.update_layout(showlegend=False, xaxis_tickangle=-45)
    fig.update_yaxes(tickprefix="€ ", tickformat=",.0f")
    return _stijl(fig)
