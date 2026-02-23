
import unittest
import json
import time
from unittest.mock import MagicMock, patch
import sys
import os
from unittest.mock import MagicMock

# Mock easytrader before importing project modules
sys.modules['easytrader'] = MagicMock()
sys.modules['easytrader.remoteclient'] = MagicMock()

# Ensure project root is in sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from pyapp.quant.strategies.trend import TrendStrategy

class TestTrendStrategy(unittest.TestCase):
    def setUp(self):
        self.mock_data = {
            'id': 1,
            'name': 'Test Trend Strategy',
            'token': 'test_token',
            'backend_url': 'http://localhost:8000',
            'account': {
                'broker': 'mock_broker',
                'id': 'acc_123'
            },
            'task': {
                'config': json.dumps({
                    'signalType': 'MA',
                    'maShortPeriod': 5,
                    'maLongPeriod': 10,
                    'quantity': 100,
                    'stopLoss': 5.0,
                    'takeProfit': 10.0,
                    'tradeDirection': 0,
                    'monitorInterval': 60
                }),
                'stock': json.dumps({
                    'ts_code': '600519.SH',
                    'name': '贵州茅台'
                })
            }
        }
        
        with patch('pyapp.quant.base.QuantTrader') as MockTrader:
            self.strategy = TrendStrategy(self.mock_data)
            self.strategy.trader = MockTrader.return_value
            self.strategy.log = MagicMock()

    def test_init_config_ma(self):
        """测试MA模式配置初始化"""
        self.assertEqual(self.strategy.signal_type, 'MA')
        self.assertEqual(self.strategy.ma_short_period, 5)
        self.assertEqual(self.strategy.ma_long_period, 10)
        self.assertEqual(self.strategy.stop_loss, 0.05)
        self.assertEqual(self.strategy.take_profit, 0.1)

    def test_init_config_macd(self):
        """测试MACD模式配置初始化"""
        data = self.mock_data.copy()
        data['task']['config'] = json.dumps({
            'signalType': 'MACD',
            'macdFastPeriod': 12,
            'macdSlowPeriod': 26,
            'macdSignalPeriod': 9
        })
        
        with patch('pyapp.quant.base.QuantTrader'):
            strategy = TrendStrategy(data)
            self.assertEqual(strategy.signal_type, 'MACD')
            self.assertEqual(strategy.macd_fast_period, 12)
            self.assertEqual(strategy.macd_slow_period, 26)
            self.assertEqual(strategy.macd_signal_period, 9)

    def test_init_config_invalid_ma(self):
        """测试无效MA参数自动修正"""
        data = self.mock_data.copy()
        data['task']['config'] = json.dumps({
            'signalType': 'MA',
            'maShortPeriod': 20,
            'maLongPeriod': 10  # Invalid: short >= long
        })
        
        # Patch log method to verify warning and suppress output
        with patch('pyapp.quant.base.QuantTrader'), \
             patch('pyapp.quant.strategies.trend.TrendStrategy.log') as mock_log:
            strategy = TrendStrategy(data)
            
            # Should reset to defaults 5/20
            self.assertEqual(strategy.ma_short_period, 5)
            self.assertEqual(strategy.ma_long_period, 20)
            
            # Verify warning was logged
            mock_log.assert_called()
            args, _ = mock_log.call_args
            self.assertIn("配置错误", args[0])
            self.assertEqual(args[1], "WARNING")

    def test_calculate_ma(self):
        """测试MA计算"""
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        ma3 = self.strategy.calculate_ma(data, 3)
        self.assertEqual(ma3, 4.0) # (3+4+5)/3 = 4
        
        ma6 = self.strategy.calculate_ma(data, 6)
        self.assertIsNone(ma6) # Not enough data

    def test_calculate_macd(self):
        """测试MACD计算"""
        # Generate some dummy data
        data = [10.0] * 50
        # MACD of constant series should be near 0
        diff, dea, prev_diff, prev_dea = self.strategy.calculate_macd(data, 12, 26, 9)
        self.assertAlmostEqual(diff, 0.0, places=4)
        self.assertAlmostEqual(dea, 0.0, places=4)

    def test_check_cross_signal(self):
        """测试交叉信号检测"""
        # Golden Cross: prev_short <= prev_long AND short > long
        golden, death = self.strategy._check_cross_signal(
            short_ma=10.5, long_ma=10.0,
            prev_short_ma=9.8, prev_long_ma=10.0
        )
        self.assertTrue(golden)
        self.assertFalse(death)

        # Death Cross: prev_short >= prev_long AND short < long
        golden, death = self.strategy._check_cross_signal(
            short_ma=9.5, long_ma=10.0,
            prev_short_ma=10.2, prev_long_ma=10.0
        )
        self.assertFalse(golden)
        self.assertTrue(death)

        # No Cross
        golden, death = self.strategy._check_cross_signal(
            short_ma=11.0, long_ma=10.0,
            prev_short_ma=10.5, prev_long_ma=10.0
        )
        self.assertFalse(golden)
        self.assertFalse(death)

    def test_check_stop_conditions(self):
        """测试止损止盈"""
        self.strategy.holding = True
        self.strategy.entry_price = 100.0
        
        # Stop Loss: -5%
        triggered, reason = self.strategy._check_stop_conditions(94.0) # -6%
        self.assertTrue(triggered)
        self.assertIn("止损", reason)

        # Take Profit: +10%
        triggered, reason = self.strategy._check_stop_conditions(111.0) # +11%
        self.assertTrue(triggered)
        self.assertIn("止盈", reason)

        # Normal
        triggered, reason = self.strategy._check_stop_conditions(102.0)
        self.assertFalse(triggered)

    def test_execute_buy(self):
        """测试买入执行"""
        self.strategy.connect_trader = True
        self.strategy.enable_real_trade = True
        self.strategy.stock_code = '600519.SH'
        
        self.strategy._execute_buy(100.0, 100)
        
        self.strategy.trader.buy.assert_called_once_with('600519.SH', price=100.0, amount=100)
        self.assertTrue(self.strategy.holding)
        self.assertEqual(self.strategy.entry_price, 100.0)

    def test_execute_sell(self):
        """测试卖出执行"""
        self.strategy.connect_trader = True
        self.strategy.enable_real_trade = True
        self.strategy.stock_code = '600519.SH'
        self.strategy.holding = True
        self.strategy.entry_price = 100.0
        
        self.strategy._execute_sell(110.0, 100, "Take Profit")
        
        self.strategy.trader.sell.assert_called_once_with('600519.SH', price=110.0, amount=100)
        self.assertFalse(self.strategy.holding)
        self.assertEqual(self.strategy.entry_price, 0.0)

    def test_parse_stock_info(self):
        """测试股票代码解析"""
        ts, sina = self.strategy._parse_stock_info()
        self.assertEqual(ts, '600519.SH')
        self.assertEqual(sina, 'sh600519')

    @patch('requests.get')
    def test_fetch_kline(self, mock_get):
        """测试K线获取"""
        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            {'day': '2023-01-01', 'open': '10', 'high': '12', 'low': '9', 'close': '11', 'volume': '1000'}
        ]
        mock_get.return_value = mock_resp
        
        closes = self.strategy.fetch_kline('sh600519')
        self.assertEqual(closes, [11.0])
        self.assertTrue(mock_get.called)

    def test_calculate_trade_quantity_buy_quantity(self):
        """测试买入数量计算 - 固定数量"""
        self.strategy.trade_mode = 'quantity'
        self.strategy.quantity = 200
        self.strategy.connect_trader = True
        
        # 模拟余额充足
        self.strategy.trader.get_balance.return_value = {
            'available_balance': 100000.0,
            'total_asset': 100000.0
        }
        
        qty = self.strategy._calculate_trade_quantity('buy', 100.0)
        self.assertEqual(qty, 200)
        
        # 模拟余额不足
        self.strategy.trader.get_balance.return_value = {
            'available_balance': 1000.0, # 仅够买10股，不足1手
            # 代码逻辑: quantity = int(available_cash / current_price / 100) * 100
            # 1000 / 100 / 100 = 0.1 -> 0
        }
        # 逻辑说明: 如果 预设数量 * 当前价格 > 可用资金
        # 200 * 100 = 20000 > 1000
        # quantity = int(1000 / 100 / 100) * 100 = 0
        qty = self.strategy._calculate_trade_quantity('buy', 100.0)
        self.assertEqual(qty, 0)
        
        # 模拟仅够买1手
        self.strategy.trader.get_balance.return_value = {
            'available_balance': 15000.0
        }
        # 15000 > 200*100=20000? 不够.
        # 20000 > 15000 -> True, 触发自动降级计算
        # qty = int(15000/100/100)*100 = 1*100 = 100
        qty = self.strategy._calculate_trade_quantity('buy', 100.0)
        self.assertEqual(qty, 100)

    def test_calculate_trade_quantity_sell(self):
        """测试卖出数量计算"""
        self.strategy.connect_trader = True
        self.strategy.stock_code = '600519.SH'
        
        # 情况1: 显式传入持仓信息
        position = {'available_quantity': 500}
        qty = self.strategy._calculate_trade_quantity('sell', 100.0, position)
        self.assertEqual(qty, 500)
        
        # 情况2: 自动获取持仓信息
        self.strategy.trader.get_position.return_value = {'available_quantity': 300}
        qty = self.strategy._calculate_trade_quantity('sell', 100.0)
        self.assertEqual(qty, 300)

if __name__ == '__main__':
    unittest.main()
