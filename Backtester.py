from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pandas as pd


ROOT = Path(__file__).resolve().parent
DEFAULT_CSV_PATH = ROOT / "cbb_data.csv"
DEFAULT_TABLE_PATH = ROOT / "negative_correlations_tables.json"


def probability_to_american(probability: float) -> float:
    if not 0 < probability < 1:
        raise ValueError(f"Probability must be between 0 and 1, got {probability}.")
    if probability > 0.5:
        return -100 * probability / (1 - probability)
    return 100 * (1 - probability) / probability


def american_to_probability(american_odds: float) -> float:
    if american_odds == 0:
        raise ValueError("American odds cannot be 0.")
    if american_odds > 0:
        return 100 / (american_odds + 100)
    abs_odds = abs(american_odds)
    return abs_odds / (abs_odds + 100)


def clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    cleaned = df.copy()
    cleaned.columns = cleaned.columns.str.replace(r"\s+", " ", regex=True).str.strip()
    return cleaned


def load_favorite_games(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df = clean_columns(df)

    numeric_columns = [
        "CLOSING SPREAD",
        "CLOSING TOTAL",
        "Team W/L (1/0)",
        "Team ML + Opp Team Over Win/Loss (1/0)",
    ]
    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    df["DATE"] = pd.to_datetime(df["DATE"], errors="coerce")

    favorite_rows = df[df["CLOSING SPREAD"] < 0].copy()
    games = (
        favorite_rows.groupby("GAME-ID", as_index=False)
        .agg(
            DATE=("DATE", "first"),
            FAVORITE=("TEAM", "first"),
            closing_spread=("CLOSING SPREAD", "first"),
            closing_total=("CLOSING TOTAL", "first"),
            actual_outcome=("Team ML + Opp Team Over Win/Loss (1/0)", "first"),
        )
        .sort_values(["DATE", "GAME-ID"])
        .reset_index(drop=True)
    )
    return games.dropna(subset=["closing_spread", "closing_total", "actual_outcome"])


@dataclass(frozen=True)
class BucketDefinition:
    label: str
    lower: float | None
    upper: float | None

    def contains(self, value: float) -> bool:
        lower_ok = True if self.lower is None else value > self.lower
        upper_ok = True if self.upper is None else value <= self.upper
        return lower_ok and upper_ok


SPREAD_BUCKETS = {
    "v1": [
        BucketDefinition("-9 and above", None, -9),
        BucketDefinition("-5 to -8.5", -9, -5),
        BucketDefinition("-1 to -4.5", -5, -1),
    ],
    "v2": [
        BucketDefinition("-12 and above", None, -12),
        BucketDefinition("-8 to -11.5", -12, -8),
        BucketDefinition("-4 to -7.5", -8, -4),
        BucketDefinition("-1 to -3.5", -4, -1),
    ],
}

TOTAL_BUCKETS = {
    "v1": [
        BucketDefinition("144.5 and below", None, 144.5),
        BucketDefinition("145 to 157.5", 144.5, 157.5),
        BucketDefinition("158 and above", 157.5, None),
    ],
    "v2": [
        BucketDefinition("148.5 and below", None, 148.5),
        BucketDefinition("149 to 153.5", 148.5, 153.5),
        BucketDefinition("153.5 and above", 153.5, None),
    ],
}


def load_probability_lookup(table_path: Path) -> dict[str, dict[str, float]]:
    raw = json.loads(table_path.read_text())
    lookup: dict[str, dict[str, float]] = {}

    for section, rows in raw.items():
        section_lookup: dict[str, float] = {}
        for row in rows:
            numerator = next(value for key, value in row.items() if "plus_opp_over" in key)
            denominator = row["total_fav_wins"]
            label = row.get("spread_bucket", row.get("total_bucket"))
            section_lookup[label] = numerator / denominator
        lookup[section] = section_lookup

    return lookup


class FavoriteOppOverBucketModel:
    def __init__(
        self,
        table_path: Path = DEFAULT_TABLE_PATH,
        spread_version: str = "v2",
        total_version: str = "v2",
        combine: str = "average",
    ) -> None:
        if spread_version not in SPREAD_BUCKETS:
            raise ValueError(f"Unsupported spread version: {spread_version}")
        if total_version not in TOTAL_BUCKETS:
            raise ValueError(f"Unsupported total version: {total_version}")
        if combine not in {"average", "spread_only", "total_only"}:
            raise ValueError(f"Unsupported combine mode: {combine}")

        self.spread_version = spread_version
        self.total_version = total_version
        self.combine = combine
        self.lookup = load_probability_lookup(table_path)

    def _find_bucket_label(
        self,
        value: float,
        buckets: list[BucketDefinition],
        kind: str,
    ) -> str:
        for bucket in buckets:
            if bucket.contains(value):
                return bucket.label
        raise ValueError(f"Could not map {kind} value {value} to a bucket.")

    def predict_probability(self, spread: float, total: float) -> float:
        spread_label = self._find_bucket_label(spread, SPREAD_BUCKETS[self.spread_version], "spread")
        total_label = self._find_bucket_label(total, TOTAL_BUCKETS[self.total_version], "total")

        spread_probability = self.lookup[f"spread_buckets_{self.spread_version}"][spread_label]
        total_probability = self.lookup[f"total_buckets_{self.total_version}"][total_label]

        if self.combine == "spread_only":
            return spread_probability
        if self.combine == "total_only":
            return total_probability
        return (spread_probability + total_probability) / 2

    def predict_american_odds(self, spread: float, total: float) -> float:
        return probability_to_american(self.predict_probability(spread, total))


def log_loss(actual: pd.Series, predicted: pd.Series) -> float:
    clipped = predicted.clip(lower=1e-9, upper=1 - 1e-9)
    losses = -(actual * clipped.map(math.log) + (1 - actual) * (1 - clipped).map(math.log))
    return float(losses.mean())


def build_calibration_table(results: pd.DataFrame, max_buckets: int = 10) -> pd.DataFrame:
    unique_predictions = results["predicted_probability"].nunique()
    bucket_count = min(max_buckets, unique_predictions)
    if bucket_count <= 1:
        calibration = results.copy()
        calibration["prediction_bucket"] = "all"
    else:
        calibration = results.copy()
        calibration["prediction_bucket"] = pd.qcut(
            calibration["predicted_probability"],
            q=bucket_count,
            duplicates="drop",
        )

    grouped = (
        calibration.groupby("prediction_bucket", observed=False)
        .agg(
            games=("GAME-ID", "size"),
            avg_predicted_probability=("predicted_probability", "mean"),
            actual_hit_rate=("actual_outcome", "mean"),
            avg_fair_odds=("predicted_fair_odds", "mean"),
        )
        .reset_index()
    )
    return grouped


def run_backtest(
    predict_fn: Callable[[float, float], float],
    csv_path: Path = DEFAULT_CSV_PATH,
) -> tuple[pd.DataFrame, dict[str, float], pd.DataFrame]:
    games = load_favorite_games(csv_path)

    results = games.copy()
    results["predicted_fair_odds"] = results.apply(
        lambda row: predict_fn(row["closing_spread"], row["closing_total"]),
        axis=1,
    )
    results["predicted_probability"] = results["predicted_fair_odds"].apply(american_to_probability)
    results["actual_outcome"] = results["actual_outcome"].astype(int)
    results["correct_direction"] = (
        (results["predicted_probability"] >= 0.5) == (results["actual_outcome"] == 1)
    ).astype(int)

    metrics = {
        "games": float(len(results)),
        "actual_hit_rate": float(results["actual_outcome"].mean()),
        "avg_predicted_probability": float(results["predicted_probability"].mean()),
        "avg_fair_odds": float(results["predicted_fair_odds"].mean()),
        "brier_score": float(
            ((results["predicted_probability"] - results["actual_outcome"]) ** 2).mean()
        ),
        "log_loss": log_loss(results["actual_outcome"], results["predicted_probability"]),
    }

    calibration = build_calibration_table(results)
    return results, metrics, calibration


def print_report(metrics: dict[str, float], calibration: pd.DataFrame) -> None:
    print("=== Fair American Odds Backtest ===")
    print(f"Games: {int(metrics['games'])}")
    print(f"Actual hit rate: {metrics['actual_hit_rate']:.4f}")
    print(f"Average predicted probability: {metrics['avg_predicted_probability']:.4f}")
    print(f"Average fair American odds: {metrics['avg_fair_odds']:.2f}")
    print(f"Brier score: {metrics['brier_score']:.4f}")
    print(f"Log loss: {metrics['log_loss']:.4f}")
    print("\nCalibration:")
    print(calibration.to_string(index=False))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Backtest a function that maps closing spread and closing total "
            "to fair American odds for Favorite ML + Opponent Over."
        )
    )
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV_PATH, help="Path to cbb_data.csv")
    parser.add_argument(
        "--tables",
        type=Path,
        default=DEFAULT_TABLE_PATH,
        help="Path to negative_correlations_tables.json",
    )
    parser.add_argument(
        "--spread-version",
        choices=sorted(SPREAD_BUCKETS.keys()),
        default="v2",
        help="Spread bucket version to use in the default predictor.",
    )
    parser.add_argument(
        "--total-version",
        choices=sorted(TOTAL_BUCKETS.keys()),
        default="v2",
        help="Total bucket version to use in the default predictor.",
    )
    parser.add_argument(
        "--combine",
        choices=["average", "spread_only", "total_only"],
        default="average",
        help="How to combine spread-based and total-based probabilities.",
    )
    parser.add_argument(
        "--save-results",
        type=Path,
        default=None,
        help="Optional path to save per-game backtest results as CSV.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    model = FavoriteOppOverBucketModel(
        table_path=args.tables,
        spread_version=args.spread_version,
        total_version=args.total_version,
        combine=args.combine,
    )

    results, metrics, calibration = run_backtest(
        predict_fn=model.predict_american_odds,
        csv_path=args.csv,
    )

    if args.save_results is not None:
        results.to_csv(args.save_results, index=False)
        print(f"Saved per-game results to {args.save_results}")

    print_report(metrics, calibration)


if __name__ == "__main__":
    main()
