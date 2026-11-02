"""Reconstruct one-month-ahead forecasts using only history before each target."""
import json
from pathlib import Path
from statistics import mean

from statistical_outlook import outlook

SOURCE = Path(__file__).resolve().parents[1] / "docs/evidence/monthly-evidence.json"


def score(history):
    errors = {"seasonal_naive": [], "holt_winters": []}
    actuals = []
    for i, row in enumerate(history):
        if not "2026-01-01" <= row["month"] <= "2026-09-01":
            continue
        estimate = outlook(history[:i])["next_month"]
        if estimate["target"] != row["month"]:
            raise ValueError("Forecast target does not match the held-out observation.")
        actual = int(row["bottles"])
        actuals.append(actual)
        for model, values in errors.items():
            values.append(abs(estimate[model] - actual))
    if len(actuals) != 9:
        raise ValueError("Expected all nine held-out months.")
    return {model: {"months": len(values), "mae_bottles": round(mean(values), 2),
                    "wape_pct": round(100 * sum(values) / sum(map(abs, actuals)), 4)}
            for model, values in errors.items()}


if __name__ == "__main__":
    print(json.dumps(score(json.loads(SOURCE.read_text())["bottle_history"]), indent=2))
