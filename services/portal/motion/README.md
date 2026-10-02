# portal 화면 영상 원본 (Hyperframes)

회사 사이트 첫 화면의 영상 2개를 만드는 원본이다. 사이트는 렌더링된 MP4만 쓴다(실행 중에는 Hyperframes·GSAP·CDN 불필요).
도구: [Hyperframes](https://github.com/heygen-com/hyperframes) (Apache-2.0) — HTML + GSAP 타임라인을 프레임마다 Chrome으로 찍어 FFmpeg로 인코딩.

| 원본 | 결과 (`../frontend/media/`) | 내용 |
| --- | --- | --- |
| `hero/index.html` | `station-judging.mp4` + `-poster.jpg` (1600×900, 12초 반복) | 교육장 키트 판정 화면 재현. 서행 → 좌회전 유도 → 우회전 유도: 손 관절이 실측 좌표 사이를 옮겨 가고, 일치율이 판정 기준 75%를 넘어 3프레임 연속이면 정답 확정 |
| `reel/index.html` | `signal-reel.mp4` + `-poster.jpg` (1200×900, 14초 반복) | 수신호 7종 손 관절 21점. 신호마다 2초(SIGNALS 순서). 사이트 목록이 이 2초 간격으로 영상과 맞물린다(`portal.js` `REEL_STEP`) |

손 관절 좌표는 `../frontend/hand-data.js`(KPI 촬영 2026-09-29, RPi5 Camera Module 3, ext01 정면 f2) 그대로다. 일치율 값은 시연 수료증(`img/certificate.png`)과 같다.

## 다시 렌더링하기 (Node 22+, FFmpeg, Chrome)

1. 자산 채우기 — 영상마다 `assets/`에 `gsap.min.js`(npm `gsap` 3.15), `hand-data.js`, `SUIT-Variable.woff2`, `JetBrainsMono-500.woff2`, `JetBrainsMono-700.woff2`
   (`hand-data.js`와 글꼴은 `../frontend/`에서 복사). `assets/`는 git에 올리지 않는다.
2. 렌더링 — 텔레메트리 끔: `HYPERFRAMES_NO_TELEMETRY=1 npx hyperframes render hero --quality delivery -o hero_master.mp4` (reel도 같게)
3. 웹용 압축 — `ffmpeg -i hero_master.mp4 -an -c:v libx264 -preset veryslow -tune animation -crf 23 -pix_fmt yuv420p -movflags +faststart ../frontend/media/station-judging.mp4`
4. 포스터 — `ffmpeg -ss 2.6 -i hero_master.mp4 -frames:v 1 hero.png` → JPEG(품질 84). reel은 `-ss 1.5`.

확인: `npx hyperframes lint hero`(오류 0), `npx hyperframes snapshot hero --at 2.5,6.3 --describe false`.
