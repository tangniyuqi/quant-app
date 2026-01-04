
import unittest
import time
import json
import math
import sys
import os
from unittest.mock import MagicMock, patch

# Add parent directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Mock pyapp.quant.base.QuantTrader BEFORE importing GridStrategy
# We need to ensure pyapp.quant.base is imported or at least mockable
import pyapp.quant.base
class MockTrader:
    def __init__(self, log_callback=None):
        self.prices = []
        self.index = 0
        self.position = {'total': 1000, 'available': 1000}
        self.calls = []

    def init_data_source(self, source, token=None):
        pass

    def get_current_price(self, code):
        if self.index < len(self.prices):
            p = self.prices[self.index]
            self.index += 1
            return p
        return self.prices[-1] if self.prices else 0

    def get_position(self, code):
        return self.position

    def buy(self, code, price, volume):
        self.calls.append(('buy', price, volume))
        self.position['total'] += volume
        self.position['available'] += volume
        return "order_id_buy"

    def sell(self, code, price, volume):
        self.calls.append(('sell', price, volume))
        if self.position['available'] >= volume:
            self.position['total'] -= volume
            self.position['available'] -= volume
            return "order_id_sell"
        return None
    
    def connect(self, account):
        pass

# Replace QuantTrader in base module
pyapp.quant.base.QuantTrader = MockTrader

# Now import GridStrategy
from pyapp.quant.grid import GridStrategy

class TestGridOptimizedVerified(unittest.TestCase):
    def setUp(self):
        self.config = {
            'id': 10001,
            'name': 'Test Grid',
            'task': {
                'config': {
                    'basePrice': 10.0,
                    'upperPrice': 12.0,
                    'lowerPrice': 8.0,
                    'gridPercent': 5.0, # 5%
                    'baseVolume': 100,
                    'maxHold': 2000,
                    'monitorInterval': 0,
                    'tradeDirection': 0, # Both
                    'maxHoldAmount': 20000.0
                },
                'stock': {'ts_code': '000001.SZ'}
            },
            'account': {'security': 'mock'},
            'backend_url': 'http://localhost:8080',
            'token': 'test_token'
        }
        
    def test_precomputed_log_performance(self):
        strategy = GridStrategy(self.config)
        # Verify log_grid_base is set
        expected_log = math.log(1 + 0.05)
        self.assertAlmostEqual(strategy.log_grid_base, expected_log)
        
        # Benchmark _get_grid_index
        start = time.time()
        for i in range(100000):
            strategy._get_grid_index(10.5, 10.0)
        end = time.time()
        print(f"100k grid calcs took: {end-start:.4f}s")

    def test_trade_direction_sell_only(self):
        self.config['task']['config']['tradeDirection'] = 1 # Sell Only
        strategy = GridStrategy(self.config)
        # We need to control the trader instance attached to strategy
        # Because BaseStrategy.__init__ creates a new MockTrader instance
        # We can access it via strategy.trader
        
        # Scenario: Price drops. Should buy in Both mode. In Sell Only, should do nothing.
        # Initial: 10.0
        # Next: 9.0 (Drop)
        strategy.trader.prices = [10.0, 9.0]
        
        # Run logic manually or verify via loop
        # Since loop is hard to control, we can test the decision logic by overriding run or just stepping
        
        # Let's inspect internal state updates
        strategy.log_grid_base = math.log(1.05)
        last_grid_index = strategy._get_grid_index(10.0, 10.0) # 0
        
        curr_price = 9.0
        curr_index = strategy._get_grid_index(curr_price, 10.0) # -2 approx
        
        # Logic snippet from grid.py:
        # if curr_index < last_grid_index:
        #    if trade_direction not in [0, 2]: continue
        
        # We can't easily call the loop body. But we can run the strategy with limited prices.
        
        # Mocking get_current_price to stop strategy after prices exhausted
        original_get = strategy.trader.get_current_price
        def side_effect(code):
            if strategy.trader.index >= len(strategy.trader.prices):
                strategy.running = False
                return 9.0
            return original_get(code)
        strategy.trader.get_current_price = side_effect
        
        with patch('requests.Session'): # Mock session
            strategy.start()
            strategy.thread.join()
            
        # Verify calls
        buys = [c for c in strategy.trader.calls if c[0] == 'buy']
        self.assertEqual(len(buys), 0, "Should not buy in Sell Only mode")

    def test_max_hold_amount(self):
        self.config['task']['config']['tradeDirection'] = 0 # Both
        self.config['task']['config']['maxHoldAmount'] = 1000.0 # Small amount
        self.config['task']['config']['baseVolume'] = 100
        # Price 9.0 -> Value 900.
        # Initial pos = 1000 total. Value = 9000 > 1000.
        # Should not buy.
        
        strategy = GridStrategy(self.config)
        strategy.trader.prices = [10.0, 9.0]
        strategy.trader.position = {'total': 1000, 'available': 1000}
        
        original_get = strategy.trader.get_current_price
        def side_effect(code):
            if strategy.trader.index >= len(strategy.trader.prices):
                strategy.running = False
                return 9.0
            return original_get(code)
        strategy.trader.get_current_price = side_effect

        with patch('requests.Session'):
            strategy.start()
            strategy.thread.join()
            
        buys = [c for c in strategy.trader.calls if c[0] == 'buy']
        self.assertEqual(len(buys), 0, "Should not buy if maxHoldAmount exceeded")

if __name__ == '__main__':
    unittest.main()
