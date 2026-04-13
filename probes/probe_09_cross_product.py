"""
PROBE 9: Cross-Product Signal Leakage
Aggressively buys Product A (first product alphabetically).
Monitors whether Product B's book changes in response.
"""
import json
from datamodel import Order

class Trader:
    def run(self, state):
        result = {}
        ts = state.timestamp
        products = sorted(state.order_depths.keys())

        target_product = products[0] if products else None

        for product, depth in state.order_depths.items():
            orders = []
            best_bid = max(depth.buy_orders.keys()) if depth.buy_orders else None
            best_ask = min(depth.sell_orders.keys()) if depth.sell_orders else None
            mid = (best_bid + best_ask) / 2 if best_bid and best_ask else None
            pos = state.position.get(product, 0)

            book_data = {
                "bids": {str(p): v for p, v in sorted(depth.buy_orders.items(), reverse=True)},
                "asks": {str(p): v for p, v in sorted(depth.sell_orders.items())}
            }

            if product == target_product and best_ask is not None and pos < 20:
                orders.append(Order(product, best_ask, 1))
                print(f"PROBE|{ts}|ACTION|{json.dumps({'product': product, 'side': 'BUY', 'price': best_ask})}")

            print(f"PROBE|{ts}|BOOK|{json.dumps({'product': product, 'mid': mid, 'spread': (best_ask - best_bid) if best_bid and best_ask else None, 'position': pos, 'book': book_data})}")

            result[product] = orders

        for product, trades in state.own_trades.items():
            for t in trades:
                print(f"PROBE|{ts}|FILL|{json.dumps({'product': product, 'price': t.price, 'quantity': t.quantity})}")

        return result, 0, ""
