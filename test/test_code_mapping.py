#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试股票代码到新浪代码的映射

测试场景:
1. 6开头 → sh前缀（上海主板）
2. 9开头 → sh前缀（上海B股）
3. 0/3开头 → sz前缀（深圳）
4. 8开头 → bj前缀（北交所）
5. 4开头 → bj前缀（老三板）
6. 不足6位 → 补零
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def to_sina_code(code):
    """复刻 server.py 中的股票代码映射逻辑"""
    c = str(code).zfill(6)
    if c.startswith("6") or c.startswith("9"):
        return f"sh{c}"
    elif c.startswith("8") or c.startswith("4"):
        return f"bj{c}"
    else:
        return f"sz{c}"


def run_tests():
    tests_passed = 0
    tests_failed = 0

    cases = [
        ("600000", "sh600000", "上海主板6开头"),
        ("601398", "sh601398", "上海主板6开头"),
        ("900901", "sh900901", "上海B股9开头"),
        ("000001", "sz000001", "深圳主板0开头"),
        ("002807", "sz002807", "深圳中小板0开头"),
        ("300750", "sz300750", "深圳创业板3开头"),
        ("430047", "bj430047", "北交所4开头"),
        ("830799", "bj830799", "北交所8开头"),
        ("870XXX", None, "占位"),
    ]

    for code, expected, desc in cases:
        if expected is None:
            continue
        result = to_sina_code(code)
        if result == expected:
            print(f"  ✅ {desc}: {code} → {result}")
            tests_passed += 1
        else:
            print(f"  ❌ {desc}: {code} → {result} (期望{expected})")
            tests_failed += 1

    # 测试补零
    result = to_sina_code("1")
    if result == "sz000001":
        print(f"  ✅ 补零: '1' → {result}")
        tests_passed += 1
    else:
        print(f"  ❌ 补零: '1' → {result} (期望sz000001)")
        tests_failed += 1

    result = to_sina_code(600000)
    if result == "sh600000":
        print(f"  ✅ 整数输入: 600000 → {result}")
        tests_passed += 1
    else:
        print(f"  ❌ 整数输入: 600000 → {result} (期望sh600000)")
        tests_failed += 1

    print(f"\n代码映射: {tests_passed}通过, {tests_failed}失败")
    return tests_failed == 0


if __name__ == "__main__":
    print("=" * 60)
    print("  测试: 股票代码到新浪代码映射")
    print("=" * 60)
    success = run_tests()
    sys.exit(0 if success else 1)
