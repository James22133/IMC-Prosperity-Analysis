# Emerald and Tomato deep dive

This report re-runs the Emerald and Tomato tutorial evidence with stricter checks than the existing notebook.
It focuses on what is stable across both available days, what is probably a sample artifact, and what that means for our current strategy.

## Scope

- Raw datasets reviewed: `prices_round_0_day_-2.csv`, `prices_round_0_day_-1.csv`, `trades_round_0_day_-2.csv`, `trades_round_0_day_-1.csv`.
- Existing repo artifacts reviewed: `prosperity_analysis.ipynb`, `prosperity_analysis.html`, `prosperity4/trader.py`, `prosperity4/backtest_analysis.py`, and the latest local backtest log if present.
- External principles referenced:
  - Prosperity 2 Linear Utility writeup: fixed-fair maker/taker logic for AMETHYSTS and market-maker-mid fair for STARFRUIT.
  - Prosperity 3 Frankfurt Hedgehogs writeup: wall-mid fair, zero-edge clearing to reopen capacity, and snapshot-based order flow.

## Dataset summary

```
              book_rows  trade_rows trade_tick_frac quote_change_frac spread_mean gap_abs_mean
day product                                                                                   
-2  EMERALDS      10000         191          0.0191            0.0648     15.7336       0.1332
    TOMATOES      10000         397          0.0397            0.6824     13.0652       0.4386
-1  EMERALDS      10000         208          0.0208            0.0618     15.7432       0.1284
    TOMATOES      10000         423          0.0423            0.6756     12.9753       0.4618
```

## Core conclusions

1. EMERALDS is a structural market-making product, not a forecasting product.
2. TOMATOES is best described as a slowly moving wall-mid fair value plus a one-tick quote asymmetry process that snaps back quickly.
3. The strongest Tomato alpha is quote-state alpha, not a spread-crossing directional alpha.
4. The notebook has a meaningful trade-feature leakage issue and an EMERALDS/TOMATOES pair-trading conclusion that does not survive practical scrutiny.

## EMERALDS

The hidden structure is unusually clean. The wall mid is exactly 10,000 on every tutorial row, so all movement in the displayed mid comes from one side temporarily collapsing from the normal inside quote back to fair.

```
    default_state_pct fair_touch_buy_pct fair_touch_sell_pct default_gap_corr_to_next_delta                 trade_prices
day                                                                                                                     
-2             0.9667             0.0170              0.0163                        -0.7039   9992:98, 10000:3, 10008:90
-1             0.9679             0.0163              0.0158                        -0.6971  9992:101, 10000:8, 10008:99
```

Gap versus next displayed-mid move:

```
         mean  count
gap                 
-4.0   3.9279    333
 0.0  -0.0025  19344
 4.0  -3.9252    321
```

Key takeaways:

- Default state is `2/2`: the best bid and ask sit 2 ticks inside the deep wall on both sides.
- The only displaced states are `2/10` and `10/2`, and they are one-tick events.
- Fair-touch opportunities show up on about 1.6% to 1.7% of ticks per side, so zero-edge clearing trades matter.
- This is a capacity-management game. The prior-winner lesson of clearing inventory at fair is fully supported by the local data.

## TOMATOES

TOMATOES becomes much cleaner under the wall-mid lens. The displayed mid can be written as `wall_mid + (bid_inside - ask_inside) / 2`, so most short-horizon predictability comes from quote asymmetry around a slower fair process.

```
    wall_start   wall_end   wall_min   wall_max wide_state_pct active_gap_pct active_run_mean inactive_run_mean gap_abs_mean gap_to_next_delta_corr
day                                                                                                                                                
-2   5000.0000  5006.5000  4989.0000  5035.0000         0.9279         0.0719          1.0620           13.6888       0.4386                -0.6214
-1   5006.0000  4957.0000  4948.0000  5009.0000         0.9278         0.0719          1.0861           13.9985       0.4618                -0.6171
```

Most common inside-quote states:

```
                           count     pct
day bid_inside ask_inside               
-2  1.0        1.0          4916  0.4916
               2.0          2100  0.2100
    2.0        1.0          2030  0.2030
               2.0           233  0.0233
    1.0        8.0           120  0.0120
    7.0        1.0           110  0.0110
-1  1.0        1.0          4670  0.4670
               2.0          2353  0.2353
    2.0        1.0          2253  0.2253
    1.0        8.0           112  0.0112
    7.0        1.0           111  0.0111
    1.0        7.0            72  0.0072
```

Gap versus next displayed-mid move:

```
         mean  count
gap                 
-4.5   4.0586    128
-4.0   4.0929     70
-3.5   3.3025    276
-3.0   2.8786    140
-2.5   2.8050    100
-0.5   0.1251   4458
 0.0  -0.0220   9819
 0.5  -0.1564   4283
 2.0  -2.3942    104
 2.5  -2.5261    153
 3.0  -2.8463    283
 3.5  -3.6642     67
 4.0  -3.6624    117
```

Gap response split by spread regime (`spread_narrow = 1` means spread <= 9):

```
                       mean  count
spread_narrow gap                 
0             -0.5   0.1292   4453
               0.0  -0.0220   9819
               0.5  -0.1564   4283
1             -4.5   4.0586    128
              -4.0   4.0929     70
              -3.5   3.3025    276
              -3.0   2.8786    140
              -2.5   2.8050    100
              -0.5  -3.6000      5
               2.0  -2.3942    104
               2.5  -2.5261    153
               3.0  -2.8463    283
               3.5  -3.6642     67
               4.0  -3.6624    117
```

The hidden pattern is that the large-gap states are the narrow-spread states, and they usually last one tick only. The wide default state lasts about 14 ticks on average; the active `|gap| >= 2` state lasts about 1.1 ticks.

Fair-proxy comparison:

```
             mse_to_next_mid mse_to_next_wall
day proxy                                    
-2  wall_mid          1.1221           0.3992
    mid               1.8089           1.1011
    ema5              1.2605           0.5412
    ema10             1.5369           0.8167
    ema20             2.0905           1.3703
-1  wall_mid          1.1216           0.4003
    mid               1.7878           1.1077
    ema5              1.2839           0.5451
    ema10             1.5928           0.8454
    ema20             2.2209           1.4657
```

Cross-day out-of-sample regression for `next_mid_delta`, using only interpretable state variables:

```
                        r2    corr active_sign_acc active_nonzero_sign_acc active_frac coef_gap coef_spread_narrow coef_imbalance_l1 coef_mom1 coef_dw_prev intercept
train_day test_day                                                                                                                                                   
-2        -1        0.3854  0.6209          0.7972                  0.9097      0.0986  -0.8509            -0.0046            0.7390   -0.0201      -0.1380   -0.0195
-1        -2        0.3931  0.6271          0.8606                  0.9306      0.0904  -0.8613             0.0055            0.4136   -0.0089      -0.1327   -0.0226
```

How to read this:

- The gap coefficient is stable around `-0.85` to `-0.86` out of sample. That is the real signal.
- The active-signal hit rate is high because the model only becomes bold on those one-tick dislocation states.
- This is much more believable than the notebook's pooled in-sample `R^2` claims.

Why spread-crossing is still a mistake:

```
               samples avg_abs_next_mid_move avg_spread avg_move_minus_spread
gap_threshold                                                                
2.0               1438                3.1732     7.0786               -3.9054
2.5               1334                3.2339     7.0067               -3.7729
3.0               1081                3.3599     6.7447               -3.3848
3.5                658                3.6527     6.1565               -2.5038
4.0                315                3.9254     5.5556               -1.6302
```

Even when `|gap| >= 4`, the average next absolute mid move is still smaller than the current spread. The edge exists relative to fair value, not relative to a full aggressive round-trip through the visible spread.

Take-edge summary:

```
    buy_opp_pct sell_opp_pct buy_edge_mean sell_edge_mean
day                                                      
-2       0.0243       0.0113        0.8066         0.5133
-1       0.0238       0.0134        0.7521         0.4701
```

## Notebook audit

Trade merge audit:

```
          exact_trade_rows  backward_asof_rows duplication_ratio  lagged_rows
product                                                                      
EMERALDS               399                 788            1.9749          389
TOMATOES               819                1601            1.9548          782
```

The existing notebook uses a backward `merge_asof(..., tolerance=100)` for trade features. Because book timestamps are spaced by 100, almost every trade gets duplicated onto the next book row as well.

Cross-product audit:

```
       level_corr  diff_corr coint_pvalue
sample                                   
pooled  -0.001805  -0.012803     0.000000
day_-2  -0.005053  -0.007091     0.000000
day_-1  -0.000140  -0.018713     0.000000
```

The notebook's EMERALDS-vs-TOMATOES pair-trading conclusion is not practically credible. Level correlation and return correlation are both near zero. Any cointegration test that fires here is reacting to EMERALDS being almost constant, not to a meaningful tradable linkage.

## Strategy implications

EMERALDS:

- Keep it simple and structural: fixed fair, strict favorable takes, and fair-value clears to reopen capacity.
- The local data says the edge is in inventory turnover, not in predictive modeling.
- Under a changed environment, keep the market-structure logic and drop any temptation to hardcode timestamp behavior.

TOMATOES:

- Treat wall mid as fair. The raw mid is a noisy symptom of one-side quote displacement.
- Do not reintroduce EMA lag. The tutorial data says current wall mid beats `ema5`, `ema10`, and `ema20` on both days.
- Use two modes:
  - default wide-state mode: quote around wall mid and manage inventory
  - active one-tick dislocation mode: lean hard into the gap signal, but express it with favorable takes versus fair and fast passive reversion quotes, not blind spread crossing
- Preserve capacity. This is where Prosperity 2's zero-edge-clearing lesson and Prosperity 3's wall-mid lesson line up cleanly.

## Latest local backtest

Latest parsed log: `2026-04-13_17-57-23.log`

```
          fills  net_position realized_pnl_fifo price_range                                                                                                    top_fill_levels
product                                                                                                                                                                       
EMERALDS    733             4         4270.0000  9998-10002                                                    10000 SELL:1322, 10000 BUY:1287, 9998 BUY:1087, 10002 SELL:1048
TOMATOES   1447           -11         2731.0000   4945-5037  4996 BUY:168, 4994 SELL:154, 4994 BUY:147, 4995 SELL:142, 4991 BUY:116, 4991 SELL:104, 4993 BUY:101, 5006 SELL:97
```

This lines up with the structural read above: EMERALDS fills cluster around fair-anchored levels, while TOMATOES profits remain more sensitive to how we express the wall-mid signal without paying too much spread.

## Bottom line

The deep edge here is not hidden ML complexity. It is state decomposition:

- EMERALDS: deterministic fair plus transient fair-touch states.
- TOMATOES: slow wall-mid fair plus one-tick quote-asymmetry states.

That is the robust bridge between the tutorial data and the prior-winner playbook. Keep the structural logic, keep the inventory discipline, use wall mid aggressively, and stay skeptical of anything that only looks good because of pooled in-sample statistics or timestamp-level leakage.
