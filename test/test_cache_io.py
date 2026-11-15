#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试缓存读写逻辑

测试场景:
1. 保存缓存再加载，数据一致
2. 加载不存在的缓存文件 → 返回False
3. 加载空data的缓存 → 返回False
4. 加载带BOM的缓存文件 → 能正确读取
5. prevYields中的字符串值能转为float
"""

import sys
import os
import json
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_save_and_load():
    """测试保存再加载，数据一致"""
    # 模拟缓存数据
    cache_data = {
        "lastUpdate": "2026-11-14 21:00:00",
        "data": [
            {"code": "600000", "name": "浦发银行", "price": 10.5, "change": 1.2,
             "yield": 5.23, "totalDividend": 0.55, "divCount": 1, "amount": 3.5},
            {"code": "601398", "name": "工商银行", "price": 5.2, "change": -0.3,
             "yield": 6.15, "totalDividend": 0.32, "divCount": 2, "amount": 8.9},
        ],
        "alerts": [
            {"type": "up", "code": "600000", "name": "浦发银行",
             "oldYield": 4.5, "newYield": 5.23, "price": 10.5,
             "time": "2026-11-14 21:00:00", "message": "测试预警"},
        ],
        "prevYields": {"600000": "5.23", "601398": "6.15"},
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False,
                                      encoding="utf-8") as f:
        json.dump(cache_data, f, ensure_ascii=False)
        tmp_path = f.name

    try:
        # 读取并验证
        with open(tmp_path, "r", encoding="utf-8-sig") as f:
            loaded = json.load(f)

        assert loaded["lastUpdate"] == "2026-11-14 21:00:00"
        assert len(loaded["data"]) == 2
        assert loaded["data"][0]["code"] == "600000"
        assert loaded["data"][0]["yield"] == 5.23
        assert len(loaded["alerts"]) == 1
        assert loaded["alerts"][0]["type"] == "up"

        # prevYields 字符串转 float
        prev_yields = {k: float(v) for k, v in loaded.get("prevYields", {}).items()}
        assert prev_yields["600000"] == 5.23
        assert prev_yields["601398"] == 6.15

        print("  ✅ 保存再加载数据一致")
        return True
    except AssertionError as e:
        print(f"  ❌ 数据不一致: {e}")
        return False
    finally:
        os.unlink(tmp_path)


def test_load_nonexistent():
    """加载不存在的文件 → 返回False"""
    import server
    orig = server.CACHE_FILE
    server.CACHE_FILE = "/nonexistent/path/cache.json"
    try:
        result = server.load_cache_from_file()
        if result == False:
            print("  ✅ 加载不存在的文件返回False")
            return True
        else:
            print(f"  ❌ 期望False，实际{result}")
            return False
    finally:
        server.CACHE_FILE = orig


def test_load_empty_data():
    """加载空data → 返回False"""
    import server
    orig = server.CACHE_FILE

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False,
                                      encoding="utf-8") as f:
        json.dump({"data": [], "alerts": [], "prevYields": {}}, f)
        tmp_path = f.name

    server.CACHE_FILE = tmp_path
    try:
        result = server.load_cache_from_file()
        if result == False:
            print("  ✅ 加载空data返回False")
            return True
        else:
            print(f"  ❌ 期望False，实际{result}")
            return False
    finally:
        server.CACHE_FILE = orig
        os.unlink(tmp_path)


def test_load_bom_file():
    """加载带BOM的缓存文件 → 能正确读取"""
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".json", delete=False) as f:
        # 写入UTF-8 BOM + JSON
        data = {"data": [{"code": "600000", "yield": 5.23}], "alerts": [], "prevYields": {}}
        f.write(b"\xef\xbb\xbf" + json.dumps(data, ensure_ascii=False).encode("utf-8"))
        tmp_path = f.name

    try:
        with open(tmp_path, "r", encoding="utf-8-sig") as f:
            loaded = json.load(f)
        assert len(loaded["data"]) == 1
        assert loaded["data"][0]["code"] == "600000"
        print("  ✅ 带BOM文件正确读取")
        return True
    except Exception as e:
        print(f"  ❌ BOM文件读取失败: {e}")
        return False
    finally:
        os.unlink(tmp_path)


def run_tests():
    tests = [
        test_save_and_load,
        test_load_nonexistent,
        test_load_empty_data,
        test_load_bom_file,
    ]

    passed = 0
    failed = 0

    for test in tests:
        if test():
            passed += 1
        else:
            failed += 1

    print(f"\n缓存读写: {passed}通过, {failed}失败")
    return failed == 0


if __name__ == "__main__":
    print("=" * 60)
    print("  测试: 缓存读写逻辑")
    print("=" * 60)
    success = run_tests()
    sys.exit(0 if success else 1)
