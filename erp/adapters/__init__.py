# -*- coding: utf-8 -*-
"""适配器工厂：settings.ERP_MODE 决定用哪一个。

    mock    → 通过 HTTP 连本机假 ERP（默认，端口 9900）
    http    → 通过 HTTP 连真实金蝶（改 ERP_BASE_URL 即可）
    offline → 不联网，直接读种子数据（自检用）
"""

from django.conf import settings

from .base import BaseErpAdapter  # noqa: F401  (对外导出)

MODE_MOCK = "mock"
MODE_HTTP = "http"
MODE_OFFLINE = "offline"


def get_adapter(mode=None):
    mode = (mode or getattr(settings, "ERP_MODE", MODE_MOCK) or MODE_MOCK).lower()

    if mode == MODE_OFFLINE:
        from .mock import MockAdapter
        return MockAdapter()

    from .kingdee import KingdeeAdapter
    return KingdeeAdapter()