<#
.SYNOPSIS
  슬로모션 영상에 프레임 번호를 새긴 사본을 만든다 — VLC에서 E 키로 한 프레임씩 넘기며 번호를 읽기 위함.
  (KPI 물리 피드백 지연 교차 확인: 손 정지 F0 → LED·AI Hand 반응 프레임 차이 × 1000 / 촬영 fps)

.EXAMPLE
  .\scripts\pc\number_frames.ps1 -Path D:\slowmo\trial.mp4
  .\scripts\pc\number_frames.ps1 -Path D:\slowmo\session1.mp4 -Start 12.5 -Duration 4   # 12.5초부터 4초만

.NOTES
  ffmpeg 필요: winget install Gyan.FFmpeg  (또는 scoop install ffmpeg) — 설치 뒤 PowerShell 창을 새로 연다.
  번호는 잘라낸 구간 안에서 0부터 센다. 지연은 프레임 '차이'만 쓰므로 상관없다.
  휴대폰은 240fps로 찍어도 파일을 30fps 재생용으로 저장하기도 한다 — 계산은 항상 '촬영 fps'로 한다(아래 출력 참고).
#>
param(
    [Parameter(Mandatory = $true)][string]$Path,
    [double]$Start = -1,
    [double]$Duration = -1,
    [string]$OutDir = ""
)

$ErrorActionPreference = "Stop"

foreach ($tool in "ffmpeg", "ffprobe") {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        Write-Host "$tool 이 없습니다. 설치: winget install Gyan.FFmpeg  (설치 뒤 PowerShell 창을 새로 여세요)" -ForegroundColor Red
        exit 1
    }
}
if (-not (Test-Path -LiteralPath $Path)) {
    Write-Host "영상 파일이 없습니다: $Path" -ForegroundColor Red
    exit 1
}
$src = (Resolve-Path -LiteralPath $Path).Path
if (-not $OutDir) { $OutDir = Split-Path -Parent $src }
$name = [System.IO.Path]::GetFileNameWithoutExtension($src)
$suffix = ""
if ($Start -ge 0) { $suffix = "_from{0}s" -f $Start }
$out = Join-Path $OutDir ("{0}{1}_numbered.mp4" -f $name, $suffix)

# ── 1. 촬영 정보 ──────────────────────────────────────────────────────────────
$info = & ffprobe -v error -select_streams v:0 -show_entries "stream=r_frame_rate,avg_frame_rate,nb_frames,width,height:format=duration:format_tags" -of json $src | ConvertFrom-Json
$stream = $info.streams[0]
function ConvertTo-Fps([string]$ratio) {
    $parts = $ratio.Split("/")
    if ($parts.Count -eq 2 -and [double]$parts[1] -ne 0) { return [math]::Round([double]$parts[0] / [double]$parts[1], 2) }
    return $ratio
}
$captureFps = $null
if ($info.format.tags) {
    # 안드로이드 슬로모션은 재생 fps(30)와 별도로 촬영 fps를 이 태그에 남긴다
    $tag = $info.format.tags.PSObject.Properties | Where-Object { $_.Name -like "*capture.fps*" } | Select-Object -First 1
    if ($tag) { $captureFps = $tag.Value }
}
Write-Host ""
Write-Host "원본       $src"
Write-Host ("해상도     {0}x{1}" -f $stream.width, $stream.height)
Write-Host ("파일 fps   r={0}  avg={1}  (프레임 {2}개, {3}초)" -f (ConvertTo-Fps $stream.r_frame_rate), (ConvertTo-Fps $stream.avg_frame_rate), $stream.nb_frames, [math]::Round([double]$info.format.duration, 2))
if ($captureFps) {
    Write-Host "촬영 fps   $captureFps  (메타데이터 — 계산에는 이 값을 쓰세요)" -ForegroundColor Green
} else {
    Write-Host "촬영 fps   메타데이터 없음 — 파일 fps가 30 근처면 휴대폰 설정의 슬로모션 fps(240/120)를 쓰세요" -ForegroundColor Yellow
}

# ── 2. 프레임 번호 새기기 ─────────────────────────────────────────────────────
# drawtext 옵션 구분자가 ':'라 글꼴 경로의 C: 를 막아야 한다. ffmpeg는 이스케이프를 두 번 푼다(필터 그래프 → 옵션) —
# C\: 는 그래프 단계에서 C: 로 풀려 다시 구분자가 된다(2026-10-02 실패). 그래서 C\\: . PowerShell 5.1은 인자 속 따옴표를 깨뜨리므로 따옴표는 쓰지 않는다.
$font = "C\\:/Windows/Fonts/arial.ttf"
$filter = "drawtext=fontfile=${font}:text=%{frame_num}:x=20:y=20:fontsize=64:fontcolor=yellow:box=1:boxcolor=black@0.7:boxborderw=8"

$ffArgs = @("-hide_banner", "-loglevel", "error", "-stats", "-y")
if ($Start -ge 0) { $ffArgs += @("-ss", "$Start") }
$ffArgs += @("-i", $src)
if ($Duration -gt 0) { $ffArgs += @("-t", "$Duration") }
# 모든 프레임을 그대로 — 재생 fps에 맞춰 프레임을 버리거나 복제하지 않는다
$ffArgs += @("-vf", $filter, "-fps_mode", "passthrough", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", $out)

Write-Host ""
Write-Host "번호 새기는 중… (240fps 영상은 시간이 좀 걸립니다)"
& ffmpeg @ffArgs
if ($LASTEXITCODE -ne 0) {
    Write-Host "ffmpeg 실패 (종료 코드 $LASTEXITCODE)" -ForegroundColor Red
    exit $LASTEXITCODE
}
Write-Host ""
Write-Host "완료       $out" -ForegroundColor Green
Write-Host "VLC 사용   Space로 멈춤 → E 키로 한 프레임씩 → 왼쪽 위 번호를 기록표(F0~F4)에 적기"
Write-Host "계산       (F - F0) x 1000 / 촬영fps  ms   예) 240fps에서 70프레임 차이 = 292ms"
