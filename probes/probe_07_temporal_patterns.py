"""
PROBE 7: Temporal Pattern Detection
Does nothing but logs everything with maximum detail.
Focuses on detecting initialization artifacts, gaps, level changes, and deterministic sequences.
"""
import json

class Trader:
    def __init__(self):
        self._prev_book = {}

    def run(self, state):
        result = {}
        ts = state.timestamp
        iteration = ts // 100

        for product, depth in state.order_depths.items():
            result[product] = []
            best_bid = max(depth.buy_orders.keys()) if depth.buy_orders else None
            best_ask = min(depth.sell_orders.keys()) if depth.sell_orders else None
            mid = (best_bid + best_ask) / 2 if best_bid and best_ask else None
            n_bid_levels = len(depth.buy_orders)
            n_ask_levels = len(depth.sell_orders)

            book_snapshot = {
                "bids": sorted([(p, v) for p, v in depth.buy_orders.items()], reverse=True),
                "asks": sorted([(p, v) for p, v in depth.sell_orders.items()])
            }

            prev = self._prev_book.get(product)
            changed = prev != book_snapshot if prev else True

            print(f"PROBE|{ts}|DETAIL|{json.dumps({'product': product, 'iteration': iteration, 'mid': mid, 'spread': (best_ask - best_bid) if best_bid and best_ask else None, 'n_bid_levels': n_bid_levels, 'n_ask_levels': n_ask_levels, 'book_changed': changed, 'book': book_snapshot})}")

            self._prev_book[product] = book_snapshot

        for product, trades in state.market_trades.items():
            for t in trades:
                print(f"PROBE|{ts}|MARKET_TRADE|{json.dumps({'product': product, 'price': t.price, 'quantity': t.quantity, 'buyer': t.buyer, 'seller': t.seller})}")

        # Flag boundary iterations
        if iteration < 10 or iteration > 990:
            print(f"PROBE|{ts}|BOUNDARY|{json.dumps({'iteration': iteration, 'type': 'start' if iteration < 10 else 'end'})}")

        return result, 0, ""
