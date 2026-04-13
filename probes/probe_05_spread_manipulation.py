"""
PROBE 5: Spread Manipulation Test
Posts very wide orders far from mid to test if bots are reactive or have independent price processes.
WIDE_OFFSET sets how far from mid the orders are placed.
"""
import json
from datamodel import Order

WIDE_OFFSET = 20

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

            if mid is not None:
                wide_bid = int(mid - WIDE_OFFSET)
                wide_ask = int(mid + WIDE_OFFSET)

                if pos < 20:
                    orders.append(Order(product, wide_bid, 5))
                if pos > -20:
                    orders.append(Order(product, wide_ask, -5))

                print(f"PROBE|{ts}|WIDE_QUOTES|{json.dumps({'product': product, 'wide_bid': wide_bid, 'wide_ask': wide_ask, 'mid': mid, 'best_bid': best_bid, 'best_ask': best_ask, 'position': pos})}")

            result[product] = orders

        for product, trades in state.own_trades.items():
            for t in trades:
                print(f"PROBE|{ts}|FILL|{json.dumps({'product': product, 'price': t.price, 'quantity': t.quantity})}")

        return result, 0, ""
