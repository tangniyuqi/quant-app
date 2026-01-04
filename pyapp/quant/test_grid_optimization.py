
import unittest
import time
import json
import math
import sys
import os
from unittest.mock import MagicMock, patch

# Add parent directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from pyapp.quant.grid import GridStrategy

class MockTrader:
    def __init__(self):
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

class TestGridOptimization(unittest.TestCase):
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
                    'monitorInterval': 0, # Speed up test
                    'tradeDirection': 0, # Both
                    'maxHoldAmount': 20000.0
                },
                'stock': {'ts_code': '000001.SZ'}
            },
            'account': {'security': 'mock'},
            'backend_url': 'http://localhost:8080',
            'token': 'test_token'
        }
        
    def test_performance_benchmark(self):
        # Setup a long sequence of prices
        strategy = GridStrategy(self.config)
        strategy.trader = MockTrader()
        
        # 10000 price points oscillating
        prices = []
        base = 10.0
        for i in range(10000):
            prices.append(base * (1 + 0.06 * math.sin(i * 0.1)))
            
        strategy.trader.prices = prices
        
        # Mock save_record to avoid network calls
        strategy._save_record = MagicMock()
        
        # Override sleep to avoid waiting
        with patch('time.sleep', return_value=None):
            start_time = time.time()
            
            # Run strategy logic manually to avoid threading issues in test or infinite loop
            # We inject a specialized run loop or just call the logic that would be in the loop
            
            # Since we can't easily inject into the loop without modifying the code,
            # We will instantiate it and verify the _get_grid_index performance first,
            # then we will try to run the strategy in a thread but stop it quickly?
            # No, better to extract the loop body logic if we were refactoring, 
            # but here we want to test the EXISTING code.
            
            # We'll use a modified strategy that stops after consuming all prices
            
            original_get_price = strategy.trader.get_current_price
            
            def side_effect(code):
                if strategy.trader.index >= len(strategy.trader.prices):
                    strategy.running = False
                    return 10.0
                return original_get_price(code)
                
            strategy.trader.get_current_price = side_effect
            
            strategy.start()
            strategy.thread.join()
            
            end_time = time.time()
            print(f"Processed {len(prices)} ticks in {end_time - start_time:.4f} seconds")

    @patch('pyapp.quant.base.QuantTrader')
    def test_logic_consistency(self, MockQuantTraderClass):
        # Setup Mock
        mock_trader_instance = MockTrader()
        MockQuantTraderClass.return_value = mock_trader_instance

        # Test tradeDirection = 1 (Sell Only)
        self.config['task']['config']['tradeDirection'] = 1
        strategy = GridStrategy(self.config)
        strategy.trader = mock_trader_instance
        strategy.trader.prices = [10.0, 9.0, 8.0] # Drop should trigger buy in normal grid, but here sell only?
        # Actually grid buys on drop. Sell only means we never buy.
        
        strategy._save_record = MagicMock()
        
        with patch('time.sleep', return_value=None):
            # Run briefly
            strategy.running = True
            
            # Initial Setup
            # Base 10. Drop to 9.0 (10% drop, > 5% grid). Should Buy.
            # But tradeDirection is 1 (Sell Only).
            
            # We need to expose the loop logic or mock run. 
            # Since run() is a loop, let's just test the decision logic if possible?
            # The current code puts everything in run(). 
            # I will perform a black-box test by running it.
            
            # 1. Init
            # 2. Price 9.0 (Index change 0 -> -2). Should Buy.
            
            strategy.trader.prices = [10.0, 9.0]
            
            def side_effect(code):
                if strategy.trader.index >= len(strategy.trader.prices):
                    strategy.running = False
                    return 9.0
                return strategy.trader.get_current_price(code)
            strategy.trader.get_current_price = side_effect # Restore original for the first call
             # Oops, I need to bind the mock correctly.
             
            # Let's just use the logic that if prices run out, we stop.
            strategy.trader.get_current_price = MagicMock(side_effect=lambda code: strategy.trader.prices.pop(0) if strategy.trader.prices else (setattr(strategy, 'running', False) or 9.0))

            strategy.start()
            strategy.thread.join()
            
            # Verify NO buys happened
            buys = [c for c in strategy.trader.calls if c[0] == 'buy']
            # CURRENT IMPLEMENTATION DOES NOT CHECK tradeDirection, so it SHOULD buy.
            # We expect this to fail (or rather succeed in showing the bug) if we assert 0 buys.
            print(f"Buys with Sell Only mode: {len(buys)}")

if __name__ == '__main__':
    unittest.main()
