"""
PROBE 11: Order Rejection Boundary Testing
Tests position limit enforcement by sending orders that approach and exceed limits.
Uses traderData to track which test phase we're in.
"""
import json
from datamodel import Order

POS_LIMIT = 20

class Trader:
    def run(self, state):
        result = {}
        ts = state.timestamp
        iteration = ts // 100

        try:
            td = json.loads(state.traderData) if state.traderData else {"phase": 0}
        except (json.JSONDecodeError, TypeError):
            td = {"phase": 0}

        for product, depth in state.order_depths.items():
            orders = []
            best_bid = max(depth.buy_orders.keys()) if depth.buy_orders else None
            best_ask = min(depth.sell_orders.keys()) if depth.sell_orders else None
            pos = state.position.get(product, 0)
            mid = (best_bid + best_ask) / 2 if best_bid and best_ask else None

            remaining = POS_LIMIT - pos

            if iteration < 200:
                # Phase 1: Buy up to limit one at a time
                if best_ask is not None and pos < POS_LIMIT:
                    orders.append(Order(product, best_ask, 1))
                    print(f"PROBE|{ts}|BUY_TO_LIMIT|{json.dumps({'product': product, 'pos': pos, 'remaining': remaining})}")
            elif iteration < 300:
                # Phase 2: Try to exceed — send buy order when at limit
                if best_ask is not None:
                    qty = 1
                    orders.append(Order(product, best_ask, qty))
                    print(f"PROBE|{ts}|EXCEED_TEST|{json.dumps({'product': product, 'pos': pos, 'order_qty': qty, 'should_reject': pos >= POS_LIMIT})}")
            elif iteration < 400:
                # Phase 3: Send multiple small orders that together exceed limit
                if best_ask is not None:
                    for _ in range(5):
                        orders.append(Order(product, best_ask, 5))
                    print(f"PROBE|{ts}|MULTI_ORDER_TEST|{json.dumps({'product': product, 'pos': pos, 'total_qty_sent': 25, 'limit': POS_LIMIT})}")
            elif iteration < 600:
                # Phase 4: Sell to unwind
                if best_bid is not None and pos > -POS_LIMIT:
                    orders.append(Order(product, best_bid, -1))
                    print(f"PROBE|{ts}|UNWIND|{json.dumps({'product': product, 'pos': pos})}")
            else:
                print(f"PROBE|{ts}|IDLE|{json.dumps({'product': product, 'pos': pos, 'mid': mid})}")

            result[product] = orders

        for product, trades in state.own_trades.items():
            for t in trades:
                print(f"PROBE|{ts}|FILL|{json.dumps({'product': product, 'price': t.price, 'quantity': t.quantity})}")

        td["phase"] = 1 if iteration < 200 else (2 if iteration < 300 else (3 if iteration < 400 else 4))
        return result, 0, json.dumps(td)
