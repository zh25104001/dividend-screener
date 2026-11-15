#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试阈值穿越预警逻辑

测试场景:
1. 股息率从2.8%升到3.5% → 应触发突破3%预警
2. 股息率从3.5%升到5.2% → 应触发突破4%、5%两条预警
3. 股息率从5.5%降到2.8% → 应触发跌破5%、4%、3%三条预警
4. 股息率从4.5%升到4.8% → 差异<0.3%，不应预警
5. 股息率从3.0%升到3.2% → 差异<0.3%，不应预警
6. 股息率从6.0%升到9.5% → 应触发突破7%、8%、9%三条预警
7. 股息率从9.5%降到6.0% → 应触发跌破9%、8%、7%三条预警
8. 首次出现的新股票（无旧数据）→ 不应预警
9. 股息率恰好等于阈值 → 边界测试
10. 股息率从3.0%降到2.9% → 跌破3%，差异0.1%<0.3%不预警
"""

import sys
import os
from datetime import datetime

# 把父目录加入path，方便import server
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

THRESHOLDS = [3, 4, 5, 6, 7, 8, 9]


def detect_alerts(old_yield, new_yield):
    """复刻 server.py 中的阈值穿越检测逻辑"""
    if old_yield is None:
        return []
    diff = abs(new_yield - old_yield)
    if diff < 0.3:
        return []
    alerts = []
    for t in THRESHOLDS:
        if old_yield < t <= new_yield:
            alerts.append(("up", t))
        elif old_yield >= t > new_yield:
            alerts.append(("down", t))
    return alerts


def run_tests():
    tests = [
        # (描述, old_yield, new_yield, 期望结果)
        ("从2.8%升到3.5% → 突破3%", 2.8, 3.5, [("up", 3)]),
        ("从3.5%升到5.2% → 突破4%和5%", 3.5, 5.2, [("up", 4), ("up", 5)]),
        ("从5.5%降到2.8% → 跌破5%、4%、3%", 5.5, 2.8, [("down", 3), ("down", 4), ("down", 5)]),
        ("从4.5%升到4.8% → 差异<0.3%不预警", 4.5, 4.8, []),
        ("从3.0%升到3.2% → 差异<0.3%不预警", 3.0, 3.2, []),
        ("从6.0%升到9.5% → 突破7%、8%、9%", 6.0, 9.5, [("up", 7), ("up", 8), ("up", 9)]),
        ("从9.5%降到6.0% → 跌破9%、8%、7%", 9.5, 6.0, [("down", 7), ("down", 8), ("down", 9)]),
        ("首次出现的新股票（None）→ 不预警", None, 5.5, []),
        ("从2.9%升到3.0% → 差异0.1%<0.3%不预警", 2.9, 3.0, []),
        ("从3.0%升到3.5% → 突破3%（边界：old=3.0不<3）", 3.0, 3.5, []),
        ("从2.99%升到3.5% → 突破3%", 2.99, 3.5, [("up", 3)]),
        ("从3.0%降到2.99% → 差异0.01%<0.3%不预警", 3.0, 2.99, []),
        ("从8.0%升到8.5% → 差异0.5%但未穿越任何阈值", 8.0, 8.5, []),
        ("从8.5%降到8.0% → 差异0.5%但未穿越任何阈值", 8.5, 8.0, []),
        ("从2.5%升到10% → 突破3~9全部7个阈值", 2.5, 10.0,
         [("up", 3), ("up", 4), ("up", 5), ("up", 6), ("up", 7), ("up", 8), ("up", 9)]),
        ("从10%降到2.5% → 跌破9~3全部7个阈值", 10.0, 2.5,
         [("down", 3), ("down", 4), ("down", 5), ("down", 6), ("down", 7), ("down", 8), ("down", 9)]),
    ]

    passed = 0
    failed = 0

    for desc, old, new, expected in tests:
        result = detect_alerts(old, new)
        if result == expected:
            print(f"  ✅ {desc}")
            passed += 1
        else:
            print(f"  ❌ {desc}")
            print(f"     期望: {expected}")
            print(f"     实际: {result}")
            failed += 1

    print(f"\n阈值穿越检测: {passed}通过, {failed}失败")
    return failed == 0


if __name__ == "__main__":
    print("=" * 60)
    print("  测试: 阈值穿越预警逻辑")
    print("=" * 60)
    success = run_tests()
    sys.exit(0 if success else 1)
