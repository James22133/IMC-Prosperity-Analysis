from datamodel import TradingState


class Trader:

    def bid(self):
        return 15

    def run(self, state: TradingState):
        result = {}
        conversions = 0

        for product in state.order_depths:
            order_depth = state.order_depths[product]
            pos = state.position.get(product, 0)

            bids = sorted(order_depth.buy_orders.items(), reverse=True)
            asks = sorted(order_depth.sell_orders.items())

            if bids:
                bid_wall = max(bids, key=lambda x: x[1])
                print(
                    f"BID_WALL|{state.timestamp}|{product}"
                    f"|price={bid_wall[0]}|vol={bid_wall[1]}"
                )
            if asks:
                ask_wall = min(asks, key=lambda x: x[1])
                print(
                    f"ASK_WALL|{state.timestamp}|{product}"
                    f"|price={ask_wall[0]}|vol={ask_wall[1]}"
                )

            print(
                f"BOOK|{state.timestamp}|{product}"
                f"|bids={dict(bids)}|asks={dict(asks)}|pos={pos}"
            )

            if product in state.market_trades:
                for trade in state.market_trades[product]:
                    print(
                        f"MTRADE|{state.timestamp}|{product}"
                        f"|price={trade.price}|qty={trade.quantity}"
                        f"|buyer={trade.buyer}|seller={trade.seller}"
                    )

            result[product] = []

        return result, conversions, ""
