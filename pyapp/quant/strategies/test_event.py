
import unittest
import json
import logging
from unittest.mock import MagicMock, patch
from datetime import datetime, date

# 假设项目根目录在 PYTHONPATH 中，或者通过相对导入
# 这里为了确保测试运行方便，尝试调整 sys.path 或者使用 mock
import sys
import os

# 将项目根目录添加到 sys.path，假设当前文件在 pyapp/quant/strategies/
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from pyapp.quant.strategies.event import EventStrategy

class TestEventStrategy(unittest.TestCase):
    def setUp(self):
        # 构造基本的初始化数据
        self.mock_data = {
            'id': 1,
            'name': 'Test Event Strategy',
            'token': 'test_token',
            'backend_url': 'http://localhost:8000',
            'account': {
                'server': {
                    'ai_model': 'gpt-3.5-turbo',
                    'ai_key': 'test_key',
                    'ai_url': 'https://api.openai.com/v1/chat/completions',
                    'webhook_url': 'http://webhook'
                }
            },
            'task': {
                'config': json.dumps({
                    'targetKeywords': ['茅台', '白酒'],
                    'triggerKeywords': ['涨价', '利好'],
                    'excludedKeywords': ['利空', '暴跌'],
                    'maxBuyRise': 5.0,  # 买入时最大涨幅限制 5%
                    'minSellFall': -7.0, # 卖出时最小跌幅限制 -7%
                    'tradeDirection': 0, # 0=中性, 1=只买, 2=只卖
                    'tradeMode': 'quantity',
                    'quantity': 100,
                    'confidenceThreshold': 0.6
                })
            }
        }
        
        # Mock QuantTrader to prevent actual connection
        with patch('pyapp.quant.base.QuantTrader') as MockTrader:
            self.strategy = EventStrategy(self.mock_data)
            self.strategy.trader = MockTrader.return_value
            # Mock log method to avoid print spam
            self.strategy.log = MagicMock()

    def test_init_config(self):
        """测试配置初始化是否正确"""
        self.assertEqual(self.strategy.target_keywords, ['茅台', '白酒'])
        self.assertEqual(self.strategy.max_buy_rise, 5.0)
        self.assertEqual(self.strategy.min_sell_fall, -7.0)
        self.assertEqual(self.strategy.ai_model, 'gpt-3.5-turbo')
        self.assertEqual(self.strategy.quantity, 100)

    def test_contains_keywords(self):
        """测试关键词过滤逻辑"""
        # 情况1: 包含标的且包含触发，不包含排除 -> True
        self.assertTrue(self.strategy.contains_keywords("茅台宣布涨价"))
        
        # 情况2: 包含标的但不包含触发 -> False
        self.assertFalse(self.strategy.contains_keywords("茅台发布年报"))
        
        # 情况3: 不包含标的但包含触发 -> False
        self.assertFalse(self.strategy.contains_keywords("五粮液宣布涨价"))
        
        # 情况4: 包含标的和触发，但也包含排除 -> False
        self.assertFalse(self.strategy.contains_keywords("茅台宣布涨价，但随后暴跌"))
        
        # 测试空配置情况
        self.strategy.target_keywords = []
        self.strategy.trigger_keywords = []
        self.strategy.excluded_keywords = []
        self.assertFalse(self.strategy.contains_keywords("任何内容"))

    def test_parse_ai_json(self):
        """测试AI响应的JSON解析"""
        # 1. 标准JSON
        json_str = '{"signal": "buy", "related_stock": "600519", "reason": "good", "confidence": 0.9}'
        result = self.strategy._parse_ai_json(json_str)
        self.assertEqual(result['signal'], 'buy')
        
        # 2. Markdown代码块包裹的JSON
        md_json = '```json\n{"signal": "sell", "related_stock": "000001", "reason": "bad"}\n```'
        result = self.strategy._parse_ai_json(md_json)
        self.assertEqual(result['signal'], 'sell')
        
        # 3. 包含杂质文本的JSON
        dirty_json = 'Here is the result: {"signal": "none", "related_stock": "", "reason": "neutral"} thank you.'
        result = self.strategy._parse_ai_json(dirty_json)
        self.assertEqual(result['signal'], 'none')
        
        # 4. 错误的格式
        bad_json = 'not a json'
        result = self.strategy._parse_ai_json(bad_json)
        self.assertIsNone(result)

    def test_process_signal_buy_success(self):
        """测试买入信号处理 - 成功情况"""
        analysis = {
            'signal': 'buy',
            'related_stock': '600519',
            'reason': 'test buy',
            'confidence': 0.8
        }
        
        # Mock trader methods
        self.strategy.trader.get_balance.return_value = {
            'available_balance': 100000.0,
            'total_asset': 100000.0
        }
        self.strategy.trader.get_stock_quote.return_value = {
            'price': 100.0,
            'pre_close': 98.0 # +2.04%
        }
        self.strategy.trader.buy.return_value = {'task_id': '123'}
        
        # Mock _safe_buy
        with patch.object(self.strategy, '_safe_buy', return_value={'id': '123'}) as mock_buy:
            self.strategy.process_signal(analysis)
            mock_buy.assert_called_once()
            args, _ = mock_buy.call_args
            self.assertEqual(args[0], '600519') # stock
            self.assertEqual(args[1], 100.0)    # price

    def test_process_signal_priced_in_skip(self):
        analysis = {
            'signal': 'buy',
            'related_stock': '600519',
            'reason': 'already priced in',
            'confidence': 0.9,
            'is_priced_in': True
        }

        with patch.object(self.strategy, '_safe_buy') as mock_buy:
            self.strategy.process_signal(analysis)
            mock_buy.assert_not_called()
            self.strategy.trader.get_balance.assert_not_called()
            self.assertTrue(any("已Price In" in str(call) for call in self.strategy.log.mock_calls))

    def test_process_signal_priced_in_string_skip(self):
        analysis = {
            'signal': 'buy',
            'related_stock': '600519',
            'reason': 'already priced in',
            'confidence': 0.9,
            'is_priced_in': "true"
        }

        with patch.object(self.strategy, '_safe_buy') as mock_buy:
            self.strategy.process_signal(analysis)
            mock_buy.assert_not_called()
            self.strategy.trader.get_balance.assert_not_called()
            self.assertTrue(any("已Price In" in str(call) for call in self.strategy.log.mock_calls))

    def test_process_signal_buy_risk_control(self):
        """测试买入风控 - 涨幅过高拦截"""
        analysis = {
            'signal': 'buy',
            'related_stock': '600519',
            'reason': 'chasing high',
            'confidence': 0.8
        }
        
        # Mock balance to pass quantity check
        self.strategy.trader.get_balance.return_value = {
            'available_balance': 100000.0,
            'total_asset': 100000.0
        }
        
        # 设定当前涨幅为 6% (pre_close=100, price=106)，超过 max_buy_rise=5.0
        self.strategy.trader.get_stock_quote.return_value = {
            'price': 106.0,
            'pre_close': 100.0
        }
        
        with patch.object(self.strategy, '_safe_buy') as mock_buy:
            self.strategy.process_signal(analysis)
            mock_buy.assert_not_called()
            # 验证是否记录了相关日志
            self.assertTrue(any("触发【防追高】风控" in str(call) for call in self.strategy.log.mock_calls))

    def test_process_signal_sell_risk_control(self):
        """测试卖出风控 - 跌幅过深拦截"""
        analysis = {
            'signal': 'sell',
            'related_stock': '600519',
            'reason': 'panic sell',
            'confidence': 0.8
        }
        
        # Mock balance/position
        self.strategy.trader.get_balance.return_value = {
            'available_balance': 100000.0,
            'total_asset': 100000.0
        }
        # Mock position for sell quantity
        self.strategy.trader.get_position.return_value = {
            'available_quantity': 100
        }
        
        # 设定当前跌幅为 -8% (pre_close=100, price=92)，低于 min_sell_fall=-7.0
        self.strategy.trader.get_stock_quote.return_value = {
            'price': 92.0,
            'pre_close': 100.0
        }
        
        with patch.object(self.strategy, '_safe_sell') as mock_sell:
            self.strategy.process_signal(analysis)
            mock_sell.assert_not_called()
            self.assertTrue(any("触发【防低吸/防割肉】风控" in str(call) for call in self.strategy.log.mock_calls))

    def test_trade_direction_filter(self):
        """测试交易方向过滤"""
        # 设置为只买
        self.strategy.trade_direction = 1 
        
        analysis_sell = {'signal': 'sell', 'related_stock': '600519', 'confidence': 0.9}
        self.strategy.process_signal(analysis_sell)
        # 应该被过滤，不调用 quote
        self.strategy.trader.get_stock_quote.assert_not_called()
        
        # 设置为只卖
        self.strategy.trade_direction = 2
        
        analysis_buy = {'signal': 'buy', 'related_stock': '600519', 'confidence': 0.9}
        self.strategy.process_signal(analysis_buy)
        self.strategy.trader.get_stock_quote.assert_not_called()

    def test_validity_period_check(self):
        """测试有效期检查"""
        # 设置一个过期的日期
        self.strategy.validity_period = "2020-01-01"
        self.strategy.running = True
        
        # Mock fetch_latest_news_id and fetch_news to avoid loop getting stuck or doing work
        self.strategy.fetch_latest_news_id = MagicMock(return_value=0)
        self.strategy.fetch_news = MagicMock(return_value=[])
        
        # 运行 run 方法，应该检测到过期并退出
        # 注意：run 是一个循环，我们需要它尽快退出。
        # 这里的 run 方法逻辑是 while self.running: check date -> break
        # 所以只要 date check 正常工作，它就会 break
        
        # 为了防止无限循环（如果逻辑有误），我们可以用超时或mock time.sleep
        with patch('time.sleep', side_effect=InterruptedError("Loop should have broken")): 
            try:
                self.strategy.run()
            except InterruptedError:
                self.fail("Strategy did not stop due to validity period")
            
        self.assertFalse(self.strategy.running)
        self.assertTrue(any("已过有效期" in str(call) for call in self.strategy.log.mock_calls))

if __name__ == '__main__':
    unittest.main()
