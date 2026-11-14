@echo off
chcp 65001 >nul
echo 正在启动A股高股息率筛选器...

REM 依次尝试找到可用的Python
set "PY="

REM 1. 尝试PATH中的python
where python >nul 2>&1 && (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3,8) else 1)" >nul 2>&1 && set "PY=python"
)

REM 2. 尝试常见安装路径
if not defined PY (
    for %%P in (
        "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python39\python.exe"
        "C:\Python312\python.exe"
        "C:\Python311\python.exe"
        "C:\Python310\python.exe"
    ) do (
        if exist %%P (
            set "PY=%%~P"
            goto found
        )
    )
)

:found
if not defined PY (
    echo 未找到Python 3，请先安装 Python 3.8+ 或将其加入PATH
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo 使用Python: %PY%
"%PY%" start.py
pause
