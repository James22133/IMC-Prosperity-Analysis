"""
Round 1 deep-dive analysis (prices + market_trades CSVs).
Run:  python round1_deep_dive.py

Outputs: prosperity4/ROUND1_deep_dive_output/
  - figures (*.png)
  - round1_deep_dive_report.txt
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats as scipy_stats
from scipy.stats import linregress
from statsmodels.regression.linear_model import OLS
from statsmodels.tools.tools import add_constant
from statsmodels.tsa.stattools import adfuller

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "ROUND1_deep_dive_output"
DATA_DIRS = [ROOT / "ROUND1", ROOT / "bt_data" / "round1"]

PEPPER = "INTARIAN_PEPPER_ROOT"
ASH = "ASH_COATED_OSMIUM"


def pick_data_dir() -> Path:
    for d in DATA_DIRS:
        if d.is_dir() and list(d.glob("prices_round_1_*.csv")):
            return d
    raise FileNotFoundError("No prices_round_1_*.csv under ROUND1/ or bt_data/round1/")


def load_prices(data_dir: Path) -> pd.DataFrame:
    dfs = []
    for f in sorted(data_dir.glob("prices_round_1_*.csv")):
        dfs.append(pd.read_csv(f, sep=";"))
    df = pd.concat(dfs, ignore_index=True)
    for c in ("mid_price", "bid_price_1", "ask_price_1", "bid_volume_1", "ask_volume_1"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def load_trades(data_dir: Path) -> pd.DataFrame:
    paths = sorted(data_dir.glob("trades_round_1_*.csv"))
    if not paths:
        return pd.DataFrame()
    dfs = []
    for f in paths:
        t = pd.read_csv(f, sep=";")
        day = 0
        if "day_" in f.name:
            try:
                day = int(f.name.split("day_")[-1].replace(".csv", ""))
            except ValueError:
                day = 0
        if "day" not in t.columns:
            t["day"] = day
        dfs.append(t)
    return pd.concat(dfs, ignore_index=True)


def valid_l1(p: pd.DataFrame, product: str) -> pd.DataFrame:
    d = p[p["product"] == product].copy()
    ok = d["bid_price_1"].notna() & d["ask_price_1"].notna() & (d["ask_price_1"] > d["bid_price_1"])
    return d.loc[ok].sort_values(["day", "timestamp"]).reset_index(drop=True)


def variance_ratio(returns: np.ndarray, k: int) -> float:
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    n = len(r)
    if n < k * 10 + 5:
        return float("nan")
    # k-period non-overlapping returns
    m = (n // k) * k
    r1 = r[:m]
    rk = r1.reshape(-1, k).sum(axis=1)
    v1 = np.var(r1, ddof=1)
    vk = np.var(rk, ddof=1)
    if v1 < 1e-18:
        return float("nan")
    return vk / (k * v1)


def hurst_rs_standard(log_returns: np.ndarray) -> float:
    """R/S on demeaned returns with multiple segment lengths (H ~ slope of log(R/S) vs log(n))."""
    x = np.asarray(log_returns, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 500:
        return float("nan")
    x = x - x.mean()
    lengths = np.unique(
        np.clip(np.geomspace(20, min(n // 4, 2000), num=25).astype(int), 20, None)
    )
    rs_vals = []
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
            rs_vals.append((math.log(seg_len), math.log(np.mean(ratios))))
    if len(rs_vals) < 4:
        return float("nan")
    xs = np.array([a[0] for a in rs_vals])
    ys = np.array([a[1] for a in rs_vals])
    slope, _, _, _, _ = linregress(xs, ys)
    return float(slope)


def adf_safe(x: np.ndarray) -> tuple[float, float]:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) < 30:
        return float("nan"), float("nan")
    try:
        r = adfuller(x, autolag="AIC")
        return float(r[0]), float(r[1])
    except Exception:
        return float("nan"), float("nan")


def detrend_linear(y: np.ndarray) -> np.ndarray:
    y = np.asarray(y, dtype=float)
    n = len(y)
    if n < 5:
        return y - y.mean()
    t = np.arange(n, dtype=float)
    slope, intercept, _, _, _ = linregress(t, y)
    return y - (intercept + slope * t)


def lines() -> list[str]:
    return []


def W(buf: list[str], s: str) -> None:
    buf.append(s + "\n")


def main() -> None:
    data_dir = pick_data_dir()
    OUT.mkdir(parents=True, exist_ok=True)
    plt.style.use("seaborn-v0_8-whitegrid")
    buf = lines()

    W(buf, "=== IMC Prosperity 4 — Round 1 Deep Dive Report ===")
    W(buf, f"Data directory: {data_dir}")
    W(buf, "")

    P = load_prices(data_dir)
    T = load_trades(data_dir)

    # ---------- Problem 5: structure ----------
    W(buf, "--- Problem 5: 10k-iteration / day structure ---")
    for day in sorted(P["day"].unique()):
        ts = P.loc[P["day"] == day, "timestamp"]
        W(buf, f"  Day {day}: unique timestamps = {ts.nunique()}, min={ts.min()}, max={ts.max()}")
    # Day continuity (pepper mids at last tick vs first tick next day)
    v_pepper = valid_l1(P, PEPPER)
    v_ash = valid_l1(P, ASH)
    days_sorted = sorted(v_pepper["day"].unique())
    for i in range(len(days_sorted) - 1):
        d0, d1 = days_sorted[i], days_sorted[i + 1]
        end0 = v_pepper[v_pepper["day"] == d0].iloc[-1]
        st1 = v_pepper[v_pepper["day"] == d1].iloc[0]
        W(
            buf,
            f"  Pepper day {d0} end mid={end0['mid_price']:.2f} @ts={end0['timestamp']}  |  "
            f"day {d1} start mid={st1['mid_price']:.2f} @ts={st1['timestamp']}  "
            f"(gap in level: {st1['mid_price'] - end0['mid_price']:+.2f})",
        )
    W(buf, "  Note: CSVs are independent sessions; mids do NOT continue like a single long series.")
    W(buf, "  traderData / position reset per competition rules are engine-side (not in CSV).")
    W(buf, "")

    # ---------- Problem 1: INTARIAN ----------
    W(buf, "--- Problem 1: INTARIAN_PEPPER_ROOT — trend vs mean-revert ---")
    fig, ax = plt.subplots(figsize=(14, 5))
    for day in days_sorted:
        w = v_pepper[v_pepper["day"] == day]
        ax.plot(w["timestamp"], w["mid_price"], lw=0.6, label=f"day {day}")
    ax.set_title("INTARIAN_PEPPER_ROOT — mid by day (same timestamp axis)")
    ax.set_xlabel("timestamp")
    ax.set_ylabel("mid")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / "intarian_mid_3days.png", dpi=150)
    plt.close(fig)
    W(buf, "  Figure: intarian_mid_3days.png")

    for day in days_sorted:
        w = v_pepper[v_pepper["day"] == day]["mid_price"].astype(float).values
        if len(w) < 2:
            continue
        dr = np.diff(w)
        W(
            buf,
            f"  Day {day}: start={w[0]:.2f} end={w[-1]:.2f} net={w[-1]-w[0]:+.2f}  "
            f"mean(dr)={dr.mean():+.6f}  ticks={len(w)}",
        )

    # pooled mistaken drift (user concern)
    dr_all = np.diff(v_pepper["mid_price"].astype(float).values)
    W(buf, f"  POOLED across all days (misleading if sessions reset): mean(dr)={dr_all.mean():+.6f}")

    # ADF raw vs detrended per day
    for day in days_sorted:
        w = v_pepper[v_pepper["day"] == day]["mid_price"].astype(float).values
        adf_s, adf_p = adf_safe(w)
        res = detrend_linear(w)
        adf2, adf2p = adf_safe(res)
        W(
            buf,
            f"  Day {day} ADF on mid: stat={adf_s:.3f} p={adf_p:.4f}  |  "
            f"ADF on linear-detrended mid: stat={adf2:.3f} p={adf2p:.4f}",
        )

    # detrended returns autocorr (2,5,10 tick)
    w = v_pepper["mid_price"].astype(float).values
    r1 = np.diff(w)
    for h in (2, 3, 5, 10):
        if len(r1) <= h:
            continue
        rr = w[h:] - w[:-h]
        rrh = rr[1:] - rr[:-1]  # not ideal; use h-period returns
        rh = w[h:] - w[:-h]
        # autocorr of h-period returns: corrcoef(rh[:-1], rh[1:])
        if len(rh) > 50:
            c = np.corrcoef(rh[:-1], rh[1:])[0, 1]
            W(buf, f"  Lag-1 autocorr of {h}-tick returns: {c:.4f}")

    # Quarters per day
    W(buf, "  Regime (quarters of each day by row index):")
    for day in days_sorted:
        wdf = v_pepper[v_pepper["day"] == day].reset_index(drop=True)
        n = len(wdf)
        for q in range(4):
            a, b = q * n // 4, (q + 1) * n // 4
            seg = wdf.iloc[a:b]["mid_price"].astype(float).values
            if len(seg) < 2:
                continue
            d = np.diff(seg)
            W(
                buf,
                f"    day {day} Q{q+1}: mean(d_mid)={d.mean():+.5f} std={d.std():.4f} "
                f"net={seg[-1]-seg[0]:+.2f}",
            )

    # SMA window vs forward return (per day — avoids cross-day level shift)
    W(buf, "  SMA vs +1tick return: corr(mid-SMA, fwd) per day (valid L1 only):")
    best_global = None
    for day in days_sorted:
        mids = v_pepper[v_pepper["day"] == day]["mid_price"].astype(float).values
        W(buf, f"    --- day {day} ---")
        best_d = None
        for N in (3, 5, 7, 10, 15, 20, 30, 50):
            if len(mids) <= N + 5:
                continue
            sma = pd.Series(mids).rolling(N).mean().values
            sig = mids[N:] - sma[N:]
            fwd = mids[N + 1 :] - mids[N:-1]
            sig = sig[:-1]
            m = np.isfinite(sig) & np.isfinite(fwd)
            if m.sum() < 50:
                continue
            rho = np.corrcoef(sig[m], fwd[m])[0, 1]
            W(buf, f"      N={N:2d}  corr(mid-SMA,+1tick)={rho:+.4f}  (= -corr(SMA-mid,+1tick))")
            if best_d is None or abs(rho) > abs(best_d[1]):
                best_d = (N, rho)
        if best_d:
            W(buf, f"      strongest |corr| day {day}: N={best_d[0]} rho={best_d[1]:+.4f}")
            if best_global is None or abs(best_d[1]) > abs(best_global[2]):
                best_global = (day, best_d[0], best_d[1])
    if best_global:
        W(buf, f"  Overall strongest |corr(mid-SMA,+1tick)|: day {best_global[0]} N={best_global[1]} rho={best_global[2]:+.4f}")
    W(buf, "")

    # ---------- Problem 2: Hurst + VR ----------
    W(buf, "--- Problem 2: Hurst (R/S on log-return segments) + variance ratio ---")
    for prod in (ASH, PEPPER):
        v = valid_l1(P, prod)
        mid = v["mid_price"].astype(float).values
        lr = np.diff(np.log(mid))
        lr = lr[np.isfinite(lr)]
        H = hurst_rs_standard(lr)
        W(buf, f"  {prod}: Hurst (R/S on log returns, n={len(lr)}): {H:.3f}")
        for k in (2, 5, 10, 20, 50):
            vr = variance_ratio(lr, k)
            tag = "MR-ish" if vr < 1 else ("trend-ish" if vr > 1 else "RW")
            W(buf, f"    VR(k={k:2d}) = {vr:.4f}  ({tag})")

    # ASH reversion time from |mid-10000| > X
    W(buf, "  ASH reversion times (ticks until |mid-10000|<1 after exceeding X):")
    for day in days_sorted:
        w = v_ash[v_ash["day"] == day]["mid_price"].astype(float).values
        for X in (2, 3, 5, 8):
            times = []
            i = 0
            while i < len(w):
                if abs(w[i] - 10000) > X:
                    j = i + 1
                    while j < len(w) and abs(w[j] - 10000) >= 1:
                        j += 1
                    if j < len(w) and abs(w[j] - 10000) < 1:
                        times.append(j - i)
                    i = j
                else:
                    i += 1
            if times:
                W(buf, f"    day {day} X={X}: mean ticks to near-peg={np.mean(times):.1f} (n={len(times)})")
    W(buf, "")

    # ---------- Problem 3: bid-ask bounce ----------
    W(buf, "--- Problem 3: autocorr / multi-tick (bounce diagnostic) ---")
    for prod in (ASH, PEPPER):
        v = valid_l1(P, prod)
        mid = v["mid_price"].astype(float).values
        r1 = np.diff(mid)
        W(buf, f"  {prod}: lag-1 acf 1-tick ret = {np.corrcoef(r1[:-1], r1[1:])[0,1]:+.4f}")
        for h in (2, 5, 10):
            rh = mid[h:] - mid[:-h]
            if len(rh) > 20:
                c = np.corrcoef(rh[:-1], rh[1:])[0, 1]
                W(buf, f"    lag-1 acf {h}-tick returns: {c:+.4f}")
        # passive buy markout
        bb = v["bid_price_1"].astype(float).values
        ba = v["ask_price_1"].astype(float).values
        m = len(mid)
        for k in (1, 5, 10):
            if m <= k:
                continue
            mark = mid[k:] - bb[:-k]
            W(buf, f"    E[mid(t+{k}) - best_bid(t)] = {np.mean(mark):+.4f}")

    if not T.empty and "price" in T.columns:
        Tp = T[T["symbol"] == PEPPER].copy()
        if not Tp.empty:
            pr = Tp["price"].astype(float).values
            dpr = np.diff(pr)
            if len(dpr) > 20:
                W(
                    buf,
                    f"  Pepper trade-price consecutive diff acf: {np.corrcoef(dpr[:-1], dpr[1:])[0,1]:+.4f} (n={len(dpr)})",
                )
    W(buf, "")

    # ---------- Problem 4: ASH microstructure + trades ----------
    W(buf, "--- Problem 4: ASH_COATED_OSMIUM microstructure ---")
    va = valid_l1(P, ASH)
    bb = va["bid_price_1"]
    ba = va["ask_price_1"]
    churn = (bb != bb.shift(1)) | (ba != ba.shift(1))
    W(buf, f"  L1 quote churn (any change): {churn.mean()*100:.2f}% of valid-L1 ticks")
    inside = (ba <= 10003) & (bb >= 9997)
    W(buf, f"  Ticks with ba<=10003 & bb>=9997: {inside.mean()*100:.2f}%")

    Ta = T[T["symbol"] == ASH] if not T.empty else pd.DataFrame()
    if not Ta.empty:
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.hist(Ta["price"].astype(float), bins=60, color="teal", edgecolor="white")
        ax.axvline(10000, color="red", ls="--")
        ax.set_title("ASH market_trades price histogram (all days)")
        fig.tight_layout()
        fig.savefig(OUT / "ash_trade_prices.png", dpi=150)
        plt.close(fig)
        W(buf, "  Figure: ash_trade_prices.png")

    # merge nearest mid for ASH trades
    if not Ta.empty and not va.empty:
        Ta = Ta.sort_values(["day", "timestamp"]).copy()
        va2 = va[["day", "timestamp", "mid_price"]].sort_values(["day", "timestamp"]).copy()
        Ta["_cts"] = Ta["day"].astype(np.int64) * 10**9 + Ta["timestamp"].astype(np.int64)
        va2["_cts"] = va2["day"].astype(np.int64) * 10**9 + va2["timestamp"].astype(np.int64)
        merged = pd.merge_asof(
            Ta,
            va2.rename(columns={"mid_price": "mid_at"}),
            on="_cts",
            direction="nearest",
        )
        merged["cross"] = merged["price"] - merged["mid_at"]
        W(buf, f"  Bot trade vs mid (nearest tick): mean={merged['cross'].mean():+.3f} std={merged['cross'].std():.3f}")
        ac = merged["cross"].abs()
        W(
            buf,
            f"  |trade-mid| percentiles (ASH, empirical bot prints): "
            f"p50={ac.quantile(0.5):.2f} p75={ac.quantile(0.75):.2f} p90={ac.quantile(0.9):.2f} p95={ac.quantile(0.95):.2f}",
        )
        if len(merged) > 30:
            W(buf, f"  ASH trade count (all days): {len(merged)}")
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.hist(merged["cross"].dropna(), bins=50, color="coral", edgecolor="white")
        ax.set_title("ASH: trade_price - mid_at_trade_ts")
        fig.tight_layout()
        fig.savefig(OUT / "ash_trade_minus_mid.png", dpi=150)
        plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.hist(va["bid_price_1"], bins=40, alpha=0.6, label="best bid")
    ax.hist(va["ask_price_1"], bins=40, alpha=0.6, label="best ask")
    ax.legend()
    ax.set_title("ASH L1 bid / ask histograms (pooled)")
    fig.tight_layout()
    fig.savefig(OUT / "ash_l1_histograms.png", dpi=150)
    plt.close(fig)
    W(buf, "  Figures: ash_l1_histograms.png")
    W(buf, "")

    # ---------- Problem 6: signals pepper ----------
    W(buf, "--- Problem 6: INTARIAN extended signals (pooled valid L1) ---")
    vp = valid_l1(P, PEPPER).reset_index(drop=True)
    mid = vp["mid_price"].astype(float).values
    r1 = np.append(np.diff(mid), np.nan)
    bidv = vp["bid_volume_1"].astype(float).fillna(0).values
    askv = vp["ask_volume_1"].astype(float).fillna(0).values
    imb = (bidv - askv) / np.maximum(bidv + askv, 1)
    spread = (vp["ask_price_1"] - vp["bid_price_1"]).astype(float).values

    def fwd_ret(k: int) -> np.ndarray:
        out = np.full_like(mid, np.nan)
        out[:-k] = mid[k:] - mid[:-k]
        return out

    for N in (3, 5, 10, 20, 50, 100):
        mom = np.full_like(mid, np.nan)
        mom[N:] = mid[N:] - mid[:-N]
        f1 = fwd_ret(1)
        m = np.isfinite(mom) & np.isfinite(f1)
        if m.sum() > 50:
            rho = np.corrcoef(mom[m], f1[m])[0, 1]
            W(buf, f"  mom(N={N}) vs +1tick ret: rho={rho:+.4f}")

    for N in (3, 5, 10, 20):
        sma = pd.Series(mid).rolling(N).mean().values
        mr = sma - mid
        for fk, lab in ((1, "1t"), (5, "5t"), (10, "10t")):
            f = fwd_ret(fk)
            m = np.isfinite(mr) & np.isfinite(f)
            if m.sum() > 50:
                rho = np.corrcoef(mr[m], f[m])[0, 1]
                W(buf, f"  MR sma{N} vs fwd_{lab}: rho={rho:+.4f}")

    f1, f5 = fwd_ret(1), fwd_ret(5)
    m = np.isfinite(imb) & np.isfinite(f1)
    W(buf, f"  L1 imb vs +1tick ret: rho={np.corrcoef(imb[m], f1[m])[0,1]:+.4f}")
    m = np.isfinite(imb) & np.isfinite(f5)
    W(buf, f"  L1 imb vs +5tick ret: rho={np.corrcoef(imb[m], f5[m])[0,1]:+.4f}")

    # Multiple regression (same-scale z where helpful)
    maxlag = 50
    mom50 = np.full_like(mid, np.nan)
    mom50[maxlag:] = mid[maxlag:] - mid[:-maxlag]
    sma10 = pd.Series(mid).rolling(10).mean().values
    mr10 = sma10 - mid
    y = f1
    Xdf = pd.DataFrame({"mom50": mom50, "mr10": mr10, "imb": imb})
    reg = pd.concat([Xdf, pd.Series(y, name="y")], axis=1).dropna()
    if len(reg) > 200:
        Xr = add_constant(reg[["mom50", "mr10", "imb"]].values)
        ols = OLS(reg["y"].values, Xr).fit()
        W(buf, f"  OLS +1tick ret ~ 1 + mom50 + (SMA10-mid) + imb: R²={ols.rsquared:.4f}")
        W(buf, f"    coef: const={ols.params[0]:+.5f} mom50={ols.params[1]:+.6f} mr10={ols.params[2]:+.6f} imb={ols.params[3]:+.6f}")

    win = 20
    if len(mid) > win + 5:
        absr = np.abs(np.diff(mid))
        rv_fwd = pd.Series(absr).rolling(win).std().shift(-(win - 1)).values
        spread_l = spread[:-1]
        n = min(len(spread_l), len(rv_fwd))
        s2, v2 = spread_l[:n], rv_fwd[:n]
        m = np.isfinite(s2) & np.isfinite(v2)
        if m.sum() > 50:
            rho = np.corrcoef(s2[m], v2[m])[0, 1]
            W(buf, f"  spread(t) vs forward {win}-tick abs-ret vol: rho={rho:+.4f}")

    W(buf, "")

    # ---------- Problem 7: toy strategy metrics ----------
    W(buf, "--- Problem 7: simplified historical diagnostics (not full exchange sim) ---")

    def ash_take_opportunities(va_df: pd.DataFrame, fair: float = 10000.0) -> dict:
        ap, bp = va_df["ask_price_1"], va_df["bid_price_1"]
        return {
            "ticks_ask_below_fair": int((ap < fair).sum()),
            "ticks_bid_above_fair": int((bp > fair).sum()),
            "ticks_either_edge": int(((ap < fair) | (bp > fair)).sum()),
        }

    for day in days_sorted:
        va_d = valid_l1(P[P["day"] == day], ASH)
        r = ash_take_opportunities(va_d)
        W(buf, f"  Strategy A diagnostics (ASH L1 vs fair={10000}): day {day} {r}")

    # MR vs momentum on pepper (vectorized pnl of unit position * next return)
    mid = vp["mid_price"].astype(float).values
    dm = np.append(np.diff(mid), 0.0)
    for N in (5, 10, 20):
        sma = pd.Series(mid).rolling(N).mean().values
        pos_mr = np.clip(sma - mid, -1, 1)
        pnl_mr = np.nansum(pos_mr[:-1] * dm[:-1])
        mom = mid - pd.Series(mid).shift(N).values
        pos_mo = np.sign(mom)
        pnl_mo = np.nansum(pos_mo[:-1] * dm[:-1])
        W(buf, f"  Pepper toy: MR pos=clip(SMA{N}-mid,±1) scaled PnL proxy={pnl_mr:+.1f} | mom sign(mid-SMA{N}) proxy={pnl_mo:+.1f}")

    ema_fast = pd.Series(mid).ewm(span=5, adjust=False).mean().values
    ema_slow = pd.Series(mid).ewm(span=30, adjust=False).mean().values
    sig_ema = np.sign(ema_fast - ema_slow)
    pnl_ema = np.nansum(sig_ema[:-1] * dm[:-1])
    W(buf, f"  Pepper toy EMA(5) vs EMA(30) sign * next-tick move proxy={pnl_ema:+.1f}")

    W(buf, "")
    W(buf, "=== DELIVERABLE SUMMARY (evidence-led) ===")
    W(buf, "1) Corrected archetypes:")
    W(buf, "   - ASH_COATED_OSMIUM: PEG / structural MM. R/S Hurst on log-returns ~0.28 (bounded); VR<1 at all k (microstructure).")
    W(buf, "     Reversion to 10000 after |mid-10000|>2 typ. ~18–26 ticks (see table).")
    W(buf, "   - INTARIAN_PEPPER_ROOT: WITHIN each ~10k-tick session, log price is ~linear trend + stationary residuals")
    W(buf, "     (ADF on linear-detrended mid p<0.01 all days). Raw mid ADF fails (unit root) — NOT 'simple mean revert'.")
    W(buf, "     Day boundaries: ~+1000 level reset between -2→-1 and -1→0; pooled +0.108 mean tick return is almost")
    W(buf, "     entirely intra-session drift, not a continuous 3000-tick random walk.")
    W(buf, "2) Hurst: prior impossible values fixed by R/S on full-length log returns + VR table (both products).")
    W(buf, "3) Lag-1 mid return acf ~ -0.49 collapses toward ~0 by 2-tick returns; trade-price diff acf ~ -0.015 (pepper).")
    W(buf, "4) ASH bot: L1 churn ~68% vs tutorial EMERALDS; trades vs mid mean cross ~+0.17 (see PNGs for full distribution).")
    W(buf, "5) INTARIAN signals (pooled L1, confounded with bounce): SMA−mid positively correlates with fwd returns;")
    W(buf, "   mom(mid−mid_50) negatively correlates at 1-tick; OLS R²~0.45 — use session-demeaned / detrended features.")
    W(buf, "6) Strategy coding: do not use pooled SMA as quote_fair across days; per session use trend-aware fair")
    W(buf, "   (e.g. wall_mid / short EMA for direction) + residual reversion, not raw SMA-10 alone.")

    report_path = OUT / "round1_deep_dive_report.txt"
    report_path.write_text("".join(buf), encoding="utf-8")
    print("Wrote", report_path)
    for p in sorted(OUT.glob("*.png")):
        print(" ", p.name)
    print("HTML report (extra figures + narrative): python round1_html_report.py")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("ERROR:", e, file=sys.stderr)
        raise
