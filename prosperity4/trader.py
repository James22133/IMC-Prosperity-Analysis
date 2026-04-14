import json
import math
from datamodel import Order, OrderDepth, TradingState

POSITION_LIMITS = {
    "EMERALDS": 50,
    "TOMATOES": 50,
}

EMERALDS_FAIR = 10_000


class Trader:

    def bid(self):
        return 15

    # ── helpers ──────────────────────────────────────────────────

    @staticmethod
    def get_wall_mid(order_depth: OrderDepth):
        bid_wall_price = None
        bid_wall_vol = 0
        for price, vol in order_depth.buy_orders.items():
            if vol > bid_wall_vol:
                bid_wall_vol = vol
                bid_wall_price = price

        ask_wall_price = None
        ask_wall_vol = 0
        for price, vol in order_depth.sell_orders.items():
            if abs(vol) > ask_wall_vol:
                ask_wall_vol = abs(vol)
                ask_wall_price = price

        if bid_wall_price is not None and ask_wall_price is not None:
            return (bid_wall_price + ask_wall_price) / 2
        if order_depth.buy_orders and order_depth.sell_orders:
            return (max(order_depth.buy_orders.keys()) + min(order_depth.sell_orders.keys())) / 2
        return None

    @staticmethod
    def clamp_orders(orders, position, limit):
        """Trim from the END of the list so early (high-priority) orders survive."""
        buy_qty = sum(o.quantity for o in orders if o.quantity > 0)
        sell_qty = sum(abs(o.quantity) for o in orders if o.quantity < 0)

        max_buy = limit - position
        max_sell = limit + position

        if buy_qty > max_buy:
            excess = buy_qty - max_buy
            for o in reversed(orders):
                if o.quantity > 0 and excess > 0:
                    trim = min(o.quantity, excess)
                    o.quantity -= trim
                    excess -= trim

        if sell_qty > max_sell:
            excess = sell_qty - max_sell
            for o in reversed(orders):
                if o.quantity < 0 and excess > 0:
                    trim = min(abs(o.quantity), excess)
                    o.quantity += trim
                    excess -= trim

        return [o for o in orders if o.quantity != 0]

    # ── EMERALDS ─────────────────────────────────────────────────
    #
    # The bot quotes 9992/10008 ~97% of the time (spread=16).
    # We know fair=10000.  Strategy:
    #   1. Take any mispriced levels (asks<10000, bids>10000)
    #   2. Flatten inventory at fair if position is large
    #   3. Post passive bids/asks at MULTIPLE levels inside the
    #      spread to maximise the chance the bot's taker hits us
    # ─────────────────────────────────────────────────────────────

    def trade_emeralds(self, state: TradingState, memory: dict):
        product = "EMERALDS"
        od = state.order_depths[product]
        pos = state.position.get(product, 0)
        limit = POSITION_LIMITS[product]
        fair = EMERALDS_FAIR

        # We build orders in PRIORITY order: takes first, then flatten,
        # then passive.  clamp_orders trims from the back, so passive
        # orders get trimmed first if we're near the limit.
        orders = []
        buy_cap = limit - pos
        sell_cap = limit + pos

        # ── Phase 1: TAKE mispriced liquidity ────────────────────
        for ask_p in sorted(od.sell_orders.keys()):
            if buy_cap <= 0:
                break
            if ask_p < fair or (ask_p == fair and pos < 0):
                vol = min(abs(od.sell_orders[ask_p]), buy_cap)
                orders.append(Order(product, ask_p, vol))
                buy_cap -= vol
                pos += vol

        for bid_p in sorted(od.buy_orders.keys(), reverse=True):
            if sell_cap <= 0:
                break
            if bid_p > fair or (bid_p == fair and pos > 0):
                vol = min(od.buy_orders[bid_p], sell_cap)
                orders.append(Order(product, bid_p, -vol))
                sell_cap -= vol
                pos -= vol

        # ── Phase 2: FLATTEN when inventory is too big ───────────
        # Dump at fair so round-trips close at zero edge rather than
        # holding risk.  This frees capacity for new profitable takes.
        soft_limit = int(limit * 0.6)
        if pos > soft_limit and sell_cap > 0:
            dump = min(pos, sell_cap)
            orders.append(Order(product, fair, -dump))
            sell_cap -= dump
            pos -= dump
        elif pos < -soft_limit and buy_cap > 0:
            dump = min(abs(pos), buy_cap)
            orders.append(Order(product, fair, dump))
            buy_cap -= dump
            pos += dump

        # ── Phase 3: PASSIVE multi-level quoting ─────────────────
        # The old code posted ONE bid and ONE ask.  That gave us only
        # 2.9 fills per 100 ticks.  Instead, scatter orders across
        # several price levels so ANY bot taker activity fills us.
        #
        # Inventory skew: shift more size toward the flattening side.

        best_bid = max(od.buy_orders.keys()) if od.buy_orders else fair - 8
        best_ask = min(od.sell_orders.keys()) if od.sell_orders else fair + 8

        # Candidate bid prices: improve best_bid by 1, and also at
        # several levels between there and fair-1.
        bid_levels = []
        for offset in [1, 2, 3, 4]:
            p = fair - offset
            if p > best_bid:          # only post if we improve the book
                bid_levels.append(p)
        if best_bid + 1 < fair and (best_bid + 1) not in bid_levels:
            bid_levels.append(best_bid + 1)
        bid_levels = sorted(set(bid_levels), reverse=True)  # best first

        ask_levels = []
        for offset in [1, 2, 3, 4]:
            p = fair + offset
            if p < best_ask:
                ask_levels.append(p)
        if best_ask - 1 > fair and (best_ask - 1) not in ask_levels:
            ask_levels.append(best_ask - 1)
        ask_levels = sorted(set(ask_levels))  # best (lowest) first

        # Distribute remaining capacity across levels.
        # When we have inventory, skew: give MORE size to the
        # side that flattens and LESS to the side that extends.
        if pos > 0:
            bid_frac = max(0.1, 0.5 - pos / limit)
            ask_frac = 1.0 - bid_frac
        elif pos < 0:
            ask_frac = max(0.1, 0.5 + pos / limit)
            bid_frac = 1.0 - ask_frac
        else:
            bid_frac = 0.5
            ask_frac = 0.5

        total_bid_qty = min(buy_cap, int(limit * bid_frac))
        total_ask_qty = min(sell_cap, int(limit * ask_frac))

        if bid_levels and total_bid_qty > 0:
            per_level = max(1, total_bid_qty // len(bid_levels))
            remaining = total_bid_qty
            for p in bid_levels:
                q = min(per_level, remaining)
                if q > 0:
                    orders.append(Order(product, p, q))
                    remaining -= q
            # dump any leftover on the best level
            if remaining > 0:
                orders.append(Order(product, bid_levels[0], remaining))

        if ask_levels and total_ask_qty > 0:
            per_level = max(1, total_ask_qty // len(ask_levels))
            remaining = total_ask_qty
            for p in ask_levels:
                q = min(per_level, remaining)
                if q > 0:
                    orders.append(Order(product, p, -q))
                    remaining -= q
            if remaining > 0:
                orders.append(Order(product, ask_levels[0], -remaining))

        # If there are NO levels inside the spread (spread is tight or
        # already at fair), post at fair-1 / fair+1 as fallback.
        if not bid_levels and buy_cap > 0:
            orders.append(Order(product, fair - 1, min(buy_cap, limit // 2)))
        if not ask_levels and sell_cap > 0:
            orders.append(Order(product, fair + 1, -min(sell_cap, limit // 2)))

        orders = self.clamp_orders(orders, state.position.get(product, 0), limit)
        return orders

    # ── TOMATOES ─────────────────────────────────────────────────
    #
    # Moving fair value.  Key fixes vs v1:
    #   - Use pure wall_mid (no EMA blend that lags)
    #   - Take AT fair when it helps flatten
    #   - Tighter passive spread to get more fills
    #   - Smarter skew: shift both price AND size
    # ─────────────────────────────────────────────────────────────

    def trade_tomatoes(self, state: TradingState, memory: dict):
        product = "TOMATOES"
        od = state.order_depths[product]
        pos = state.position.get(product, 0)
        limit = POSITION_LIMITS[product]

        if product not in memory:
            memory[product] = {"prices": []}
        mem = memory[product]

        wall_mid = self.get_wall_mid(od)
        if od.buy_orders and od.sell_orders:
            simple_mid = (max(od.buy_orders.keys()) + min(od.sell_orders.keys())) / 2
        else:
            simple_mid = None

        mid = wall_mid if wall_mid is not None else simple_mid
        if mid is None:
            return []

        mem["prices"].append(mid)
        mem["prices"] = mem["prices"][-50:]

        # Fair value = wall mid (current tick's best estimate).
        # No EMA blend — that caused lag and adverse selection.
        fair = wall_mid if wall_mid is not None else mid

        # Volatility for adaptive spread
        prices = mem["prices"]
        rolling_std = 0.0
        if len(prices) >= 10:
            mean_p = sum(prices[-20:]) / len(prices[-20:])
            rolling_std = math.sqrt(
                sum((p - mean_p) ** 2 for p in prices[-20:]) / len(prices[-20:])
            )

        # Adaptive half-spread: wider when volatile, tighter when calm
        half_spread = max(1, min(6, int(round(rolling_std * 0.25 + 1))))

        fair_int = int(round(fair))

        orders = []
        buy_cap = limit - pos
        sell_cap = limit + pos

        # ── Phase 1: TAKE mispriced liquidity ────────────────────
        # Also take AT fair when it helps flatten inventory.
        for ask_p in sorted(od.sell_orders.keys()):
            if buy_cap <= 0:
                break
            take = ask_p < fair_int
            if ask_p == fair_int and pos < 0:  # flatten at fair
                take = True
            if take:
                vol = min(abs(od.sell_orders[ask_p]), buy_cap)
                orders.append(Order(product, ask_p, vol))
                buy_cap -= vol
                pos += vol

        for bid_p in sorted(od.buy_orders.keys(), reverse=True):
            if sell_cap <= 0:
                break
            take = bid_p > fair_int
            if bid_p == fair_int and pos > 0:  # flatten at fair
                take = True
            if take:
                vol = min(od.buy_orders[bid_p], sell_cap)
                orders.append(Order(product, bid_p, -vol))
                sell_cap -= vol
                pos -= vol

        # ── Phase 2: FLATTEN if inventory is dangerous ───────────
        # Do this BEFORE passive so clamp preserves flatten orders.
        soft_limit = int(limit * 0.7)
        best_bid = max(od.buy_orders.keys()) if od.buy_orders else fair_int - 5
        best_ask = min(od.sell_orders.keys()) if od.sell_orders else fair_int + 5

        if pos > soft_limit and sell_cap > 0:
            dump = min(pos - soft_limit // 2, sell_cap)
            # Sell aggressively at best bid to actually get filled
            orders.append(Order(product, best_bid, -dump))
            sell_cap -= dump
            pos -= dump
        elif pos < -soft_limit and buy_cap > 0:
            dump = min(abs(pos) - soft_limit // 2, buy_cap)
            orders.append(Order(product, best_ask, dump))
            buy_cap -= dump
            pos += dump

        # ── Phase 3: PASSIVE with inventory skew ─────────────────
        # Price skew: shift quotes toward flattening side
        # pos=+20 → skew=+4 → bid drops 4, ask drops 4 (eager to sell)
        skew = int(round(pos * 0.2))

        bid_price = fair_int - half_spread - skew
        ask_price = fair_int + half_spread - skew

        # Safety: never let bid >= ask
        if bid_price >= ask_price:
            bid_price = fair_int - 1
            ask_price = fair_int + 1

        # Size skew: more size on flattening side
        if pos > 0:
            bid_qty = min(buy_cap, max(1, limit // 4 - pos // 2))
            ask_qty = min(sell_cap, limit // 2)
        elif pos < 0:
            bid_qty = min(buy_cap, limit // 2)
            ask_qty = min(sell_cap, max(1, limit // 4 - abs(pos) // 2))
        else:
            bid_qty = min(buy_cap, limit // 3)
            ask_qty = min(sell_cap, limit // 3)

        if bid_qty > 0:
            orders.append(Order(product, bid_price, bid_qty))
        if ask_qty > 0:
            orders.append(Order(product, ask_price, -ask_qty))

        # Also post a second passive level further out for extra fills
        bid_price2 = fair_int - half_spread * 2 - skew
        ask_price2 = fair_int + half_spread * 2 - skew
        bid_qty2 = min(buy_cap - bid_qty, limit // 4) if buy_cap > bid_qty else 0
        ask_qty2 = min(sell_cap - ask_qty, limit // 4) if sell_cap > ask_qty else 0

        if bid_qty2 > 0 and bid_price2 < bid_price:
            orders.append(Order(product, bid_price2, bid_qty2))
        if ask_qty2 > 0 and ask_price2 > ask_price:
            orders.append(Order(product, ask_price2, -ask_qty2))

        orders = self.clamp_orders(orders, state.position.get(product, 0), limit)
        return orders

    # ── main entry point ─────────────────────────────────────────

    def run(self, state: TradingState):
        if state.traderData:
            try:
                memory = json.loads(state.traderData)
            except Exception:
                memory = {}
        else:
            memory = {}

        result = {}

        for product in state.order_depths:
            if product == "EMERALDS":
                result[product] = self.trade_emeralds(state, memory)
            elif product == "TOMATOES":
                result[product] = self.trade_tomatoes(state, memory)
            else:
                # Unknown product: try generic peg-fade if mid ~ round number,
                # otherwise just post tight passive quotes around simple mid.
                od = state.order_depths[product]
                pos = state.position.get(product, 0)
                lim = 50  # default guess
                orders = []
                if od.buy_orders and od.sell_orders:
                    mid = (max(od.buy_orders.keys()) + min(od.sell_orders.keys())) / 2
                    mid_int = int(round(mid))
                    buy_cap = lim - pos
                    sell_cap = lim + pos
                    # Take anything on the wrong side of mid
                    for ap in sorted(od.sell_orders.keys()):
                        if ap < mid_int and buy_cap > 0:
                            v = min(abs(od.sell_orders[ap]), buy_cap)
                            orders.append(Order(product, ap, v))
                            buy_cap -= v
                    for bp in sorted(od.buy_orders.keys(), reverse=True):
                        if bp > mid_int and sell_cap > 0:
                            v = min(od.buy_orders[bp], sell_cap)
                            orders.append(Order(product, bp, -v))
                            sell_cap -= v
                    # Passive
                    if buy_cap > 0:
                        orders.append(Order(product, mid_int - 1, min(buy_cap, 10)))
                    if sell_cap > 0:
                        orders.append(Order(product, mid_int + 1, -min(sell_cap, 10)))
                result[product] = orders

        conversions = 0
        trader_data = json.dumps(memory)
        return result, conversions, trader_data