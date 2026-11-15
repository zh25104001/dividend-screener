#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A股高股息率筛选器 - Python后端
启动: python server.py
浏览器访问: http://localhost:8081
配置文件: config.json
"""

import json
import os
import re
import threading
import time
from datetime import datetime, timedelta

import requests
from flask import Flask, jsonify, send_file

# ===== 读取配置文件 =====
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")
CACHE_FILE = os.path.join(SCRIPT_DIR, "cache.json")
HTML_FILE = os.path.join(SCRIPT_DIR, "index.html")

config = {
    "proxy": None,
    "port": 8081,
    "update_interval": 300,  # 秒
}
if os.path.exists(CONFIG_FILE):
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8-sig") as f:
            cfg = json.load(f)
            config["proxy"] = cfg.get("proxy") or None
            config["port"] = int(cfg.get("port", 8081))
            config["update_interval"] = int(cfg.get("updateInterval", 300000)) // 1000
    except Exception:
        pass

PROXY = config["proxy"]
PORT = config["port"]
UPDATE_INTERVAL = config["update_interval"]

# requests session with proxy and retry
session = requests.Session()
if PROXY:
    session.proxies = {"http": PROXY, "https": PROXY}
    # 华为代理需要NTLM认证，用requests_ntlm处理407
    try:
        from requests_ntlm import HttpNtlmAuth
        session.auth = HttpNtlmAuth("", "")
    except ImportError:
        session.trust_env = True  # fallback: rely on system proxy credentials
session.verify = False  # skip SSL cert verification (corporate proxy MITM)
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
retry_strategy = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("https://", adapter)
session.mount("http://", adapter)

# ===== 全局缓存（线程安全） =====
cache_lock = threading.Lock()
cache = {
    "data": [],
    "json_bytes": None,
    "last_update": None,
    "updating": False,
    "prev_yields": {},
    "alerts": [],
}


# ===== 启动时加载本地缓存 =====
def load_cache_from_file():
    if not os.path.exists(CACHE_FILE):
        return False
    try:
        with open(CACHE_FILE, "r", encoding="utf-8-sig") as f:
            saved = json.load(f)
        if saved.get("data") and len(saved["data"]) > 0:
            with cache_lock:
                cache["data"] = saved["data"]
                cache["alerts"] = saved.get("alerts", [])
                cache["prev_yields"] = {k: float(v) for k, v in saved.get("prev_yields", {}).items()}
                cache["last_update"] = saved.get("lastUpdate")
                cache["updating"] = True
                # 预生成JSON
                snapshot = {
                    "success": True,
                    "count": len(saved["data"]),
                    "lastUpdate": saved.get("lastUpdate"),
                    "updating": True,
                    "alertCount": 0,
                    "data": saved["data"],
                    "alerts": cache["alerts"],
                }
                cache["json_bytes"] = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            print(f"[缓存] 已加载上次数据: {len(saved['data'])} 只股票, 更新于 {saved.get('lastUpdate')}")
            return True
    except Exception as e:
        print(f"[缓存] 读取缓存失败: {e}")
    return False


def save_cache_to_file():
    try:
        with cache_lock:
            to_save = {
                "lastUpdate": cache["last_update"] or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "data": cache["data"],
                "alerts": cache["alerts"],
                "prevYields": cache["prev_yields"],
            }
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(to_save, f, ensure_ascii=False, separators=(",", ":"))
        print("[缓存] 已保存到文件")
    except Exception as e:
        print(f"[缓存] 保存失败: {e}")


# ===== 获取过去12个月分红记录 =====
def get_dividend_data():
    print("  [1/2] 获取分红数据...")
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"}
    cutoff_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    all_dividends = {}
    total_pages = 50
    consecutive_empty = 0

    for page in range(1, total_pages + 1):
        url = (
            f"https://datacenter-web.eastmoney.com/api/data/v1/get"
            f"?reportName=RPT_SHAREBONUS_DET"
            f"&columns=SECURITY_CODE,SECURITY_NAME_ABBR,PRETAX_BONUS_RMB,EX_DIVIDEND_DATE,ASSIGN_PROGRESS"
            f"&source=WEB&client=WEB&pageSize=100&pageNumber={page}"
            f"&sortColumns=EX_DIVIDEND_DATE&sortTypes=-1"
            f"&filter=(ASSIGN_PROGRESS=%22%E5%AE%9E%E6%96%BD%E5%88%86%E9%85%8D%22)"
            f"(EX_DIVIDEND_DATE%3E=%27{cutoff_date}%27)"
        )
        try:
            r = session.get(url, headers=headers, timeout=15)
            j = r.json()
            if not j.get("success") or not j.get("result"):
                consecutive_empty += 1
                if consecutive_empty >= 2:
                    break
                continue
            consecutive_empty = 0
            for item in j["result"]["data"]:
                code = item["SECURITY_CODE"]
                bonus_raw = item.get("PRETAX_BONUS_RMB")
                if bonus_raw is None:
                    continue
                bonus = float(bonus_raw)
                if bonus <= 0:
                    continue
                per_share = bonus / 10
                if code in all_dividends:
                    all_dividends[code]["total_dividend"] += per_share
                    all_dividends[code]["count"] += 1
                else:
                    all_dividends[code] = {
                        "code": code,
                        "name": item["SECURITY_NAME_ABBR"],
                        "total_dividend": per_share,
                        "count": 1,
                    }
            if page % 10 == 0:
                print(f"    分红数据: 已获取 {page} / {total_pages} 页")
        except Exception as e:
            print(f"    分红数据第{page}页失败: {e}")

    print(f"    分红数据完成: {len(all_dividends)} 只股票有分红记录")
    return all_dividends


# ===== 从新浪获取实时行情 =====
def get_realtime_quotes(codes):
    print("  [2/2] 获取实时行情...")
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"}
    quotes = {}
    batch_size = 100

    sina_codes = []
    for code in codes:
        c = str(code).zfill(6)
        if c.startswith("6") or c.startswith("9"):
            sina_codes.append(f"sh{c}")
        elif c.startswith("8") or c.startswith("4"):
            sina_codes.append(f"bj{c}")
        else:
            sina_codes.append(f"sz{c}")

    total_batches = (len(sina_codes) + batch_size - 1) // batch_size

    for i in range(0, len(sina_codes), batch_size):
        batch = sina_codes[i : i + batch_size]
        batch_num = i // batch_size + 1
        code_str = ",".join(batch)
        url = f"https://hq.sinajs.cn/list={code_str}"
        try:
            r = session.get(url, headers=headers, timeout=15)
            r.encoding = "gbk"
            for line in r.text.split("\n"):
                m = re.search(r'hq_str_\w{2}(\d{6})="([^"]*)"', line)
                if m:
                    code = m.group(1)
                    fields = m.group(2).split(",")
                    if len(fields) >= 10:
                        try:
                            price = float(fields[3])
                            if price <= 0:
                                price = float(fields[2])
                            if price > 0:
                                prev_close = float(fields[2])
                                change = round((price - prev_close) / prev_close * 100, 2) if prev_close != 0 else 0
                                amount = float(fields[9]) if len(fields) > 9 else 0
                                quotes[code] = {"price": price, "change": change, "amount": amount}
                        except (ValueError, IndexError):
                            pass
            if batch_num % 5 == 0:
                print(f"    行情数据: 已获取 {batch_num} / {total_batches} 批")
        except Exception as e:
            print(f"    行情批次{batch_num}/{total_batches}失败: {e}")

    print(f"    行情数据完成: {len(quotes)} 只股票有实时价格")
    return quotes


# ===== 数据更新主流程 =====
def update_data():
    with cache_lock:
        cache["updating"] = True

    print(f"[更新] {datetime.now().strftime('%H:%M:%S')} 开始更新数据...")

    dividends = get_dividend_data()
    quotes = get_realtime_quotes(list(dividends.keys()))

    result = []
    for code, div in dividends.items():
        if code not in quotes:
            continue
        q = quotes[code]
        if q["price"] <= 0 or div["total_dividend"] <= 0:
            continue
        result.append({
            "code": code,
            "name": div["name"],
            "price": round(q["price"], 2),
            "change": q["change"],
            "yield": round(div["total_dividend"] / q["price"] * 100, 2),
            "totalDividend": round(div["total_dividend"], 3),
            "divCount": div["count"],
            "amount": round(q["amount"] / 100000000, 2),
        })
    result.sort(key=lambda x: x["yield"], reverse=True)

    # ===== 数据完整性检查 =====
    with cache_lock:
        prev_data_count = len(cache["data"])

    if prev_data_count > 0 and len(result) < prev_data_count * 0.95:
        print(f"[更新] 数据不完整({len(result)}/{prev_data_count})，保留上一轮数据，跳过预警")
        with cache_lock:
            cache["updating"] = False
        return

    print(f"[更新] 数据完整: {len(result)} 只股票 (上轮: {prev_data_count})")

    # ===== 阈值穿越检测 =====
    with cache_lock:
        prev_yields = dict(cache["prev_yields"])

    new_alerts = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    THRESHOLDS = [3, 4, 5, 6, 7, 8, 9]
    for stock in result:
        code = stock["code"]
        old_yield = prev_yields.get(code)
        new_yield = stock["yield"]
        if old_yield is not None:
            diff = abs(new_yield - old_yield)
            if diff < 0.3:
                continue
            crossed = []
            for t in THRESHOLDS:
                if old_yield < t <= new_yield:
                    crossed.append(t)
                elif old_yield >= t > new_yield:
                    crossed.append(t)
            if not crossed:
                continue
            if new_yield > old_yield:
                thresholds_str = "、".join(f"{t}%" for t in crossed)
                new_alerts.append({
                    "type": "up", "code": code, "name": stock["name"],
                    "oldYield": round(old_yield, 2), "newYield": new_yield,
                    "price": stock["price"], "time": now,
                    "message": f"{stock['name']}({code}) 股息率从 {round(old_yield, 2)}% 升至 {new_yield}%，突破{thresholds_str}关口",
                })
            else:
                thresholds_str = "、".join(f"{t}%" for t in crossed)
                new_alerts.append({
                    "type": "down", "code": code, "name": stock["name"],
                    "oldYield": round(old_yield, 2), "newYield": new_yield,
                    "price": stock["price"], "time": now,
                    "message": f"{stock['name']}({code}) 股息率从 {round(old_yield, 2)}% 降至 {new_yield}%，跌破{thresholds_str}关口",
                })

    # 更新快照
    new_prev_yields = {s["code"]: s["yield"] for s in result}

    with cache_lock:
        all_alerts = new_alerts + cache["alerts"]
        if len(all_alerts) > 200:
            all_alerts = all_alerts[:200]
        cache["alerts"] = all_alerts
        cache["prev_yields"] = new_prev_yields
        alert_snapshot = list(cache["alerts"])

    if new_alerts:
        print(f"[预警] 发现 {len(new_alerts)} 条股息率穿越提醒")
        for a in new_alerts:
            icon = "↑" if a["type"] == "up" else "↓"
            color = "\033[91m" if a["type"] == "up" else "\033[92m"  # red / green
            print(f"  {color}{icon} {a['message']}\033[0m")

    # 预生成JSON
    snapshot = {
        "success": True,
        "count": len(result),
        "lastUpdate": now,
        "updating": False,
        "alertCount": len(new_alerts),
        "data": result,
        "alerts": alert_snapshot,
    }
    json_bytes = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    with cache_lock:
        cache["data"] = result
        cache["json_bytes"] = json_bytes
        cache["last_update"] = now
        cache["updating"] = False

    # 统计
    high5 = sum(1 for s in result if s["yield"] >= 5)
    print(f"[更新] 完成: {len(result)} 只股票, 股息率≥5%: {high5} 只")

    # 保存缓存
    save_cache_to_file()


# ===== 定时更新线程 =====
def update_loop():
    while True:
        time.sleep(UPDATE_INTERVAL)
        with cache_lock:
            is_updating = cache["updating"]
        if is_updating:
            print("[定时] 跳过：数据正在更新中")
            continue
        print(f"[定时] {datetime.now().strftime('%H:%M:%S')} 启动新一轮数据更新...")
        try:
            update_data()
        except Exception as e:
            print(f"[定时] 更新失败: {e}")
            with cache_lock:
                cache["updating"] = False


# ===== Flask Web服务器 =====
app = Flask(__name__)


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response


@app.route("/api/data")
def api_data():
    with cache_lock:
        if cache["json_bytes"]:
            from flask import Response
            return Response(
                cache["json_bytes"],
                content_type="application/json; charset=utf-8",
            )
        # 数据还没加载完
        return jsonify({
            "success": True, "count": 0, "lastUpdate": None,
            "updating": True, "alertCount": 0, "data": [],
        })


@app.route("/")
@app.route("/index.html")
def index():
    with open(HTML_FILE, "r", encoding="utf-8") as f:
        html = f.read()
    # 替换端口号
    html = html.replace("localhost:8081", f"localhost:{PORT}")
    return html


# ===== 启动 =====
if __name__ == "__main__":
    print("=" * 50)
    print("  A股高股息率筛选器已启动 (Python)")
    print(f"  浏览器访问: http://localhost:{PORT}")
    print(f"  代理: {PROXY or '直连'}")
    print(f"  更新间隔: {UPDATE_INTERVAL}秒")
    print("  按 Ctrl+C 停止")
    print("=" * 50)

    # 启动时加载缓存
    load_cache_from_file()

    # 后台线程首次加载数据
    with cache_lock:
        cache["updating"] = True
    print("正在后台加载数据，浏览器可以先打开...")

    def first_load():
        try:
            update_data()
        except Exception as e:
            print(f"[启动] 数据加载失败: {e}")
            with cache_lock:
                cache["updating"] = False

    t = threading.Thread(target=first_load, daemon=True)
    t.start()

    # 定时更新线程
    timer_thread = threading.Thread(target=update_loop, daemon=True)
    timer_thread.start()

    # 启动HTTP服务
    app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False)
