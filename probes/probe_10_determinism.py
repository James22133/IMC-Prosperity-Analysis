"""
PROBE 10: Determinism Test
Upload this EXACT file twice. Compare the two debug logs character by character.
If identical → simulation is fully deterministic → bots follow a fixed script.
Does nothing — just logs everything with a hash of the full state for easy comparison.
"""
import json
import hashlib

class Trader:
    def run(self, state):
        result = {}
        ts = state.timestamp

        state_parts = []
        for product in sorted(state.order_depths.keys()):
            result[product] = []
            depth = state.order_depths[product]
            bids = sorted(depth.buy_orders.items(), reverse=True)
            asks = sorted(depth.sell_orders.items())
            state_parts.append(f"{product}|B{bids}|A{asks}")

            for product_t, trades in state.market_trades.items():
                for t in trades:
                    state_parts.append(f"T|{product_t}|{t.price}|{t.quantity}|{t.buyer}|{t.seller}")

        state_str = "||".join(state_parts)
        state_hash = hashlib.md5(state_str.encode()).hexdigest()[:16]

        print(f"PROBE|{ts}|HASH|{state_hash}")
        print(f"PROBE|{ts}|FULL|{json.dumps({'state': state_str[:500]})}")

        return result, 0, ""
