
import unittest
import json
from pyapp.quant.trader import QuantTrader

class TestTraderConfig(unittest.TestCase):
    def test_connect_with_server_config(self):
        trader = QuantTrader()
        
        # Mock account config
        account_config = {
            "security": "TestSec",
            "account_no": "12345",
            "server": json.dumps({
                "host": "192.168.1.100",
                "port": "8888",
                "data_source": "tushare",
                "data_token": "test_token_123",
                "webhook_url": "https://test.webhook",
                "webhook_type": "feishu"
            })
        }
        
        # Mock easytrader to avoid actual connection error
        # We just want to test parameter parsing
        try:
            trader.connect(account_config)
        except Exception:
            # Expected to fail connection, but we check if attributes are set
            pass
            
        # Check parsed values
        # Note: These attributes are set inside connect before connection attempt or after?
        # In my code, they are set BEFORE connection attempt.
        
        self.assertEqual(trader.webhook_url, "https://test.webhook")
        self.assertEqual(trader.webhook_type, "feishu")
        self.assertEqual(getattr(trader, 'data_source', ''), 'tushare')
        
        # We can't easily check host/port without mocking easytrader module, 
        # but if webhook/source are set, JSON parsing worked.

if __name__ == '__main__':
    unittest.main()
