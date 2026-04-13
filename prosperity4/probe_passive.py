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

            if order_depth.buy_orders and order_depth.sell_orders:
                best_bid = max(order_depth.buy_orders.keys())
                best_ask = min(order_depth.sell_orders.keys())
                mid = (best_bid + best_ask) / 2

                if pos < 20:
                    buy_price = best_bid + 1
                    if buy_price < best_ask:
                        orders.append(Order(product, buy_price, 1))
                        print(
                            f"PASSIVE_BID|{state.timestamp}|{product}"
                            f"|price={buy_price}|mid={mid}"
                        )

                if pos > -20:
                    sell_price = best_ask - 1
                    if sell_price > best_bid:
                        orders.append(Order(product, sell_price, -1))
                        print(
                            f"PASSIVE_ASK|{state.timestamp}|{product}"
                            f"|price={sell_price}|mid={mid}"
                        )

            if product in state.own_trades:
                for t in state.own_trades[product]:
                    print(
                        f"FILL|{state.timestamp}|{product}"
                        f"|price={t.price}|qty={t.quantity}"
                        f"|buyer={t.buyer}|seller={t.seller}"
                    )

            print(f"POS|{state.timestamp}|{product}|{pos}")
            result[product] = orders

        return result, conversions, ""
