from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock
import pandas as pd

from app.core.config import Settings
from app.providers.akshare import AKShareProvider


def test_akshare_fetch_news_eastmoney():
    mock_ak = MagicMock()
    provider = AKShareProvider(Settings(_env_file=None), ak_client=mock_ak)
    df = pd.DataFrame([
        {
            "标题": "利好！多只宽基ETF持续放量",
            "摘要": "多只沪深300ETF和中证500ETF成交放量，资金净流入明显。",
            "发布时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "链接": "https://finance.eastmoney.com/a/123.html",
        }
    ])
    mock_ak.stock_info_global_em.return_value = df

    records = provider.fetch_news(since_hours=24)
    assert len(records) == 1
    assert records[0].source == "akshare:eastmoney"
    assert "多只宽基ETF持续放量" in records[0].title
    assert records[0].summary is not None
    assert "资金净流入" in records[0].summary
    assert records[0].url == "https://finance.eastmoney.com/a/123.html"


def test_akshare_fetch_news_cls_fallback():
    mock_ak = MagicMock()
    provider = AKShareProvider(Settings(_env_file=None), ak_client=mock_ak)
    # Eastmoney throws exception, CLS succeeds
    mock_ak.stock_info_global_em.side_effect = RuntimeError("EM timeout")
    df_cls = pd.DataFrame([
        {
            "标题": "【重磅信号】半导体板块盘中异动",
            "内容": "【重磅信号】半导体板块盘中异动，多只芯片龙头股拉升。",
            "发布日期": datetime.now().date(),
            "发布时间": datetime.now().time(),
        }
    ])
    mock_ak.stock_info_global_cls.return_value = df_cls

    records = provider.fetch_news(since_hours=24)
    assert len(records) == 1
    assert records[0].source == "akshare:cls"
    assert "半导体板块盘中异动" in records[0].title
