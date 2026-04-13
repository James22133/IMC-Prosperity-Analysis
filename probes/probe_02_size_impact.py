"""
PROBE 2: Size Impact Experiment
Every 50 iterations, buy Q units at best_ask.
Run separate uploads for Q = 1, 2, 5, 10. Measures price impact ΔP = f(Q).
"""
import json
from datamodel import Order

INTERVAL = 50
TRADE_QTY = 1  # Change to 2, 5, 10, or max for separate runs

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
            pos = state.position.get(product, 0)

            print(f"PROBE|{ts}|BOOK|{json.dumps({'product': product, 'mid': mid, 'best_bid': best_bid, 'best_ask': best_ask, 'spread': (best_ask - best_bid) if best_bid and best_ask else None, 'position': pos})}")

            if iteration % INTERVAL == 0 and iteration > 0 and best_ask is not None:
                qty = min(TRADE_QTY, 20 - pos)  # respect position limit
                if qty > 0:
                    orders.append(Order(product, best_ask, qty))
                    print(f"PROBE|{ts}|ACTION|{json.dumps({'product': product, 'side': 'BUY', 'price': best_ask, 'qty': qty, 'pre_mid': mid})}")

            result[product] = orders

        for product, trades in state.own_trades.items():
            for t in trades:
                print(f"PROBE|{ts}|FILL|{json.dumps({'product': product, 'price': t.price, 'quantity': t.quantity})}")

        pos = {p: state.position.get(p, 0) for p in state.order_depths}
        print(f"PROBE|{ts}|POSITION|{json.dumps(pos)}")

        return result, 0, ""
