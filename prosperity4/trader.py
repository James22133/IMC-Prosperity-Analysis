import json
import math
from datamodel import Order, OrderDepth, TradingState

POSITION_LIMITS = {
    "EMERALDS": 50,
    "TOMATOES": 50,
}

EMERALDS_FAIR = 10_000

TOMATOES_EMA_ALPHA = 0.2
TOMATOES_BASE_SPREAD = 3
TOMATOES_SKEW_FACTOR = 0.4
TOMATOES_FLATTEN_THRESHOLD = 0.75


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
    def get_simple_mid(order_depth: OrderDepth):
        if order_depth.buy_orders and order_depth.sell_orders:
            return (max(order_depth.buy_orders.keys()) + min(order_depth.sell_orders.keys())) / 2
        return None

    @staticmethod
    def clamp_orders(orders, position, limit):
        """Trim order list so aggregate buys/sells cannot breach position limits."""
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

    def trade_emeralds(self, state: TradingState, memory: dict):
        product = "EMERALDS"
        order_depth = state.order_depths[product]
        position = state.position.get(product, 0)
        limit = POSITION_LIMITS[product]
        fair = EMERALDS_FAIR

        orders = []
        buy_capacity = limit - position
        sell_capacity = limit + position

        # Phase 1 — TAKE everything below fair (and AT fair if we're not too long/short)
        for ask_price in sorted(order_depth.sell_orders.keys()):
            if buy_capacity <= 0:
                break
            take = False
            if ask_price < fair:
                take = True
            elif ask_price == fair and position <= 0:
                take = True
            if take:
                vol = min(abs(order_depth.sell_orders[ask_price]), buy_capacity)
                if vol > 0:
                    orders.append(Order(product, ask_price, vol))
                    buy_capacity -= vol
                    position += vol

        for bid_price in sorted(order_depth.buy_orders.keys(), reverse=True):
            if sell_capacity <= 0:
                break
            take = False
            if bid_price > fair:
                take = True
            elif bid_price == fair and position >= 0:
                take = True
            if take:
                vol = min(order_depth.buy_orders[bid_price], sell_capacity)
                if vol > 0:
                    orders.append(Order(product, bid_price, -vol))
                    sell_capacity -= vol
                    position -= vol

        # Phase 2 — POST PASSIVE inside the spread
        best_bid = max(order_depth.buy_orders.keys()) if order_depth.buy_orders else fair - 3
        best_ask = min(order_depth.sell_orders.keys()) if order_depth.sell_orders else fair + 3

        passive_bid = max(best_bid + 1, fair - 2)
        passive_bid = min(passive_bid, fair - 1)

        passive_ask = min(best_ask - 1, fair + 2)
        passive_ask = max(passive_ask, fair + 1)

        if buy_capacity > 0:
            bid_qty = buy_capacity
            if position > 0:
                bid_qty = max(1, buy_capacity - position)
            orders.append(Order(product, passive_bid, bid_qty))

        if sell_capacity > 0:
            ask_qty = sell_capacity
            if position < 0:
                ask_qty = max(1, sell_capacity - abs(position))
            orders.append(Order(product, passive_ask, -ask_qty))

        # Phase 3 — FLATTEN if inventory too large
        flatten_thresh = int(limit * 0.7)
        if position > flatten_thresh:
            dump = position - 0
            dump = min(dump, sell_capacity)
            if dump > 0:
                orders.append(Order(product, fair, -dump))
        elif position < -flatten_thresh:
            dump = abs(position) - 0
            dump = min(dump, buy_capacity)
            if dump > 0:
                orders.append(Order(product, fair, dump))

        orders = self.clamp_orders(orders, state.position.get(product, 0), limit)
        return orders

    # ── TOMATOES ─────────────────────────────────────────────────

    def trade_tomatoes(self, state: TradingState, memory: dict):
        product = "TOMATOES"
        order_depth = state.order_depths[product]
        position = state.position.get(product, 0)
        limit = POSITION_LIMITS[product]

        if product not in memory:
            memory[product] = {"prices": [], "ema_fair": None}
        mem = memory[product]

        wall_mid = self.get_wall_mid(order_depth)
        simple_mid = self.get_simple_mid(order_depth)
        mid = wall_mid if wall_mid is not None else simple_mid

        if mid is None:
            return []

        mem["prices"].append(mid)
        mem["prices"] = mem["prices"][-100:]

        if mem["ema_fair"] is None:
            mem["ema_fair"] = mid
        else:
            mem["ema_fair"] = TOMATOES_EMA_ALPHA * mid + (1 - TOMATOES_EMA_ALPHA) * mem["ema_fair"]

        if wall_mid is not None:
            fair = 0.5 * wall_mid + 0.5 * mem["ema_fair"]
        else:
            fair = mem["ema_fair"]

        vol_window = mem["prices"][-20:]
        rolling_std = 0
        if len(vol_window) >= 5:
            mean_p = sum(vol_window) / len(vol_window)
            rolling_std = math.sqrt(sum((p - mean_p) ** 2 for p in vol_window) / len(vol_window))

        half_spread = max(2, min(8, int(round(rolling_std * 0.3 + 1))))

        orders = []
        buy_capacity = limit - position
        sell_capacity = limit + position

        fair_int = int(round(fair))
        for ask_price in sorted(order_depth.sell_orders.keys()):
            if buy_capacity <= 0:
                break
            if ask_price < fair_int:
                vol = min(abs(order_depth.sell_orders[ask_price]), buy_capacity)
                if vol > 0:
                    orders.append(Order(product, ask_price, vol))
                    buy_capacity -= vol
                    position += vol

        for bid_price in sorted(order_depth.buy_orders.keys(), reverse=True):
            if sell_capacity <= 0:
                break
            if bid_price > fair_int:
                vol = min(order_depth.buy_orders[bid_price], sell_capacity)
                if vol > 0:
                    orders.append(Order(product, bid_price, -vol))
                    sell_capacity -= vol
                    position -= vol

        # Phase 2 — POST PASSIVE with inventory skew
        skew = round(position * TOMATOES_SKEW_FACTOR)

        bid_price = fair_int - half_spread - skew
        ask_price = fair_int + half_spread - skew

        if bid_price >= ask_price:
            bid_price = fair_int - 1
            ask_price = fair_int + 1

        bid_qty = min(buy_capacity, limit // 3)
        ask_qty = min(sell_capacity, limit // 3)

        if bid_qty > 0:
            orders.append(Order(product, bid_price, bid_qty))
        if ask_qty > 0:
            orders.append(Order(product, ask_price, -ask_qty))

        # Phase 3 — FLATTEN if inventory dangerously high
        flatten_thresh = int(limit * TOMATOES_FLATTEN_THRESHOLD)

        if position > flatten_thresh:
            dump_qty = min(position - flatten_thresh // 2, sell_capacity)
            if dump_qty > 0:
                orders.append(Order(product, fair_int - 1, -dump_qty))
        elif position < -flatten_thresh:
            dump_qty = min(abs(position) - flatten_thresh // 2, buy_capacity)
            if dump_qty > 0:
                orders.append(Order(product, fair_int + 1, dump_qty))

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

        if "EMERALDS" in state.order_depths:
            result["EMERALDS"] = self.trade_emeralds(state, memory)

        if "TOMATOES" in state.order_depths:
            result["TOMATOES"] = self.trade_tomatoes(state, memory)

        for product in state.order_depths:
            if product not in result:
                result[product] = []

        conversions = 0
        trader_data = json.dumps(memory)

        return result, conversions, trader_data
