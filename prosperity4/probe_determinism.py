from datamodel import TradingState


class Trader:

    def bid(self):
        return 15

    def run(self, state: TradingState):
        result = {}
        conversions = 0

        for product in state.order_depths:
            order_depth = state.order_depths[product]
            mid = 0
            if order_depth.buy_orders and order_depth.sell_orders:
                best_bid = max(order_depth.buy_orders.keys())
                best_ask = min(order_depth.sell_orders.keys())
                mid = (best_bid + best_ask) / 2

            print(
                f"DET|{state.timestamp}|{product}|mid={mid}"
                f"|bids={sorted(order_depth.buy_orders.items())}"
                f"|asks={sorted(order_depth.sell_orders.items())}"
            )

            if product in state.market_trades:
                for t in state.market_trades[product]:
                    print(
                        f"DET_TRADE|{state.timestamp}|{product}"
                        f"|{t.price}|{t.quantity}"
                    )

            result[product] = []

        return result, conversions, ""
