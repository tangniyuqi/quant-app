
import math

class GridStrategy:
    def __init__(self):
        self.log_layer_base = math.log(1.03)

    def _get_layer_index(self, price, base_price):
        if price <= 0 or base_price <= 0 or self.log_layer_base == 0: return 0
        val = math.log(price / base_price) / self.log_layer_base
        return int(math.floor(val))

strategy = GridStrategy()
base_price = 10.0

prices = [10.31, 10.30, 10.29, 10.01, 10.00, 9.99, 9.72, 9.71, 9.70]

print(f"Base Price: {base_price}")
print(f"Layer Percent: 3%")
print("-" * 30)
for p in prices:
    idx = strategy._get_layer_index(p, base_price)
    print(f"Price: {p:.2f} -> Index: {idx}")
