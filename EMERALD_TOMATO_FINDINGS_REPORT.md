# Emerald and Tomato findings report

This report is a narrative summary of the deeper technical work in [EMERALD_TOMATO_DEEP_DIVE.md](./EMERALD_TOMATO_DEEP_DIVE.md). The goal here is not just to restate statistics, but to explain what they mean for how we should think about the products, what parts of the existing repo analysis seem robust, what parts need to be treated more carefully, and how these conclusions should shape our trading model.

## Executive summary

The most important conclusion is that neither product rewards complexity for its own sake.

EMERALDS is not a prediction problem. It is a structural market-making and inventory-capacity problem around a fixed fair value. The evidence strongly supports the same core lesson top teams used in similar products in previous Prosperity editions: take strictly favorable quotes, use zero-edge trades to clear inventory when needed, and treat position headroom as a scarce resource that directly limits future alpha.

TOMATOES is more interesting, but not in the way the first notebook framing suggests. Its short-horizon predictability is real, yet the cleanest explanation is not "the market is deeply forecastable" but rather "the displayed mid temporarily deviates from a slower fair process." The hidden fair proxy is the wall mid. The visible mid then oscillates around it through one-tick quote asymmetries that tend to mean-revert quickly. That means the edge is primarily about state decomposition and execution quality, not about fitting an elaborate forecasting model.

The practical implication is that we should keep the wall-mid and inventory-discipline lessons from past winners, while explicitly rejecting the brittle parts of older playbooks such as timestamp hardcoding or overfitting pooled in-sample regressions. The environment may have changed, the batch mechanics may differ, and the exact bot landscape may no longer be stable enough to support exploit-style frontrunning. But the structural logic still transfers.

## Evidence base

The analysis in this report is based on:

- `prices_round_0_day_-2.csv`
- `prices_round_0_day_-1.csv`
- `trades_round_0_day_-2.csv`
- `trades_round_0_day_-1.csv`
- the existing notebook and HTML exports in this repo
- the current local `prosperity4` strategy and latest backtest logs

External winner writeups were used as conceptual references only:

- Linear Utility's Prosperity 2 writeup for the fixed-fair AMETHYSTS logic and market-maker-mid STARFRUIT logic
- Frankfurt Hedgehogs' Prosperity 3 writeup for the wall-mid framing, fair-value inventory clears, and one-step snapshot order-flow interpretation

The key principle was to use those older ideas as priors, not as truths. Where the local data confirmed them, we kept them. Where the local environment looks different, we did not force the analogy.

## What is robust across both days

Several patterns were stable across both tutorial days and should be treated as the strongest evidence in the repo.

For EMERALDS:

- The inferred wall mid is exactly `10000` on all rows.
- The best visible quotes spend about `96.7%` of the time in the default `2/2` state relative to the wall.
- Fair-touch opportunities appear on roughly `1.6%` to `1.7%` of ticks per side.
- The only meaningful deviations are short-lived one-tick states where one side collapses back toward fair.

For TOMATOES:

- The wall mid is much more stable than the raw mid as a fair-value estimate.
- The average absolute gap between raw mid and wall mid is only about `0.44` to `0.46`, but that small gap carries a strong directional signal for the next displayed-mid move.
- The active large-gap regime occurs only about `7.2%` of the time.
- When it appears, it usually lasts only one tick.
- The out-of-sample coefficient on `gap = mid - wall_mid` is very stable across days, around `-0.85` to `-0.86`.

This matters because it tells us the tutorial sample is not just "some noisy data with a few correlations." It has a consistent microstructure story.

## EMERALDS: what the product really is

EMERALDS behaves like a textbook pegged-fair product.

The deep liquidity wall implies a true fair value of `10000`, and the visible top of book usually sits two ticks inside that wall on each side. In other words, the normal market state is not a discovery process. It is a quoting process around a known value. The visible mid only moves when one side of that quoting structure temporarily changes.

That means the product should be thought of as:

- a spread-capture product
- an inventory-management product
- a capacity-allocation product

It should not be thought of as:

- a machine-learning prediction problem
- a regime detection problem
- a directional momentum product

This distinction is important because it changes how we evaluate strategy quality. A good EMERALDS strategy is not the one with the fanciest signal. It is the one that converts the known fair into realized spread capture as consistently as possible without getting stuck at the limit.

The strongest implication is that zero-edge clearing is not a minor implementation detail. It is part of the alpha engine. If we refuse to flatten at fair when inventory is skewed, we sacrifice future positive-edge opportunities. Prior winners discovered this in analogous settings, and the local data supports exactly the same conclusion here.

## TOMATOES: what the product really is

TOMATOES is not just "mean reverting" in a loose time-series sense. The more precise description is:

- there is a slower fair process, which the wall mid tracks well
- there is a fast microstructure process, where the visible best quotes shift asymmetrically around that fair
- the visible mid therefore contains both fair movement and temporary quote distortion

This decomposition is the key hidden pattern.

If we look only at the displayed mid, it is easy to conclude that TOMATOES is highly forecastable. The notebook leans in this direction with high in-sample regression scores. But when we separate wall mid from quote asymmetry, the story becomes much cleaner:

- the fair itself moves
- the displayed mid overshoots and undershoots that fair through transient quoting states
- most of the short-horizon signal comes from those transient states, not from rich directional structure in the fair

That matters because it changes what we should optimize.

The right question is not "how do we predict the next raw mid?" The right question is "how do we estimate fair, detect when the visible book is temporarily distorted away from it, and express that edge without paying too much spread?"

This is a very different design problem.

## The most important Tomato insight: signal strength does not imply aggressive execution

One of the easiest mistakes to make from the notebook is to see a strong short-horizon signal and conclude that aggressive market-taking must be optimal. The deeper analysis does not support that.

Even on the strongest dislocation states, the average next absolute mid move is still smaller than the current spread. In plain language: the visible price usually snaps back, but not enough to justify blindly crossing the spread and then crossing back.

So the correct interpretation is:

- the state signal is real
- the direction is useful
- the edge is relative to fair
- the execution still needs to be careful

This is a subtle but crucial point. It means TOMATOES should not be traded like a pure one-tick directional scalp. It should be traded like a fair-value market-making problem with conditional aggressiveness.

That naturally leads to a two-mode view of the product:

- normal mode: when the book is in its wide default state, quote around wall mid and manage inventory
- active mode: when the book enters a one-tick dislocation state, shift quoting and taking behavior to lean into the reversion, but still avoid paying full spread unless the quote is actually favorable relative to fair

That framing is much more robust than a raw momentum or EMA crossover story.

## What prior winners got right, and what does not transfer cleanly

The strongest transferable lessons from prior winner writeups are structural, not exploitative.

The parts that still clearly transfer are:

- use the best available fair-value proxy rather than the visible mid
- treat inventory headroom as part of the edge
- flatten at zero edge when doing so unlocks future positive-edge trades
- prefer simple, robust logic when the market structure itself explains the opportunity

The parts that do not transfer cleanly are:

- hardcoding bot timing or exact historical actions
- overfitting parameter-heavy regressions to tiny samples
- assuming that because a previous competition reused bot logic, the current one will too

This is especially important given the user concern that the batch environment behaved differently this year. If order sequencing or fill attribution has changed, timestamp-level exploit strategies can fail abruptly. A strategy built on fair estimation and inventory logic degrades much more gracefully.

So the right way to use prior winners here is:

- copy their reasoning discipline
- copy their emphasis on fair value and microstructure
- do not copy any dependence on deterministic bot repetition unless we re-prove it locally

## Where the current notebook is strongest

The existing notebook deserves credit for several genuinely useful ideas.

It is directionally right that:

- EMERALDS is a pegged-fair product
- TOMATOES has a real reversion component
- wall-type fair estimates are valuable
- simple naive backtests can identify that some classes of strategies are clearly better than others

It also deserves credit for exploring many views of the data. That broad sweep is useful for forming hypotheses.

The issue is not that the notebook is useless. The issue is that some of its strongest statements need to be narrowed before they are strategy-safe.

## Where the current notebook overstates the case

Two parts of the notebook should not be used as-is for production thinking.

First, the trade-feature construction leaks information. The backward `merge_asof(..., tolerance=100)` effectively duplicates many trades onto the next book row as well as the true trade row, because timestamps are spaced by `100`. That nearly doubles the coverage of trade-linked features. Once this is recognized, the very high in-sample predictive fits become much less persuasive.

Second, the EMERALDS/TOMATOES cointegration conclusion is not economically meaningful. The test fires because EMERALDS is nearly constant, not because there is a real tradable cross-product relationship. Level correlation and return correlation are both effectively zero. This should not be treated as a viable pairs trade.

There is also a softer issue: the phrase "trade aggressively" is too broad. Low measured impact is not the same as low transaction cost. In TOMATOES, spread cost is still the main drag on naive aggressive expression.

## Implications for our model

The model implications are fairly direct.

For EMERALDS, the model should be intentionally simple:

- fixed fair at `10000`
- strict favorable takes only
- active zero-edge clearing when inventory is constraining future opportunity
- passive quoting designed to maximize fill probability while maintaining positive edge

The optimization target here should not be forecast quality. It should be realized spread capture per unit of inventory capacity.

For TOMATOES, the model should be state-based:

- estimate fair with wall mid
- compute and track the raw-mid gap to wall mid
- identify whether we are in the normal wide state or the short-lived dislocation state
- alter quote placement, skew, and willingness to take based on that state
- keep inventory logic asymmetric, because buy-side fair opportunities appear somewhat more often than sell-side fair opportunities in the tutorial sample

The optimization target here should be edge realization after spread, not just directional hit rate.

## Implications for execution logic

The strategy implications are not only about signal generation. They are also about execution.

For EMERALDS:

- quote structure matters more than signal complexity
- multi-level quoting inside the spread is sensible
- fair-value clears should be treated as productive, not wasteful

For TOMATOES:

- current wall mid should be favored over lagged EMA blends
- when a dislocation appears, we should lean into it quickly because it often lasts only one tick
- that does not mean crossing everything; it means reacting quickly with the right mix of favorable takes and passive reversion quotes
- the strategy should be robust to the possibility that fills arrive in a slightly different order than in the tutorial batch

The main design principle is to separate "I have signal" from "I should cross the spread." Those are not the same decision.

## Implications for validation

The repo should validate these products in a more structured way going forward.

The most important checks are:

- exact trade-to-book alignment, with no duplicated trade rows in features
- day-split and, when possible, regime-split out-of-sample testing
- signal-quality metrics separate from execution-quality metrics
- strategy diagnostics that explicitly track capacity usage, fair-value clears, and spread paid

For TOMATOES especially, we should monitor:

- wall-mid estimation stability
- fraction of time in active dislocation states
- realized PnL from favorable takes versus passive reversion quotes
- PnL lost to spread crossing

If those metrics deteriorate in a changed environment, we will know whether the problem is with fair estimation, state detection, or execution.

## Implications for competition strategy more generally

This analysis points to a broader competition lesson.

The biggest risk in Prosperity-style environments is not just missing alpha. It is believing the wrong explanation for alpha. If we think the edge is forecasting when it is really quote-state reversion, we will build the wrong trader. If we think the edge is deterministic bot behavior when it is really structural microstructure, we will overfit and become fragile.

The correct posture is:

- explain the market in the simplest way that fits the data
- only add complexity when the simple explanation stops working
- favor edges that come from structure over edges that come from historical coincidences

That is exactly the part of prior winner thinking that remains useful even when the environment changes.

## Recommended next steps

The natural next actions are:

1. keep the new deep-dive report as the technical reference
2. use this findings report as the strategy summary for the team
3. update the notebook or future feature pipeline to remove the trade-leakage issue
4. refine the TOMATOES trader around a two-mode wall-mid framework rather than a lagged EMA framework
5. evaluate current `trader.py` specifically on how much PnL comes from favorable fair-relative takes versus passive fill capture versus inventory-clearing behavior

## Final view

If we strip away the noise, the picture is quite strong.

EMERALDS offers durable structural alpha so long as we respect fair value and preserve inventory capacity.

TOMATOES offers real but more fragile alpha, and the fragility comes mostly from execution, not from the absence of signal. The signal is there. The challenge is expressing it efficiently.

That combination suggests a sensible portfolio mindset:

- let EMERALDS provide the stable floor
- let TOMATOES provide the conditional upside
- keep both strategies grounded in fair value, not in overfit prediction stories

That is the best synthesis of the local data, the prior-winner lessons that still transfer, and the changed environment we need to respect.
