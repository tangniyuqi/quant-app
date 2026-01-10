# -*- coding: utf-8 -*-
import threading
import time
from .trader import QuantTrader

class BaseStrategy:
    def __init__(self, data, log_callback=None):
        self.data = data
        self.log_callback = log_callback
        self.running = False
        self.thread = None
        self.trader = QuantTrader(log_callback)
        
        # 初始化交易器，根据任务配置中的账户信息连接到真实交易接口或模拟交易接口
        account = data.get('account', {})
        backend_url = data.get('backend_url')
        token = data.get('token')
        
        if account:
            print(f"正在连接账户：{account.get('broker')}")
            self.trader.connect(account, backend_url=backend_url, token=token)
        else:
            self.log("任务配置中未找到账户信息，使用模拟交易接口。", "WARNING")

    def log(self, message, level='INFO'):
        print(f"[{level}] {message}")
        if self.log_callback:
            try:
                module = self.__class__.__name__
                self.log_callback(level, module, str(message))
            except Exception:
                pass

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_loop)
        self.thread.daemon = True
        self.thread.start()
        self.trader.start_balance_monitor(interval=600)

    def stop(self):
        self.running = False
        self.trader.stop_balance_monitor()
        #if self.thread and self.thread != threading.current_thread():
        if self.thread:
            self.thread.join(timeout=1)

    def _run_loop(self):
        try:
            self.run()
        except Exception as e:
            print(f"任务错误：{e}")
            import traceback
            traceback.print_exc()
            self.running = False

    def run(self):
        raise NotImplementedError
