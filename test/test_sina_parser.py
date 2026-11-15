#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试新浪行情数据解析

测试场景:
1. 正常行情行 → 正确解析code、price、change
2. 行情行为空（停牌）→ 跳过
3. 行情行字段不足 → 跳过
4. var前缀 → 正确解析（re.search而非re.match）
5. 批量多行 → 全部解析
"""

import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def parse_sina_line(line):
    """复刻 server.py 中的新浪行情解析逻辑"""
    m = re.search(r'hq_str_\w{2}(\d{6})="([^"]*)"', line)
    if not m:
        return None
    code = m.group(1)
    fields = m.group(2).split(",")
    if len(fields) < 10:
        return None
    try:
        price = float(fields[3])
        if price <= 0:
            price = float(fields[2])
        if price <= 0:
            return None
        prev_close = float(fields[2])
        change = round((price - prev_close) / prev_close * 100, 2) if prev_close != 0 else 0
        amount = float(fields[9]) if len(fields) > 9 else 0
        return {"code": code, "price": price, "change": change, "amount": amount}
    except (ValueError, IndexError):
        return None


def run_tests():
    tests_passed = 0
    tests_failed = 0

    # Test 1: 正常行情行
    line = 'var hq_str_sh600000="浦发银行,10.21,10.19,10.40,10.44,10.12,10.39,10.40,76157313,786507841.000,225000,10.39,46000,10.38";'
    result = parse_sina_line(line)
    if result and result["code"] == "600000" and result["price"] == 10.40:
        print(f"  ✅ 正常行情行: {result['code']} price={result['price']} change={result['change']}%")
        tests_passed += 1
    else:
        print(f"  ❌ 正常行情行解析失败: {result}")
        tests_failed += 1

    # Test 2: 停牌（price=0, prev_close=0）
    line = 'var hq_str_sh600001="停牌股,0,0,0,0,0,0,0,0,0";'
    result = parse_sina_line(line)
    if result is None:
        print(f"  ✅ 停牌股正确跳过")
        tests_passed += 1
    else:
        print(f"  ❌ 停牌股应跳过，实际: {result}")
        tests_failed += 1

    # Test 3: 字段不足
    line = 'var hq_str_sh600002="短数据,1.0,2.0";'
    result = parse_sina_line(line)
    if result is None:
        print(f"  ✅ 字段不足正确跳过")
        tests_passed += 1
    else:
        print(f"  ❌ 字段不足应跳过，实际: {result}")
        tests_failed += 1

    # Test 4: var前缀（re.search vs re.match的关键区别）
    line = 'var hq_str_sz000001="平安银行,12.5,12.3,12.8,13.0,12.2,12.7,12.8,1000000,12800000.0";'
    result = parse_sina_line(line)
    if result and result["code"] == "000001" and result["price"] == 12.8:
        print(f"  ✅ var前缀正确解析(re.search): {result['code']} price={result['price']}")
        tests_passed += 1
    else:
        print(f"  ❌ var前缀解析失败: {result}")
        tests_failed += 1

    # Test 5: 空字符串
    line = 'var hq_str_sh600003="";'
    result = parse_sina_line(line)
    if result is None:
        print(f"  ✅ 空字符串正确跳过")
        tests_passed += 1
    else:
        print(f"  ❌ 空字符串应跳过，实际: {result}")
        tests_failed += 1

    # Test 6: 北交所股票(bj前缀)
    line = 'var hq_str_bj430047="诺思兰德,10.5,10.3,10.8,11.0,10.2,10.7,10.8,500000,5400000.0";'
    result = parse_sina_line(line)
    if result and result["code"] == "430047" and result["price"] == 10.8:
        print(f"  ✅ 北交所股票正确解析: {result['code']} price={result['price']}")
        tests_passed += 1
    else:
        print(f"  ❌ 北交所股票解析失败: {result}")
        tests_failed += 1

    # Test 7: 涨停（price=最高价）
    line = 'var hq_str_sh601398="工商银行,5.0,5.0,5.5,5.5,5.0,5.0,5.5,2000000,11000000.0";'
    result = parse_sina_line(line)
    if result and result["code"] == "601398" and result["change"] == 10.0:
        print(f"  ✅ 涨停股正确计算涨幅: {result['code']} change={result['change']}%")
        tests_passed += 1
    else:
        print(f"  ❌ 涨停股计算失败: {result}")
        tests_failed += 1

    # Test 8: 跌停
    line = 'var hq_str_sh601398="工商银行,5.0,5.0,4.5,5.0,4.5,4.5,4.5,2000000,9000000.0";'
    result = parse_sina_line(line)
    if result and result["code"] == "601398" and result["change"] == -10.0:
        print(f"  ✅ 跌停股正确计算跌幅: {result['code']} change={result['change']}%")
        tests_passed += 1
    else:
        print(f"  ❌ 跌停股计算失败: {result}")
        tests_failed += 1

    # Test 9: price=0但prev_close有值 → fallback到prev_close
    line = 'var hq_str_sh600004="测试股,10.0,10.5,0,0,0,0,0,0,0";'
    result = parse_sina_line(line)
    if result and result["price"] == 10.5:
        print(f"  ✅ price=0时fallback到prev_close: price={result['price']}")
        tests_passed += 1
    else:
        print(f"  ❌ price=0 fallback失败: {result}")
        tests_failed += 1

    print(f"\n新浪行情解析: {tests_passed}通过, {tests_failed}失败")
    return tests_failed == 0


if __name__ == "__main__":
    print("=" * 60)
    print("  测试: 新浪行情数据解析")
    print("=" * 60)
    success = run_tests()
    sys.exit(0 if success else 1)
