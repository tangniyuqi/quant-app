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
import datetime
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
        self.signal_type = config.get('signalType', 'MA')
        
        if self.signal_type == 'MACD':
            # MACD 模式：快线(12)、慢线(26)、信号线(9)
            self.macd_fast_period = int(config.get('macdFastPeriod', 12))
            self.macd_slow_period = int(config.get('macdSlowPeriod', 26))
            self.macd_signal_period = int(config.get('macdSignalPeriod', 9))
            
            # 为了兼容性或避免未定义错误，给 MA 参数赋默认值
            self.ma_short_period = 5
            self.ma_long_period = 20
        else:
            # MA 模式：短期(5)、长期(20)
            self.ma_short_period = int(config.get('maShortPeriod', 5))
            self.ma_long_period = int(config.get('maLongPeriod', 20))
            
            # 为了兼容性或避免未定义错误，给 MACD 参数赋默认值
            self.macd_fast_period = 12
            self.macd_slow_period = 26
            self.macd_signal_period = 9
        
        # 交易参数
        self.quantity = int(config.get('quantity', 100))
        self.stop_loss = float(config.get('stopLoss', 0)) / 100.0
        self.take_profit = float(config.get('takeProfit', 0)) / 100.0
        self.trade_direction = int(config.get('tradeDirection', 0))
        self.trade_mode = config.get('tradeMode', 'quantity')
        self.amount = float(config.get('amount', 10000))
        self.ratio = float(config.get('ratio', 5)) / 100.0
        
        # 运行参数
        self.timeframe = int(config.get('timeframe') or 240)  # K线周期
        
        # 高级设置
        self.ignore_trading_time = bool(config.get('ignoreTradingTime', False))
        self.enable_real_trade = bool(config.get('enableRealTrade', True))
        self.monitor_interval = int(config.get('monitorInterval', 60))

        # 任务有效期
        self.expiration_time = None
        validity_period = config.get('validityPeriod')
        if validity_period:
            try:
                if isinstance(validity_period, str):
                    dt = datetime.datetime.strptime(validity_period[:10], "%Y-%m-%d")
                    self.expiration_time = dt.replace(hour=15, minute=0, second=0, microsecond=0)
            except Exception as e:
                self.log(f"任务({self.data.get('id', 0)})：无效的有效期格式 {validity_period}: {e}", "ERROR")
        
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
        if self.signal_type == 'MACD':
            if self.macd_fast_period >= self.macd_slow_period:
                self.log(
                    f"配置错误: MACD快慢周期({self.macd_fast_period}/{self.macd_slow_period})设置不合理(快线需小于慢线)，"
                    f"已重置为默认值 12/26", 
                    "WARNING"
                )
                self.macd_fast_period = 12
                self.macd_slow_period = 26
            
            if self.macd_signal_period < 1:
                self.log(f"配置错误: MACD信号线周期({self.macd_signal_period})必须大于等于1，已重置为9", "WARNING")
                self.macd_signal_period = 9

        elif self.signal_type == 'MA':
            if self.ma_short_period >= self.ma_long_period:
                self.log(
                    f"配置错误: MA短长周期({self.ma_short_period}/{self.ma_long_period})设置不合理(短期需小于长期)，"
                    f"已重置为默认值 5/20", 
                    "WARNING"
                )
                self.ma_short_period = 5
                self.ma_long_period = 20

        if self.signal_type not in ["MA", "MACD"]:
            self.log(f"配置错误: 信号方式({self.signal_type})无效，已重置为MA", "WARNING")
            self.signal_type = "MA"
            # 重置为 MA 后再次校验 MA 参数
            if self.ma_short_period >= self.ma_long_period:
                 self.ma_short_period = 5
                 self.ma_long_period = 20
            
        if self.quantity < 100:
            self.log(f"交易数量({self.quantity})小于最小值100，已调整为100", "WARNING")
            self.quantity = 100
            
        if self.monitor_interval < 5:
            self.log(f"轮询间隔({self.monitor_interval}秒)过短，已调整为5秒", "WARNING")
            self.monitor_interval = 5
        
        if self.stop_loss < 0 or self.stop_loss > 1:
            self.log(f"止损比例({self.stop_loss * 100:.2f}%)超出范围，已重置为0", "WARNING")
            self.stop_loss = 0
        
        if self.take_profit < 0 or self.take_profit > 10:
            self.log(f"止盈比例({self.take_profit * 100:.2f}%)超出范围，已重置为0", "WARNING")
            self.take_profit = 0
        
        valid_timeframes = {5, 15, 30, 60, 240, 1200, 7200}
        if self.timeframe not in valid_timeframes:
            self.log(f"K线周期({self.timeframe})无效，已重置为240", "WARNING")
            self.timeframe = 240
        
        if self.trade_direction not in [0, 1, 2]:
            self.log(f"交易方向({self.trade_direction})无效，已重置为双向", "WARNING")
            self.trade_direction = 0
        
        if self.trade_mode not in ["quantity", "amount", "ratio"]:
            self.log(f"仓位控制方式({self.trade_mode})无效，已重置为固定股数", "WARNING")
            self.trade_mode = "quantity"
        
        if self.amount < 0:
            self.log(f"交易金额({self.amount})无效，已重置为10000", "WARNING")
            self.amount = 10000
        
        if self.ratio < 0 or self.ratio > 1:
            self.log(f"仓位比例({self.ratio * 100:.2f}%)无效，已重置为5%", "WARNING")
            self.ratio = 0.05
            
    def _init_position_state(self):
        """初始化持仓状态"""
        self.holding = False
        self.entry_price = 0.0
        self.entry_time = None
        self.last_trade_time = 0.0
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
            scale: K线周期 (5, 15, 30, 60, 240=日线, 1200=周线, 7200=月线)
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
    
    def calculate_ma(self, data: List[float], period: int) -> Optional[float]:
        """
        计算简单移动平均线
        
        参数:
            data: 价格数据列表
            period: 窗口大小
            
        返回:
            均线值，数据不足时返回None
        """
        if len(data) < period:
            return None
        return sum(data[-period:]) / period
    
    def calculate_ema_series(self, data: List[float], period: int) -> List[float]:
        """
        计算指数移动平均线序列
        """
        if len(data) < period:
            return []
        k = 2 / (period + 1)
        ema = sum(data[:period]) / period
        series = [ema]
        for price in data[period:]:
            ema = price * k + ema * (1 - k)
            series.append(ema)
        return series
    
    def calculate_macd(
        self, 
        data: List[float], 
        fast_period: int, 
        slow_period: int, 
        signal_period: int
    ) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
        short_series = self.calculate_ema_series(data, fast_period)
        long_series = self.calculate_ema_series(data, slow_period)
        if not short_series or not long_series:
            return None, None, None, None
        
        min_len = min(len(short_series), len(long_series))
        short_series = short_series[-min_len:]
        long_series = long_series[-min_len:]
        diff_series = [s - l for s, l in zip(short_series, long_series)]
        dea_series = self.calculate_ema_series(diff_series, signal_period)
        if not dea_series:
            return None, None, None, None
        
        diff = diff_series[-1]
        prev_diff = diff_series[-2] if len(diff_series) >= 2 else None
        dea = dea_series[-1]
        prev_dea = dea_series[-2] if len(dea_series) >= 2 else None
        return diff, dea, prev_diff, prev_dea
    
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
        # API 延迟保护：如果刚买入（60秒内），且 API 未返回持仓，暂时信任本地状态
        if self.holding and self.entry_time and (time.time() - self.entry_time < 60):
            if not position or float(position.get('volume', 0)) <= 0:
                self.log("API未同步持仓，保持本地持仓状态", "INFO")
                return

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
    
    def _calculate_trade_quantity(self, direction: str, current_price: float, position: Optional[Dict] = None) -> int:
        if current_price <= 0:
            return 0
        
        if not self.connect_trader:
            if direction == 'buy' and self.trade_mode == 'amount':
                return int(self.amount / current_price / 100) * 100 if self.amount > 0 else 0
            return self.quantity
        
        if direction == 'buy':
            balance = self.trader.get_balance()
            try:
                available_cash = float(balance.get('available_balance', 0) or 0)
            except Exception:
                available_cash = 0.0
            try:
                total_asset = float(balance.get('total_asset', 0) or 0)
            except Exception:
                total_asset = 0.0
            
            if self.trade_mode == 'quantity':
                quantity = self.quantity
                if quantity * current_price > available_cash:
                    quantity = int(available_cash / current_price / 100) * 100
            elif self.trade_mode == 'ratio':
                asset_base = total_asset if total_asset > 0 else available_cash
                target_amount = min(available_cash, asset_base * self.ratio)
                quantity = int(target_amount / current_price / 100) * 100
            else:
                target_amount = min(available_cash, self.amount)
                quantity = int(target_amount / current_price / 100) * 100
            
            return max(0, int(quantity))
        
        if position is None and self.stock_code:
            stock_code_base = self.stock_code.split('.')[0]
            position = self.trader.get_position(stock_code_base)
        
        if position:
            available = position.get('available_quantity', 0) or position.get('total_quantity', 0)
        else:
            available = 0
        return max(0, int(available))
    
    def _execute_buy(self, price: float, quantity: int):
        """执行买入操作"""
        self.log(f"【买入信号】价格: {price:.2f}, 数量: {quantity}")
        
        if self.connect_trader and self.enable_real_trade:
            try:
                self.trader.buy(self.stock_code, price=price, amount=quantity)
                self.holding = True
                self.entry_price = price
                self.entry_time = time.time()
                self.last_trade_time = time.time()
                self.log(f"买入成功", "INFO")
                self._save_trade_record("buy", price, quantity, "金叉")
            except Exception as e:
                self.log(f"买入失败: {e}", "ERROR")
        else:
            # 模拟交易或未开启实盘
            mode = "模拟" if not self.connect_trader else "实盘禁用"
            self.log(f"[{mode}] 执行虚拟买入", "INFO")
            self.holding = True
            self.entry_price = price
            self.entry_time = time.time()
            self.last_trade_time = time.time()
            self._save_trade_record("buy", price, quantity, "金叉")
    
    def _execute_sell(self, price: float, quantity: int, reason: str):
        """执行卖出操作"""
        profit = (price - self.entry_price) / self.entry_price * 100 if self.entry_price > 0 else 0
        self.log(
            f"【卖出信号】原因: {reason}, 价格: {price:.2f}, "
            f"数量: {quantity}, 盈亏: {profit:+.2f}%"
        )
        
        if self.connect_trader and self.enable_real_trade:
            try:
                self.trader.sell(self.stock_code, price=price, amount=quantity)
                self.holding = False
                self.entry_price = 0.0
                self.entry_time = None
                self.last_trade_time = time.time()
                self.log(f"卖出成功", "INFO")
                self._save_trade_record("sell", price, quantity, reason)
            except Exception as e:
                self.log(f"卖出失败: {e}", "ERROR")
        else:
            # 模拟交易或未开启实盘
            mode = "模拟" if not self.connect_trader else "实盘禁用"
            self.log(f"[{mode}] 执行虚拟卖出", "INFO")
            self.holding = False
            self.entry_price = 0.0
            self.entry_time = None
            self.last_trade_time = time.time()
            self._save_trade_record("sell", price, quantity, reason)

    def _save_trade_record(self, action, price, quantity, reason="trend_trade"):
        backend_url = self.data.get('backend_url')
        token = self.data.get('token')
        
        if not backend_url or not token:
            return

        if backend_url.endswith('/'):
            backend_url = backend_url[:-1]
            
        url = f"{backend_url}/quant/tradeRecord/createTradeRecord"
        
        stock_info = self.data.get('task', {}).get('stock', {})
        if isinstance(stock_info, str):
            try:
                stock_info = json.loads(stock_info)
            except Exception:
                stock_info = {}
        
        if not isinstance(stock_info, dict):
            stock_info = {}

        account = self.data.get('account', {})

        data = {
            "member_id": account.get('member_id'),
            "account_id": account.get('id'),
            "task_id": self.data.get('id'),
            "symbol": stock_info.get('ts_code', ''),
            "name": stock_info.get('name', ''),
            "price": float(price),
            "quantity": float(quantity),
            "amount": float(price) * float(quantity),
            "action": action, 
            "reason": reason,
            "traded_at": time.strftime('%Y-%m-%dT%H:%M:%S+08:00'),
        }
        
        headers = {
            "x-token": token,
            "Content-Type": "application/json"
        }
        
        try:
            requests.post(url, json=data, headers=headers, timeout=5)
            self.log("TRADE_RECORD_UPDATE_TRIGGER")
        except Exception:
            pass
    
    def _is_trading_time(self) -> bool:
        """判断当前是否为交易时间"""
        if self.ignore_trading_time:
            return True
            
        now = datetime.datetime.now()
        
        # 周末不交易
        if now.weekday() > 4:
            return False
            
        current = now.time()
        morning_start = datetime.time(9, 25, 0)
        morning_end = datetime.time(11, 30, 0)
        afternoon_start = datetime.time(13, 0, 0)
        afternoon_end = datetime.time(15, 0, 0)
        
        return (morning_start <= current < morning_end) or (afternoon_start <= current < afternoon_end)

    def run(self):
        """策略主循环"""
        task_id = self.data.get('id', 0)
        
        # 解析股票信息
        self.stock_code, self.sina_symbol = self._parse_stock_info()
        if not self.stock_code or not self.sina_symbol:
            self.log(f"任务({task_id}): 股票代码解析失败", "ERROR")
            return
        
        mode_str = "实盘交易" if self.enable_real_trade else "模拟演示 (仅日志)"
        if self.signal_type == "MACD":
            signal_desc = f"MACD({self.macd_fast_period}/{self.macd_slow_period}/{self.macd_signal_period})"
        else:
            signal_desc = f"MA{self.ma_short_period}/MA{self.ma_long_period}"
        direction_map = {0: "双向", 1: "只买", 2: "只卖"}
        trade_mode_map = {"quantity": "固定股数", "amount": "固定金额", "ratio": "按资金比例"}
        self.log(
            f"任务({task_id}): 趋势策略启动\n"
            f"  股票: {self.stock_code}\n"
            f"  信号方式: {signal_desc}\n"
            f"  K线周期: {self.timeframe}分钟\n"
            f"  交易数量: {self.quantity}\n"
            f"  止损: {self.stop_loss*100:.1f}% | 止盈: {self.take_profit*100:.1f}%\n"
            f"  交易方向: {direction_map.get(self.trade_direction, '双向')}\n"
            f"  仓位方式: {trade_mode_map.get(self.trade_mode, '固定股数')}\n"
            f"  冷却时间: {self.cooldown_seconds}秒\n"
            f"  运行模式: {mode_str}"
        )
        
        # 主循环
        error_count = 0
        max_errors = 5
        is_paused = False
        
        while self.running:
            try:
                # 0. 有效期检查
                if self.expiration_time and datetime.datetime.now() > self.expiration_time:
                    self.log(f"任务({task_id})有效期已至 ({self.expiration_time})，自动停止任务...", "WARNING")
                    from ..manager import TaskManager
                    TaskManager().stop_task(task_id)
                    break
                
                # 检查交易时间
                if not self._is_trading_time():
                    if not is_paused:
                        self.log(f"任务({task_id})非交易日期或时段，等待开盘...", "WARNING")
                        is_paused = True
                    time.sleep(10)
                    continue
                
                if is_paused:
                    self.log(f"任务({task_id})交易时间到达，恢复运行...", "INFO")
                    is_paused = False
                
                # 1. 获取K线数据
                if self.signal_type == "MACD":
                    required_len = max(self.macd_fast_period, self.macd_slow_period) + self.macd_signal_period + 5
                else:
                    required_len = self.ma_long_period + 1
                datalen = required_len + 10
                closes = self.fetch_kline(self.sina_symbol, scale=self.timeframe, datalen=datalen)
                
                if not closes or len(closes) < required_len:
                    self.log(f"K线数据不足，需要{required_len}条，实际{len(closes)}条", "WARNING")
                    time.sleep(self.monitor_interval)
                    continue
                
                current_price = closes[-1]
                
                # 2. 计算技术指标
                if self.signal_type == "MACD":
                    diff, dea, prev_diff, prev_dea = self.calculate_macd(
                        closes, self.macd_fast_period, self.macd_slow_period, self.macd_signal_period
                    )
                    if None in (diff, dea, prev_diff, prev_dea):
                        self.log("MACD计算失败", "WARNING")
                        time.sleep(self.monitor_interval)
                        continue
                    self.log(
                        f"价格: {current_price:.2f} | "
                        f"DIFF: {diff:.4f} | "
                        f"DEA: {dea:.4f}"
                    )
                    golden_cross, death_cross = self._check_cross_signal(
                        diff, dea, prev_diff, prev_dea
                    )
                else:
                    short_ma = self.calculate_ma(closes, self.ma_short_period)
                    long_ma = self.calculate_ma(closes, self.ma_long_period)
                    prev_short_ma = self.calculate_ma(closes[:-1], self.ma_short_period)
                    prev_long_ma = self.calculate_ma(closes[:-1], self.ma_long_period)
                    
                    if None in (short_ma, long_ma, prev_short_ma, prev_long_ma):
                        self.log("均线计算失败", "WARNING")
                        time.sleep(self.monitor_interval)
                        continue
                    
                    self.log(
                        f"价格: {current_price:.2f} | "
                        f"MA{self.ma_short_period}: {short_ma:.2f} | "
                        f"MA{self.ma_long_period}: {long_ma:.2f}"
                    )
                    golden_cross, death_cross = self._check_cross_signal(
                        short_ma, long_ma, prev_short_ma, prev_long_ma
                    )
                
                # 3. 同步持仓状态
                position = self._sync_position()
                self._update_position_state(position, current_price)
                
                # 4. 执行交易逻辑
                if not self.holding and golden_cross:
                    if self.trade_direction == 2:
                        self.log("交易方向限制(只卖)，跳过买入信号", "INFO")
                    else:
                        quantity = self._calculate_trade_quantity('buy', current_price, position)
                        if quantity < 100:
                            self.log(f"买入数量不足({quantity})，跳过本次信号", "WARNING")
                        else:
                            self._execute_buy(current_price, quantity)
                    
                elif self.holding:
                    # 检查卖出条件
                    should_sell = False
                    sell_reason = ""
                    
                    # 死叉信号
                    if death_cross:
                        # 卖出平仓通常不受方向限制，除非是做空策略的平仓。
                        # 对于现货，只买(1)也需要卖出平仓；只卖(2)本身就是只做卖出。
                        should_sell = True
                        sell_reason = "死叉"
                    
                    # 止损止盈
                    stop_triggered, stop_reason = self._check_stop_conditions(current_price)
                    if stop_triggered:
                        should_sell = True
                        sell_reason = stop_reason
                    
                    if should_sell:
                        # 卖出平仓不受冷却时间限制，防止无法止损
                        quantity = self._calculate_trade_quantity('sell', current_price, position)
                        if quantity <= 0:
                            self.log("卖出数量为0，跳过本次信号", "WARNING")
                        else:
                            self._execute_sell(current_price, quantity, sell_reason)
                
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
            time.sleep(self.monitor_interval)
