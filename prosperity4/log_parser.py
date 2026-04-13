"""
Parse Prosperity 4 debug logs into structured DataFrames and generate diagnostics.

Usage:
    python log_parser.py <log_file.txt> [--output output_dir]
"""
import argparse
import ast
import os
import re
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


# ── parsers ──────────────────────────────────────────────────────

def _safe_eval(s: str):
    try:
        return ast.literal_eval(s)
    except Exception:
        return {}


def parse_log(log_text: str) -> dict:
    books, trades, fills, positions, walls = [], [], [], [], []

    for line in log_text.splitlines():
        line = line.strip()
        if not line:
            continue

        # BOOK lines
        m = re.match(
            r"BOOK\|(\d+)\|(\w+)\|bids=(.+?)\|asks=(.+?)\|pos=(-?\d+)", line
        )
        if m:
            ts, prod = int(m.group(1)), m.group(2)
            bids = _safe_eval(m.group(3))
            asks = _safe_eval(m.group(4))
            pos = int(m.group(5))
            best_bid = max(bids.keys()) if bids else None
            best_ask = min(asks.keys()) if asks else None
            mid = (best_bid + best_ask) / 2 if best_bid and best_ask else None
            spread = (best_ask - best_bid) if best_bid and best_ask else None
            books.append(dict(
                timestamp=ts, product=prod,
                best_bid=best_bid, best_ask=best_ask,
                mid=mid, spread=spread, position=pos,
                bids=bids, asks=asks,
            ))
            positions.append(dict(timestamp=ts, product=prod, position=pos))
            continue

        # STATE lines (from oracle probe)
        m = re.match(
            r"STATE\|(\d+)\|(\w+)\|pos=(-?\d+)\|bids=(.+?)\|asks=(.+)", line
        )
        if m:
            ts, prod = int(m.group(1)), m.group(2)
            pos = int(m.group(3))
            bids = _safe_eval(m.group(4))
            asks = _safe_eval(m.group(5))
            best_bid = max(bids.keys()) if bids else None
            best_ask = min(asks.keys()) if asks else None
            mid = (best_bid + best_ask) / 2 if best_bid and best_ask else None
            spread = (best_ask - best_bid) if best_bid and best_ask else None
            books.append(dict(
                timestamp=ts, product=prod,
                best_bid=best_bid, best_ask=best_ask,
                mid=mid, spread=spread, position=pos,
                bids=bids, asks=asks,
            ))
            positions.append(dict(timestamp=ts, product=prod, position=pos))
            continue

        # WALL lines
        m = re.match(
            r"(BID_WALL|ASK_WALL)\|(\d+)\|(\w+)\|price=(-?\d+)\|vol=(-?\d+)",
            line,
        )
        if m:
            side = "bid" if m.group(1) == "BID_WALL" else "ask"
            walls.append(dict(
                timestamp=int(m.group(2)), product=m.group(3),
                side=side, price=int(m.group(4)), vol=int(m.group(5)),
            ))
            continue

        # MTRADE / DET_TRADE
        m = re.match(
            r"(?:MTRADE|DET_TRADE)\|(\d+)\|(\w+)\|(?:price=)?(-?\d+)\|(?:qty=)?(-?\d+)",
            line,
        )
        if m:
            trades.append(dict(
                timestamp=int(m.group(1)), product=m.group(2),
                price=int(m.group(3)), qty=int(m.group(4)),
            ))
            continue

        # FILL lines
        m = re.match(
            r"FILL\|(\d+)\|(\w+)\|price=(-?\d+)\|qty=(-?\d+)", line
        )
        if m:
            fills.append(dict(
                timestamp=int(m.group(1)), product=m.group(2),
                price=int(m.group(3)), qty=int(m.group(4)),
            ))
            continue

        # POS lines
        m = re.match(r"POS\|(\d+)\|(\w+)\|(-?\d+)", line)
        if m:
            positions.append(dict(
                timestamp=int(m.group(1)), product=m.group(2),
                position=int(m.group(3)),
            ))
            continue

        # DET lines
        m = re.match(r"DET\|(\d+)\|(\w+)\|mid=([\d.]+)", line)
        if m:
            ts, prod = int(m.group(1)), m.group(2)
            mid = float(m.group(3))
            books.append(dict(
                timestamp=ts, product=prod,
                best_bid=None, best_ask=None,
                mid=mid, spread=None, position=None,
                bids={}, asks={},
            ))
            continue

        # PROBE_BUY
        m = re.match(r"PROBE_BUY\|(\w+)\|(-?\d+)\|(\d+)", line)
        if m:
            fills.append(dict(
                timestamp=0, product=m.group(1),
                price=int(m.group(2)), qty=int(m.group(3)),
            ))
            continue

    # Assemble wall mids
    df_walls = pd.DataFrame(walls) if walls else pd.DataFrame()
    wall_mids = {}
    if not df_walls.empty:
        for (ts, prod), grp in df_walls.groupby(["timestamp", "product"]):
            bid_row = grp[grp["side"] == "bid"]
            ask_row = grp[grp["side"] == "ask"]
            if not bid_row.empty and not ask_row.empty:
                wm = (bid_row.iloc[0]["price"] + ask_row.iloc[0]["price"]) / 2
                key = (ts, prod)
                wall_mids[key] = wm

    df_books = pd.DataFrame(books) if books else pd.DataFrame()
    if not df_books.empty and wall_mids:
        df_books["wall_mid"] = df_books.apply(
            lambda r: wall_mids.get((r["timestamp"], r["product"])), axis=1
        )
    elif not df_books.empty:
        df_books["wall_mid"] = None

    return {
        "df_books": df_books,
        "df_trades": pd.DataFrame(trades) if trades else pd.DataFrame(),
        "df_fills": pd.DataFrame(fills) if fills else pd.DataFrame(),
        "df_positions": pd.DataFrame(positions) if positions else pd.DataFrame(),
        "df_walls": df_walls,
    }


# ── plotting ─────────────────────────────────────────────────────

def plot_diagnostics(parsed: dict, output_dir: str = None):
    df_books = parsed["df_books"]
    df_fills = parsed["df_fills"]
    df_pos = parsed["df_positions"]

    if df_books.empty:
        print("No book data to plot.")
        return

    products = df_books["product"].unique()
    save = output_dir is not None
    if save:
        os.makedirs(output_dir, exist_ok=True)

    for prod in products:
        bk = df_books[df_books["product"] == prod].sort_values("timestamp")

        # Price time series + fills
        fig, ax = plt.subplots(figsize=(14, 5))
        ax.plot(bk["timestamp"], bk["mid"], label="mid", linewidth=0.8)
        if "wall_mid" in bk.columns and bk["wall_mid"].notna().any():
            ax.plot(bk["timestamp"], bk["wall_mid"], label="wall_mid",
                    linewidth=0.8, alpha=0.8)
        if not df_fills.empty:
            fl = df_fills[df_fills["product"] == prod]
            buys = fl[fl["qty"] > 0]
            sells = fl[fl["qty"] < 0]
            if not buys.empty:
                ax.scatter(buys["timestamp"], buys["price"],
                           marker="^", c="green", s=30, label="buy fill", zorder=5)
            if not sells.empty:
                ax.scatter(sells["timestamp"], sells["price"],
                           marker="v", c="red", s=30, label="sell fill", zorder=5)
        ax.set_title(f"{prod} — Price")
        ax.legend()
        ax.set_xlabel("timestamp")
        ax.set_ylabel("price")
        plt.tight_layout()
        if save:
            fig.savefig(os.path.join(output_dir, f"{prod}_price.png"), dpi=150)
        plt.show()
        plt.close(fig)

        # Spread
        if bk["spread"].notna().any():
            fig, ax = plt.subplots(figsize=(14, 3))
            ax.plot(bk["timestamp"], bk["spread"], linewidth=0.7)
            ax.set_title(f"{prod} — Spread")
            ax.set_xlabel("timestamp")
            ax.set_ylabel("spread")
            plt.tight_layout()
            if save:
                fig.savefig(os.path.join(output_dir, f"{prod}_spread.png"), dpi=150)
            plt.show()
            plt.close(fig)

    # Position over time
    if not df_pos.empty:
        for prod in df_pos["product"].unique():
            ps = df_pos[df_pos["product"] == prod].sort_values("timestamp")
            fig, ax = plt.subplots(figsize=(14, 3))
            ax.plot(ps["timestamp"], ps["position"], linewidth=0.8)
            ax.axhline(0, color="gray", linewidth=0.5, linestyle="--")
            ax.set_title(f"{prod} — Position")
            ax.set_xlabel("timestamp")
            ax.set_ylabel("position")
            plt.tight_layout()
            if save:
                fig.savefig(os.path.join(output_dir, f"{prod}_position.png"), dpi=150)
            plt.show()
            plt.close(fig)

    # Cumulative PnL from fills
    if not df_fills.empty:
        for prod in df_fills["product"].unique():
            fl = df_fills[df_fills["product"] == prod].sort_values("timestamp")
            fl = fl.copy()
            fl["cash_flow"] = -fl["price"] * fl["qty"]
            fl["cum_pnl"] = fl["cash_flow"].cumsum()
            fig, ax = plt.subplots(figsize=(14, 3))
            ax.plot(fl["timestamp"], fl["cum_pnl"], linewidth=0.8)
            ax.set_title(f"{prod} — Cumulative PnL (from fills, excl. open position)")
            ax.set_xlabel("timestamp")
            ax.set_ylabel("cumulative PnL")
            plt.tight_layout()
            if save:
                fig.savefig(os.path.join(output_dir, f"{prod}_pnl.png"), dpi=150)
            plt.show()
            plt.close(fig)

    # Fill rate summary
    if not df_fills.empty:
        print("\n=== Fill Summary ===")
        for prod in df_fills["product"].unique():
            fl = df_fills[df_fills["product"] == prod]
            n_buys = (fl["qty"] > 0).sum()
            n_sells = (fl["qty"] < 0).sum()
            total_ticks = df_books[df_books["product"] == prod]["timestamp"].nunique()
            print(f"{prod}: {n_buys} buy fills, {n_sells} sell fills "
                  f"across {total_ticks} ticks")


# ── CLI ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Parse Prosperity 4 debug logs")
    parser.add_argument("log_file", help="Path to debug log text file")
    parser.add_argument("--output", "-o", help="Output directory for plots")
    args = parser.parse_args()

    log_text = Path(args.log_file).read_text(encoding="utf-8", errors="replace")
    parsed = parse_log(log_text)

    for name, df in parsed.items():
        if not df.empty:
            print(f"\n=== {name} ({len(df)} rows) ===")
            print(df.head(10).to_string())
        else:
            print(f"\n=== {name}: empty ===")

    plot_diagnostics(parsed, output_dir=args.output)


if __name__ == "__main__":
    main()
