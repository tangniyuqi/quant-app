# -*- coding: utf-8 -*-
"""
趋势跟踪策略 - 基于双均线交叉
策略逻辑：
1. 金叉买入：短期均线上穿长期均线时买入
2. 死叉卖出：短期均线下穿长期均线时卖出
3. 止损止盈：支持设置止损和止盈比例
"""
import time
import json
import requests
from typing import Optional, Dict, List, Tuple
from ..base import BaseStrategy


class TrendStrategy(BaseStrategy):
    """双均线趋势跟踪策略"""
    
    def __init__(self, data, log_callback=None):
        super().__init__(data, log_callback)
        self._init_config()
        self._init_position_state()
        
    def _init_config(self):
        """初始化策略配置参数"""
        config = self._parse_config()
        
        # 均线参数
        self.short_window = int(config.get('shortWindow', 5))
        self.long_window = int(config.get('longWindow', 20))
        
        # 交易参数
        self.quantity = int(config.get('quantity', 100))
        self.stop_loss = float(config.get('stopLoss', 0)) / 100.0
        self.take_profit = float(config.get('takeProfit', 0)) / 100.0
        
        # 运行参数
        self.timeframe = int(config.get('timeframe', 240))  # K线周期
        self.interval = int(config.get('interval', 60))  # 轮询间隔
        
        # 参数校验
        self._validate_config()
        
    def _parse_config(self) -> dict:
        """解析配置信息"""
        config = self.data.get('task', {}).get('config', {})
        if isinstance(config, str):
            try:
                config = json.loads(config)
            except json.JSONDecodeError as e:
                self.log(f"配置解析失败: {e}", "ERROR")
                config = {}
        return config
    
    def _validate_config(self):
        """校验配置参数的合法性"""
        if self.short_window >= self.long_window:
            self.log(
                f"配置错误: 短期窗口({self.short_window})必须小于长期窗口({self.long_window})，"
                f"已重置为默认值 5/20", 
                "WARNING"
            )
            self.short_window, self.long_window = 5, 20
            
        if self.quantity < 100:
            self.log(f"交易数量({self.quantity})小于最小值100，已调整为100", "WARNING")
            self.quantity = 100
            
        if self.interval < 5:
            self.log(f"轮询间隔({self.interval}秒)过短，已调整为5秒", "WARNING")
            self.interval = 5
    
    def _init_position_state(self):
        """初始化持仓状态"""
        self.holding = False
        self.entry_price = 0.0
        self.entry_time = None
        self.stock_code = None
        self.sina_symbol = None
        
    def _parse_stock_info(self) -> Tuple[Optional[str], Optional[str]]:
        """
        解析股票信息
        返回: (ts_code, sina_symbol)
        """
        stock_info = self.data.get('task', {}).get('stock', {})
        if isinstance(stock_info, str):
            try:
                stock_info = json.loads(stock_info)
            except json.JSONDecodeError:
                return None, None
        
        ts_code = stock_info.get('ts_code', '')
        if not ts_code:
            return None, None
            
        # 转换为新浪代码格式: 000001.SZ -> sz000001
        parts = ts_code.split('.')
        if len(parts) == 2:
            sina_symbol = parts[1].lower() + parts[0]
        else:
            sina_symbol = ts_code
            
        return ts_code, sina_symbol
    
    def fetch_kline(self, symbol: str, scale: int = 240, datalen: int = 100) -> List[float]:
        """
        从新浪财经API获取K线数据
        
        参数:
            symbol: 股票代码，如 sh600519
            scale: K线周期 (5, 15, 30, 60, 240)
            datalen: 数据点数量
            
        返回:
            收盘价列表
        """
        try:
            url = (
                f"http://money.finance.sina.com.cn/quotes_service/api/"
                f"json_v2.php/CN_MarketData.getKLineData"
                f"?symbol={symbol}&scale={scale}&ma=no&datalen={datalen}"
            )
            
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            
            data = resp.json()
            if not data:
                self.log(f"K线数据为空", "WARNING")
                return []
                
            closes = [float(item['close']) for item in data]
            return closes
            
        except requests.RequestException as e:
            self.log(f"获取K线数据失败: {e}", "ERROR")
            return []
        except (KeyError, ValueError, TypeError) as e:
            self.log(f"解析K线数据失败: {e}", "ERROR")
            return []
    
    def calculate_ma(self, data: List[float], window: int) -> Optional[float]:
        """
        计算简单移动平均线
        
        参数:
            data: 价格数据列表
            window: 窗口大小
            
        返回:
            均线值，数据不足时返回None
        """
        if len(data) < window:
            return None
        return sum(data[-window:]) / window
    
    def _sync_position(self) -> Optional[Dict]:
        """
        同步持仓信息
        
        返回:
            持仓信息字典，无持仓时返回None
        """
        if not self.connect_trader:
            return None
            
        try:
            positions = self.trader.get_positions()
            stock_code_base = self.stock_code.split('.')[0] if self.stock_code else None
            
            for pos in positions:
                if pos.get('stock_code') == stock_code_base:
                    return pos
                    
        except Exception as e:
            self.log(f"获取持仓信息失败: {e}", "WARNING")
            
        return None
    
    def _update_position_state(self, position: Optional[Dict], current_price: float):
        """
        更新持仓状态
        
        参数:
            position: 持仓信息
            current_price: 当前价格
        """
        if position and float(position.get('volume', 0)) > 0:
            self.holding = True
            # 首次持仓时记录入场价格
            if self.entry_price == 0:
                self.entry_price = float(position.get('price', current_price))
                self.entry_time = time.time()
                self.log(f"检测到持仓，入场价: {self.entry_price:.2f}")
        else:
            self.holding = False
            self.entry_price = 0.0
            self.entry_time = None
    
    def _check_cross_signal(
        self, 
        short_ma: float, 
        long_ma: float, 
        prev_short_ma: float, 
        prev_long_ma: float
    ) -> Tuple[bool, bool]:
        """
        检测均线交叉信号
        
        返回:
            (金叉, 死叉)
        """
        golden_cross = prev_short_ma <= prev_long_ma and short_ma > long_ma
        death_cross = prev_short_ma >= prev_long_ma and short_ma < long_ma
        return golden_cross, death_cross
    
    def _check_stop_conditions(self, current_price: float) -> Tuple[bool, str]:
        """
        检查止损止盈条件
        
        返回:
            (是否触发, 触发原因)
        """
        if not self.holding or self.entry_price == 0:
            return False, ""
        
        # 计算盈亏比例
        profit_ratio = (current_price - self.entry_price) / self.entry_price
        
        # 止损检查
        if self.stop_loss > 0 and profit_ratio < -self.stop_loss:
            return True, f"止损(设定{self.stop_loss*100:.1f}%, 实际{profit_ratio*100:.2f}%)"
        
        # 止盈检查
        if self.take_profit > 0 and profit_ratio > self.take_profit:
            return True, f"止盈(设定{self.take_profit*100:.1f}%, 实际{profit_ratio*100:.2f}%)"
        
        return False, ""
    
    def _execute_buy(self, price: float):
        """执行买入操作"""
        self.log(f"【买入信号】价格: {price:.2f}, 数量: {self.quantity}")
        
        if self.connect_trader:
            try:
                self.trader.buy(self.stock_code, price=price, amount=self.quantity)
                self.holding = True
                self.entry_price = price
                self.entry_time = time.time()
                self.log(f"买入成功", "INFO")
            except Exception as e:
                self.log(f"买入失败: {e}", "ERROR")
        else:
            # 模拟交易
            self.holding = True
            self.entry_price = price
            self.entry_time = time.time()
    
    def _execute_sell(self, price: float, reason: str):
        """执行卖出操作"""
        profit = (price - self.entry_price) / self.entry_price * 100 if self.entry_price > 0 else 0
        self.log(
            f"【卖出信号】原因: {reason}, 价格: {price:.2f}, "
            f"数量: {self.quantity}, 盈亏: {profit:+.2f}%"
        )
        
        if self.connect_trader:
            try:
                self.trader.sell(self.stock_code, price=price, amount=self.quantity)
                self.holding = False
                self.entry_price = 0.0
                self.entry_time = None
                self.log(f"卖出成功", "INFO")
            except Exception as e:
                self.log(f"卖出失败: {e}", "ERROR")
        else:
            # 模拟交易
            self.holding = False
            self.entry_price = 0.0
            self.entry_time = None
    
    def run(self):
        """策略主循环"""
        task_id = self.data.get('id', 0)
        
        # 解析股票信息
        self.stock_code, self.sina_symbol = self._parse_stock_info()
        if not self.stock_code or not self.sina_symbol:
            self.log(f"任务({task_id}): 股票代码解析失败", "ERROR")
            return
        
        self.log(
            f"任务({task_id}): 趋势策略启动\n"
            f"  股票: {self.stock_code}\n"
            f"  均线: MA{self.short_window}/MA{self.long_window}\n"
            f"  K线周期: {self.timeframe}分钟\n"
            f"  交易数量: {self.quantity}\n"
            f"  止损: {self.stop_loss*100:.1f}% | 止盈: {self.take_profit*100:.1f}%"
        )
        
        # 主循环
        error_count = 0
        max_errors = 5
        
        while self.running:
            try:
                # 1. 获取K线数据
                datalen = self.long_window + 10  # 多获取一些数据以确保计算准确
                closes = self.fetch_kline(self.sina_symbol, scale=self.timeframe, datalen=datalen)
                
                if not closes or len(closes) < self.long_window + 1:
                    self.log(f"K线数据不足，需要{self.long_window + 1}条，实际{len(closes)}条", "WARNING")
                    time.sleep(self.interval)
                    continue
                
                current_price = closes[-1]
                
                # 2. 计算技术指标
                short_ma = self.calculate_ma(closes, self.short_window)
                long_ma = self.calculate_ma(closes, self.long_window)
                prev_short_ma = self.calculate_ma(closes[:-1], self.short_window)
                prev_long_ma = self.calculate_ma(closes[:-1], self.long_window)
                
                if None in (short_ma, long_ma, prev_short_ma, prev_long_ma):
                    self.log("均线计算失败", "WARNING")
                    time.sleep(self.interval)
                    continue
                
                self.log(
                    f"价格: {current_price:.2f} | "
                    f"MA{self.short_window}: {short_ma:.2f} | "
                    f"MA{self.long_window}: {long_ma:.2f}"
                )
                
                # 3. 同步持仓状态
                position = self._sync_position()
                self._update_position_state(position, current_price)
                
                # 4. 检测交易信号
                golden_cross, death_cross = self._check_cross_signal(
                    short_ma, long_ma, prev_short_ma, prev_long_ma
                )
                
                # 5. 执行交易逻辑
                if not self.holding and golden_cross:
                    # 买入信号
                    self._execute_buy(current_price)
                    
                elif self.holding:
                    # 检查卖出条件
                    should_sell = False
                    sell_reason = ""
                    
                    # 死叉信号
                    if death_cross:
                        should_sell = True
                        sell_reason = "死叉"
                    
                    # 止损止盈
                    stop_triggered, stop_reason = self._check_stop_conditions(current_price)
                    if stop_triggered:
                        should_sell = True
                        sell_reason = stop_reason
                    
                    if should_sell:
                        self._execute_sell(current_price, sell_reason)
                
                # 重置错误计数
                error_count = 0
                
            except Exception as e:
                error_count += 1
                self.log(f"策略执行异常({error_count}/{max_errors}): {e}", "ERROR")
                
                if error_count >= max_errors:
                    self.log(f"连续错误次数过多，策略停止", "ERROR")
                    break
                    
                import traceback
                traceback.print_exc()
            
            # 等待下一轮
            time.sleep(self.interval)
