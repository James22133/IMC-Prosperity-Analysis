"""
PROBE 4: Quote Posting — Do Bots Hit Resting Orders?
Posts passive orders at configurable offsets from the best bid/ask.
OFFSET = 1: one tick outside the spread. OFFSET = 0: at the best. OFFSET = -1: inside the spread.
"""
import json
from datamodel import Order

OFFSET = 1  # +1 = outside spread, 0 = at best, -1 = inside spread

class Trader:
    def run(self, state):
        result = {}
        ts = state.timestamp

        for product, depth in state.order_depths.items():
            orders = []
            best_bid = max(depth.buy_orders.keys()) if depth.buy_orders else None
            best_ask = min(depth.sell_orders.keys()) if depth.sell_orders else None
            pos = state.position.get(product, 0)
            mid = (best_bid + best_ask) / 2 if best_bid and best_ask else None

            if best_bid is not None and best_ask is not None:
                my_bid = best_bid - OFFSET
                my_ask = best_ask + OFFSET

                if pos < 20:
                    orders.append(Order(product, my_bid, 1))
                if pos > -20:
                    orders.append(Order(product, my_ask, -1))

                print(f"PROBE|{ts}|QUOTES|{json.dumps({'product': product, 'my_bid': my_bid, 'my_ask': my_ask, 'best_bid': best_bid, 'best_ask': best_ask, 'mid': mid, 'position': pos})}")

            result[product] = orders

        for product, trades in state.own_trades.items():
            for t in trades:
                side = 'BUY' if t.quantity > 0 else 'SELL'
                print(f"PROBE|{ts}|FILL|{json.dumps({'product': product, 'price': t.price, 'quantity': abs(t.quantity), 'side': side})}")

        return result, 0, ""
