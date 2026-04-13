"""
PROBE 8: Reaction Latency Test
At specific iterations, execute a large trade. Measure how many ticks until
the book returns to pre-trade state (or equilibrium). Uses traderData for state.
"""
import json
from datamodel import Order

SHOCK_ITERATIONS = [100, 300, 500, 700]
SHOCK_QTY = 10

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
            spread = (best_ask - best_bid) if best_bid and best_ask else None

            prod_key = f"{product}_state"
            pstate = td.get(prod_key, {"phase": "idle", "pre_mid": None, "shock_ts": None, "recovery_count": 0})

            if iteration in SHOCK_ITERATIONS and pstate["phase"] == "idle":
                if best_ask is not None and pos + SHOCK_QTY <= 20:
                    orders.append(Order(product, best_ask, SHOCK_QTY))
                    pstate = {"phase": "recovery", "pre_mid": mid, "shock_ts": ts, "recovery_count": 0}
                    print(f"PROBE|{ts}|SHOCK|{json.dumps({'product': product, 'qty': SHOCK_QTY, 'pre_mid': mid, 'price': best_ask})}")
            elif pstate["phase"] == "recovery":
                pstate["recovery_count"] += 1
                pre_mid = pstate["pre_mid"]
                if mid is not None and pre_mid is not None and abs(mid - pre_mid) < 1:
                    print(f"PROBE|{ts}|RECOVERED|{json.dumps({'product': product, 'ticks': pstate['recovery_count'], 'pre_mid': pre_mid, 'current_mid': mid})}")
                    pstate = {"phase": "idle", "pre_mid": None, "shock_ts": None, "recovery_count": 0}
                elif pstate["recovery_count"] > 100:
                    print(f"PROBE|{ts}|NO_RECOVERY|{json.dumps({'product': product, 'ticks': pstate['recovery_count'], 'pre_mid': pre_mid, 'current_mid': mid})}")
                    pstate = {"phase": "idle", "pre_mid": None, "shock_ts": None, "recovery_count": 0}

            td[prod_key] = pstate

            print(f"PROBE|{ts}|BOOK|{json.dumps({'product': product, 'mid': mid, 'spread': spread, 'position': pos, 'phase': pstate['phase']})}")
            result[product] = orders

        for product, trades in state.own_trades.items():
            for t in trades:
                print(f"PROBE|{ts}|FILL|{json.dumps({'product': product, 'price': t.price, 'quantity': t.quantity})}")

        return result, 0, json.dumps(td)
