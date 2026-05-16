import json
import os

DOELSTELLINGEN_PAD = os.path.join(os.path.dirname(__file__), "..", "data", "doelstellingen.json")


def laad_doelstellingen() -> dict:
    if os.path.exists(DOELSTELLINGEN_PAD):
        with open(DOELSTELLINGEN_PAD, "r") as f:
            return json.load(f)
    return {"totaal": 0, "per_klant": {}}


def sla_doelstellingen_op(doelstellingen: dict):
    os.makedirs(os.path.dirname(DOELSTELLINGEN_PAD), exist_ok=True)
    with open(DOELSTELLINGEN_PAD, "w") as f:
        json.dump(doelstellingen, f, indent=2)
