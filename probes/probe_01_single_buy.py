"""
PROBE 1: Single Aggressive Buy at Fixed Intervals
Every N iterations, buy 1 unit at best_ask. Logs pre/post book state.
Set INTERVAL below (test 10, 30, 50, 100). Flip SIDE to 'SELL' for the sell variant.
"""
import json
from datamodel import Order

INTERVAL = 50
SIDE = 'BUY'  # or 'SELL'

class Trader:
    def run(self, state):
        result = {}
        ts = state.timestamp
        iteration = ts // 100

        for product, depth in state.order_depths.items():
            orders = []
            best_bid = max(depth.buy_orders.keys()) if depth.buy_orders else None
            best_ask = min(depth.sell_orders.keys()) if depth.sell_orders else None
            mid = (best_bid + best_ask) / 2 if best_bid and best_ask else None
            spread = (best_ask - best_bid) if best_bid and best_ask else None

            book_data = {
                "bids": {str(p): v for p, v in sorted(depth.buy_orders.items(), reverse=True)},
                "asks": {str(p): v for p, v in sorted(depth.sell_orders.items())}
            }
            print(f"PROBE|{ts}|BOOK|{json.dumps({'product': product, 'mid': mid, 'spread': spread, 'book': book_data})}")

            if iteration % INTERVAL == 0 and iteration > 0:
                if SIDE == 'BUY' and best_ask is not None:
                    orders.append(Order(product, best_ask, 1))
                    print(f"PROBE|{ts}|ACTION|{json.dumps({'product': product, 'side': 'BUY', 'price': best_ask, 'qty': 1})}")
                elif SIDE == 'SELL' and best_bid is not None:
                    orders.append(Order(product, best_bid, -1))
                    print(f"PROBE|{ts}|ACTION|{json.dumps({'product': product, 'side': 'SELL', 'price': best_bid, 'qty': 1})}")

            result[product] = orders

        for product, trades in state.own_trades.items():
            for t in trades:
                print(f"PROBE|{ts}|OWN_TRADE|{json.dumps({'product': product, 'price': t.price, 'quantity': t.quantity})}")

        pos = {p: state.position.get(p, 0) for p in state.order_depths}
        print(f"PROBE|{ts}|POSITION|{json.dumps(pos)}")

        return result, 0, ""
