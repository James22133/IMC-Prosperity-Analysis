"""
PROBE 3: Sustained Directional Pressure
Buy 1 unit every single iteration. Tests whether bots mean-revert the price or let it drift.
Set SIDE = 'SELL' for the sell variant.
"""
import json
from datamodel import Order

SIDE = 'BUY'  # or 'SELL'

class Trader:
    def run(self, state):
        result = {}
        ts = state.timestamp

        for product, depth in state.order_depths.items():
            orders = []
            best_bid = max(depth.buy_orders.keys()) if depth.buy_orders else None
            best_ask = min(depth.sell_orders.keys()) if depth.sell_orders else None
            mid = (best_bid + best_ask) / 2 if best_bid and best_ask else None
            pos = state.position.get(product, 0)

            if SIDE == 'BUY' and best_ask is not None and pos < 20:
                orders.append(Order(product, best_ask, 1))
            elif SIDE == 'SELL' and best_bid is not None and pos > -20:
                orders.append(Order(product, best_bid, -1))

            print(f"PROBE|{ts}|STATE|{json.dumps({'product': product, 'mid': mid, 'position': pos, 'spread': (best_ask - best_bid) if best_bid and best_ask else None})}")

            result[product] = orders

        for product, trades in state.own_trades.items():
            for t in trades:
                print(f"PROBE|{ts}|FILL|{json.dumps({'product': product, 'price': t.price, 'quantity': t.quantity})}")

        return result, 0, ""
