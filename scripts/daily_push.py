#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基金每日战报（GitHub Actions 定时任务）
流程：读 holdings.json -> 抓天天基金最新净值 -> 计算当日收益 -> Server酱 推送到微信
持仓配置与网页版共用同一份 holdings.json（网页「导出持仓」按钮生成的就是它）。
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

CST = timezone(timedelta(hours=8))  # 北京时间
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOLDINGS_FILE = os.path.join(ROOT, "holdings.json")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def today_cst():
    return datetime.now(CST).strftime("%Y-%m-%d")


def http_get(url, timeout=20):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Referer": "https://fund.eastmoney.com/",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def http_post_form(url, fields, timeout=20):
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={
        "User-Agent": UA,
        "Content-Type": "application/x-www-form-urlencoded",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def load_holdings():
    with open(HOLDINGS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("holdings.json 应为数组，例如 [{\"code\":\"005827\",\"shares\":1000,\"cost\":1.85}]")
    out = []
    for x in data:
        code = str(x.get("code", "")).strip()
        shares = float(x.get("shares") or 0)
        cost = float(x.get("cost") or 0)
        if code and shares > 0:
            out.append({"code": code, "shares": shares, "cost": cost})
    return out


def fetch_fund(code):
    """抓取天天基金 pingzhongdata（标准 JSON 字面量），返回名称与净值走势"""
    text = http_get(f"https://fund.eastmoney.com/pingzhongdata/{code}.js?v={int(datetime.now().timestamp() * 1000)}")
    m_name = re.search(r'fS_name\s*=\s*"([^"]*)"', text)
    m_trend = re.search(r"Data_netWorthTrend\s*=\s*(\[.*?\]);", text, re.S)
    if not m_trend:
        raise ValueError("未找到净值走势数据")
    trend = json.loads(m_trend.group(1))
    if not trend:
        raise ValueError("净值走势为空")
    name = m_name.group(1) if m_name else code
    return {"name": name, "trend": trend}


def calc(fund, holding):
    """与网页版 calcFund 一致的口径：当日收益 = (最新净值 - 上一净值) * 份额"""
    trend = fund["trend"]
    latest, prev = trend[-1], trend[-2]
    latest_nav = float(latest["y"])
    prev_nav = float(prev["y"])
    latest_date = datetime.fromtimestamp(latest["x"] / 1000, CST).strftime("%Y-%m-%d")
    equity_return = latest.get("equityReturn")
    try:
        day_pct = float(equity_return) if equity_return not in (None, "") else None
    except (TypeError, ValueError):
        day_pct = None
    if day_pct is None and prev_nav:
        day_pct = (latest_nav / prev_nav - 1) * 100
    shares = holding["shares"]
    cost = holding["cost"]
    return {
        "code": holding["code"],
        "name": fund["name"],
        "date": latest_date,
        "isToday": latest_date == today_cst(),
        "latestNav": latest_nav,
        "dayProfit": (latest_nav - prev_nav) * shares,
        "dayPct": day_pct,
        "marketValue": latest_nav * shares,
        "totalProfit": (latest_nav - cost) * shares if cost > 0 else None,
        "totalPct": (latest_nav / cost - 1) * 100 if cost > 0 else None,
    }


def fmt_money(n):
    return f"{n:,.2f}"


def sign(n):
    return "+" if n > 0 else ""


def signed_money(n):
    p = "+" if n > 0 else ("-" if n < 0 else "")
    return f"{p}¥{abs(n):,.2f}"


def build_report(results):
    today = today_cst()
    items = [r for r in results if r["isToday"] and r["dayProfit"] is not None]
    waiting = [r for r in results if not r["isToday"]]
    if not items:
        return None
    total = sum(r["dayProfit"] for r in items)
    total_val = sum(r["marketValue"] for r in items)
    lines = []
    for r in sorted(items, key=lambda x: x["dayProfit"], reverse=True):
        emoji = "🔺" if r["dayProfit"] > 0 else ("🔻" if r["dayProfit"] < 0 else "➖")
        line = (f"{emoji} **{r['name']}**（{r['code']}）："
                f"{signed_money(r['dayProfit'])}（{sign(r['dayPct'])}{r['dayPct']:.2f}%）")
        if r["totalProfit"] is not None:
            line += f"\n　　持仓收益：{signed_money(r['totalProfit'])}（{sign(r['totalPct'])}{r['totalPct']:.2f}%）"
        lines.append(line)
    lines.append("")
    lines.append(f"**当日合计：{signed_money(total)}**")
    lines.append(f"**持仓市值：¥{fmt_money(total_val)}**")
    if waiting:
        names = "、".join(f"{r['name']}({r['code']})" for r in waiting)
        lines.append(f"\n> ⏳ 净值待更新：{names}")
    title = f"基金每日战报 {signed_money(total)}"
    return {"title": title, "desp": "\n\n".join(lines)}


def push(report):
    key = os.environ.get("SCT_SENDKEY", "").strip()
    if not key:
        print("[提示] 未设置 SCT_SENDKEY，仅打印战报（dry run）\n")
        print(report["title"])
        print(report["desp"])
        return
    raw = http_post_form(
        f"https://sctapi.ftqq.com/{urllib.parse.quote(key)}.send",
        {"title": report["title"], "desp": report["desp"]},
    )
    try:
        resp = json.loads(raw)
        # Server酱成功时返回 {"code":0,"error":"SUCCESS","errno":0}
        if resp.get("error") == "SUCCESS" or resp.get("errno") == 0:
            print("[推送] Server酱发送成功")
        else:
            print(f"[推送] Server酱返回异常：{raw[:200]}")
            sys.exit(1)
    except json.JSONDecodeError:
        print(f"[推送] Server酱响应无法解析：{raw[:200]}")
        sys.exit(1)


def main():
    holdings = load_holdings()
    if not holdings:
        print("holdings.json 中没有有效持仓（需要 code 和 shares），未推送")
        return
    results = []
    for h in holdings:
        try:
            fund = fetch_fund(h["code"])
            results.append(calc(fund, h))
            print(f"[OK] {h['code']} {results[-1]['name']} 净值日期 {results[-1]['date']}")
        except Exception as e:
            print(f"[失败] {h['code']}: {e}")
    if not results:
        print("所有基金数据抓取失败，未推送")
        sys.exit(1)
    report = build_report(results)
    if report is None:
        print(f"所有基金净值均未更新到今日({today_cst()})，视为非交易日或未公布，跳过推送")
        return
    push(report)


if __name__ == "__main__":
    main()
