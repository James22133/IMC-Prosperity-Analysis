"""
Prosperity 4 — Probe Log Parser

Parses raw debug log text from Prosperity dashboard, extracts structured data
from PROBE|timestamp|event_type|json_data log lines, and produces DataFrames + plots.

Usage:
    python log_parser.py <log_file.txt> [--baseline baseline_log.txt] [--output output_dir]

Or import and use programmatically:
    from log_parser import parse_log, analyze_probe, diff_against_baseline
"""

import json
import re
import sys
import os
import argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

sns.set_theme(style='whitegrid', palette='muted')


def parse_log(log_text):
    """Parse raw debug log text into structured DataFrames."""
    books = []
    trades = []
    own_trades = []
    positions = []
    actions = []
    fills = []
    search_results = []
    hashes = []
    misc = []

    for line in log_text.strip().split('\n'):
        line = line.strip()
        if not line.startswith('PROBE|'):
            continue

        parts = line.split('|', 3)
        if len(parts) < 4:
            continue

        _, ts_str, event_type, data_str = parts
        try:
            ts = int(ts_str)
        except ValueError:
            try:
                ts = float(ts_str)
            except ValueError:
                continue

        try:
            data = json.loads(data_str)
        except json.JSONDecodeError:
            data = {'raw': data_str}

        data['timestamp'] = ts
        data['event_type'] = event_type

        if event_type == 'BOOK':
            books.append(data)
        elif event_type == 'MARKET_TRADE':
            trades.append(data)
        elif event_type == 'OWN_TRADE':
            own_trades.append(data)
        elif event_type == 'POSITION':
            positions.append(data)
        elif event_type in ('ACTION', 'QUOTES', 'WIDE_QUOTES'):
            actions.append(data)
        elif event_type in ('FILL', 'SEARCH_FILL'):
            fills.append(data)
        elif event_type == 'SEARCH_RESULT':
            search_results.append(data)
        elif event_type == 'HASH':
            hashes.append({'timestamp': ts, 'hash': data_str.strip()})
        elif event_type == 'STATE':
            books.append(data)
        else:
            misc.append(data)

    result = {
        'df_books': pd.DataFrame(books) if books else pd.DataFrame(),
        'df_trades': pd.DataFrame(trades) if trades else pd.DataFrame(),
        'df_own_trades': pd.DataFrame(own_trades) if own_trades else pd.DataFrame(),
        'df_positions': pd.DataFrame(positions) if positions else pd.DataFrame(),
        'df_actions': pd.DataFrame(actions) if actions else pd.DataFrame(),
        'df_fills': pd.DataFrame(fills) if fills else pd.DataFrame(),
        'df_search_results': pd.DataFrame(search_results) if search_results else pd.DataFrame(),
        'df_hashes': pd.DataFrame(hashes) if hashes else pd.DataFrame(),
        'df_misc': pd.DataFrame(misc) if misc else pd.DataFrame(),
    }

    for key, df in result.items():
        if not df.empty and 'timestamp' in df.columns:
            df.sort_values('timestamp', inplace=True)
            df.reset_index(drop=True, inplace=True)

    return result


def analyze_probe(parsed, title="Probe Analysis", output_dir=None):
    """Generate standard analysis plots and stats from parsed probe data."""
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    df_books = parsed['df_books']
    df_fills = parsed['df_fills']
    df_trades = parsed['df_trades']

    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

    # Summary stats
    for name, df in parsed.items():
        if not df.empty:
            print(f"  {name}: {len(df)} rows")

    if df_books.empty:
        print("  No book data to analyze.")
        return

    # --- Mid price time series ---
    if 'mid' in df_books.columns:
        products = df_books['product'].unique() if 'product' in df_books.columns else ['unknown']
        for product in products:
            mask = df_books['product'] == product if 'product' in df_books.columns else [True]*len(df_books)
            bk = df_books[mask].copy()

            fig, axes = plt.subplots(2, 2, figsize=(16, 10))

            # Price
            axes[0, 0].plot(bk['timestamp'], bk['mid'], linewidth=0.8)
            axes[0, 0].set_title(f'{product} — Mid Price')
            axes[0, 0].set_xlabel('Timestamp')

            # Spread
            if 'spread' in bk.columns:
                axes[0, 1].plot(bk['timestamp'], bk['spread'], linewidth=0.8, color='orange')
                axes[0, 1].set_title(f'{product} — Spread')

            # Position
            if 'position' in bk.columns:
                axes[1, 0].plot(bk['timestamp'], bk['position'], linewidth=0.8, color='green')
                axes[1, 0].set_title(f'{product} — Position')
                axes[1, 0].set_xlabel('Timestamp')

            # Returns
            if len(bk) > 1:
                mid_vals = pd.to_numeric(bk['mid'], errors='coerce')
                rets = mid_vals.pct_change().dropna()
                axes[1, 1].hist(rets, bins=50, alpha=0.7, color='steelblue')
                axes[1, 1].set_title(f'{product} — Returns Distribution')

            plt.suptitle(title, y=1.02)
            plt.tight_layout()
            if output_dir:
                plt.savefig(os.path.join(output_dir, f'{product}_overview.png'), dpi=100, bbox_inches='tight')
            plt.show()

            # Stats
            mid_vals = pd.to_numeric(bk['mid'], errors='coerce').dropna()
            if len(mid_vals) > 1:
                print(f"\n  {product} — Mid price stats:")
                print(f"    Mean:  {mid_vals.mean():.2f}")
                print(f"    Std:   {mid_vals.std():.4f}")
                print(f"    Min:   {mid_vals.min():.2f}")
                print(f"    Max:   {mid_vals.max():.2f}")

            if 'spread' in bk.columns:
                sp = pd.to_numeric(bk['spread'], errors='coerce').dropna()
                if len(sp) > 0:
                    print(f"    Spread — mean: {sp.mean():.2f}, std: {sp.std():.2f}")

    # --- Fill analysis ---
    if not df_fills.empty:
        print(f"\n  Fills: {len(df_fills)} total")
        if 'product' in df_fills.columns:
            for product in df_fills['product'].unique():
                pf = df_fills[df_fills['product'] == product]
                print(f"    {product}: {len(pf)} fills")
                if 'price' in pf.columns:
                    prices = pd.to_numeric(pf['price'], errors='coerce').dropna()
                    if len(prices) > 0:
                        print(f"      Price — mean: {prices.mean():.2f}, min: {prices.min():.2f}, max: {prices.max():.2f}")
                if 'quantity' in pf.columns:
                    qtys = pd.to_numeric(pf['quantity'], errors='coerce').dropna()
                    if len(qtys) > 0:
                        print(f"      Qty — mean: {qtys.mean():.1f}, total: {qtys.sum():.0f}")

    # --- Trade analysis ---
    if not df_trades.empty:
        print(f"\n  Market trades observed: {len(df_trades)}")

    return parsed


def diff_against_baseline(probe_parsed, baseline_parsed, title="Diff Analysis"):
    """Compare probe results against baseline (Probe 0)."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

    pb = probe_parsed['df_books']
    bb = baseline_parsed['df_books']

    if pb.empty or bb.empty:
        print("  Insufficient data for diff.")
        return

    products = pb['product'].unique() if 'product' in pb.columns else ['unknown']

    for product in products:
        p_mask = pb['product'] == product if 'product' in pb.columns else [True]*len(pb)
        b_mask = bb['product'] == product if 'product' in bb.columns else [True]*len(bb)

        p_bk = pb[p_mask].copy()
        b_bk = bb[b_mask].copy()

        p_mid = pd.to_numeric(p_bk['mid'], errors='coerce') if 'mid' in p_bk.columns else pd.Series()
        b_mid = pd.to_numeric(b_bk['mid'], errors='coerce') if 'mid' in b_bk.columns else pd.Series()

        if p_mid.empty or b_mid.empty:
            continue

        min_len = min(len(p_mid), len(b_mid))

        fig, axes = plt.subplots(1, 3, figsize=(18, 5))

        # Price comparison
        axes[0].plot(range(min_len), b_mid.values[:min_len], label='Baseline', alpha=0.7)
        axes[0].plot(range(min_len), p_mid.values[:min_len], label='Probe', alpha=0.7)
        axes[0].set_title(f'{product} — Price Comparison')
        axes[0].legend()

        # Price difference
        diff = p_mid.values[:min_len] - b_mid.values[:min_len]
        axes[1].plot(diff, linewidth=0.8, color='red')
        axes[1].set_title(f'{product} — Price Δ (Probe - Baseline)')
        axes[1].axhline(0, color='black', linewidth=0.5)

        # Spread comparison
        if 'spread' in p_bk.columns and 'spread' in b_bk.columns:
            p_sp = pd.to_numeric(p_bk['spread'], errors='coerce').values[:min_len]
            b_sp = pd.to_numeric(b_bk['spread'], errors='coerce').values[:min_len]
            axes[2].plot(range(min_len), b_sp, label='Baseline', alpha=0.7)
            axes[2].plot(range(min_len), p_sp, label='Probe', alpha=0.7)
            axes[2].set_title(f'{product} — Spread Comparison')
            axes[2].legend()

        plt.suptitle(title, y=1.02)
        plt.tight_layout()
        plt.show()

        print(f"\n  {product}:")
        print(f"    Price diff — mean: {np.nanmean(diff):.4f}, max abs: {np.nanmax(np.abs(diff)):.4f}")
        if 'spread' in p_bk.columns and 'spread' in b_bk.columns:
            sp_diff = p_sp - b_sp
            print(f"    Spread diff — mean: {np.nanmean(sp_diff):.4f}")


def compare_determinism(log1_text, log2_text):
    """Compare two logs from Probe 10 to test determinism."""
    p1 = parse_log(log1_text)
    p2 = parse_log(log2_text)

    h1 = p1['df_hashes']
    h2 = p2['df_hashes']

    if h1.empty or h2.empty:
        print("No hash data found. Use Probe 10 for determinism testing.")
        return

    min_len = min(len(h1), len(h2))
    matches = 0
    mismatches = 0
    for i in range(min_len):
        if h1.iloc[i]['hash'] == h2.iloc[i]['hash']:
            matches += 1
        else:
            mismatches += 1
            if mismatches <= 5:
                print(f"  Mismatch at ts={h1.iloc[i]['timestamp']}: {h1.iloc[i]['hash']} vs {h2.iloc[i]['hash']}")

    total = matches + mismatches
    print(f"\nDeterminism Test Results:")
    print(f"  Total comparisons: {total}")
    print(f"  Matches:    {matches} ({matches/total*100:.1f}%)")
    print(f"  Mismatches: {mismatches} ({mismatches/total*100:.1f}%)")
    if mismatches == 0:
        print("  → FULLY DETERMINISTIC — bots follow a fixed script!")
    else:
        print(f"  → STOCHASTIC — {mismatches/total*100:.1f}% divergence")


def main():
    parser = argparse.ArgumentParser(description='Parse Prosperity 4 probe logs')
    parser.add_argument('logfile', help='Path to the probe debug log file')
    parser.add_argument('--baseline', help='Path to baseline (Probe 0) log for diff analysis')
    parser.add_argument('--output', default='probe_output', help='Output directory for plots')
    parser.add_argument('--compare', help='Second log file for determinism comparison (Probe 10)')
    args = parser.parse_args()

    with open(args.logfile, 'r', encoding='utf-8', errors='ignore') as f:
        log_text = f.read()

    parsed = parse_log(log_text)
    analyze_probe(parsed, title=f"Analysis: {os.path.basename(args.logfile)}", output_dir=args.output)

    if args.baseline:
        with open(args.baseline, 'r', encoding='utf-8', errors='ignore') as f:
            baseline_text = f.read()
        baseline_parsed = parse_log(baseline_text)
        diff_against_baseline(parsed, baseline_parsed,
                              title=f"Diff: {os.path.basename(args.logfile)} vs Baseline")

    if args.compare:
        with open(args.compare, 'r', encoding='utf-8', errors='ignore') as f:
            compare_text = f.read()
        compare_determinism(log_text, compare_text)

    print("\nDone.")


if __name__ == '__main__':
    main()
