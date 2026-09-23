<#
.SYNOPSIS
    부하 테스트 중 무선 신호를 시각과 함께 기록한다 (PowerShell / Windows).

.DESCRIPTION
    `load_test.py`가 요청 실패를 보고했을 때, **모터 노이즈인지 신호 부족인지**를 가르려면
    그 시각의 신호 세기가 필요하다. 이 스크립트는 **PC ↔ AP 구간**을 1초 간격으로 기록한다.

    ⚠️ 요청 경로는 `PC → AP → picar` 두 구간이다. 이 스크립트는 **앞 구간만** 잰다.
       정작 움직이는 쪽은 picar이므로, **picar 구간을 같이 봐야 한다** — 아래 참고.

    picar 구간(권장, 별도 창):
        ssh pi@192.168.0.42 "while true; do L=`$(iw dev wlan0 link); echo `"`$(date +%T) `$(echo `"`$L`" | grep -oP 'signal:\s*\K-?\d+') dBm`"; sleep 1; done" | Tee-Object picar_wifi.log

    Windows는 신호를 **품질 백분율(0~100%)** 로 보고한다. dBm 환산은 근사식
        dBm ≈ (품질 / 2) - 100
    을 쓴다 (100% ≈ -50dBm, 60% ≈ -70dBm). 절대값보다 **구간 내 변화**를 보는 용도다.

.PARAMETER LogPath
    기록 파일 경로. 기본 wifi_pc.log

.PARAMETER IntervalSec
    샘플 간격(초). 기본 1

.EXAMPLE
    .\wifi_watch.ps1
    .\wifi_watch.ps1 -LogPath run3.log -IntervalSec 0.5
#>
param(
    [string]$LogPath = "wifi_pc.log",
    [double]$IntervalSec = 1.0
)

# 한국어 Windows는 netsh 출력 레이블이 "신호"다. 영문/한글 모두 잡는다.
$SignalLabel = '신호|Signal'
$RateLabel   = '수신 속도|받기 속도|Receive rate'

function Get-WifiSample {
    try {
        $out = netsh wlan show interfaces 2>$null
    } catch {
        return [pscustomobject]@{ Percent = $null; Dbm = $null; Rate = $null; Note = 'netsh 실패' }
    }
    if (-not $out) {
        return [pscustomobject]@{ Percent = $null; Dbm = $null; Rate = $null; Note = '어댑터 없음' }
    }

    $percent = $null
    $rate = $null
    foreach ($line in $out) {
        if ($null -eq $percent -and $line -match "($SignalLabel)\s*:\s*(\d+)\s*%") {
            $percent = [int]$Matches[2]
        }
        if ($null -eq $rate -and $line -match "($RateLabel).*:\s*([\d.]+)") {
            $rate = $Matches[2]
        }
    }

    if ($null -eq $percent) {
        # 연결이 끊기면 "신호" 줄 자체가 사라진다 — 이것이 곧 끊김 신호다.
        return [pscustomobject]@{ Percent = $null; Dbm = $null; Rate = $null; Note = '연결 끊김' }
    }
    [pscustomobject]@{
        Percent = $percent
        Dbm     = [math]::Round($percent / 2.0 - 100, 0)
        Rate    = $rate
        Note    = ''
    }
}

Write-Host "PC <-> AP 구간 기록 시작 (Ctrl+C 로 종료) -> $LogPath"
Write-Host "주의: picar 구간은 별도로 봐야 합니다 (스크립트 주석의 ssh 예시 참고)`n"

$samples = New-Object System.Collections.Generic.List[int]
try {
    while ($true) {
        $t = Get-Date -Format 'HH:mm:ss'
        $s = Get-WifiSample

        if ($null -eq $s.Percent) {
            $line = "$t  ---  $($s.Note)"
            Write-Host $line -ForegroundColor Red
        } else {
            $samples.Add($s.Dbm)
            $rateText = if ($s.Rate) { "  rate=$($s.Rate) Mbps" } else { "" }
            $line = "$t  signal=$($s.Percent)%  ~$($s.Dbm) dBm$rateText"
            # -67dBm(= 66%) 아래로 내려가면 눈에 띄게 표시한다.
            if ($s.Dbm -le -67) { Write-Host $line -ForegroundColor Yellow }
            else { Write-Host $line }
        }
        Add-Content -Path $LogPath -Value $line -Encoding utf8
        Start-Sleep -Seconds $IntervalSec
    }
} finally {
    Write-Host "`n$('=' * 46)"
    if ($samples.Count -gt 0) {
        $min = ($samples | Measure-Object -Minimum).Minimum
        $avg = [math]::Round(($samples | Measure-Object -Average).Average, 0)
        Write-Host "샘플 $($samples.Count)개  최저 $min dBm  평균 $avg dBm"
        if ($min -le -70) {
            Write-Host "최저값이 -70dBm 이하입니다 - 실패가 났다면 신호 부족일 수 있습니다" -ForegroundColor Yellow
        } elseif ($min -le -67) {
            Write-Host "최저값이 -67dBm 이하입니다 - 경계 구간입니다" -ForegroundColor Yellow
        } else {
            Write-Host "구간 내내 양호 - 실패가 났다면 신호 탓으로 보기 어렵습니다"
        }
        Write-Host "13_picar_하드웨어_검증리포트 4.1 표의 '신호(dBm) 최저~평균' 칸에 적으세요: $min ~ $avg"
    } else {
        Write-Host "유효한 샘플이 없습니다 - 무선 어댑터 연결을 확인하세요"
    }
    Write-Host "기록: $LogPath"
}
