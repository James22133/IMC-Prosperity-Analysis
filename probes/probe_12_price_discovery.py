"""
PROBE 12: Price Discovery — Binary Search for Bot Fair Value
Uses traderData to persist binary search state between iterations.
Alternates between testing buy-side and sell-side to narrow down the bot's fair value.
"""
import json
from datamodel import Order

SEARCH_WINDOW = 50  # iterations per test level
MAX_OFFSET = 30     # initial search range from mid

class Trader:
    def run(self, state):
        result = {}
        ts = state.timestamp
        iteration = ts // 100

        try:
            td = json.loads(state.traderData) if state.traderData else {}
        except (json.JSONDecodeError, TypeError):
            td = {}

        for product, depth in state.order_depths.items():
            orders = []
            best_bid = max(depth.buy_orders.keys()) if depth.buy_orders else None
            best_ask = min(depth.sell_orders.keys()) if depth.sell_orders else None
            mid = (best_bid + best_ask) / 2 if best_bid and best_ask else None
            pos = state.position.get(product, 0)

            pk = f"{product}_search"
            if pk not in td:
                td[pk] = {
                    "low": int(mid - MAX_OFFSET) if mid else 0,
                    "high": int(mid + MAX_OFFSET) if mid else 10000,
                    "test_price": int(mid) if mid else 5000,
                    "fills_at_level": 0,
                    "tests_at_level": 0,
                    "side": "BUY",
                    "results": []
                }

            s = td[pk]

            if s["side"] == "BUY":
                test_price = s["test_price"]
                if pos < 20:
                    orders.append(Order(product, test_price, 1))
                s["tests_at_level"] += 1
            else:
                test_price = s["test_price"]
                if pos > -20:
                    orders.append(Order(product, test_price, -1))
                s["tests_at_level"] += 1

            # Check fills from previous iteration
            for t in state.own_trades.get(product, []):
                s["fills_at_level"] += 1
                print(f"PROBE|{ts}|SEARCH_FILL|{json.dumps({'product': product, 'test_price': test_price, 'fill_price': t.price, 'side': s['side']})}")

            if s["tests_at_level"] >= SEARCH_WINDOW:
                fill_rate = s["fills_at_level"] / s["tests_at_level"]
                result_entry = {"price": s["test_price"], "side": s["side"], "fill_rate": fill_rate, "fills": s["fills_at_level"]}
                s["results"].append(result_entry)
                print(f"PROBE|{ts}|SEARCH_RESULT|{json.dumps(result_entry)}")

                # Binary search logic
                if s["side"] == "BUY":
                    if fill_rate > 0.1:
                        s["high"] = s["test_price"]
                    else:
                        s["low"] = s["test_price"]
                    s["test_price"] = (s["low"] + s["high"]) // 2
                    if s["high"] - s["low"] <= 2:
                        s["side"] = "SELL"
                        if mid:
                            s["low"] = int(mid - MAX_OFFSET)
                            s["high"] = int(mid + MAX_OFFSET)
                            s["test_price"] = int(mid)
                else:
                    if fill_rate > 0.1:
                        s["low"] = s["test_price"]
                    else:
                        s["high"] = s["test_price"]
                    s["test_price"] = (s["low"] + s["high"]) // 2

                s["fills_at_level"] = 0
                s["tests_at_level"] = 0

            print(f"PROBE|{ts}|SEARCH_STATE|{json.dumps({'product': product, 'mid': mid, 'test_price': s['test_price'], 'side': s['side'], 'low': s['low'], 'high': s['high'], 'position': pos})}")

            td[pk] = s
            result[product] = orders

        return result, 0, json.dumps(td)
