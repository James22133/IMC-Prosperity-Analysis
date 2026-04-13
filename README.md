# IMC Prosperity 4 — Trading Bot Analysis

This repo is a pretty extensive analysis of IMC's trading challenge in which I went back and forth with cursor and claude to build (in other words - vibecoded). It's  main goal was to 1figure out how the bots on the exchange actually behave, find patterns we can exploit and build strategies around them... See below for some cool results tho.

## What's in here

**`prosperity_analysis.ipynb`** — The main notebook. It loads up the raw market data (prices + trades), crunches a *ton* of stats, and spits out plots for everything from price dynamics to order book imbalances to regime detection. If you only look at one thing, look at this.

**`prosperity_analysis.html`** — Same notebook but pre-rendered as HTML, so you can view all the plots without running anything.

**`probes/`** — 13 small Python scripts (Probe 0–12) that act as experimental `Trader` bots. Each one pokes the exchange in a specific way — e.g., "what happens if I slam a market buy?" or "is the bot deterministic?" — and logs everything. You run these inside the Prosperity simulator.

**`log_parser.py`** — Parses the debug logs from those probes into clean DataFrames, generates plots, and can diff any probe against the baseline to see what changed.

**`TUTORIAL_ROUND_1 (1)/`** — The raw CSV data files (prices + trades for Round 0, Days -1 and -2).

## Quick start

1. Install deps:
   ```
   pip install pandas numpy matplotlib seaborn scipy statsmodels scikit-learn xgboost shap hmmlearn ruptures nolds PyWavelets plotly nbformat
   ```

2. Open `prosperity_analysis.ipynb` in Jupyter and run all cells. Or just open the `.html` file to browse the results.

3. To run a probe, drop any file from `probes/` into the Prosperity simulator as your trader script and grab the debug log. Then:
   ```
   python log_parser.py your_log.txt --output results/
   ```

## Key findings (tl;dr)

- **EMERALDS** is pegged around 10,000. The bot's spread flips between 8 and 16 ticks. When the spread is tight and book imbalance is strong, you can fade deviations from the peg with very high confidence.
- **TOMATOES** mean-reverts hard. A ~5-10 tick momentum window followed by a snap-back is highly predictable (R² ≈ 0.71). A Kalman filter + mean-reversion market-maker is the move here.
- **Zero price impact** on both products — you can trade aggressively without moving the market.
- The bots appear largely deterministic, which means once you map their logic, you can anticipate their quotes.

## What's next

Run the probes on the live sim, parse the logs, and use those insights to fine-tune the strategies outlined in the notebook. The big wins are in EMERALDS peg-fading and TOMATOES mean-reversion.
