"""
PROBE 0: Baseline — Do Nothing
Sends zero orders. Logs full order book and all market trades every iteration.
This is the control group. Compare all other probes against this baseline.
"""
import json

class Trader:
    def run(self, state):
        result = {}
        for product in state.order_depths:
            result[product] = []

        ts = state.timestamp
        for product, depth in state.order_depths.items():
            book_data = {
                "bids": {str(p): v for p, v in sorted(depth.buy_orders.items(), reverse=True)},
                "asks": {str(p): v for p, v in sorted(depth.sell_orders.items())}
            }
            best_bid = max(depth.buy_orders.keys()) if depth.buy_orders else None
            best_ask = min(depth.sell_orders.keys()) if depth.sell_orders else None
            mid = (best_bid + best_ask) / 2 if best_bid and best_ask else None
            spread = (best_ask - best_bid) if best_bid and best_ask else None
            print(f"PROBE|{ts}|BOOK|{json.dumps({'product': product, 'best_bid': best_bid, 'best_ask': best_ask, 'mid': mid, 'spread': spread, 'book': book_data})}")

        for product, trades in state.market_trades.items():
            for t in trades:
                print(f"PROBE|{ts}|MARKET_TRADE|{json.dumps({'product': product, 'price': t.price, 'quantity': t.quantity, 'buyer': t.buyer, 'seller': t.seller})}")

        for product, trades in state.own_trades.items():
            for t in trades:
                print(f"PROBE|{ts}|OWN_TRADE|{json.dumps({'product': product, 'price': t.price, 'quantity': t.quantity})}")

        pos = {p: state.position.get(p, 0) for p in state.order_depths}
        print(f"PROBE|{ts}|POSITION|{json.dumps(pos)}")

        return result, 0, ""
