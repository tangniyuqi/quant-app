import unittest
from unittest.mock import MagicMock, patch
import json
from quant.strategies.event import EventStrategy

class TestEventStrategy(unittest.TestCase):
    def setUp(self):
        self.trader_patcher = patch('quant.base.QuantTrader')
        self.MockQuantTrader = self.trader_patcher.start()
        
        self.data = {
            'id': 123,
            'name': 'Test AI Strategy',
            'task': {
                'config': json.dumps({
                    'deepseekApiKey': 'test_key',
                    'industryKeywords': ['Tech', 'AI'],
                    'eventKeywords': ['Growth'],
                    'newsApiUrl': 'http://test.news/api',
                    'maxSingleOrderAmount': 5000,
                    'maxPositionRatio': 0.5
                })
            },
            # 'account': {'broker': 'mock'} # Commented out to avoid real connection attempt
            'account': {
                'server': { # Mock server config needed for EventStrategy
                    'ai_key': 'test_key',
                    'ai_model': 'deepseek-chat',
                    'ai_url': 'https://api.deepseek.com/v1/chat/completions'
                }
            }
        }
        self.strategy = EventStrategy(self.data)
        self.strategy.trader = MagicMock()
        self.strategy.trader.get_balance.return_value = {
            'available_balance': 10000,
            'total_asset': 20000
        }
        self.strategy.trader.get_stock_quote.return_value = {'price': 100}
        self.strategy.trader.get_position.return_value = {'available_quantity': 500}

    def tearDown(self):
        self.trader_patcher.stop()

    def test_init_config(self):
        self.assertEqual(self.strategy.ai_key, 'test_key')
        self.assertIn('Tech', self.strategy.industry_keywords)
        self.assertEqual(self.strategy.max_single_order_amount, 5000)

    def test_contains_keywords(self):
        self.assertTrue(self.strategy.contains_keywords("Tech company reports Growth"))
        self.assertFalse(self.strategy.contains_keywords("No keywords here"))

    @patch('httpx.post')
    def test_analyze_news_with_ai(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        # Mock DeepSeek response
        mock_response.json.return_value = {
            'choices': [{
                'message': {
                    'content': '```json\n{"related_stock": "600000", "signal": "buy", "reason": "Good news", "confidence": 0.9}\n```'
                }
            }]
        }
        mock_post.return_value = mock_response

        result = self.strategy.analyze_news_with_ai("Some news content")
        self.assertEqual(result['signal'], 'buy')
        self.assertEqual(result['related_stock'], '600000')

    def test_calculate_order_quantity_buy(self):
        # Available cash 10000, max single 5000. Price 100.
        # Should buy 5000 / 100 = 50 shares -> round to 0 (must be 100 multiples?) 
        # Wait, int(5000/100/100)*100 = 0.
        # Let's adjust price to 10.
        self.strategy.trader.get_stock_quote.return_value = {'price': 10}
        # 5000 / 10 = 500 shares.
        qty = self.strategy.calculate_order_quantity('600000', 'buy')
        self.assertEqual(qty, 500)

    def test_calculate_order_quantity_sell(self):
        qty = self.strategy.calculate_order_quantity('600000', 'sell')
        self.assertEqual(qty, 500) # Available 500

if __name__ == '__main__':
    unittest.main()
