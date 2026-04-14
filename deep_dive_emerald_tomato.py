from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

try:
    from statsmodels.tsa.stattools import coint
except Exception:  # pragma: no cover
    coint = None


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "TUTORIAL_ROUND_1 (1)"
BACKTEST_DIR = ROOT / "prosperity4" / "backtests"
REPORT_PATH = ROOT / "EMERALD_TOMATO_DEEP_DIVE.md"

PRODUCTS = ("EMERALDS", "TOMATOES")
DAYS = (-2, -1)


@dataclass
class RegressionResult:
    train_day: int
    test_day: int
    r2: float
    corr: float
    active_sign_acc: float
    active_nonzero_sign_acc: float
    active_frac: float
    coefficients: List[float]
    intercept: float


def load_prices() -> pd.DataFrame:
    frames = [pd.read_csv(path, sep=";") for path in sorted(DATA_DIR.glob("prices_round_0_day_*.csv"))]
    if not frames:
        raise FileNotFoundError(f"No price files found in {DATA_DIR}")
    return pd.concat(frames, ignore_index=True)


def load_trades() -> pd.DataFrame:
    frames = []
    for path in sorted(DATA_DIR.glob("trades_round_0_day_*.csv")):
        df = pd.read_csv(path, sep=";")
        df["day"] = int(path.stem.split("_")[-1])
        frames.append(df)
    if not frames:
        raise FileNotFoundError(f"No trade files found in {DATA_DIR}")
    trades = pd.concat(frames, ignore_index=True)
    return trades.rename(columns={"symbol": "product"})


def _pick_wall(row: pd.Series, side: str) -> Tuple[float, float]:
    levels: List[Tuple[float, float]] = []
    for level in (1, 2, 3):
        price_col = f"{side}_price_{level}"
        volume_col = f"{side}_volume_{level}"
        price = row[price_col]
        volume = row[volume_col]
        if pd.notna(price) and pd.notna(volume):
            levels.append((float(price), abs(float(volume))))
    if not levels:
        return np.nan, np.nan
    return max(levels, key=lambda item: item[1])


def prepare_books(prices: pd.DataFrame) -> pd.DataFrame:
    prepared: List[pd.DataFrame] = []
    for day in DAYS:
        for product in PRODUCTS:
            book = prices[(prices["day"] == day) & (prices["product"] == product)].copy()
            book = book.sort_values("timestamp").reset_index(drop=True)

            bid_wall_pairs = book.apply(lambda row: _pick_wall(row, "bid"), axis=1)
            ask_wall_pairs = book.apply(lambda row: _pick_wall(row, "ask"), axis=1)

            book["bid_wall_price"] = [pair[0] for pair in bid_wall_pairs]
            book["bid_wall_volume"] = [pair[1] for pair in bid_wall_pairs]
            book["ask_wall_price"] = [pair[0] for pair in ask_wall_pairs]
            book["ask_wall_volume"] = [pair[1] for pair in ask_wall_pairs]

            book["best_bid"] = book["bid_price_1"]
            book["best_ask"] = book["ask_price_1"]
            book["mid"] = book["mid_price"]
            book["spread"] = book["best_ask"] - book["best_bid"]
            book["wall_mid"] = (book["bid_wall_price"] + book["ask_wall_price"]) / 2.0
            book["gap"] = book["mid"] - book["wall_mid"]
            book["bid_inside"] = book["best_bid"] - book["bid_wall_price"]
            book["ask_inside"] = book["ask_wall_price"] - book["best_ask"]
            book["quote_state"] = book["bid_inside"].astype(str) + "/" + book["ask_inside"].astype(str)
            book["fair_int"] = book["wall_mid"].round().astype(int)
            book["quote_change"] = (
                book["best_bid"].diff().fillna(0).ne(0) | book["best_ask"].diff().fillna(0).ne(0)
            )
            book["next_mid_delta"] = book["mid"].shift(-1) - book["mid"]
            book["next_wall_delta"] = book["wall_mid"].shift(-1) - book["wall_mid"]
            book["mom1"] = book["mid"].diff().fillna(0)
            book["dw_prev"] = book["wall_mid"].diff().fillna(0)
            bid_v1 = book["bid_volume_1"].fillna(0)
            ask_v1 = book["ask_volume_1"].fillna(0)
            denom = bid_v1 + ask_v1
            book["imbalance_l1"] = np.where(denom > 0, (bid_v1 - ask_v1) / denom, 0.0)
            book["spread_narrow"] = (book["spread"] <= 9).astype(int)
            book["active_gap"] = (book["gap"].abs() >= 2).astype(int)
            prepared.append(book)
    return pd.concat(prepared, ignore_index=True)


def aggregate_trades(trades: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        trades.groupby(["day", "product", "timestamp"], as_index=False)
        .agg(
            trade_count=("price", "size"),
            trade_qty=("quantity", "sum"),
            trade_price_last=("price", "last"),
        )
        .sort_values(["day", "product", "timestamp"])
    )
    return grouped


def run_regression(train: pd.DataFrame, test: pd.DataFrame, features: Iterable[str], target: str) -> RegressionResult:
    feature_list = list(features)
    x_train = train[feature_list].to_numpy(dtype=float)
    y_train = train[target].to_numpy(dtype=float)
    x_test = test[feature_list].to_numpy(dtype=float)
    y_test = test[target].to_numpy(dtype=float)

    x_train_aug = np.column_stack([np.ones(len(x_train)), x_train])
    coeffs = np.linalg.lstsq(x_train_aug, y_train, rcond=None)[0]
    x_test_aug = np.column_stack([np.ones(len(x_test)), x_test])
    pred = x_test_aug @ coeffs

    ss_res = float(np.sum((y_test - pred) ** 2))
    ss_tot = float(np.sum((y_test - y_test.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot else np.nan
    corr = float(np.corrcoef(y_test, pred)[0, 1]) if np.std(pred) > 0 and np.std(y_test) > 0 else np.nan

    active = np.abs(pred) >= 0.5
    nonzero = y_test != 0

    def sign_acc(mask: np.ndarray) -> float:
        if mask.sum() == 0:
            return np.nan
        return float((np.sign(pred[mask]) == np.sign(y_test[mask])).mean())

    return RegressionResult(
        train_day=int(train["day"].iloc[0]),
        test_day=int(test["day"].iloc[0]),
        r2=float(r2),
        corr=float(corr),
        active_sign_acc=sign_acc(active),
        active_nonzero_sign_acc=sign_acc(active & nonzero),
        active_frac=float(active.mean()),
        coefficients=[float(value) for value in coeffs[1:]],
        intercept=float(coeffs[0]),
    )


def compute_run_stats(series: pd.Series) -> pd.DataFrame:
    runs: List[Tuple[int, int]] = []
    current = int(series.iloc[0])
    length = 1
    for value in series.iloc[1:]:
        value = int(value)
        if value == current:
            length += 1
        else:
            runs.append((current, length))
            current = value
            length = 1
    runs.append((current, length))
    run_df = pd.DataFrame(runs, columns=["state", "run"])
    return run_df.groupby("state")["run"].agg(["count", "mean", "median", "max"])


def format_table(df: pd.DataFrame, float_precision: int = 4) -> str:
    frame = df.copy()
    for column in frame.columns:
        if pd.api.types.is_float_dtype(frame[column]):
            frame[column] = frame[column].map(lambda value: f"{value:.{float_precision}f}" if pd.notna(value) else "nan")
    return "```\n" + frame.to_string() + "\n```"


def summarize_dataset(books: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame:
    trade_counts = trades.groupby(["day", "product"]).size().rename("trade_rows")
    summary_rows = []
    for (day, product), book in books.groupby(["day", "product"]):
        trade_rows = int(trade_counts.get((day, product), 0))
        summary_rows.append(
            {
                "day": day,
                "product": product,
                "book_rows": len(book),
                "trade_rows": trade_rows,
                "trade_tick_frac": trade_rows / len(book),
                "quote_change_frac": float(book["quote_change"].mean()),
                "spread_mean": float(book["spread"].mean()),
                "gap_abs_mean": float(book["gap"].abs().mean()),
            }
        )
    return pd.DataFrame(summary_rows).set_index(["day", "product"]).sort_index()


def emerald_tables(books: pd.DataFrame, trades: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    trade_price_counts = (
        trades[trades["product"] == "EMERALDS"]
        .groupby(["day", "price"])
        .size()
        .rename("count")
        .reset_index()
    )
    state_rows = []
    for day in DAYS:
        book = books[(books["day"] == day) & (books["product"] == "EMERALDS")]
        trade_counts = trade_price_counts[trade_price_counts["day"] == day]
        trade_summary = ", ".join(f"{int(price)}:{count}" for price, count in zip(trade_counts["price"], trade_counts["count"]))
        state_rows.append(
            {
                "day": day,
                "default_state_pct": float((book["quote_state"] == "2.0/2.0").mean()),
                "fair_touch_buy_pct": float((book["best_ask"] <= book["fair_int"]).mean()),
                "fair_touch_sell_pct": float((book["best_bid"] >= book["fair_int"]).mean()),
                "default_gap_corr_to_next_delta": float(book["gap"].corr(book["next_mid_delta"])),
                "trade_prices": trade_summary,
            }
        )
    state_table = pd.DataFrame(state_rows).set_index("day")
    response_table = (
        books[books["product"] == "EMERALDS"]
        .groupby("gap")["next_mid_delta"]
        .agg(["mean", "count"])
        .sort_index()
    )
    return state_table, response_table


def tomatoes_tables(books: pd.DataFrame) -> dict[str, pd.DataFrame]:
    tomato_books = books[books["product"] == "TOMATOES"].copy()

    summary_rows = []
    for day in DAYS:
        book = tomato_books[tomato_books["day"] == day]
        run_stats = compute_run_stats(book["active_gap"])
        summary_rows.append(
            {
                "day": day,
                "wall_start": float(book["wall_mid"].iloc[0]),
                "wall_end": float(book["wall_mid"].iloc[-1]),
                "wall_min": float(book["wall_mid"].min()),
                "wall_max": float(book["wall_mid"].max()),
                "wide_state_pct": float((book["spread_narrow"] == 0).mean()),
                "active_gap_pct": float(book["active_gap"].mean()),
                "active_run_mean": float(run_stats.loc[1, "mean"]),
                "inactive_run_mean": float(run_stats.loc[0, "mean"]),
                "gap_abs_mean": float(book["gap"].abs().mean()),
                "gap_to_next_delta_corr": float(book["gap"].corr(book["next_mid_delta"])),
            }
        )
    summary = pd.DataFrame(summary_rows).set_index("day")

    state_mix = (
        tomato_books.groupby(["day", "bid_inside", "ask_inside"])
        .size()
        .rename("count")
        .reset_index()
    )
    state_mix["pct"] = state_mix.groupby("day")["count"].transform(lambda value: value / value.sum())
    state_mix = (
        state_mix.sort_values(["day", "pct"], ascending=[True, False])
        .groupby("day")
        .head(6)
        .set_index(["day", "bid_inside", "ask_inside"])[["count", "pct"]]
    )

    gap_response = tomato_books.groupby("gap")["next_mid_delta"].agg(["mean", "count"]).sort_index()
    gap_response = gap_response[(gap_response["count"] >= 50) | (gap_response.index == 0)]

    spread_gap_response = (
        tomato_books.groupby(["spread_narrow", "gap"])["next_mid_delta"]
        .agg(["mean", "count"])
        .sort_index()
    )

    taker_rows = []
    for threshold in (2.0, 2.5, 3.0, 3.5, 4.0):
        subset = tomato_books[tomato_books["gap"].abs() >= threshold].dropna(subset=["next_mid_delta"])
        taker_rows.append(
            {
                "gap_threshold": threshold,
                "samples": len(subset),
                "avg_abs_next_mid_move": float(subset["next_mid_delta"].abs().mean()),
                "avg_spread": float(subset["spread"].mean()),
                "avg_move_minus_spread": float((subset["next_mid_delta"].abs() - subset["spread"]).mean()),
            }
        )
    taker_table = pd.DataFrame(taker_rows).set_index("gap_threshold")

    edge_rows = []
    for day in DAYS:
        book = tomato_books[tomato_books["day"] == day]
        buy_edges = (book["fair_int"] - book["best_ask"])[book["best_ask"] <= book["fair_int"]]
        sell_edges = (book["best_bid"] - book["fair_int"])[book["best_bid"] >= book["fair_int"]]
        edge_rows.append(
            {
                "day": day,
                "buy_opp_pct": float((book["best_ask"] <= book["fair_int"]).mean()),
                "sell_opp_pct": float((book["best_bid"] >= book["fair_int"]).mean()),
                "buy_edge_mean": float(buy_edges.mean()),
                "sell_edge_mean": float(sell_edges.mean()),
            }
        )
    edge_table = pd.DataFrame(edge_rows).set_index("day")

    regression_rows = []
    features = ["gap", "spread_narrow", "imbalance_l1", "mom1", "dw_prev"]
    for train_day, test_day in ((-2, -1), (-1, -2)):
        train = tomato_books[tomato_books["day"] == train_day].dropna(subset=["next_mid_delta"])
        test = tomato_books[tomato_books["day"] == test_day].dropna(subset=["next_mid_delta"])
        result = run_regression(train, test, features, "next_mid_delta")
        regression_rows.append(
            {
                "train_day": result.train_day,
                "test_day": result.test_day,
                "r2": result.r2,
                "corr": result.corr,
                "active_sign_acc": result.active_sign_acc,
                "active_nonzero_sign_acc": result.active_nonzero_sign_acc,
                "active_frac": result.active_frac,
                "coef_gap": result.coefficients[0],
                "coef_spread_narrow": result.coefficients[1],
                "coef_imbalance_l1": result.coefficients[2],
                "coef_mom1": result.coefficients[3],
                "coef_dw_prev": result.coefficients[4],
                "intercept": result.intercept,
            }
        )
    regression_table = pd.DataFrame(regression_rows).set_index(["train_day", "test_day"])

    fair_proxy_rows = []
    for day in DAYS:
        book = tomato_books[tomato_books["day"] == day].copy()
        next_mid = book["mid"].shift(-1)
        next_wall = book["wall_mid"].shift(-1)
        proxies = {
            "wall_mid": book["wall_mid"],
            "mid": book["mid"],
            "ema5": book["wall_mid"].ewm(span=5, adjust=False).mean(),
            "ema10": book["wall_mid"].ewm(span=10, adjust=False).mean(),
            "ema20": book["wall_mid"].ewm(span=20, adjust=False).mean(),
        }
        for label, series in proxies.items():
            mask_mid = next_mid.notna() & series.notna()
            mask_wall = next_wall.notna() & series.notna()
            fair_proxy_rows.append(
                {
                    "day": day,
                    "proxy": label,
                    "mse_to_next_mid": float(((next_mid[mask_mid] - series[mask_mid]) ** 2).mean()),
                    "mse_to_next_wall": float(((next_wall[mask_wall] - series[mask_wall]) ** 2).mean()),
                }
            )
    fair_proxy = pd.DataFrame(fair_proxy_rows).set_index(["day", "proxy"])

    return {
        "summary": summary,
        "state_mix": state_mix,
        "gap_response": gap_response,
        "spread_gap_response": spread_gap_response,
        "taker_table": taker_table,
        "edge_table": edge_table,
        "regression_table": regression_table,
        "fair_proxy": fair_proxy,
    }


def audit_notebook_assumptions(books: pd.DataFrame, trades: pd.DataFrame) -> dict[str, pd.DataFrame]:
    trade_agg = aggregate_trades(trades)
    merge_rows = []
    for product in PRODUCTS:
        book = books[books["product"] == product].copy()
        trade_sample = trade_agg[trade_agg["product"] == product]
        exact = book.merge(trade_sample[["day", "timestamp", "trade_count"]], on=["day", "timestamp"], how="left")
        exact_rows = int(exact["trade_count"].notna().sum())
        lagged_rows = 0
        for day in DAYS:
            book_day = book[book["day"] == day].sort_values("timestamp").copy()
            trade_ticks = set(trade_sample[trade_sample["day"] == day]["timestamp"].tolist())
            previous_tick_has_trade = book_day["timestamp"].sub(100).isin(trade_ticks)
            exact_tick_has_trade = book_day["timestamp"].isin(trade_ticks)
            lagged_rows += int((previous_tick_has_trade & ~exact_tick_has_trade).sum())
        asof_rows = exact_rows + lagged_rows
        merge_rows.append(
            {
                "product": product,
                "exact_trade_rows": exact_rows,
                "backward_asof_rows": asof_rows,
                "duplication_ratio": asof_rows / exact_rows if exact_rows else np.nan,
                "lagged_rows": lagged_rows,
            }
        )
    merge_audit = pd.DataFrame(merge_rows).set_index("product")

    pair = (
        books[books["product"] == "EMERALDS"][["day", "timestamp", "mid"]]
        .rename(columns={"mid": "emerald_mid"})
        .merge(
            books[books["product"] == "TOMATOES"][["day", "timestamp", "mid"]].rename(columns={"mid": "tomato_mid"}),
            on=["day", "timestamp"],
            how="inner",
        )
    )
    pair_rows = []
    pooled = pair.copy()
    pair_rows.append(
        {
            "sample": "pooled",
            "level_corr": float(pooled["emerald_mid"].corr(pooled["tomato_mid"])),
            "diff_corr": float(pooled["emerald_mid"].diff().corr(pooled["tomato_mid"].diff())),
            "coint_pvalue": float(coint(pooled["emerald_mid"], pooled["tomato_mid"])[1]) if coint is not None else np.nan,
        }
    )
    for day, sample in pair.groupby("day"):
        pair_rows.append(
            {
                "sample": f"day_{day}",
                "level_corr": float(sample["emerald_mid"].corr(sample["tomato_mid"])),
                "diff_corr": float(sample["emerald_mid"].diff().corr(sample["tomato_mid"].diff())),
                "coint_pvalue": float(coint(sample["emerald_mid"], sample["tomato_mid"])[1]) if coint is not None else np.nan,
            }
        )
    pair_audit = pd.DataFrame(pair_rows).set_index("sample")

    return {"merge_audit": merge_audit, "pair_audit": pair_audit}


def parse_latest_backtest() -> Optional[pd.DataFrame]:
    import re

    logs = sorted(BACKTEST_DIR.glob("*.log"))
    if not logs:
        return None
    latest = logs[-1]
    content = latest.read_text(encoding="utf-8", errors="replace")
    marker = "Trade History:"
    start = content.find(marker)
    if start == -1:
        return None

    trade_json = content[start + len(marker):].strip()
    end = trade_json.rfind("]")
    if end == -1:
        return None
    trade_json = trade_json[: end + 1]
    trade_json = re.sub(r",\s*}", "}", trade_json)
    trade_json = re.sub(r",\s*]", "]", trade_json)

    try:
        trade_list = json.loads(trade_json)
    except json.JSONDecodeError:
        return None

    fills = []
    for trade in trade_list:
        is_buy = trade.get("buyer") == "SUBMISSION"
        is_sell = trade.get("seller") == "SUBMISSION"
        if not (is_buy or is_sell):
            continue
        fills.append(
            {
                "timestamp": trade["timestamp"],
                "product": trade["symbol"],
                "price": trade["price"],
                "quantity": trade["quantity"],
                "side": "BUY" if is_buy else "SELL",
                "signed_qty": trade["quantity"] if is_buy else -trade["quantity"],
            }
        )
    if not fills:
        return None
    fill_df = pd.DataFrame(fills).sort_values(["product", "timestamp"]).reset_index(drop=True)
    fill_df.attrs["log_name"] = latest.name
    return fill_df


def summarize_backtest(fill_df: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
    if fill_df is None or fill_df.empty:
        return None

    rows = []
    for product, sample in fill_df.groupby("product"):
        realized = 0.0
        position = 0
        fifo: List[List[float]] = []
        for trade in sample.itertuples(index=False):
            qty = int(trade.signed_qty)
            price = float(trade.price)
            if qty > 0:
                fifo.append([price, qty])
            else:
                remaining = -qty
                while remaining > 0 and fifo:
                    buy_price, buy_qty = fifo[0]
                    matched = min(remaining, int(buy_qty))
                    realized += (price - buy_price) * matched
                    remaining -= matched
                    if matched == buy_qty:
                        fifo.pop(0)
                    else:
                        fifo[0][1] = buy_qty - matched
                if remaining > 0:
                    fifo.append([price, -remaining])
            position += qty

        fill_prices = sample.groupby(["price", "side"])["quantity"].sum().sort_values(ascending=False)
        price_summary = ", ".join(
            f"{int(price)} {side}:{int(qty)}" for (price, side), qty in fill_prices.head(8).items()
        )
        rows.append(
            {
                "product": product,
                "fills": len(sample),
                "net_position": position,
                "realized_pnl_fifo": realized,
                "price_range": f"{int(sample['price'].min())}-{int(sample['price'].max())}",
                "top_fill_levels": price_summary,
            }
        )
    result = pd.DataFrame(rows).set_index("product")
    result.attrs["log_name"] = fill_df.attrs.get("log_name", "")
    return result


def build_report() -> str:
    prices = load_prices()
    trades = load_trades()
    books = prepare_books(prices)

    dataset_summary = summarize_dataset(books, trades)
    emerald_state_table, emerald_response = emerald_tables(books, trades)
    tomato_tables = tomatoes_tables(books)
    audits = audit_notebook_assumptions(books, trades)
    latest_backtest = summarize_backtest(parse_latest_backtest())

    report: List[str] = []
    report.append("# Emerald and Tomato deep dive")
    report.append("")
    report.append("This report re-runs the Emerald and Tomato tutorial evidence with stricter checks than the existing notebook.")
    report.append("It focuses on what is stable across both available days, what is probably a sample artifact, and what that means for our current strategy.")
    report.append("")
    report.append("## Scope")
    report.append("")
    report.append("- Raw datasets reviewed: `prices_round_0_day_-2.csv`, `prices_round_0_day_-1.csv`, `trades_round_0_day_-2.csv`, `trades_round_0_day_-1.csv`.")
    report.append("- Existing repo artifacts reviewed: `prosperity_analysis.ipynb`, `prosperity_analysis.html`, `prosperity4/trader.py`, `prosperity4/backtest_analysis.py`, and the latest local backtest log if present.")
    report.append("- External principles referenced:")
    report.append("  - Prosperity 2 Linear Utility writeup: fixed-fair maker/taker logic for AMETHYSTS and market-maker-mid fair for STARFRUIT.")
    report.append("  - Prosperity 3 Frankfurt Hedgehogs writeup: wall-mid fair, zero-edge clearing to reopen capacity, and snapshot-based order flow.")
    report.append("")
    report.append("## Dataset summary")
    report.append("")
    report.append(format_table(dataset_summary, float_precision=4))
    report.append("")
    report.append("## Core conclusions")
    report.append("")
    report.append("1. EMERALDS is a structural market-making product, not a forecasting product.")
    report.append("2. TOMATOES is best described as a slowly moving wall-mid fair value plus a one-tick quote asymmetry process that snaps back quickly.")
    report.append("3. The strongest Tomato alpha is quote-state alpha, not a spread-crossing directional alpha.")
    report.append("4. The notebook has a meaningful trade-feature leakage issue and an EMERALDS/TOMATOES pair-trading conclusion that does not survive practical scrutiny.")
    report.append("")
    report.append("## EMERALDS")
    report.append("")
    report.append("The hidden structure is unusually clean. The wall mid is exactly 10,000 on every tutorial row, so all movement in the displayed mid comes from one side temporarily collapsing from the normal inside quote back to fair.")
    report.append("")
    report.append(format_table(emerald_state_table, float_precision=4))
    report.append("")
    report.append("Gap versus next displayed-mid move:")
    report.append("")
    report.append(format_table(emerald_response, float_precision=4))
    report.append("")
    report.append("Key takeaways:")
    report.append("")
    report.append("- Default state is `2/2`: the best bid and ask sit 2 ticks inside the deep wall on both sides.")
    report.append("- The only displaced states are `2/10` and `10/2`, and they are one-tick events.")
    report.append("- Fair-touch opportunities show up on about 1.6% to 1.7% of ticks per side, so zero-edge clearing trades matter.")
    report.append("- This is a capacity-management game. The prior-winner lesson of clearing inventory at fair is fully supported by the local data.")
    report.append("")
    report.append("## TOMATOES")
    report.append("")
    report.append("TOMATOES becomes much cleaner under the wall-mid lens. The displayed mid can be written as `wall_mid + (bid_inside - ask_inside) / 2`, so most short-horizon predictability comes from quote asymmetry around a slower fair process.")
    report.append("")
    report.append(format_table(tomato_tables["summary"], float_precision=4))
    report.append("")
    report.append("Most common inside-quote states:")
    report.append("")
    report.append(format_table(tomato_tables["state_mix"], float_precision=4))
    report.append("")
    report.append("Gap versus next displayed-mid move:")
    report.append("")
    report.append(format_table(tomato_tables["gap_response"], float_precision=4))
    report.append("")
    report.append("Gap response split by spread regime (`spread_narrow = 1` means spread <= 9):")
    report.append("")
    report.append(format_table(tomato_tables["spread_gap_response"], float_precision=4))
    report.append("")
    report.append("The hidden pattern is that the large-gap states are the narrow-spread states, and they usually last one tick only. The wide default state lasts about 14 ticks on average; the active `|gap| >= 2` state lasts about 1.1 ticks.")
    report.append("")
    report.append("Fair-proxy comparison:")
    report.append("")
    report.append(format_table(tomato_tables["fair_proxy"], float_precision=4))
    report.append("")
    report.append("Cross-day out-of-sample regression for `next_mid_delta`, using only interpretable state variables:")
    report.append("")
    report.append(format_table(tomato_tables["regression_table"], float_precision=4))
    report.append("")
    report.append("How to read this:")
    report.append("")
    report.append("- The gap coefficient is stable around `-0.85` to `-0.86` out of sample. That is the real signal.")
    report.append("- The active-signal hit rate is high because the model only becomes bold on those one-tick dislocation states.")
    report.append("- This is much more believable than the notebook's pooled in-sample `R^2` claims.")
    report.append("")
    report.append("Why spread-crossing is still a mistake:")
    report.append("")
    report.append(format_table(tomato_tables["taker_table"], float_precision=4))
    report.append("")
    report.append("Even when `|gap| >= 4`, the average next absolute mid move is still smaller than the current spread. The edge exists relative to fair value, not relative to a full aggressive round-trip through the visible spread.")
    report.append("")
    report.append("Take-edge summary:")
    report.append("")
    report.append(format_table(tomato_tables["edge_table"], float_precision=4))
    report.append("")
    report.append("## Notebook audit")
    report.append("")
    report.append("Trade merge audit:")
    report.append("")
    report.append(format_table(audits["merge_audit"], float_precision=4))
    report.append("")
    report.append("The existing notebook uses a backward `merge_asof(..., tolerance=100)` for trade features. Because book timestamps are spaced by 100, almost every trade gets duplicated onto the next book row as well.")
    report.append("")
    report.append("Cross-product audit:")
    report.append("")
    report.append(format_table(audits["pair_audit"], float_precision=6))
    report.append("")
    report.append("The notebook's EMERALDS-vs-TOMATOES pair-trading conclusion is not practically credible. Level correlation and return correlation are both near zero. Any cointegration test that fires here is reacting to EMERALDS being almost constant, not to a meaningful tradable linkage.")
    report.append("")
    report.append("## Strategy implications")
    report.append("")
    report.append("EMERALDS:")
    report.append("")
    report.append("- Keep it simple and structural: fixed fair, strict favorable takes, and fair-value clears to reopen capacity.")
    report.append("- The local data says the edge is in inventory turnover, not in predictive modeling.")
    report.append("- Under a changed environment, keep the market-structure logic and drop any temptation to hardcode timestamp behavior.")
    report.append("")
    report.append("TOMATOES:")
    report.append("")
    report.append("- Treat wall mid as fair. The raw mid is a noisy symptom of one-side quote displacement.")
    report.append("- Do not reintroduce EMA lag. The tutorial data says current wall mid beats `ema5`, `ema10`, and `ema20` on both days.")
    report.append("- Use two modes:")
    report.append("  - default wide-state mode: quote around wall mid and manage inventory")
    report.append("  - active one-tick dislocation mode: lean hard into the gap signal, but express it with favorable takes versus fair and fast passive reversion quotes, not blind spread crossing")
    report.append("- Preserve capacity. This is where Prosperity 2's zero-edge-clearing lesson and Prosperity 3's wall-mid lesson line up cleanly.")
    report.append("")
    if latest_backtest is not None:
        log_name = latest_backtest.attrs.get("log_name", "")
        report.append("## Latest local backtest")
        report.append("")
        if log_name:
            report.append(f"Latest parsed log: `{log_name}`")
            report.append("")
        report.append(format_table(latest_backtest, float_precision=4))
        report.append("")
        report.append("This lines up with the structural read above: EMERALDS fills cluster around fair-anchored levels, while TOMATOES profits remain more sensitive to how we express the wall-mid signal without paying too much spread.")
        report.append("")
    report.append("## Bottom line")
    report.append("")
    report.append("The deep edge here is not hidden ML complexity. It is state decomposition:")
    report.append("")
    report.append("- EMERALDS: deterministic fair plus transient fair-touch states.")
    report.append("- TOMATOES: slow wall-mid fair plus one-tick quote-asymmetry states.")
    report.append("")
    report.append("That is the robust bridge between the tutorial data and the prior-winner playbook. Keep the structural logic, keep the inventory discipline, use wall mid aggressively, and stay skeptical of anything that only looks good because of pooled in-sample statistics or timestamp-level leakage.")
    report.append("")
    return "\n".join(report)


def main() -> None:
    report = build_report()
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"Wrote {REPORT_PATH}")


if __name__ == "__main__":
    main()
