#!/usr/bin/env python3
"""钉钉群机器人 markdown 消息推送（加签版）。

凭据读取优先级：
1. 环境变量 DINGTALK_WEBHOOK / DINGTALK_SECRET
2. 本目录下 secrets.json（不入库，格式见 secrets.example.json）
"""
import base64
import hashlib
import hmac
import json
import os
import time
import urllib.parse
from pathlib import Path

import requests

_SECRETS_PATH = Path(__file__).resolve().parent / "secrets.json"


def _load_credentials() -> tuple[str, str]:
    webhook = os.environ.get("DINGTALK_WEBHOOK", "")
    secret = os.environ.get("DINGTALK_SECRET", "")
    if not webhook and _SECRETS_PATH.exists():
        data = json.loads(_SECRETS_PATH.read_text(encoding="utf-8"))
        webhook = data.get("webhook", "")
        secret = data.get("secret", "")
    return webhook, secret


def _sign(secret: str) -> tuple[str, str]:
    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        secret.encode("utf-8"), string_to_sign.encode("utf-8"), digestmod=hashlib.sha256
    ).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    return timestamp, sign


def send_markdown(title: str, content: str) -> bool:
    """发送 markdown 消息，返回是否成功。"""
    webhook, secret = _load_credentials()
    if not webhook:
        print("DINGTALK_WEBHOOK 未配置，跳过推送")
        return False

    url = webhook
    if secret:
        timestamp, sign = _sign(secret)
        url = f"{webhook}&timestamp={timestamp}&sign={sign}"

    body = {
        "msgtype": "markdown",
        "markdown": {"title": title, "text": f"## {title}\n\n{content}"},
        "at": {"isAtAll": False},
    }
    resp = requests.post(url, json=body, timeout=15)
    result = resp.json()
    if result.get("errcode") == 0:
        return True
    print(f"钉钉 API 错误: {result}")
    return False


if __name__ == "__main__":
    # 手动测试: python3 dingtalk_notify.py
    ok = send_markdown("测试", "这是一条来自 dingtalk_notify 的测试消息。")
    print("发送成功" if ok else "发送失败")
