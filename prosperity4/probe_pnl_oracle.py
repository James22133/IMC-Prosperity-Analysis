from datamodel import Order, TradingState


class Trader:

    def bid(self):
        return 15

    def run(self, state: TradingState):
        result = {}
        conversions = 0

        for product in state.order_depths:
            orders = []
            order_depth = state.order_depths[product]
            pos = state.position.get(product, 0)

            if state.timestamp == 0:
                if order_depth.sell_orders:
                    best_ask = min(order_depth.sell_orders.keys())
                    orders.append(Order(product, best_ask, 1))
                    print(f"PROBE_BUY|{product}|{best_ask}|1")

            bids = sorted(order_depth.buy_orders.items(), reverse=True)
            asks = sorted(order_depth.sell_orders.items())
            print(
                f"STATE|{state.timestamp}|{product}|pos={pos}"
                f"|bids={dict(bids)}|asks={dict(asks)}"
            )

            result[product] = orders

        return result, conversions, ""
