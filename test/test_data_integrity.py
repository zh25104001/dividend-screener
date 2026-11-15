#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试数据完整性检查逻辑

测试场景:
1. 首次加载（上轮0只）→ 任何数据量都应通过
2. 数据量≥95% → 应通过
3. 数据量<95% → 应跳过（保留旧数据）
4. 数据量恰好95% → 应通过（边界）
5. 数据量为0 → 应跳过
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def check_integrity(prev_count, new_count):
    """复刻 server.py 中的数据完整性检查逻辑"""
    if prev_count > 0 and new_count < prev_count * 0.95:
        return False  # 不完整，跳过
    return True  # 完整，通过


def run_tests():
    tests = [
        ("首次加载(0→3480) → 通过", 0, 3480, True),
        ("数据量100% → 通过", 3480, 3480, True),
        ("数据量≥95% → 通过", 3480, 3480, True),
        ("数据量95% → 通过(边界)", 3480, int(3480 * 0.95), True),
        ("数据量94.9% → 跳过", 3480, int(3480 * 0.949), False),
        ("数据量50% → 跳过", 3480, 1740, False),
        ("数据量0 → 跳过", 3480, 0, False),
        ("数据量1只(上轮0) → 通过", 0, 1, True),
        ("数据量3306(3480的95%) → 通过", 3480, 3306, True),
        ("数据量3305(3480的94.97%) → 跳过", 3480, 3305, False),
    ]

    passed = 0
    failed = 0

    for desc, prev, new, expected in tests:
        result = check_integrity(prev, new)
        if result == expected:
            print(f"  ✅ {desc}")
            passed += 1
        else:
            print(f"  ❌ {desc}")
            print(f"     期望: {'通过' if expected else '跳过'}")
            print(f"     实际: {'通过' if result else '跳过'}")
            failed += 1

    print(f"\n数据完整性检查: {passed}通过, {failed}失败")
    return failed == 0


if __name__ == "__main__":
    print("=" * 60)
    print("  测试: 数据完整性检查逻辑")
    print("=" * 60)
    success = run_tests()
    sys.exit(0 if success else 1)
