# -*- coding: utf-8 -*-
import time
import json
import requests
import datetime
from ..base import BaseStrategy

class TrendStrategy(BaseStrategy):
    def __init__(self, data, log_callback=None):
        super().__init__(data, log_callback)
        self._init_config()
        self.holding = False
        self.entry_price = 0.0

    def _init_config(self):
        config = self.data.get('task', {}).get('config', {})
        if isinstance(config, str):
            try: config = json.loads(config)
            except: pass
        
        self.short_window = int(config.get('shortWindow', 5))
        self.long_window = int(config.get('longWindow', 20))
        self.quantity = int(config.get('quantity', 100))
        self.stop_loss = float(config.get('stopLoss', 0)) / 100.0
        self.take_profit = float(config.get('takeProfit', 0)) / 100.0
        self.timeframe = int(config.get('timeframe', 240)) # 默认 240 (日线)
        self.interval = int(config.get('interval', 60))
        
        # 确保长期窗口大于短期窗口
        if self.short_window >= self.long_window:
            self.short_window, self.long_window = 5, 20
            self.log(f"配置错误: 短期窗口必须小于长期窗口。重置为 5/20。", "WARNING")

    def fetch_kline(self, symbol, scale=240, datalen=100):
        """
        从新浪 API 获取 K 线数据
        symbol: 例如 sh600519
        scale: 5, 15, 30, 60, 240(日线)
        datalen: 数据点数量
        """
        try:
            url = f"http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={symbol}&scale={scale}&ma=no&datalen={datalen}"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                # 解析收盘价
                closes = [float(item['close']) for item in data]
                return closes
            else:
                self.log(f"获取 K 线失败: {resp.status_code}", "ERROR")
                return []
        except Exception as e:
            self.log(f"获取 K 线异常: {e}", "ERROR")
            return []

    def calculate_ma(self, data, window):
        if len(data) < window:
            return None
        return sum(data[-window:]) / window

    def run(self):
        id = self.data.get('id', 0)
        self.log(f"任务({id}): 趋势策略启动。短期:{self.short_window}, 长期:{self.long_window}")
        
        stock_info = self.data.get('task', {}).get('stock', {})
        if isinstance(stock_info, str):
            try: stock_info = json.loads(stock_info)
            except: pass
        
        ts_code = stock_info.get('ts_code', '')
        if not ts_code:
            self.log(f"任务({id}): 未找到股票代码", "ERROR")
            return

        # 将 ts_code (000001.SZ) 转换为新浪代码 (sz000001)
        symbol = ts_code.split('.')
        if len(symbol) == 2:
            sina_symbol = symbol[1].lower() + symbol[0]
        else:
            sina_symbol = ts_code # 回退

        while self.running:
            try:
                # 1. 获取数据
                closes = self.fetch_kline(sina_symbol, scale=self.timeframe, datalen=self.long_window + 5)
                if not closes or len(closes) < self.long_window + 1:
                    time.sleep(self.interval)
                    continue

                current_price = closes[-1]
                
                # 2. 计算指标
                # 当前均线
                short_ma = self.calculate_ma(closes, self.short_window)
                long_ma = self.calculate_ma(closes, self.long_window)
                
                # 前一均线 (用于交叉检查)
                prev_closes = closes[:-1]
                prev_short_ma = self.calculate_ma(prev_closes, self.short_window)
                prev_long_ma = self.calculate_ma(prev_closes, self.long_window)
                
                if not (short_ma and long_ma and prev_short_ma and prev_long_ma):
                    time.sleep(self.interval)
                    continue

                self.log(f"当前价: {current_price}, MA{self.short_window}: {short_ma:.2f}, MA{self.long_window}: {long_ma:.2f}")

                # 3. 检查持仓 (模拟或真实)
                # 在真实场景中，我们应该同步账户持仓。
                # 为简单起见，我们使用 self.holding 标志或查询交易员。
                # 如果已连接，查询交易员获取实际持仓。
                
                position = None
                if self.connect_trader:
                    try:
                        positions = self.trader.get_positions()
                        for pos in positions:
                            if pos.get('stock_code') == symbol[0]: # 检查不带后缀的代码
                                position = pos
                                break
                    except Exception as e:
                        # self.log(f"获取持仓失败: {e}", "WARNING")
                        pass
                
                has_position = position is not None and float(position.get('volume', 0)) > 0
                if has_position:
                    self.holding = True
                    # 如果未设置，更新入场价格 (近似值)
                    if self.entry_price == 0: 
                        self.entry_price = float(position.get('price', current_price)) 
                else:
                    self.holding = False
                    self.entry_price = 0

                # 4. 信号逻辑
                # 金叉: 短期均线上穿长期均线
                golden_cross = prev_short_ma <= prev_long_ma and short_ma > long_ma
                
                # 死叉: 短期均线下穿长期均线
                death_cross = prev_short_ma >= prev_long_ma and short_ma < long_ma

                # 5. 执行
                if not self.holding and golden_cross:
                    self.log(f"检测到金叉。买入 {self.quantity} 股。")
                    if self.connect_trader:
                        self.trader.buy(ts_code, price=current_price, amount=self.quantity)
                        self.holding = True
                        self.entry_price = current_price
                
                elif self.holding:
                    # 卖出信号
                    sell_signal = False
                    reason = ""

                    if death_cross:
                        sell_signal = True
                        reason = "死叉"
                    
                    # 止损
                    if self.stop_loss > 0 and current_price < self.entry_price * (1 - self.stop_loss):
                        sell_signal = True
                        reason = f"止损 ({self.stop_loss*100}%)"

                    # 止盈
                    if self.take_profit > 0 and current_price > self.entry_price * (1 + self.take_profit):
                        sell_signal = True
                        reason = f"止盈 ({self.take_profit*100}%)"

                    if sell_signal:
                        self.log(f"触发 {reason}。卖出 {self.quantity} 股。")
                        if self.connect_trader:
                            self.trader.sell(ts_code, price=current_price, amount=self.quantity)
                            self.holding = False
                            self.entry_price = 0

            except Exception as e:
                self.log(f"策略循环错误: {e}", "ERROR")
                import traceback
                traceback.print_exc()
            
            time.sleep(self.interval)
