#!/usr/bin/env python3
"""监控合肥物质院研究生处及中科大研究生院通知页面，新条目经钉钉机器人推送。

支持两种页面格式（hf.cas.cn 静态列表 / gradschool.ustc.edu.cn 文章列表）。
新纳入监控的栏目会静默收录既有条目（不推送），之后每小时 diff 推送新增。
由 cron 每小时调用一次：
    0 * * * * /usr/bin/python3 /path/to/hfcas_notice/monitor.py >> /path/to/hfcas_notice/logs/cron.log 2>&1
"""

import argparse
from html import unescape
import json
import logging
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests

from dingtalk_notify import send_markdown

BASE_DIR = Path(__file__).resolve().parent
STATE_PATH = BASE_DIR / "data" / "seen.json"

# 页面格式：hf = hf.cas.cn 静态列表；ustc = gradschool.ustc.edu.cn /article/ 列表
CHANNELS = {
    "合肥物质院 · 通知公告": ("https://hf.cas.cn/sbpy/yjsc/tzgg/", "hf"),
    "合肥物质院 · 奖助学金": ("https://hf.cas.cn/sbpy/yjsc/py_1/jzxj/", "hf"),
    "合肥物质院 · 公示公开": ("https://hf.cas.cn/sbpy/yjsc/gsgk/", "hf"),
    "合肥物质院 · 学位": ("https://hf.cas.cn/sbpy/yjsc/xw_1/xwsy/", "hf"),
    "合肥物质院 · 毕业离校": ("https://hf.cas.cn/sbpy/yjsc/rcgl/rcgl_bylx/", "hf"),
    "合肥物质院 · 学籍管理": ("https://hf.cas.cn/sbpy/yjsc/py_1/xjgl/", "hf"),
    "合肥物质院 · 开题考核": ("https://hf.cas.cn/sbpy/yjsc/py_1/ktzq/", "hf"),
    "合肥物质院 · 项目申报": ("https://hf.cas.cn/sbpy/yjsc/py_1/xmsb/", "hf"),
    "合肥物质院 · 课程安排": ("https://hf.cas.cn/sbpy/yjsc/py_1/kcap/", "hf"),
    "合肥物质院 · 就业信息": ("https://hf.cas.cn/sbpy/yjsc/jyxx_1/", "hf"),
    "中科大研究生院 · 通知公告": ("https://gradschool.ustc.edu.cn/column/9", "ustc"),
    "安光所 · 通知公告": ("https://aiofm.cas.cn/2022anguangsuo9/2022_xwzhongxin/2022_tzgonggao/", "aiofm"),
}

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; hfcas-notice-monitor/1.0)"}
HF_LINK_RE = re.compile(r'<a href="(\./(?:[a-z0-9_]+/)?\d{6}/t\d+_\d+\.html)"[^>]*title="([^"]+)"')
HF_DATE_RE = re.compile(r"20\d{2}-\d{2}-\d{2}")
USTC_ITEM_RE = re.compile(
    r'href="/article/(\d+)"[^>]*>\s*([^<]{4,})\s*</a>\s*<time>(\d{4}-\d{2}-\d{2})</time>'
)
AIOFM_ITEM_RE = re.compile(
    r'href="(\./\d{6}/t\d{8}_\d+\.html)"[^>]*>\s*([^<]{6,})\s*</a>'
)
AIOFM_DATE_RE = re.compile(r"20\d{2}\.\d{2}\.\d{2}")

# 旧状态文件的频道名迁移（避免改名后重复推送）
LEGACY_KEY_MAP = {
    "通知公告": "合肥物质院 · 通知公告",
    "公示公开": "合肥物质院 · 公示公开",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("hfcas_notice")


def fetch(url: str, retries: int = 3, timeout: int = 25) -> str:
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            return resp.text
        except requests.RequestException:
            logger.warning("抓取失败(第%d/%d次): %s", attempt, retries, url)
            if attempt == retries:
                raise
            time.sleep(10)


def parse_hf(html: str, page_url: str) -> list[dict]:
    items = []
    for m in HF_LINK_RE.finditer(html):
        dm = HF_DATE_RE.search(html, m.end(), m.end() + 400)
        items.append({
            "url": urljoin(page_url, m.group(1)),
            "title": unescape(m.group(2)).strip(),
            "date": dm.group(0) if dm else "",
        })
    return items


def parse_ustc(html: str, page_url: str) -> list[dict]:
    return [
        {
            "url": urljoin(page_url, f"/article/{m.group(1)}"),
            "title": unescape(m.group(2)).strip(),
            "date": m.group(3),
        }
        for m in USTC_ITEM_RE.finditer(html)
    ]


def parse_aiofm(html: str, page_url: str) -> list[dict]:
    items = []
    for m in AIOFM_ITEM_RE.finditer(html):
        dm = AIOFM_DATE_RE.search(html, m.end(), m.end() + 400)
        items.append({
            "url": urljoin(page_url, m.group(1)),
            "title": unescape(m.group(2)).strip(),
            "date": dm.group(0).replace(".", "-") if dm else "",
        })
    return items


PARSERS = {"hf": parse_hf, "ustc": parse_ustc, "aiofm": parse_aiofm}


def load_state() -> dict:
    state = {}
    if STATE_PATH.exists():
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    for old, new in LEGACY_KEY_MAP.items():
        if old in state and new not in state:
            state[new] = state.pop(old)
    return state


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def send_dingtalk(title: str, content: str) -> None:
    if not send_markdown(title, content):
        logger.error("钉钉推送失败: %s", title)


def main() -> None:
    parser = argparse.ArgumentParser(description="合肥物质院/中科大研究生院通知监控")
    parser.add_argument("--dry-run", action="store_true", help="只打印结果，不推送、不写状态")
    args = parser.parse_args()

    state = load_state()
    new_by_channel = {}
    seeded = []

    for name, (url, fmt) in CHANNELS.items():
        already_tracked = name in state
        seen = state.setdefault(name, {})
        try:
            items = PARSERS[fmt](fetch(url), url)
        except requests.RequestException:
            logger.error("抓取最终失败，本频道跳过: %s", name)
            continue
        if not already_tracked:
            # 首次纳入监控：收录既有条目为基线；最近 7 天内的条目仍推送（大概率还在有效期内）
            seeded.append((name, len(items)))
            cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            fresh = [it for it in items if it["date"] >= cutoff]
        else:
            fresh = [it for it in items if it["url"] not in seen]
        for it in items:
            if it["url"] not in seen:
                it["first_seen"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                seen[it["url"]] = it
        new_by_channel[name] = fresh
        logger.info("%s: 页面共 %d 条, 新增 %d 条", name, len(items), len(fresh))

    if args.dry_run:
        for name, n in seeded:
            print(f"[新纳入] {name}: {n} 条既有条目（将静默收录）")
        for name, fresh in new_by_channel.items():
            for it in fresh:
                print(f"[{name}] {it['date']} {it['title']}\n    {it['url']}")
        return

    save_state(state)

    if seeded:
        lines = ["以下栏目已纳入监控，既有条目已收录、不重复提醒："]
        lines += [
            f"- [{name}]({CHANNELS[name][0]})（收录 {n} 条）" for name, n in seeded
        ]
        recent = {n: f for n, f in new_by_channel.items() if f}
        if recent:
            lines.append("\n**收录时发现近期条目（可能仍在有效期内）：**")
            for name, fresh in recent.items():
                for it in fresh:
                    lines.append(f"- [{it['title']}]({it['url']})  `{it['date']}`")
        logger.info("新纳入 %d 个频道，推送扩展通知（含 %d 条近期条目）",
                    len(seeded), sum(len(v) for v in recent.values()))
        send_dingtalk("通知监控范围已扩展", "\n".join(lines))
        return

    total = sum(len(v) for v in new_by_channel.values())
    if total == 0:
        logger.info("无新通知")
        return

    lines = [f"共 {total} 条新通知："]
    for name, fresh in new_by_channel.items():
        if not fresh:
            continue
        lines.append(f"\n**{name}（{len(fresh)}）**")
        for it in fresh:
            lines.append(f"- [{it['title']}]({it['url']})  `{it['date']}`")
    logger.info("发现 %d 条新通知，推送钉钉", total)
    send_dingtalk(f"共 {total} 条新通知", "\n".join(lines))


if __name__ == "__main__":
    main()
