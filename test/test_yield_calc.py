#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试股息率计算和分红数据聚合

测试场景:
1. 单次分红股息率计算
2. 多次分红累计计算
3. PRETAX_BONUS_RMB为None → 跳过
4. PRETAX_BONUS_RMB为0 → 跳过
5. 税前分红转每股分红（除以10）
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def calc_yield(total_dividend, price):
    """复刻 server.py 中的股息率计算"""
    if price <= 0 or total_dividend <= 0:
        return None
    return round(total_dividend / price * 100, 2)


def aggregate_dividends(dividends_list):
    """复刻 server.py 中的分红数据聚合逻辑
    dividends_list: [{"bonus": 2.5}, {"bonus": 3.0}] (每10股派X元)
    返回: (total_per_share, count)
    """
    total = 0.0
    count = 0
    for d in dividends_list:
        bonus_raw = d.get("bonus")
        if bonus_raw is None:
            continue
        bonus = float(bonus_raw)
        if bonus <= 0:
            continue
        total += bonus / 10  # 每10股派X元 → 每股派X/10元
        count += 1
    return (round(total, 3), count) if count > 0 else (None, 0)


def run_tests():
    tests_passed = 0
    tests_failed = 0

    def check(desc, condition):
        nonlocal tests_passed, tests_failed
        if condition:
            print(f"  ✅ {desc}")
            tests_passed += 1
        else:
            print(f"  ❌ {desc}")
            tests_failed += 1

    # Test 1: 基本股息率计算
    y = calc_yield(0.55, 10.0)
    check(f"0.55元分红/10元股价 = {y}% (期望5.5%)", y == 5.5)

    # Test 2: 高股息率
    y = calc_yield(2.0, 20.0)
    check(f"2.0元分红/20元股价 = {y}% (期望10.0%)", y == 10.0)

    # Test 3: 股价为0
    y = calc_yield(0.55, 0)
    check("股价为0返回None", y is None)

    # Test 4: 分红为0
    y = calc_yield(0, 10.0)
    check("分红为0返回None", y is None)

    # Test 5: 多次分红累计
    total, count = aggregate_dividends([{"bonus": 2.5}, {"bonus": 3.0}])
    check(f"两次分红(2.5+3.0)/10 = {total}元/股, count={count} (期望0.55, 2)",
          total == 0.55 and count == 2)

    # Test 6: bonus为None → 跳过
    total, count = aggregate_dividends([{"bonus": None}, {"bonus": 3.0}])
    check(f"bonus=None跳过, 剩余0.3元/股, count={count} (期望0.3, 1)",
          total == 0.3 and count == 1)

    # Test 7: bonus为0 → 跳过
    total, count = aggregate_dividends([{"bonus": 0}, {"bonus": 3.0}])
    check(f"bonus=0跳过, 剩余0.3元/股, count={count} (期望0.3, 1)",
          total == 0.3 and count == 1)

    # Test 8: 全部为None → 返回None
    total, count = aggregate_dividends([{"bonus": None}, {"bonus": None}])
    check("全部bonus=None → 返回(None, 0)", total is None and count == 0)

    # Test 9: 三次分红累计
    total, count = aggregate_dividends([{"bonus": 1.0}, {"bonus": 2.0}, {"bonus": 3.0}])
    check(f"三次分红(1+2+3)/10 = {total}元/股, count={count} (期望0.6, 3)",
          total == 0.6 and count == 3)

    # Test 10: 精度测试
    total, count = aggregate_dividends([{"bonus": 1.234}])
    check(f"精度测试: 1.234/10 = {total} (期望0.123)", total == 0.123)

    # Test 11: 负数bonus跳过
    total, count = aggregate_dividends([{"bonus": -1.0}, {"bonus": 3.0}])
    check(f"负数bonus跳过, 剩余0.3, count={count} (期望0.3, 1)",
          total == 0.3 and count == 1)

    # Test 12: 空列表
    total, count = aggregate_dividends([])
    check("空列表 → (None, 0)", total is None and count == 0)

    # Test 13: 混合None/0/正常
    total, count = aggregate_dividends([{"bonus": None}, {"bonus": 0}, {"bonus": 5.0}, {"bonus": 3.0}])
    check(f"混合数据: (5+3)/10={total}, count={count} (期望0.8, 2)",
          total == 0.8 and count == 2)

    print(f"\n股息率计算: {tests_passed}通过, {tests_failed}失败")
    return tests_failed == 0


if __name__ == "__main__":
    print("=" * 60)
    print("  测试: 股息率计算和分红数据聚合")
    print("=" * 60)
    success = run_tests()
    sys.exit(0 if success else 1)
