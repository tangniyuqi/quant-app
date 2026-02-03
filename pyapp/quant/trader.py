# -*- coding: utf-8 -*-
import time
import re
import urllib.request
import threading
import json
import requests
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from easytrader import remoteclient

class QuantTrader:
    _monitor_lock = threading.Lock()
    _monitors = {} # {account_id: {'stop_event': Event, 'thread': Thread, 'count': int}}

    def __init__(self, log_callback=None):
        self.log_callback = log_callback
        self.user = None

    def log(self, message, level='INFO'):
        print(f'[{level}] {message}')
        if self.log_callback:
            try:
                module = self.__class__.__name__
                self.log_callback(level, module, str(message))
            except Exception:
                pass

    def _create_client(self):
        '''
        创建交易客户端实例
        '''
        server_config = self.account.get('server', {}) 
        mode = server_config.get('type', 'easytrader-remote')
        client_type = server_config.get('client_type', 'universal_client')
        host = server_config.get('host', '127.0.0.1')
        port = int(server_config.get('port', 1430))

        if mode == 'easytrader':
            return easytrader.use(client_type)
        elif mode == 'easytrader-remote':
            return remoteclient.use(client_type, host=host, port=port)
        elif mode == 'strategyease': # 此处暂按 remoteclient 处理
            return remoteclient.use(client_type, host=host, port=port)
        else:
            return remoteclient.use(client_type, host=host, port=port)

    def connect(self, account, backend_url=None, token=None):
        '''
        连接交易账户 (远程客户端模式)
        '''
        self.account = account
        self.backend_url = backend_url
        self.token = token

        # 从账户配置解析配置
        server = account.get('server', {})
        self.webhook_url = server.get('webhook_url')
        self.webhook_type = server.get('webhook_type')
        
        # 使用 remoteclient 连接
        self.log(f'正在连接和验证服务器...')
        self.user = self._create_client()

        try:
            _ = self.user.balance
            self.log(f'服务器已连接成功。')
            # 初始化数据源
            self.init_data_source(server.get('data_platform'), server.get('data_source'), server.get('data_token'))
        except Exception as e:
            self.user = None
            msg = f'服务器连接验证失败：{e}' # self.log(msg, 'ERROR') #重复消息
            raise Exception(msg)

    def _normalize_order_price(self, price):
        try:
            return float(Decimal(str(price)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        except (InvalidOperation, TypeError, ValueError):
            try:
                return float(f"{float(price):.2f}")
            except Exception:
                return 0.0

    def init_data_source(self, data_platform='tushare', data_source='sina', data_token=None):
        '''初始化数据源'''
        self.log(f'正在初始化行情数据...')
        self.data_platform = data_platform
        self.data_source = data_source
        self.tushare = None
        self.akshare = None
        self.easyquotation = None

        def init_tushare():
            import tushare as ts
            ts.set_token(data_token)
            self.tushare = ts

        def init_akshare():
            import akshare
            self.akshare = akshare

        def init_easyquotation():
            import easyquotation
            self.easyquotation = easyquotation.use(data_source)

        platform_map = {
            'tushare': init_tushare,
            'akshare': init_akshare,
            'easyquotation': init_easyquotation,
        }

        try:
            init_func = platform_map.get(data_platform, init_tushare)
            msg = init_func()
            self.log(f'行情数据初始化已完成。')
        except ImportError as e:
            self.log(f'相关库未安装: {e}', 'ERROR')
        except Exception as e:
            self.log(f'初始化失败: {e}', 'ERROR')
      
    def get_stock_quote(self, ts_code):
        '''获取股票行情：现价、开盘价、昨收价'''
        stock_code = ''.join(filter(str.isdigit, ts_code)) or ts_code

        # 1. 尝试 Tushare
        if self.data_platform == 'tushare' and self.tushare:
            try:
                df = self.tushare.realtime_quote(ts_code=ts_code, src=self.data_source) # 不须token，tscode须后缀
                # df = ts.get_realtime_quotes(ts_code=ts_code) # 不须token，tscode须无后缀
                # df = pro.fund_basic(ts_code=ts_code) # ETF须token，tscode须后缀
                if df is not None and not df.empty:
                    return {
                        'price': float(df.iloc[0]['PRICE']),
                        'open': float(df.iloc[0]['OPEN']),
                        'pre_close': float(df.iloc[0]['PRE_CLOSE'])
                    }
            except Exception as e:
                self.log(f'获取行情数据错误(tushare）：{e}', 'ERROR')

        # 2. 尝试 AkShare
        if self.data_platform == 'akshare' and self.akshare:
            return self._get_akshare_detail(stock_code)
        
        # 3. 尝试 Easyquotation
        if self.data_platform == 'easyquotation' and self.easyquotation:
            try:
                data = self.easyquotation.real(stock_code)
                item = None
                if stock_code in data:
                    item = data[stock_code]
                else:
                    code_clean = ''.join(filter(str.isdigit, stock_code))
                    data = self.easyquotation.real(code_clean)
                    if code_clean in data:
                        item = data[code_clean]
                
                if item:
                    return {
                        'price': float(item.get('now', 0)),
                        'open': float(item.get('open', 0)),
                        'pre_close': float(item.get('close', 0))
                    }
            except Exception as e:
                self.log(f'获取行情数据错误(Easyquotation)：{e}', 'ERROR')
        
        # 4. 备用方案：手动获取新浪数据
        return self._get_sina_detail_manual(stock_code)

    def _get_akshare_detail(self, stock_code):
        '''获取 AkShare 股票详细信息'''
        try:
            import akshare as ak
            code_clean = ''.join(filter(str.isdigit, stock_code))
            
            # 使用 stock_zh_a_spot_em 获取实时行情
            # 注意：此接口返回全市场数据，效率较低，如有更优接口请替换
            df = ak.stock_zh_a_spot_em()
            row = df[df['代码'] == code_clean]
            
            if not row.empty:
                return {
                    'price': float(row.iloc[0]['最新价']),
                    'open': float(row.iloc[0]['今开']),
                    'pre_close': float(row.iloc[0]['昨收'])
                }
        except Exception as e:
            self.log(f'获取行情数据错误(AkShare)：{e}', 'ERROR')

    def _get_sina_detail_manual(self, stock_code):
        '''获取新浪股票详细信息'''
        try:
            code_clean = ''.join(filter(str.isdigit, stock_code))
            if not stock_code.startswith(('sh', 'sz', 'bj')):
                if code_clean.startswith('6'):
                    code_full = f'sh{code_clean}'
                elif code_clean.startswith('0') or code_clean.startswith('3'):
                    code_full = f'sz{code_clean}'
                elif code_clean.startswith('8') or code_clean.startswith('4'):
                    code_full = f'bj{code_clean}'
                else:
                    code_full = stock_code
            else:
                code_full = stock_code

            url = f'http://hq.sinajs.cn/list={code_full}'
            req = urllib.request.Request(url)
            req.add_header('Referer', 'http://finance.sina.com.cn/')
            
            with urllib.request.urlopen(req, timeout=3) as response:
                data = response.read().decode('gbk') 
                if 'var hq_str_' in data:
                    content = data.split('"')[1]
                    parts = content.split(',')
                    if len(parts) > 3:
                        return {
                            'price': float(parts[3]),
                            'open': float(parts[1]),
                            'pre_close': float(parts[2])
                        }
        except Exception as e:
            self.log(f'获取行情数据错误(sina)：{e}', 'WARNING')
        return {'price': 0.0, 'open': 0.0, 'pre_close': 0.0}

    def buy(self, stock_code, price, volume, reason=None):
        if not self.user:
            self.log('交易接口未连接', 'ERROR')
            return None
            
        try:
            price = self._normalize_order_price(price)
            res = self.user.buy(stock_code, price=price, amount=volume)
            if res:
                content = f'股票: {stock_code}\n价格: {price}\n数量: {volume}'
                if reason:
                    content = f'{reason}\n{content}'
                self.send_notification(color='green', title='买入委托通知', content=content)
            return res
        except Exception as e:
            self.log(f'{stock_code}买入发生错误：{e}', 'ERROR')
            self.send_notification(color='red', title='买入失败', content=f'股票: {stock_code}\n错误: {e}')
            return None

    def sell(self, stock_code, price, volume, reason=None):
        if not self.user:
            self.log('交易接口未连接', 'ERROR')
            return None
            
        try:
            price = self._normalize_order_price(price)
            res = self.user.sell(stock_code, price=price, amount=volume)
            if res:
                content = f'股票: {stock_code}\n价格: {price}\n数量: {volume}'
                if reason:
                    content = f'{reason}\n{content}'
                self.send_notification(color='orange', title='卖出委托通知', content=content)
            return res
        except Exception as e:
            self.log(f'{stock_code}卖出发生错误：{e}', 'ERROR')
            self.send_notification(color='red', title='卖出失败', content=f'股票: {stock_code}\n错误: {e}')
            return None

    def get_position(self, stock_code):
        '''获取持仓信息'''
        position = { }

        if not self.user:
            return position

        try:
            positions = self.user.position.get('data', [])

            for p in positions: # 依次为：平安证券-银河证券-中山证券
                stock_code_new = p.get('证券代码') or p.get('stock_code') or ''
                if stock_code == stock_code_new:
                    stock_name = p.get('证券名称') or p.get('stock_name') or ''
                    total_quantity = p.get('持仓数量') or p.get('股票余额') or p.get('实际数量') or p.get('stock_amount') or 0
                    available_quantity = p.get('可用数量') or p.get('可用余额') or p.get('enable_amount') or 0
                    frozen_quantity = p.get('冻结数量') or p.get('冻结余额') or p.get('frozen_quantity') or 0
                    cost_price = p.get('参考成本价') or p.get('成本价') or p.get('参考成本') or p.get('cost_price') or 0.0
                    current_price = p.get('当前价') or p.get('市价') or p.get('current_price') or 0.0
                    market_value = p.get('最新市值') or p.get('市值') or p.get('market_value') or 0.0
                    total_pl_amount = p.get('浮动盈亏') or p.get('盈亏') or p.get('总盈亏') or p.get('total_pl_amount') or 0.0
                    total_pl_ratio = p.get('盈亏比例(%)') or p.get('盈亏比(%)') or p.get('total_pl_ratio') or 0.0
                    daily_pl_amount = p.get('当日盈亏') or p.get('daily_pl_amount') or 0.0
                    daily_pl_ratio = p.get('当日盈亏比(%)') or p.get('daily_pl_ratio') or 0.0
                    position_ratio = p.get('仓位占比(%)') or p.get('仓位占比(%)') or p.get('position_ratio') or 0.0
                    daily_buy_quantity = p.get('当日买入') or p.get('daily_buy_quantity') or 0
                    daily_sell_quantity = p.get('当日卖出') or p.get('daily_sell_quantity') or 0
                    
                    return {
                        'stock_code': stock_code,
                        'stock_name': stock_name,
                        'total_quantity': int(total_quantity), 
                        'available_quantity': int(available_quantity),
                        'frozen_quantity': int(frozen_quantity),
                        'cost_price': float(cost_price),
                        'current_price': float(current_price),
                        'market_value': float(market_value),
                        'total_pl_amount': float(total_pl_amount),
                        'total_pl_ratio': float(total_pl_ratio),
                        'daily_pl_amount': float(daily_pl_amount),
                        'daily_pl_ratio': float(daily_pl_ratio),
                        'position_ratio': float(position_ratio),
                        'daily_buy_quantity': int(daily_buy_quantity),    
                        'daily_sell_quantity': int(daily_sell_quantity),
                    }

            return position
        except Exception as e:
            print(f'获取持仓错误：{e}')
            return position

    def get_balance(self):
        '''获取资金余额'''
        summary = {'total_asset': 0.0, 'market_value': 0.0, 'available_balance': 0.0}
        if not self.user:
            return summary
             
        try:
            balance = self.user.balance['data']
            return {
                'total_asset': float(balance.get('total_asset') or 0),  
                'market_value': float(balance.get('market_value') or 0),  
                'available_balance': float(balance.get('available_balance') or 0)
            }
        except Exception as e:
            print(f'获取资金余额错误：{e}')
            return summary

    def start_balance_monitor(self, interval=600):
        '''启动资产监控（支持多策略共享同一账户监控）'''
        if not getattr(self, 'account', None) or not self.account.get('id'):
            return
        account_id = self.account['id']
        with self._monitor_lock:
            if account_id not in self._monitors:
                stop_event = threading.Event()
                t = threading.Thread(
                    target=self._monitor_loop,
                    args=(account_id, interval, stop_event)
                )
                t.daemon = True
                t.start()
                self._monitors[account_id] = {
                    'thread': t,
                    'stop_event': stop_event,
                    'count': 1,
                    'instance': self
                }
                self.log(f'启动账户资产监控...')
            else:
                self._monitors[account_id]['count'] += 1

    def stop_balance_monitor(self):
        '''停止资产监控'''
        if not getattr(self, 'account', None) or not self.account.get('id'):
            return

        account_id = self.account['id']
        
        with self._monitor_lock:
            if account_id in self._monitors:
                self._monitors[account_id]['count'] -= 1
                count = self._monitors[account_id]['count']
                
                if count <= 0:
                    self._monitors[account_id]['stop_event'].set()
                    # 不阻塞等待，允许线程自然结束
                    del self._monitors[account_id]
                    self.log(f'已停止账户资产监控。')

    def _monitor_loop(self, account_id, interval, stop_event):
        try:
            # 使用独立的客户端实例以避免阻塞主交易线程
            user = self._create_client()
            print(f"[{time.strftime('%H:%M:%S')}] 资产监控线程已启动 (Account {account_id})")
            
            while not stop_event.is_set():
                self._update_assets(account_id, user)
                
                if stop_event.wait(interval):
                    break
                    
        except Exception as e:
            stop_event.set()    
            print(f'资产监控线程启动失败: {e}')

    def _update_assets(self, account_id, user):
        try:
            balance_raw = user.balance.get('data', {})
            if isinstance(balance_raw, dict):
                summary = {**balance_raw, 'updated_at': time.strftime('%Y-%m-%d %H:%M:%S')}
            
            if self.backend_url and self.token:
                base_url = self.backend_url

                if base_url.endswith('/'):
                    base_url = base_url[:-1]
            
                url = f'{base_url}/quant/account/updateAccount'
                data = {
                    'id': account_id,
                    'summary': summary
                }
                headers = {
                    'x-token': self.token,
                    'Content-Type': 'application/json'
                }
                response = requests.put(url, json=data, headers=headers, timeout=5)
                if response.status_code != 200:
                    print(f"[{time.strftime('%H:%M:%S')}] 资产上报失败: {response.status_code} {response.text}")
                else:
                    # 成功上报后，通知前端刷新
                    if self.log_callback:
                        try:
                            self.log_callback('INFO', 'QuantTrader', 'ASSET_UPDATE_TRIGGER')
                        except:
                            pass

        except Exception as e:
            print(f'账户资产获取异常: {e}')

    @classmethod
    def refresh_account(cls, data):
        '''手动触发账户资产刷新'''
        account = data.get('account', {})
        backend_url = data.get('backend_url')
        token = data.get('token')
        account_id = account.get('id')
        instance = None
        
        with cls._monitor_lock:
            if account_id in cls._monitors:
                instance = cls._monitors[account_id].get('instance')
        
        if instance:
            try:
                user = instance._create_client()
                instance._update_assets(account_id, user)
                return True, '刷新已触发'
            except Exception as e:
                print(f'Update failed: {e}')
                return False, f'刷新失败: {e}'
        
        if account:
            try:
                temp_trader = cls()
                temp_trader.connect(account, backend_url=backend_url, token=token)
                user = temp_trader._create_client()
                temp_trader._update_assets(account_id, user)
                return True, '刷新已触发（临时连接）'
            except Exception as e:
                return False, f'刷新失败(临时): {e}'
        
        return False, '未找到该账户的运行监控且无法建立临时连接'

    def send_notification(self, color='blue', title=None, content=None):
        '''发送通知到飞书/钉钉/微信'''
        if not getattr(self, 'webhook_url', None):
            return

        try:
            if self.webhook_type == 'feishu':
                headers = {'Content-Type': 'application/json'}
                
                # 构造富文本卡片消息
                card_content = {
                    'config': {
                        'wide_screen_mode': True
                    },
                    'header': {
                        'template': color,
                        'title': {
                            'content': title,
                            'tag': 'plain_text'
                        }
                    },
                    'elements': [
                        {
                            'tag': 'div',
                            'text': {
                                'content': content,
                                'tag': 'lark_md'
                            }
                        },
                        {
                            'tag': 'hr'
                        },
                        {
                            'tag': 'note',
                            'elements': [
                                {
                                    'content': f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
                                    'tag': 'plain_text'
                                }
                            ]
                        }
                    ]
                }

                data = {
                    'msg_type': 'interactive',
                    'card': card_content
                }
                requests.post(self.webhook_url, json=data, headers=headers, timeout=5)
            
        except Exception as e:
            self.log(f'发送通知失败：{e}', 'ERROR')
