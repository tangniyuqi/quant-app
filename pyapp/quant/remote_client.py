# -*- coding: utf-8 -*-
import requests

class RemoteClient:
    def __init__(self):
        self.host = '127.0.0.1'
        self.port = 14300
        self.session = requests.Session()
        self.base_url = f"http://{self.host}:{self.port}"

    def connect(self, host, port):
        self.host = host
        self.port = port
        self.base_url = f"http://{self.host}:{self.port}"

    def buy(self, stock_code, price, amount, **kwargs):
        url = f"{self.base_url}/buy"
        params = {
            "security": stock_code,
            "price": price,
            "amount": amount
        }
        params.update(kwargs)
        resp = self.session.post(url, json=params)
        resp.raise_for_status()
        return resp.json()

    def sell(self, stock_code, price, amount, **kwargs):
        url = f"{self.base_url}/sell"
        params = {
            "security": stock_code,
            "price": price,
            "amount": amount
        }
        params.update(kwargs)
        resp = self.session.post(url, json=params)
        resp.raise_for_status()
        return resp.json()

    @property
    def balance(self):
        url = f"{self.base_url}/balance"
        resp = self.session.get(url)
        resp.raise_for_status()
        return resp.json()

    @property
    def position(self):
        url = f"{self.base_url}/position"
        resp = self.session.get(url)
        resp.raise_for_status()
        return resp.json()

    @property
    def today_entrusts(self):
        url = f"{self.base_url}/today_entrusts"
        resp = self.session.get(url)
        resp.raise_for_status()
        return resp.json()

    @property
    def today_trades(self):
        url = f"{self.base_url}/today_trades"
        resp = self.session.get(url)
        resp.raise_for_status()
        return resp.json()

    @property
    def cancel_entrusts(self):
        url = f"{self.base_url}/cancel_entrusts"
        resp = self.session.get(url)
        resp.raise_for_status()
        return resp.json()

    def cancel_entrust(self, entrust_no, **kwargs):
        url = f"{self.base_url}/cancel_entrust"
        params = {"entrust_no": entrust_no}
        params.update(kwargs)
        resp = self.session.post(url, json=params)
        resp.raise_for_status()
        return resp.json()
