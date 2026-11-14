# A股高股息率筛选器 - PowerShell后端
# 启动: powershell -ExecutionPolicy Bypass -File server.ps1
# 然后浏览器访问: http://localhost:8081

param(
    [int]$Port = 8081
)

$ErrorActionPreference = "SilentlyContinue"

# ===== 全局缓存（线程安全） =====
$script:cacheFile = "$PSScriptRoot\cache.json"
$script:cache = @{
    data = @()
    jsonBytes = $null
    lastUpdate = $null
    updating = $false
    prevYields = @{}
    alerts = @()
}
$script:lock = [System.Threading.Mutex]::new($false, "DividendCacheLock")

# ===== 启动时加载本地缓存 =====
function Load-CacheFromFile {
    if (Test-Path $script:cacheFile) {
        try {
            $saved = Get-Content $script:cacheFile -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($saved.data -and $saved.data.Count -gt 0) {
                $script:cache.data = $saved.data
                $script:cache.alerts = $saved.alerts
                $script:cache.prevYields = @{}
                if ($saved.prevYields) {
                    foreach ($p in $saved.prevYields.PSObject.Properties) {
                        $script:cache.prevYields[$p.Name] = [decimal]$p.Value
                    }
                }
                # 预生成JSON
                $snapshot = @{
                    success = $true
                    count = $saved.data.Count
                    lastUpdate = $saved.lastUpdate
                    updating = $true
                    alertCount = 0
                    data = $saved.data
                    alerts = $saved.alerts
                }
                $jsonStr = $snapshot | ConvertTo-Json -Depth 5 -Compress
                $script:cache.jsonBytes = [System.Text.Encoding]::UTF8.GetBytes($jsonStr)
                $script:cache.lastUpdate = $saved.lastUpdate
                Write-Host "[缓存] 已加载上次数据: $($saved.data.Count) 只股票, 更新于 $($saved.lastUpdate)" -ForegroundColor Green
                return $true
            }
        } catch {
            Write-Host "[缓存] 读取缓存失败: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }
    return $false
}

# ===== 保存缓存到文件 =====
function Save-CacheToFile {
    try {
        $toSave = @{
            lastUpdate = if ($script:cache.lastUpdate) { $script:cache.lastUpdate.ToString("yyyy-MM-dd HH:mm:ss") } else { $null }
            data = $script:cache.data
            alerts = $script:cache.alerts
            prevYields = $script:cache.prevYields
        }
        $jsonStr = $toSave | ConvertTo-Json -Depth 5 -Compress
        [System.IO.File]::WriteAllText($script:cacheFile, $jsonStr, [System.Text.Encoding]::UTF8)
        Write-Host "[缓存] 已保存到文件" -ForegroundColor Green
    } catch {
        Write-Host "[缓存] 保存失败: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

# 启动时加载缓存
$hasCache = Load-CacheFromFile

# ===== 获取过去12个月分红记录 =====
function Get-DividendData {
    Write-Host "  [1/2] 获取分红数据..." -ForegroundColor Cyan
    $headers = @{ "User-Agent" = "Mozilla/5.0"; "Referer" = "https://data.eastmoney.com/" }
    $cutoffDate = (Get-Date).AddYears(-1).ToString("yyyy-MM-dd")
    $allDividends = @{}
    $totalPages = 50

    for ($page = 1; $page -le $totalPages; $page++) {
        $url = "https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_SHAREBONUS_DET&columns=SECURITY_CODE,SECURITY_NAME_ABBR,PRETAX_BONUS_RMB,EX_DIVIDEND_DATE,ASSIGN_PROGRESS&source=WEB&client=WEB&pageSize=100&pageNumber=$page&sortColumns=EX_DIVIDEND_DATE&sortTypes=-1&filter=(ASSIGN_PROGRESS=%22%E5%AE%9E%E6%96%BD%E5%88%86%E9%85%8D%22)(EX_DIVIDEND_DATE%3E=%27$cutoffDate%27)"
        try {
            $r = Invoke-WebRequest -Uri $url -Headers $headers -TimeoutSec 10 -UseBasicParsing
            $json = $r.Content | ConvertFrom-Json
            if (-not $json.success -or -not $json.result) { break }
            foreach ($item in $json.result.data) {
                $code = $item.SECURITY_CODE
                $bonus = [decimal]$item.PRETAX_BONUS_RMB
                if ($bonus -le 0) { continue }
                $perShare = $bonus / 10
                if ($allDividends.ContainsKey($code)) {
                    $allDividends[$code].totalDividend += $perShare
                    $allDividends[$code].count++
                } else {
                    $allDividends[$code] = @{
                        code = $code
                        name = $item.SECURITY_NAME_ABBR
                        totalDividend = $perShare
                        count = 1
                    }
                }
            }
            if ($page % 10 -eq 0) { Write-Host "    分红数据: 已获取 $page / $totalPages 页" -ForegroundColor Gray }
        } catch {
            Write-Host "    第${page}页获取失败: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }

    Write-Host "    分红数据完成: $($allDividends.Count) 只股票有分红记录" -ForegroundColor Green
    return $allDividends
}

# ===== 从新浪获取实时行情 =====
function Get-RealtimeQuotes {
    param([array]$Codes)

    Write-Host "  [2/2] 获取实时行情..." -ForegroundColor Cyan
    $quotes = @{}
    $batchSize = 100

    $sinaCodes = $Codes | ForEach-Object {
        $c = $_.ToString().PadLeft(6, '0')
        if ($c.StartsWith('6') -or $c.StartsWith('9')) { "sh$c" }
        elseif ($c.StartsWith('8') -or $c.StartsWith('4')) { "bj$c" }
        else { "sz$c" }
    }

    $totalBatches = [math]::Ceiling($sinaCodes.Count / $batchSize)
    $batchNum = 0

    for ($i = 0; $i -lt $sinaCodes.Count; $i += $batchSize) {
        $batchNum++
        $batch = $sinaCodes[$i..([math]::Min($i + $batchSize - 1, $sinaCodes.Count - 1))]
        $codeStr = $batch -join ','
        $url = "https://hq.sinajs.cn/list=$codeStr"

        try {
            $r = Invoke-WebRequest -Uri $url -Headers @{ "User-Agent" = "Mozilla/5.0"; "Referer" = "https://finance.sina.com.cn" } -TimeoutSec 10 -UseBasicParsing
            $lines = $r.Content -split "`n" | Where-Object { $_.Trim() -ne '' }

            foreach ($line in $lines) {
                if ($line -match 'hq_str_\w{2}(\d{6})="([^"]*)"') {
                    $code = $matches[1]
                    $fields = $matches[2] -split ','
                    if ($fields.Count -ge 10) {
                        $price = [decimal]$fields[3]
                        if ($price -le 0) { $price = [decimal]$fields[2] }
                        if ($price -gt 0) {
                            $quotes[$code] = @{
                                price = $price
                                prevClose = [decimal]$fields[2]
                                change = if ([decimal]$fields[2] -ne 0) { [math]::Round(($price - [decimal]$fields[2]) / [decimal]$fields[2] * 100, 2) } else { 0 }
                                volume = [decimal]$fields[8]
                                amount = [decimal]$fields[9]
                            }
                        }
                    }
                }
            }
            if ($batchNum % 5 -eq 0) { Write-Host "    行情数据: 已获取 $batchNum / $totalBatches 批" -ForegroundColor Gray }
        } catch {
            Write-Host "    行情批次${batchNum}/${totalBatches}失败: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }

    Write-Host "    行情数据完成: $($quotes.Count) 只股票有实时价格" -ForegroundColor Green
    return $quotes
}

# ===== 合并数据，计算股息率 =====
function Update-StockData {
    $script:lock.WaitOne()
    if ($script:cache.updating) {
        $script:lock.ReleaseMutex()
        return
    }
    $script:cache.updating = $true
    $script:lock.ReleaseMutex()

    Write-Host "[更新数据] $(Get-Date -Format 'HH:mm:ss')" -ForegroundColor Cyan

    $dividends = Get-DividendData
    $codes = @($dividends.Keys)
    $quotes = Get-RealtimeQuotes -Codes $codes

    $result = @()
    foreach ($code in $dividends.Keys) {
        $div = $dividends[$code]
        if (-not $quotes.ContainsKey($code)) { continue }

        $q = $quotes[$code]
        $price = $q.price
        $totalDiv = $div.totalDividend

        if ($price -le 0 -or $totalDiv -le 0) { continue }

        $yield = [math]::Round($totalDiv / $price * 100, 2)

        $result += [PSCustomObject]@{
            code = $code
            name = $div.name
            price = [math]::Round($price, 2)
            change = $q.change
            yield = $yield
            totalDividend = [math]::Round($totalDiv, 3)
            divCount = $div.count
            amount = [math]::Round($q.amount / 100000000, 2)
        }
    }

    $result = $result | Sort-Object yield -Descending

    $script:lock.WaitOne()
    $script:cache.data = $result
    $script:cache.lastUpdate = Get-Date
    $script:cache.updating = $false
    $script:lock.ReleaseMutex()

    $high5 = ($result | Where-Object { $_.yield -ge 5 }).Count
    Write-Host "[完成] 共 $($result.Count) 只有分红记录的股票，其中 $high5 只股息率>=5%" -ForegroundColor Green
}

# ===== 后台数据加载（Runspace） =====
function Start-BackgroundUpdate {
    $ps = [PowerShell]::Create()
    $ps.AddScript({
        param($parentScript)
        # 在子runspace中执行父脚本的函数
        . $parentScript
        Update-StockData
    }).AddArgument($null) | Out-Null
    $handle = $ps.BeginInvoke()
    return @{ ps = $ps; handle = $handle }
}

# ===== HTTP服务器 =====
$html = Get-Content "$PSScriptRoot\index.html" -Raw -Encoding UTF8

$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add("http://localhost:$Port/")
$listener.Start()
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  A股高股息率筛选器已启动" -ForegroundColor Cyan
Write-Host "  浏览器访问: http://localhost:$Port" -ForegroundColor Yellow
Write-Host "  按 Ctrl+C 停止" -ForegroundColor Gray
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 首次加载数据 - 用Start-Job后台执行，不阻塞HTTP
Write-Host "正在后台加载数据，浏览器可以先打开..." -ForegroundColor Yellow
$updateJob = Start-Job -ScriptBlock {
    param($scriptPath)
    & $scriptPath -Command "Update-StockData"
} -ArgumentList $PSCommandPath

# 实际上Start-Job启动新进程，无法共享$script:cache
# 改用Runspace
Stop-Job $updateJob -ErrorAction SilentlyContinue
Remove-Job $updateJob -ErrorAction SilentlyContinue

# 用Runspace异步加载数据
$runspace = [RunspaceFactory]::CreateRunspace()
$runspace.Open()
$ps = [PowerShell]::Create()
$ps.Runspace = $runspace

# 把函数定义和cache引用传进去
$ps.AddScript({
    param($cache, $lock, $cacheFilePath)

    # 重新定义函数（子runspace无法访问父scope）
    function Get-DividendData {
        $headers = @{ "User-Agent" = "Mozilla/5.0"; "Referer" = "https://data.eastmoney.com/" }
        $cutoffDate = (Get-Date).AddYears(-1).ToString("yyyy-MM-dd")
        $allDividends = @{}

        for ($page = 1; $page -le 50; $page++) {
            $url = "https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_SHAREBONUS_DET&columns=SECURITY_CODE,SECURITY_NAME_ABBR,PRETAX_BONUS_RMB,EX_DIVIDEND_DATE,ASSIGN_PROGRESS&source=WEB&client=WEB&pageSize=100&pageNumber=$page&sortColumns=EX_DIVIDEND_DATE&sortTypes=-1&filter=(ASSIGN_PROGRESS=%22%E5%AE%9E%E6%96%BD%E5%88%86%E9%85%8D%22)(EX_DIVIDEND_DATE%3E=%27$cutoffDate%27)"
            try {
                $r = Invoke-WebRequest -Uri $url -Headers $headers -TimeoutSec 10 -UseBasicParsing
                $json = $r.Content | ConvertFrom-Json
                if (-not $json.success -or -not $json.result) { break }
                foreach ($item in $json.result.data) {
                    $code = $item.SECURITY_CODE
                    $bonus = [decimal]$item.PRETAX_BONUS_RMB
                    if ($bonus -le 0) { continue }
                    $perShare = $bonus / 10
                    if ($allDividends.ContainsKey($code)) {
                        $allDividends[$code].totalDividend += $perShare
                        $allDividends[$code].count++
                    } else {
                        $allDividends[$code] = @{ code = $code; name = $item.SECURITY_NAME_ABBR; totalDividend = $perShare; count = 1 }
                    }
                }
            } catch {}
        }
        return $allDividends
    }

    function Get-RealtimeQuotes {
        param([array]$Codes)
        $quotes = @{}
        $sinaCodes = $Codes | ForEach-Object {
            $c = $_.ToString().PadLeft(6, '0')
            if ($c.StartsWith('6') -or $c.StartsWith('9')) { "sh$c" }
            elseif ($c.StartsWith('8') -or $c.StartsWith('4')) { "bj$c" }
            else { "sz$c" }
        }
        for ($i = 0; $i -lt $sinaCodes.Count; $i += 100) {
            $batch = $sinaCodes[$i..([math]::Min($i + 99, $sinaCodes.Count - 1))]
            $url = "https://hq.sinajs.cn/list=$($batch -join ',')"
            try {
                $r = Invoke-WebRequest -Uri $url -Headers @{ "User-Agent" = "Mozilla/5.0"; "Referer" = "https://finance.sina.com.cn" } -TimeoutSec 10 -UseBasicParsing
                foreach ($line in ($r.Content -split "`n")) {
                    if ($line -match 'hq_str_\w{2}(\d{6})="([^"]*)"') {
                        $code = $matches[1]
                        $f = $matches[2] -split ','
                        if ($f.Count -ge 10) {
                            $price = [decimal]$f[3]
                            if ($price -le 0) { $price = [decimal]$f[2] }
                            if ($price -gt 0) {
                                $chg = if ([decimal]$f[2] -ne 0) { [math]::Round(([decimal]$f[3] - [decimal]$f[2]) / [decimal]$f[2] * 100, 2) } else { 0 }
                                $quotes[$code] = @{ price = $price; change = $chg; amount = [decimal]$f[9] }
                            }
                        }
                    }
                }
            } catch {}
        }
        return $quotes
    }

    # 执行更新
    $lock.WaitOne()
    $cache.updating = $true
    $lock.ReleaseMutex()

    $dividends = Get-DividendData
    $quotes = Get-RealtimeQuotes -Codes @($dividends.Keys)

    $result = @()
    foreach ($code in $dividends.Keys) {
        if (-not $quotes.ContainsKey($code)) { continue }
        $div = $dividends[$code]
        $q = $quotes[$code]
        if ($q.price -le 0 -or $div.totalDividend -le 0) { continue }
        $result += [PSCustomObject]@{
            code = $code; name = $div.name
            price = [math]::Round($q.price, 2); change = $q.change
            yield = [math]::Round($div.totalDividend / $q.price * 100, 2)
            totalDividend = [math]::Round($div.totalDividend, 3)
            divCount = $div.count
            amount = [math]::Round($q.amount / 100000000, 2)
        }
    }
    $result = $result | Sort-Object yield -Descending

    # ===== 阈值穿越检测 =====
    $lock.WaitOne()
    $prevYields = $cache.prevYields.Clone()
    $lock.ReleaseMutex()

    $newAlerts = @()
    $now = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    foreach ($stock in $result) {
        $code = $stock.code
        $oldYield = $null
        if ($prevYields.ContainsKey($code)) { $oldYield = [decimal]$prevYields[$code] }
        $newYield = [decimal]$stock.yield

        if ($oldYield -ne $null) {
            # 上升穿越5%: 从<5%升到>=5%
            if ($oldYield -lt 5 -and $newYield -ge 5) {
                $newAlerts += [PSCustomObject]@{
                    type = "up"; code = $code; name = $stock.name
                    oldYield = [math]::Round($oldYield, 2); newYield = $newYield
                    price = $stock.price; time = $now
                    message = "$($stock.name)($code) 股息率从 $([math]::Round($oldYield,2))% 升至 $($newYield)%，突破5%关口"
                }
            }
            # 下降跌破4%: 从>=4%降到<4%
            elseif ($oldYield -ge 4 -and $newYield -lt 4) {
                $newAlerts += [PSCustomObject]@{
                    type = "down"; code = $code; name = $stock.name
                    oldYield = [math]::Round($oldYield, 2); newYield = $newYield
                    price = $stock.price; time = $now
                    message = "$($stock.name)($code) 股息率从 $([math]::Round($oldYield,2))% 降至 $($newYield)%，跌破4%关口"
                }
            }
        }
    }

    # 更新快照
    $newPrevYields = @{}
    foreach ($stock in $result) { $newPrevYields[$stock.code] = $stock.yield }

    # 合并预警（保留最近100条）
    $lock.WaitOne()
    $allAlerts = @($newAlerts) + $cache.alerts
    if ($allAlerts.Count -gt 100) { $allAlerts = $allAlerts[0..99] }
    $cache.alerts = $allAlerts
    $cache.prevYields = $newPrevYields
    $lock.ReleaseMutex()

    if ($newAlerts.Count -gt 0) {
        Write-Host "[预警] 发现 $($newAlerts.Count) 条股息率穿越提醒" -ForegroundColor Yellow
        foreach ($a in $newAlerts) {
            $icon = if ($a.type -eq "up") { "↑" } else { "↓" }
            Write-Host "  $icon $($a.message)" -ForegroundColor $(if ($a.type -eq "up") { "Green" } else { "Red" })
        }
    }

    # 预生成JSON（在后台线程做，不阻塞HTTP）
    $lock.WaitOne()
    $alertSnapshot = $cache.alerts
    $lock.ReleaseMutex()

    $snapshot = @{
        success = $true
        count = $result.Count
        lastUpdate = $now
        updating = $false
        alertCount = $newAlerts.Count
        data = $result
        alerts = $alertSnapshot
    }
    $jsonStr = $snapshot | ConvertTo-Json -Depth 5 -Compress
    $jsonBytesArr = [System.Text.Encoding]::UTF8.GetBytes($jsonStr)

    $lock.WaitOne()
    $cache.data = $result
    $cache.jsonBytes = $jsonBytesArr
    $cache.lastUpdate = Get-Date
    $cache.updating = $false
    $lock.ReleaseMutex()

    # 保存缓存到文件（在后台线程做，不阻塞HTTP）
    try {
        $toSave = @{
            lastUpdate = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
            data = $result
            alerts = $cache.alerts
            prevYields = $cache.prevYields
        }
        $saveJson = $toSave | ConvertTo-Json -Depth 5 -Compress
        [System.IO.File]::WriteAllText($cacheFilePath, $saveJson, [System.Text.Encoding]::UTF8)
        Write-Host "[缓存] 已保存到文件" -ForegroundColor Green
    } catch {
        Write-Host "[缓存] 保存失败: $($_.Exception.Message)" -ForegroundColor Yellow
    }

}).AddArgument($script:cache).AddArgument($script:lock).AddArgument($script:cacheFile) | Out-Null

$asyncHandle = $ps.BeginInvoke()
$script:shared = @{
    ps = $ps
    asyncHandle = $asyncHandle
    cache = $script:cache
    lock = $script:lock
}
Write-Host "后台数据加载已启动，HTTP服务正常监听..." -ForegroundColor Green

# 定时更新定时器 - 每5分钟更新一次
$updateTimer = New-Object System.Timers.Timer
$updateTimer.Interval = 300000  # 5分钟
$updateTimer.AutoReset = $true

# 用同步哈希表在Runspace间共享状态
$script:shared = @{
    ps = $ps
    asyncHandle = $asyncHandle
    cache = $script:cache
    lock = $script:lock
}

Register-ObjectEvent -InputObject $updateTimer -EventName Elapsed -Action {
    # 用MessageData传递引用，避免scope问题
    $shared = $Event.MessageData
    $lock = $shared.lock
    $cache = $shared.cache

    $lock.WaitOne()
    $isUpdating = $cache.updating
    $lock.ReleaseMutex()

    if ($isUpdating) { return }

    # 上一次完成才能启动新一轮
    if ($shared.asyncHandle -and -not $shared.asyncHandle.IsCompleted) { return }

    Write-Host "[定时] 启动新一轮数据更新..." -ForegroundColor Cyan
    $shared.asyncHandle = $shared.ps.BeginInvoke()
} -MessageData $script:shared | Out-Null
$updateTimer.Start()

# HTTP监听循环
while ($listener.IsListening) {
    $context = $listener.GetContext()
    $req = $context.Request
    $res = $context.Response
    $path = $req.Url.LocalPath

    # 允许跨域（支持直接双击打开index.html）
    try { $res.Headers["Access-Control-Allow-Origin"] = "*" } catch {}

    if ($path -eq "/api/data") {
        $script:lock.WaitOne()
        $cachedBytes = $script:cache.jsonBytes
        $isUpdating = $script:cache.updating
        $script:lock.ReleaseMutex()

        if ($cachedBytes) {
            $res.ContentType = "application/json; charset=utf-8"
            $res.ContentLength64 = $cachedBytes.Length
            $res.OutputStream.Write($cachedBytes, 0, $cachedBytes.Length)
        } else {
            # 数据还没加载完，返回loading状态
            $loadingJson = '{"success":true,"count":0,"lastUpdate":null,"updating":true,"data":[]}'
            $bytes = [System.Text.Encoding]::UTF8.GetBytes($loadingJson)
            $res.ContentType = "application/json; charset=utf-8"
            $res.ContentLength64 = $bytes.Length
            $res.OutputStream.Write($bytes, 0, $bytes.Length)
        }
    }
    elseif ($path -eq "/" -or $path -eq "/index.html") {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($html)
        $res.ContentType = "text/html; charset=utf-8"
        $res.ContentLength64 = $bytes.Length
        $res.OutputStream.Write($bytes, 0, $bytes.Length)
    }
    else {
        $res.StatusCode = 404
    }
    $res.Close()
}
