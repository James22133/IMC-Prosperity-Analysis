"""
PROBE 6: Inventory Response Test
Phase 1 (0-300): Aggressively buy to build long position near limit.
Phase 2 (300-700): Do nothing — observe bot behavior.
Phase 3 (700-1000): Aggressively sell to unwind.
Tests if bots adjust quotes based on player inventory.
"""
import json
from datamodel import Order

class Trader:
    def run(self, state):
        result = {}
        ts = state.timestamp
        iteration = ts // 100

        if iteration < 300:
            phase = "ACCUMULATE"
        elif iteration < 700:
            phase = "OBSERVE"
        else:
            phase = "UNWIND"

        for product, depth in state.order_depths.items():
            orders = []
            best_bid = max(depth.buy_orders.keys()) if depth.buy_orders else None
            best_ask = min(depth.sell_orders.keys()) if depth.sell_orders else None
            mid = (best_bid + best_ask) / 2 if best_bid and best_ask else None
            pos = state.position.get(product, 0)
            spread = (best_ask - best_bid) if best_bid and best_ask else None

            book_data = {
                "bids": {str(p): v for p, v in sorted(depth.buy_orders.items(), reverse=True)[:3]},
                "asks": {str(p): v for p, v in sorted(depth.sell_orders.items())[:3]}
            }

            if phase == "ACCUMULATE" and best_ask is not None and pos < 20:
                qty = min(3, 20 - pos)
                orders.append(Order(product, best_ask, qty))
            elif phase == "UNWIND" and best_bid is not None and pos > -20:
                qty = min(3, pos + 20)
                orders.append(Order(product, best_bid, -qty))

            print(f"PROBE|{ts}|STATE|{json.dumps({'product': product, 'phase': phase, 'mid': mid, 'spread': spread, 'position': pos, 'book': book_data})}")

            result[product] = orders

        for product, trades in state.own_trades.items():
            for t in trades:
                print(f"PROBE|{ts}|FILL|{json.dumps({'product': product, 'price': t.price, 'quantity': t.quantity})}")

        return result, 0, ""
