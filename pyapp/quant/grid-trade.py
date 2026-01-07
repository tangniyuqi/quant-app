import os
import json
import time 
import random
# import logging
import requests
import threading
from urllib.parse import urljoin, urlencode
from datetime import datetime, timedelta, time as dt_time
import pandas as pd
import tushare as ts
from strategyease_sdk import Client
from strategyease_sdk.client import MediaType

# 量化平台配置接口
CONFIG_BASE_PATH = 'http://47.98.178.188:8888/'
TRADE_RECORD_API = 'quant/tradeRecord/createPublic'
ACCOUNT_API = 'quant/account/getAccountPublic'
ACCOUNT_API_PARAMS = {
    'id': 10002
}

# 股票配置
STOCKS = {
    # '300891.SZ': {
    #     'name': '惠云钛业',      # 股票名称
    #     'only_sell': False,     # 只卖不买，默认False
    #     'grid_percent': 0.02,   # 网格间距（普通2%，牛市3-5%，熊市1%）
    #     'grid_layers': 5,       # 网格层数配置，1-10，默认5
    #     'base_volume': 100,     # 基础交易股数，0则默认为BASE_VOLUME
    #     'volume_calc': False,   # 交易量计算，默认 False: 固定量购买，True: 网格倍数购买 
    #     'max_hold': 5000,       # 最大持仓量(股)
    #     'current_hold': 0,      # 当前持仓
    #     'avg_cost': 0,          # 持仓平均成本
    #     'grid_levels': {},      # 网格层级(自动生成)
    #     'base_price': None,     # 基准价(自动获取)
    #     'stop_loss': -0.08,     # 止损比例(普通-8%，牛市-10%，熊市-5%）
    #     'use_open_price': True, # 是否使用开盘价作为基准，否则使用前收盘价
    #     'max_resets': 3,        # 最大重置次数
    #     'reset_ratio': 0.5      # 重置阈值比例（0.5=网格间距的50%）
    # }
    '002741.SZ': {
        'name': '光华科技',
        'only_sell': False,
        'grid_percent': 0.03,
        'grid_layers': 5,
        'base_volume': 200,
        'volume_calc': False,
        'max_hold': 500,
        'current_hold': 0,
        'avg_cost': 0,
        'grid_levels': {},
        'base_price': None,
        'stop_loss': -0.08,
        'use_open_price': True,
        'max_resets': 0,
        'reset_ratio': 0.5
    },
    '603386.SH': {
        'name': '骏亚科技',
        'only_sell': False,
        'grid_percent': 0.03,
        'grid_layers': 5,
        'base_volume': 200,
        'volume_calc': False,
        'max_hold': 1500,
        'current_hold': 0,
        'avg_cost': 0,
        'grid_levels': {},
        'base_price': None,
        'stop_loss': -0.08,
        'use_open_price': True,
        'max_resets': 0,
        'reset_ratio': 0.5
    }
}

# 程序运行标志
RUNNING = True

# 日志配置
# logging.basicConfig(level=logging.WARNING)

# 创建锁
lock = threading.Lock()

# 交易状态保存目录
STATE_DIR = 'trading'
os.makedirs(STATE_DIR, exist_ok=True)

# 交易记录结构定义
TRADE_LOG = []

def get_config():
    """获取配置信息"""
    try:
        url = f"{urljoin(CONFIG_BASE_PATH, ACCOUNT_API)}?{urlencode(ACCOUNT_API_PARAMS)}"
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"获取配置信息失败: {e}")
        return None

def load_config():
    """加载配置信息并设置全局参数"""
    global CONFIG
    global TRADING_CHECK_INTERVAL, STOCK_MONITOR_INTERVAL, HOLDINGS_CHECK_INTERVAL
    global MARKET_CHECK_INTERVAL, VOLUME_CALC, BASE_VOLUME, MIN_VOLUME, MAX_VOLUME
    global client, WEBHOOK_URL, pro
    
    CONFIG = get_config()

    if CONFIG and CONFIG['code'] == 0:
        data = CONFIG['data']

        # 交易基本参数配置
        TRADING_CHECK_INTERVAL = data['strategy']['trading_check_interval']
        STOCK_MONITOR_INTERVAL = data['strategy']['stock_monitor_interval']
        HOLDINGS_CHECK_INTERVAL = data['strategy']['holdings_check_interval']
        MARKET_CHECK_INTERVAL = data['strategy']['market_check_interval']

        # 股票基本参数配置
        VOLUME_CALC = bool(data['strategy']['volume_calc'])
        BASE_VOLUME = data['strategy']['base_volume']
        MIN_VOLUME = data['strategy']['min_volume']
        MAX_VOLUME = data['strategy']['max_volume']

        # 自动化实盘交易接口配置
        client = Client(host=data['config']['host'], port=int(data['config']['port']), key=data['config']['key'], client=data['config']['client'])

        # 消息推送配置
        WEBHOOK_URL = data['config']['webhook_url']

        # 初始化TS数据接口
        ts.set_token(data['config']['data_token'])
        pro = ts.pro_api()
        
        print("【配置加载成功】")
        return data
    else:
        error_msg = "获取配置信息失败，程序无法启动"
        print(error_msg)
        send_feishu_message('⚠️ 配置异常', error_msg, 'red')
        return None

def save_trading_state():
    """保存交易状态到文件"""
    state = {
        "stocks": STOCKS,
        "trade_log": TRADE_LOG,
        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    with open(f"{STATE_DIR}/trading_state.json", "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    print(f"交易状态已保存至文件！")

def send_feishu_message(title, content, color='green'):
    """发送飞书消息"""
    headers = {'Content-Type': 'application/json'}
    message = {
        "msg_type": "interactive",
        "card": {
            "elements": [{
                "tag": "div",
                "text": {"content": content, "tag": "lark_md"}
            }],
            "header": {
                "title": {"content": title, "tag": "plain_text"},
                "template": color
            }
        }
    }

    try:
        requests.post(WEBHOOK_URL, headers=headers, data=json.dumps(message))
    except Exception as e:
        print(f"飞书消息发送失败: {e}")

def is_trading_time():
    """精确检查交易时段"""
    now = datetime.now()
    current = now.time()
    
    MORNING_START = dt_time(9, 25, 0)
    MORNING_END = dt_time(11, 30, 0)
    AFTERNOON_START = dt_time(13, 0, 0)
    AFTERNOON_END = dt_time(15, 0, 0)

    return (
        (MORNING_START <= current <= MORNING_END) or
        (AFTERNOON_START <= current < AFTERNOON_END)
    )

def get_base_price(ts_code, use_open_price=False):
    """获取基准价"""
    global RUNNING
    while RUNNING:
        if not is_trading_time():
            print(f"⚠️ 现在不是交易时间，请等待...")
            time.sleep(TRADING_CHECK_INTERVAL)
            continue

        try:
            if use_open_price:
                df = ts.realtime_quote(ts_code)
                if df is not None and not df.empty:
                    open_price = float(df.iloc[0]['OPEN'])
                    if open_price > 0:
                        return open_price
                    print(f"{STOCKS[ts_code]['name']}({ts_code}) 开盘价为0，尝试获取前收盘价")
            
            # 获取前收盘价
            df = pro.daily(ts_code=ts_code, start_date=(datetime.now() - timedelta(days=10)).strftime('%Y%m%d'))
            return float(df.iloc[0]['close']) if not df.empty else None
        except Exception as e:
            error_msg = f"获取 {STOCKS[ts_code]['name']} 基准价失败: {e}"
            print(error_msg)
            send_feishu_message('⚠️ 数据异常', error_msg, 'red')
            return None

# ==================== 核心交易逻辑 ====================
def init_grids(force_reset=False):
    """初始化网格"""
    for ts_code in STOCKS:
        stock = STOCKS[ts_code]

        if not 0.1 <= stock['reset_ratio'] <= 1.0:
            raise ValueError(f"{stock['name']}({ts_code})的reset_ratio必须在0.1到1.0之间")
        if not 1 <= stock['grid_layers'] <= 10:
            raise ValueError(f"{stock['name']}({ts_code})的grid_layers必须在1到10之间")

        # base_price = stock['base_price'] or get_base_price(ts_code, stock['use_open_price'])

        if force_reset or stock['base_price'] is None:
            base_price = get_base_price(ts_code, stock['use_open_price'])
        else:
            base_price = stock['base_price']

        if base_price is None:
            print(f"⚠️ {stock['name']}({ts_code}) 基准价获取失败，跳过初始化")
            continue

        stock['base_price'] = base_price
        only_sell = stock.get('only_sell', True)
        stock['grid_levels'] = {}
        grid_percent = stock['grid_percent']
        max_resets = stock.get('max_resets', 3)
        reset_ratio = stock.get('reset_ratio', 0.5)
        grid_layers = stock.get('grid_layers', 5)
        base_volume = stock.get('base_volume', 0) if stock.get('base_volume', 0) > 0 else BASE_VOLUME

        for i in range(1, grid_layers + 1):
            # 计单网格单元交易量
            volume = min(base_volume * i, MAX_VOLUME) if stock.get('volume_calc', VOLUME_CALC) else base_volume

            # 生成买入网格
            buy_price = round(base_price * (1 - grid_percent) ** i, 2)
            stock['grid_levels'][buy_price] = {
                'action': 'buy',
                'executed': False,
                'volume': volume,
                'reset_count': 0,
                'max_resets': max_resets,
                'reset_threshold': round(buy_price * (1 + reset_ratio * grid_percent), 2)
            }

            # 生成卖出网格
            sell_price = round(base_price * (1 + grid_percent) ** i, 2)
            stock['grid_levels'][sell_price] = {
                'action': 'sell',
                'executed': False,
                'volume': volume,
                'reset_count': 0,
                'max_resets': max_resets,
                'reset_threshold': round(sell_price * (1 - reset_ratio * grid_percent), 2)
            }

        source = '开盘价' if stock['use_open_price'] else '前收盘价'
        msg = (f"{stock['name']}({ts_code}) 数据初始化完成\n"
               f"基准源: {source}\n"
               f"基准价: {base_price}\n"
               f"只卖不买: {only_sell}\n"
               f"网格层数: {grid_layers}层\n"
               f"网格间距: {grid_percent*100}%\n"
               f"基易股数: {base_volume}\n"
               f"最大持仓: {stock['max_hold']} 股\n"
               f"当前持仓: {stock['current_hold']} 股\n"
               f"强制止损: {stock['stop_loss']*100}%\n"
               f"买入网格: {[p for p in stock['grid_levels'] if stock['grid_levels'][p]['action']=='buy']}\n"
               f"卖出网格: {[p for p in stock['grid_levels'] if stock['grid_levels'][p]['action']=='sell']}\n"
               f"重置策略: 阈值={reset_ratio*100}%间距, 最大重置={max_resets}次")

        print(msg)
        send_feishu_message(f"📊 {stock['name']}({ts_code}) 数据初始化", msg, 'blue')

def execute_trade(ts_code, action, price, stock_info, reason=''):
    """执行交易"""
    grid = stock_info['grid_levels'].get(price, None)
    if not grid or grid['executed']:
        return

    # 检查是否只卖不买
    if action == 'buy' and stock_info.get('only_sell', False):
        return

    # 计算实际交易量
    volume = grid['volume']
    if action == 'buy':
        volume = min(volume, stock_info['max_hold'] - stock_info['current_hold'])
    else:
        volume = min(volume, stock_info['current_hold'])

    if volume < MIN_VOLUME:
        return
    
    # API方式交易
    # trade_api(ts_code, action.upper(), price, volume)

    symbol = ts_code.split('.')[0]
    
    if action == 'buy':
        client.buy(symbol=symbol, price=price, amount=volume, type='LIMIT')
        stock_info['current_hold'] += volume
        if stock_info['current_hold'] == volume:  # 首次买入
            stock_info['avg_cost'] = price
        else:
            total_cost = stock_info['avg_cost'] * stock_info['current_hold'] + price * volume
            stock_info['avg_cost'] = total_cost / (stock_info['current_hold'] + volume)
    else:
        client.sell(symbol=symbol, price=price, amount=volume, type='LIMIT')
        stock_info['current_hold'] -= volume
        if stock_info['current_hold'] == 0:
            stock_info['avg_cost'] = 0

    grid['executed'] = True

    # 记录交易
    log_trade(ts_code, price, volume, action, reason)

    # 保存最新状态
    save_trading_state()

    # 发送通知
    profit = (price - stock_info['avg_cost']) * volume if action == 'sell' else 0
    msg = (f"股票: {stock_info['name']}({ts_code})\n"
           f"操作: {'买入' if action == 'buy' else '卖出'}\n"
           f"价格: {price}\n数量: {volume}\n"
           f"持仓: {stock_info['current_hold']}\n成本: {stock_info['avg_cost']:.2f}")
    if profit != 0:
        msg += f"\n{'盈利' if profit > 0 else '亏损'}: {abs(profit):.2f}"
    send_feishu_message(f"{'✅' if profit >=0 else '⚠️'} 交易执行", msg, 'green' if profit >=0 else 'yellow')

def log_trade(ts_code, price, volume, direction, reason):
    """记录交易并发送到远程接口"""
    global TRADE_LOG

    trade_data = {
        "member_id": CONFIG.get('member_id'),
        "account_id": CONFIG.get('id'),
        "strategy_id": CONFIG.get('strategy_id'),
        "traded_at": datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ'),
        "direction": direction,
        "type": "add",
        "symbol": ts_code,
        "price": price,
        "volume": volume,
        "amount": price * volume
    }

    TRADE_LOG.append(trade_data)

    url = urljoin(CONFIG_BASE_PATH, TRADE_RECORD_API)
    headers = {'Content-Type': 'application/json'}
    try:
        response = requests.post(url, headers=headers, data=json.dumps(trade_data))
        response.raise_for_status()
        print(f"交易记录已发送到远程接口，状态码: {response.status_code}")
    except requests.RequestException as e:
        error_msg = f"发送交易记录到远程接口失败: {e}"
        print(error_msg)
        send_feishu_message('⚠️ 交易记录发送异常', error_msg, 'red')

# ==================== 监控与风控 ====================
def check_stop_loss(ts_code, current_price):
    """止损检查"""
    stock = STOCKS[ts_code]
    if stock['current_hold'] > 0 and stock['avg_cost'] > 0:
        profit_pct = (current_price - stock['avg_cost']) / stock['avg_cost']
        if profit_pct <= stock['stop_loss']:
            execute_trade(ts_code, 'sell', current_price, stock, 'stop_loss')
            return True
    return False

def grid_trading(tick_data):
    """执行网格交易（含动态重置逻辑）"""
    ts_code = tick_data['ts_code']
    current_price = tick_data['price']
    stock_info = STOCKS[ts_code]

    # 检查止损
    if check_stop_loss(ts_code, current_price):
        return

    # 遍历排序后的网格层级
    for price in sorted(stock_info['grid_levels'].keys()):
        grid = stock_info['grid_levels'][price]
        price = float(price)
        
        # --- 重置条件检查 ---
        if grid['executed']:
            if ((grid['action'] == 'buy' and current_price > grid['reset_threshold']) or \
                (grid['action'] == 'sell' and current_price < grid['reset_threshold'])) and \
                grid['reset_count'] < grid['max_resets']:
                
                grid['executed'] = False
                grid['reset_count'] += 1
                print(f"{stock_info['name']}({ts_code}) {price}层级重置({grid['reset_count']}/{grid['max_resets']})")
                
                # 保存状态变更
                save_trading_state()
            continue

        # --- 正常触发检查 ---
        if (grid['action'] == 'buy' and current_price <= price) or \
           (grid['action'] == 'sell' and current_price >= price):
            execute_trade(ts_code, grid['action'], price, stock_info, 'grid_trading')
            grid['executed'] = True

def monitor_stock(ts_code):
    """监控股票行情"""
    global RUNNING
    while RUNNING:
        if not is_trading_time():
            time.sleep(TRADING_CHECK_INTERVAL)
            continue

        tick_data = get_realtime_tick(ts_code)
        if tick_data:
            with lock:
                # 计算涨跌幅百分比
                base_price = STOCKS[ts_code]['base_price']
                current_price = tick_data['price']
                if base_price:
                    percent = ((current_price - base_price) / base_price) * 100
                    percent_str = f"{percent:.2f}%"
                else:
                    percent_str = 'N/A'

                print(f"{STOCKS[ts_code]['name']}({ts_code}) 价格: {tick_data['price']} 浮动: {percent_str} (基准价: {STOCKS[ts_code]['base_price']}) 时间: {tick_data['time']}")
            grid_trading(tick_data)
        time.sleep(STOCK_MONITOR_INTERVAL)        

def get_realtime_tick(ts_code):
    """获取实时Tick数据"""
    try:
        time.sleep(random.randint(0, 3))
        df = ts.realtime_quote(ts_code)

        if df is not None and not df.empty:
            return {
                'ts_code': ts_code,
                'time': datetime.now().strftime('%H:%M:%S'),
                'price': float(df.iloc[0]['PRICE']),
                'bid': float(df.iloc[0]['B1_P']),
                'ask': float(df.iloc[0]['A1_P']),
                'volume': int(df.iloc[0]['VOLUME'])
            }
    except Exception as e:
        error_msg = f"获取 {STOCKS[ts_code]['name']}({ts_code}) 实时数据失败: {e}"
        print(error_msg)
        send_feishu_message('⚠️ 数据获取异常', error_msg, 'red')
    return None

def check_holdings_and_cost():
    """检查实际持仓与平均成本"""
    while RUNNING:
        if is_trading_time():
            try:
                portfolio = client.get_portfolio(media_type=MediaType.JOIN_QUANT)

                account = '\n【📈 账户基本信息】\n'
                account += f"余额：{portfolio.get('balanceCash', 0)}，\n"
                account += f"可取：{portfolio.get('availableCash', 0)}，\n"
                account += f"冻结：{portfolio.get('frozenCash', 0)}，\n"
                account += f"总资产：{portfolio.get('totalValue', 0)}\n"
                print(account)
                
                for ts_code in STOCKS:
                    symbol = ts_code.split('.')[0]
                    position = portfolio.get('positions', {}).get(symbol, None) 
                    if position:
                        STOCKS[ts_code]['current_hold'] = position.get('totalAmount', 0)
                        STOCKS[ts_code]['avg_cost'] = position.get('costPrice', 0)
                        save_trading_state()
                        print(f"{STOCKS[ts_code]['name']}({ts_code}) 持仓更新: {STOCKS[ts_code]['current_hold']}股, 成本价 {STOCKS[ts_code]['avg_cost']}")
                    else:
                        if STOCKS[ts_code]['current_hold'] != 0:
                            STOCKS[ts_code]['current_hold'] = 0
                            STOCKS[ts_code]['avg_cost'] = 0
                            save_trading_state()
                            print(f"{STOCKS[ts_code]['name']}({ts_code}) 无持仓记录，已重置为0")
            
            except Exception as e:
                error_msg = f"{STOCKS[ts_code]['name']}({ts_code}) 持仓信息更新失败: {e}"
                print(error_msg)
                send_feishu_message('⚠️ 持仓更新异常', error_msg, 'red')

        time.sleep(HOLDINGS_CHECK_INTERVAL)

def check_market_close():
    """收盘检查"""
    global RUNNING
    while RUNNING:
        now = datetime.now()
        if now.hour >= 15:
            RUNNING = False

            title = '🕒 交易停止（超过15:00）'
            report = '📈 当日交易总结\n'
            report += f"总交易次数: {len(TRADE_LOG)}\n"
            report += '最终持仓:\n'
            for ts_code in STOCKS:
                stock = STOCKS[ts_code]
                report += f"- {stock['name']}: {stock['current_hold']}股, 成本 {stock['avg_cost']:.2f}\n"
            send_feishu_message(title, report, 'red')
            print(title)

            # 保存最终状态
            save_trading_state()
            break
        time.sleep(MARKET_CHECK_INTERVAL)

# ==================== 主函数 ====================
def main():
    """主函数"""
    global RUNNING
    
    # 加载配置
    config = load_config()

    if not config:
        print("程序因配置错误退出")
        return 1  # 返回错误码
    
    # 检查是否需要重新初始化网格（首次启动或基准价缺失）
    force_reset = False
    for ts_code in STOCKS:
        if STOCKS[ts_code]['base_price'] is None:
            force_reset = True
            break
    
    # 初始化网格
    init_grids(force_reset=force_reset)

    # 启动通知
    title = '🚀 自动化交易系统已启动'
    stock_list = "\n".join([f"{v['name']}({k})" for k,v in STOCKS.items()])
    print(f"{title}")
    send_feishu_message(f"{title}", f"监控以下股票:\n{stock_list}", 'blue')

    # 启动监控股票行情线程
    threads = []
    for ts_code in STOCKS:
        t = threading.Thread(target=monitor_stock, args=(ts_code,))
        t.daemon = True
        threads.append(t)
        t.start()

    # 启动检查持仓和成本线程
    holdings_thread = threading.Thread(target=check_holdings_and_cost)
    holdings_thread.daemon = True
    holdings_thread.start()

    # 启动收盘检查线程
    close_thread = threading.Thread(target=check_market_close)
    close_thread.daemon = True
    close_thread.start()

    # 手动停止
    try:
        while RUNNING:
            time.sleep(1)
    except KeyboardInterrupt:
        RUNNING = False
        title = '🛑 策略停止（手动停止）'
        msg = '后持仓情况:\n' + '\n'.join(
            f"{v['name']}({k}): 持仓{v['current_hold']}股, 成本{v['avg_cost']:.2f}"
            for k,v in STOCKS.items()
        )
        print(title)
        send_feishu_message(title, msg, 'red')
    finally:
        save_trading_state()
        print('交易记录已保存至管理后台！')

if __name__ == '__main__':
    main()  