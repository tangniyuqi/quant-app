#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
Author: Tang Ming
Date: 2025-12-12 17:01:39
LastEditTime: 2025-12-18 20:28:48
Description: 操作存储在数据库中的数据
usage: 调用window.pywebview.api.storage.<methodname>(<parameters>)从Javascript执行
'''

from api.db.orm import ORM


class Storage():
    '''存储类'''

    orm = ORM()    # 操作数据库类

    def storage_get(self, key):
        '''获取关键词的值'''
        return self.orm.getStorageVar(key)

    def storage_set(self, key, val):
        '''设置关键词的值'''
        self.orm.setStorageVar(key, val)
