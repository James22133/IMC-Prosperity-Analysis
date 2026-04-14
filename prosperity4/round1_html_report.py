"""
Build a detailed HTML report for Round 1 (tutorial-style narrative + many figures).

Run from prosperity4/:
  python round1_html_report.py

Reads: ROUND1/ or bt_data/round1/ price + trade CSVs
Writes: ROUND1_deep_dive_output/round1_analysis_report.html
        ROUND1_deep_dive_output/html_figures/*.png
"""
from __future__ import annotations

import html
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import linregress

import round1_deep_dive as r1

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "ROUND1_deep_dive_output"
FIG = OUT / "html_figures"


def esc(s: str) -> str:
    return html.escape(str(s), quote=True)


def fig_style():
    plt.style.use("seaborn-v0_8-whitegrid")
    plt.rcParams.update({"figure.dpi": 120, "font.size": 10})


def plot_intarian_sessions(vp: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(14, 5))
    for day in sorted(vp["day"].unique()):
        w = vp[vp["day"] == day]
        ax.plot(w["timestamp"], w["mid_price"], lw=0.65, label=f"day {day}")
    ax.set_title("INTARIAN_PEPPER_ROOT — mid price (all sessions, shared timestamp axis)")
    ax.set_xlabel("timestamp (µs grid)")
    ax.set_ylabel("mid")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_intarian_normalized(vp: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(14, 5))
    for day in sorted(vp["day"].unique()):
        w = vp[vp["day"] == day].reset_index(drop=True)
        m = w["mid_price"].astype(float).values
        ax.plot(w["timestamp"], m - m[0], lw=0.65, label=f"day {day} (rebased to 0)")
    ax.axhline(0, color="black", lw=0.4)
    ax.set_title("INTARIAN — intra-session path (mid minus session open)")
    ax.set_xlabel("timestamp")
    ax.set_ylabel("Δ mid from session start")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_intarian_detrend_one_day(vp: pd.DataFrame, day: int, path: Path) -> None:
    w = vp[vp["day"] == day].reset_index(drop=True)
    mid = w["mid_price"].astype(float).values
    t = np.arange(len(mid), dtype=float)
    slope, intercept, _, _, _ = linregress(t, mid)
    trend = intercept + slope * t
    res = mid - trend
    fig, axes = plt.subplots(2, 1, figsize=(14, 7), sharex=True)
    axes[0].plot(w["timestamp"], mid, lw=0.5, label="mid")
    axes[0].plot(w["timestamp"], trend, lw=1.2, color="darkred", label="linear trend")
    axes[0].set_ylabel("price")
    axes[0].set_title(f"INTARIAN day {day}: mid vs linear drift")
    axes[0].legend(loc="upper left")
    axes[1].plot(w["timestamp"], res, lw=0.5, color="teal")
    axes[1].axhline(0, color="black", lw=0.4)
    axes[1].set_ylabel("residual")
    axes[1].set_xlabel("timestamp")
    axes[1].set_title("Detrended residuals (stationary band around trend)")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_quarter_heatmap(vp: pd.DataFrame, path: Path) -> None:
    days = sorted(vp["day"].unique())
    mat = np.zeros((len(days), 4))
    for i, day in enumerate(days):
        wdf = vp[vp["day"] == day].reset_index(drop=True)
        n = len(wdf)
        for q in range(4):
            a, b = q * n // 4, (q + 1) * n // 4
            seg = wdf.iloc[a:b]["mid_price"].astype(float).values
            mat[i, q] = np.mean(np.diff(seg)) if len(seg) > 1 else np.nan
    fig, ax = plt.subplots(figsize=(8, 3.5))
    im = ax.imshow(mat, aspect="auto", cmap="RdBu", vmin=-0.15, vmax=0.15)
    ax.set_xticks(range(4))
    ax.set_xticklabels([f"Q{j+1}" for j in range(4)])
    ax.set_yticks(range(len(days)))
    ax.set_yticklabels([f"day {d}" for d in days])
    ax.set_title("Mean one-tick mid change by session quarter")
    fig.colorbar(im, ax=ax, label="mean Δmid")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_acf_multiscale(v_ash: pd.DataFrame, v_pep: pd.DataFrame, path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))

    def acf_series(mid: np.ndarray, h: int) -> np.ndarray:
        if h == 1:
            r = np.diff(mid)
        else:
            r = mid[h:] - mid[:-h]
        if len(r) < 30:
            return np.array([])
        out = []
        for lag in range(1, 16):
            if len(r) <= lag:
                out.append(np.nan)
            else:
                out.append(np.corrcoef(r[:-lag], r[lag:])[0, 1])
        return np.array(out)

    for ax, name, v in (
        (axes[0], "ASH", v_ash),
        (axes[1], "INTARIAN", v_pep),
    ):
        mid = v["mid_price"].astype(float).values
        for h, sty in ((1, "-"), (2, "--"), (5, ":")):
            ys = acf_series(mid, h)
            if ys.size:
                ax.plot(range(1, len(ys) + 1), ys, sty, lw=2, label=f"{h}-tick ret")
        ax.axhline(0, color="black", lw=0.5)
        ax.set_xlabel("lag")
        ax.set_ylabel("autocorrelation")
        ax.set_title(f"{name}: lag-k acf of h-tick returns")
        ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_variance_ratio_bars(v_ash: pd.DataFrame, v_pep: pd.DataFrame, path: Path) -> None:
    ks = [2, 5, 10, 20, 50]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    x = np.arange(len(ks))
    w = 0.35
    for i, (label, v) in enumerate((("ASH", v_ash), ("INTARIAN", v_pep))):
        mid = v["mid_price"].astype(float).values
        lr = np.diff(np.log(mid))
        lr = lr[np.isfinite(lr)]
        vals = [r1.variance_ratio(lr, k) for k in ks]
        ax.bar(x + (i - 0.5) * w, vals, width=w, label=label)
    ax.axhline(1.0, color="red", ls="--", lw=1, label="VR=1 (RW)")
    ax.set_xticks(x)
    ax.set_xticklabels([f"k={k}" for k in ks])
    ax.set_ylabel("variance ratio")
    ax.set_title("Lo–MacKinlay-style variance ratio on log returns")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_hurst_rs_fit(v: pd.DataFrame, product: str, path: Path) -> None:
    mid = v["mid_price"].astype(float).values
    lr = np.diff(np.log(mid))
    lr = lr[np.isfinite(lr)]
    x = lr - lr.mean()
    n = len(x)
    lengths = np.unique(np.clip(np.geomspace(20, min(n // 4, 2000), num=20).astype(int), 20, None))
    log_L, log_RS = [], []
    for seg_len in lengths:
        nseg = n // seg_len
        if nseg < 4:
            continue
        ratios = []
        for j in range(nseg):
            seg = x[j * seg_len : (j + 1) * seg_len]
            y = np.cumsum(seg)
            R = y.max() - y.min()
            S = seg.std(ddof=1)
            if S > 1e-12:
                ratios.append(R / S)
        if ratios:
            log_L.append(np.log(seg_len))
            log_RS.append(np.log(np.mean(ratios)))
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.scatter(log_L, log_RS, s=40, alpha=0.7)
    if len(log_L) >= 3:
        slope, intercept, _, _, _ = linregress(log_L, log_RS)
        xx = np.array([min(log_L), max(log_L)])
        ax.plot(xx, intercept + slope * xx, color="darkred", lw=2, label=f"slope≈H {slope:.3f}")
        ax.legend()
    ax.set_xlabel("log(segment length)")
    ax.set_ylabel("log(mean R/S)")
    ax.set_title(f"{product}: R/S scaling (log returns)")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_ash_deviation(v_ash: pd.DataFrame, path: Path) -> None:
    days = sorted(v_ash["day"].unique())
    n = max(1, len(days))
    fig, axes = plt.subplots(n, 1, figsize=(14, 2.8 * n), sharex=False, squeeze=False)
    axes = axes.ravel()
    for ax, day in zip(axes, days):
        w = v_ash[v_ash["day"] == day]
        dev = w["mid_price"].astype(float) - 10000.0
        ax.plot(w["timestamp"], dev, lw=0.5)
        ax.axhline(0, color="black", lw=0.5)
        ax.set_ylabel("mid − 10000")
        ax.set_title(f"ASH day {day}: deviation from peg")
    axes[-1].set_xlabel("timestamp")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_spreads(v: pd.DataFrame, product: str, path: Path) -> None:
    days = sorted(v["day"].unique())
    n = max(1, len(days))
    fig, axes = plt.subplots(n, 1, figsize=(14, 2.5 * n), sharex=False, squeeze=False)
    axes = axes.ravel()
    for ax, day in zip(axes, days):
        w = v[v["day"] == day]
        sp = w["ask_price_1"].astype(float) - w["bid_price_1"].astype(float)
        ax.plot(w["timestamp"], sp, lw=0.4, color="steelblue")
        ax.set_ylabel("L1 spread")
        ax.set_title(f"{product} day {day}: spread")
    axes[-1].set_xlabel("timestamp")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_cross_mids(P: pd.DataFrame, path: Path) -> None:
    v0 = r1.valid_l1(P, r1.ASH)[["day", "timestamp", "mid_price"]].rename(columns={"mid_price": "ash"})
    v1 = r1.valid_l1(P, r1.PEPPER)[["day", "timestamp", "mid_price"]].rename(columns={"mid_price": "pep"})
    J = pd.merge(v0, v1, on=["day", "timestamp"], how="inner")
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    sc = axes[0].scatter(J["ash"], J["pep"], c=J["day"], s=3, alpha=0.25, cmap="coolwarm")
    axes[0].set_xlabel("ASH mid")
    axes[0].set_ylabel("INTARIAN mid")
    axes[0].set_title("Joined mids (colour = day)")
    fig.colorbar(sc, ax=axes[0], label="day")
    ra = J["ash"].diff()
    rp = J["pep"].diff()
    axes[1].scatter(ra, rp, s=3, alpha=0.2, c="darkgreen")
    axes[1].set_xlabel("Δ ASH")
    axes[1].set_ylabel("Δ INTARIAN")
    axes[1].set_title(f"Return scatter (ρ ≈ {ra.corr(rp):.3f})")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_pepper_signals(vp: pd.DataFrame, path: Path) -> None:
    mid = vp["mid_price"].astype(float).values
    sma10 = pd.Series(mid).rolling(10).mean().values
    mr = sma10 - mid
    fwd5 = np.full_like(mid, np.nan)
    fwd5[:-5] = mid[5:] - mid[:-5]
    m = np.isfinite(mr) & np.isfinite(fwd5)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    axes[0].hexbin(mr[m], fwd5[m], gridsize=55, cmap="viridis", mincnt=1)
    axes[0].set_xlabel("SMA10 − mid")
    axes[0].set_ylabel("5-tick forward Δmid")
    axes[0].set_title("Mean-reversion signal vs short horizon move")
    bidv = vp["bid_volume_1"].astype(float).fillna(0).values
    askv = vp["ask_volume_1"].astype(float).fillna(0).values
    imb = (bidv - askv) / np.maximum(bidv + askv, 1)
    f1 = np.append(np.diff(mid), np.nan)
    m2 = np.isfinite(imb) & np.isfinite(f1)
    axes[1].hexbin(imb[m2], f1[m2], gridsize=45, cmap="magma", mincnt=1)
    axes[1].set_xlabel("L1 book imbalance")
    axes[1].set_ylabel("1-tick forward Δmid")
    axes[1].set_title("Imbalance vs next tick (bounce-dominated)")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_ash_churn_and_inside(v_ash: pd.DataFrame, path: Path) -> None:
    days = sorted(v_ash["day"].unique())
    fig, axes = plt.subplots(len(days), 1, figsize=(14, 3.2 * len(days)), squeeze=False)
    axes = axes.ravel()
    for ax, day in zip(axes, days):
        w = v_ash[v_ash["day"] == day].reset_index(drop=True)
        bbw = w["bid_price_1"]
        baw = w["ask_price_1"]
        ch = ((bbw != bbw.shift(1)) | (baw != baw.shift(1))).rolling(200).mean()
        ins = ((baw <= 10003) & (bbw >= 9997)).rolling(500).mean()
        ax2 = ax.twinx()
        ax.plot(w["timestamp"], w["mid_price"].astype(float) - 10000, lw=0.4, color="gray", alpha=0.6)
        ax.set_ylabel("mid−10000", color="gray")
        ax2.plot(w["timestamp"], ch, lw=0.8, color="steelblue", label="quote churn MA200")
        ax2.plot(w["timestamp"], ins, lw=0.8, color="darkorange", label="inside 9997–10003 MA500")
        ax2.set_ylim(0, 1.05)
        ax2.set_ylabel("rolling rate")
        ax.set_title(f"ASH day {day}: churn vs tight inside band")
        ax2.legend(loc="upper right", fontsize=8)
    axes[-1].set_xlabel("timestamp")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_pepper_trade_prices(T: pd.DataFrame, path: Path) -> None:
    Tp = T[T["symbol"] == r1.PEPPER]
    if Tp.empty:
        return
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.hist(Tp["price"].astype(float), bins=50, color="purple", edgecolor="white", alpha=0.85)
    ax.set_title("INTARIAN market_trades: trade prices (all days)")
    ax.set_xlabel("price")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def build_html(fig_names: dict[str, str], stats_lines: list[str]) -> str:
    """fig_names: section_id -> relative path from html file."""
    css = """
    :root { --bg:#0f1419; --panel:#1a2332; --text:#e7ecf3; --muted:#9aa8b8; --accent:#5eb8ff; --border:#2d3d52; }
    * { box-sizing: border-box; }
    body { font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg); color: var(--text);
           line-height: 1.55; margin: 0; padding: 0 0 4rem; }
    header { background: linear-gradient(135deg, #1a2a3d, #0f1419); border-bottom: 1px solid var(--border);
             padding: 2rem 1.5rem 1.5rem; }
    header h1 { margin: 0 0 0.5rem; font-size: 1.65rem; font-weight: 600; }
    header p { margin: 0; color: var(--muted); max-width: 56rem; }
    nav { position: sticky; top: 0; z-index: 10; background: rgba(15,20,25,0.92); backdrop-filter: blur(8px);
           border-bottom: 1px solid var(--border); padding: 0.75rem 1rem; }
    nav a { color: var(--accent); text-decoration: none; margin-right: 1.1rem; font-size: 0.9rem; }
    nav a:hover { text-decoration: underline; }
    main { max-width: 58rem; margin: 0 auto; padding: 1.5rem 1rem; }
    section { margin-bottom: 2.75rem; }
    section h2 { font-size: 1.2rem; border-left: 4px solid var(--accent); padding-left: 0.65rem; margin-top: 0; }
    .card { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 1rem 1.15rem; margin: 1rem 0; }
    .card p:last-child { margin-bottom: 0; }
    figure { margin: 1rem 0; background: #111820; border-radius: 8px; padding: 0.5rem; border: 1px solid var(--border); }
    figure img { width: 100%; height: auto; display: block; border-radius: 4px; }
    figcaption { font-size: 0.85rem; color: var(--muted); margin-top: 0.5rem; }
    ul.key { color: var(--muted); padding-left: 1.2rem; }
    ul.key li { margin: 0.35rem 0; }
    pre.stats { font-size: 0.78rem; background: #111820; border: 1px solid var(--border); padding: 1rem; overflow-x: auto; border-radius: 8px; color: #c5d4e0; }
    footer { text-align: center; color: var(--muted); font-size: 0.85rem; padding: 2rem 1rem; border-top: 1px solid var(--border); }
    """

    def section(sid: str, title: str, body: str, fig_key: str | None = None, cap: str = "") -> str:
        fig_html = ""
        if fig_key and fig_key in fig_names:
            fig_html = f"""
            <figure id="fig-{esc(fig_key)}">
              <img src="{esc(fig_names[fig_key])}" alt="{esc(title)}" loading="lazy" />
              <figcaption>{esc(cap)}</figcaption>
            </figure>"""
        return f"""
        <section id="{esc(sid)}">
          <h2>{esc(title)}</h2>
          <div class="card">{body}</div>
          {fig_html}
        </section>"""

    body_intro = """<p>This report summarises Round 1 official CSVs (three independent <strong>10 000-tick</strong> sessions)
    for <code>ASH_COATED_OSMIUM</code> and <code>INTARIAN_PEPPER_ROOT</code>. It mirrors the style of a tutorial-round
    write-up: narrative, caveats, and many static plots for offline review.</p>
    <ul class="key">
      <li><strong>Do not pool days</strong> as one price process — each day starts a new level band (especially INTARIAN).</li>
      <li><strong>Mid return lag-1 autocorrelation ≈ −0.5</strong> is largely <strong>bid–ask bounce</strong> in the mid proxy, not alpha.</li>
      <li>Use <strong>detrended / session</strong> statistics for INTARIAN; use <strong>peg + microstructure</strong> for ASH.</li>
    </ul>"""

    nav = """<nav>
      <a href="#intro">Intro</a>
      <a href="#sessions-raw">INTARIAN raw</a>
      <a href="#sessions-norm">INTARIAN rebased</a>
      <a href="#detrend-example">Detrend</a>
      <a href="#acf">ACF</a>
      <a href="#vr">VR</a>
      <a href="#hurst-ash">Hurst</a>
      <a href="#ash-dev">ASH</a>
      <a href="#pepper-spread">Spreads</a>
      <a href="#sig-hex">Signals</a>
      <a href="#cross">Cross</a>
      <a href="#stats">Numbers</a>
      <a href="#legacy">+ deep_dive</a>
    </nav>"""

    parts = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8" />',
        '<meta name="viewport" content="width=device-width, initial-scale=1" />',
        "<title>IMC Prosperity 4 — Round 1 Analysis Report</title>",
        f"<style>{css}</style>",
        "</head><body>",
        "<header><h1>IMC Prosperity 4 — Round 1 Deep Dive</h1>",
        "<p>Price &amp; market trade CSVs · exploratory patterns · microstructure diagnostics</p></header>",
        nav,
        "<main>",
        f'<section id="intro"><h2>Introduction</h2><div class="card">{body_intro}</div></section>',
        section(
            "sessions-raw",
            "INTARIAN — three sessions & intra-session drift",
            "<p>Overlay shows each day’s mid on the same timestamp axis. The rebased chart removes the ~+1000 "
            "level shift between days so you can compare <em>shape</em> of intra-session drift.</p>",
            "intarian_sessions",
            "Raw mids: upward drift within each session is visible; day boundaries are not continuous walks.",
        ),
        section(
            "sessions-norm",
            "INTARIAN — rebased to session open",
            "<p>Same data as above, minus each session’s first mid — highlights parallel drift shapes.</p>",
            "intarian_norm",
            "Each series starts at 0; typical net move is ~+1000 ticks × ~0.11 ≈ +1000 price points per session.",
        ),
        section(
            "detrend-example",
            "Linear trend + residuals (example day)",
            "<p>ADF on raw mid fails (unit root) while ADF on <strong>linearly detrended</strong> mids rejects a unit root "
            "in the residual — consistent with “smooth drift + stationary band” within a session.</p>",
            "intarian_detrend",
            "Example: day −2. Red line = OLS trend; lower panel = residuals.",
        ),
        section(
            "detrend-quarters",
            "Drift homogeneity across quarters",
            "<p>Heatmap of mean one-tick price change by quarter of each session. If mean-reversion dominated halves, "
            "you would see sign flips; instead drift is positive in every cell.</p>",
            "quarter_heatmap",
            "Quarters are by row index within each day (2500-tick bins on ~9200 rows).",
        ),
        section(
            "acf",
            "Autocorrelation at multiple return horizons",
            "<p>Lag-k autocorrelation for 1-, 2-, and 5-tick <strong>mid</strong> returns. The 1-tick curve near −0.5 "
            "largely collapses when using 2-tick returns — consistent with microstructure bounce.</p>",
            "acf_multiscale",
            "Left: ASH (peg). Right: INTARIAN.",
        ),
        section(
            "vr",
            "Variance ratios (log returns)",
            "<p>VR &lt; 1 at short horizons indicates variance of multi-period returns lower than random-walk scaling — "
            "common under mean-reversion <em>in returns</em> or microstructure; interpret next to plots, not alone.</p>",
            "variance_ratio",
            "Bars below the red line (VR=1) are “MR-ish” under this test.",
        ),
        section(
            "hurst-ash",
            "R/S scaling on log returns — ASH",
            "<p>Scatter of log segment length vs log mean R/S; slope ≈ Hurst exponent under classical R/S assumptions. "
            "Values are modest (~0.28–0.30) — not impossible Hurst values from mis-specified subsampled level series.</p>",
            "hurst_ash",
            "ASH",
        ),
        section(
            "hurst-pepper",
            "R/S scaling on log returns — INTARIAN",
            "",
            "hurst_pepper",
            "INTARIAN",
        ),
        section(
            "ash-dev",
            "ASH — peg deviation",
            "<p>Deviation from 10 000 by day; ASH remains tightly anchored.</p>",
            "ash_dev",
            "Deviation mid−10000.",
        ),
        section(
            "ash-spread",
            "ASH — L1 spread over time",
            "",
            "ash_spread",
            "Wider spread segments correspond to thinner books or bot quote shifts.",
        ),
        section(
            "pepper-spread",
            "INTARIAN — L1 spread over time",
            "<p>Spread width sets how much mid can bounce without true information; compare across days.</p>",
            "pepper_spread",
            "Three sessions stacked.",
        ),
        section(
            "ash-churn",
            "ASH — quote churn vs tight inside band",
            "<p>Rolling mean of “any L1 change” (blue) and rare “inside 9997–10003” band (orange), with mid deviation in grey.</p>",
            "ash_churn",
            "High churn vs tutorial EMERALDS (~3%) — strategy must assume faster-moving L1.",
        ),
        section(
            "sig-hex",
            "INTARIAN — signal density plots",
            "<p>Hexbin: (SMA10−mid) vs 5-tick forward move, and L1 imbalance vs 1-tick forward move. "
            "Correlations are partly mechanical from bounce; use for <em>relative</em> comparison of signal families.</p>",
            "pepper_signals",
            "Pooled valid-L1 rows across all days (caveat: cross-day pooling for visuals only).",
        ),
        section(
            "sig-trades",
            "INTARIAN — market trade prices",
            "<p>Histogram of transaction prices from <code>trades_round_1_*.csv</code> (bot prints).</p>",
            "pepper_trades",
            "Transaction prices avoid mid bounce; distribution is informative for where bots actually print.",
        ),
        section(
            "cross",
            "Cross-product mids & return scatter",
            "<p>Joined on (day, timestamp) where both have valid L1. Level correlation is dominated by day dummies; "
            "return scatter shows weak short-horizon linkage.</p>",
            "cross_mids",
            "Left: level scatter coloured by day. Right: concurrent returns.",
        ),
        '<section id="stats"><h2>Key numbers (auto)</h2><div class="card"><p>Quick snapshot from this run:</p>',
        "<pre class=\"stats\">",
        esc("\n".join(stats_lines)),
        "</pre></div></section>",
        "</main>",
        f"<footer>Generated {esc(datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'))} · "
        "Open this file from disk; figures live alongside in <code>html_figures/</code>.</footer>",
        "</body></html>",
    ]

    return "".join(parts)


def main() -> None:
    fig_style()
    data_dir = r1.pick_data_dir()
    OUT.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)

    P = r1.load_prices(data_dir)
    T = r1.load_trades(data_dir)
    v_ash = r1.valid_l1(P, r1.ASH)
    v_pep = r1.valid_l1(P, r1.PEPPER)

    plot_intarian_sessions(v_pep, FIG / "intarian_sessions.png")
    plot_intarian_normalized(v_pep, FIG / "intarian_norm.png")
    plot_intarian_detrend_one_day(v_pep, -2, FIG / "intarian_detrend.png")
    plot_quarter_heatmap(v_pep, FIG / "quarter_heatmap.png")
    plot_acf_multiscale(v_ash, v_pep, FIG / "acf_multiscale.png")
    plot_variance_ratio_bars(v_ash, v_pep, FIG / "variance_ratio.png")
    plot_hurst_rs_fit(v_ash, r1.ASH, FIG / "hurst_ash.png")
    plot_hurst_rs_fit(v_pep, r1.PEPPER, FIG / "hurst_pepper.png")
    plot_ash_deviation(v_ash, FIG / "ash_dev.png")
    plot_spreads(v_ash, r1.ASH, FIG / "ash_spread.png")
    plot_spreads(v_pep, r1.PEPPER, FIG / "pepper_spread.png")
    plot_cross_mids(P, FIG / "cross_mids.png")
    plot_pepper_signals(v_pep, FIG / "pepper_signals.png")
    plot_ash_churn_and_inside(v_ash, FIG / "ash_churn.png")
    if not T.empty:
        plot_pepper_trade_prices(T, FIG / "pepper_trades.png")

    # Relative paths from OUT/round1_analysis_report.html → html_figures/
    rel = "html_figures/"
    fig_map = {
        "intarian_sessions": rel + "intarian_sessions.png",
        "intarian_norm": rel + "intarian_norm.png",
        "intarian_detrend": rel + "intarian_detrend.png",
        "quarter_heatmap": rel + "quarter_heatmap.png",
        "acf_multiscale": rel + "acf_multiscale.png",
        "variance_ratio": rel + "variance_ratio.png",
        "hurst_ash": rel + "hurst_ash.png",
        "hurst_pepper": rel + "hurst_pepper.png",
        "ash_dev": rel + "ash_dev.png",
        "ash_spread": rel + "ash_spread.png",
        "ash_churn": rel + "ash_churn.png",
        "pepper_signals": rel + "pepper_signals.png",
        "pepper_trades": rel + "pepper_trades.png",
        "cross_mids": rel + "cross_mids.png",
        "pepper_spread": rel + "pepper_spread.png",
    }
    if not (FIG / "pepper_trades.png").is_file():
        del fig_map["pepper_trades"]

    # Also link existing deep-dive PNGs (parent folder)
    legacy = {
        "legacy_intarian_3d": "../intarian_mid_3days.png",
        "legacy_ash_trades": "../ash_trade_prices.png",
        "legacy_ash_trademid": "../ash_trade_minus_mid.png",
        "legacy_ash_l1": "../ash_l1_histograms.png",
    }

    stats_lines = [
        f"Data: {data_dir}",
        f"Valid L1 rows ASH: {len(v_ash)}  INTARIAN: {len(v_pep)}",
    ]
    for day in sorted(v_pep["day"].unique()):
        w = v_pep[v_pep["day"] == day]["mid_price"].astype(float).values
        if len(w) > 1:
            stats_lines.append(
                f"INTARIAN day {day}: start {w[0]:.2f} end {w[-1]:.2f} mean_tick_dr {np.mean(np.diff(w)):+.5f}"
            )
    midp = v_pep["mid_price"].astype(float).values
    r1tick = np.diff(midp)
    stats_lines.append(f"INTARIAN pooled lag-1 acf(1-tick mid ret): {np.corrcoef(r1tick[:-1], r1tick[1:])[0,1]:+.4f}")
    lr = np.diff(np.log(v_ash["mid_price"].astype(float).values))
    lr = lr[np.isfinite(lr)]
    stats_lines.append(f"ASH Hurst R/S log-ret: {r1.hurst_rs_standard(lr):.3f}")
    lr2 = np.diff(np.log(v_pep["mid_price"].astype(float).values))
    lr2 = lr2[np.isfinite(lr2)]
    stats_lines.append(f"INTARIAN Hurst R/S log-ret: {r1.hurst_rs_standard(lr2):.3f}")

    html_doc = build_html(fig_map, stats_lines)

    # Appendix: embed legacy figures as extra section
    legacy_block = "<section id=\"legacy\"><h2>Figures from round1_deep_dive.py</h2><div class=\"card\"><p>Earlier pipeline outputs (same folder parent):</p></div>"
    for key, src in legacy.items():
        p = OUT / src.lstrip("../")
        if p.is_file():
            legacy_block += f'<figure><img src="{esc(src)}" alt="{esc(key)}" loading="lazy" /></figure>'
    legacy_block += "</section>"
    html_doc = html_doc.replace("</main>", legacy_block + "\n</main>")

    out_html = OUT / "round1_analysis_report.html"
    out_html.write_text(html_doc, encoding="utf-8")
    print("Wrote", out_html)


if __name__ == "__main__":
    main()
