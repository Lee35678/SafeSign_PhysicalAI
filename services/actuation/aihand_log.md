
### AI Hand 검증 — 2026-09-23 16:07

- 실행 환경: **Rpi5 네이티브**
- micro:bit 재부팅 후 첫 회차: y
- `/health` 전: `{'status': 'ok', 'service': 'actuation', 'mock_hardware': False, 'microbit_connected': {'_value': True}}`
- `/health` 후: `{'status': 'ok', 'service': 'actuation', 'mock_hardware': False, 'microbit_connected': {'_value': True}}`

| 시각 | 회차 | 명령 | HTTP(ms) | status | 회신 | **완료(s)** | 판정 | 비고 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 16:05:01 | 1 | G1 정지 | 1050 | ok | `OK1` | 1.96 | 정상 |  |
| 16:05:08 | 1 | G2 서행 | 1040 | ok | `OK2` | 1.83 | 정상 |  |
| 16:05:16 | 1 | G3 좌회전_유도 | 1046 | ok | `OK3` | 1.49 | 정상 |  |
| 16:05:22 | 1 | G4 우회전_유도 | 1042 | ok | `OK4` | 1.66 | 정상 |  |
| 16:05:38 | 1 | G5 확인_완료 | 1041 | ok | `OK5` | 1.76 | 정상 |  |
| 16:05:45 | 1 | G6 후진 | 1054 | ok | `OK6` | 1.85 | 정상 |  |
| 16:05:53 | 1 | G7 주의 | 1049 | ok | `OK7` | 1.84 | 정상 |  |
| 16:06:13 | 1 | result correct | 2042 | timeout | `-` | 3.52 | 정상 |  |
| 16:06:34 | 1 | result incorrect | 2037 | timeout | `-` | 0.62 | 정상 |  |
| 16:06:56 | 1 | progress 3/7 | 35 | ok | `OKP37` | 5.63 | 정상 |  |
| 16:07:10 | 1 | progress 1/7 | 33 | ok | `OKP17` | 2.50 | 정상 |  |

- **펌웨어 보고 완료**(G1~G7 HTTP): 중앙 1046ms · 최대 1054ms  (7건) — 회신이 손 동작 **이후**라 동작 시간 포함
- **완료**(육안): 중앙 1.84s · 최대 5.63s  (11건)
  > KPI 2.0초를 **어느 쪽으로 재느냐**가 팀 결정이다 (`proposals/picar_주행시간_스키마_변경안.md` 결정 2).

### AI Hand 검증 — 2026-09-23 17:41

특이 사항
- 손가락별 구동 간격을 150ms 바꿈
-  O, X 응답을 먼저하고 LED를 출력하도록 바꿈 


- 실행 환경: **Rpi5 네이티브**
- micro:bit 재부팅 후 첫 회차: y
- `/health` 전: `{'status': 'ok', 'service': 'actuation', 'mock_hardware': False, 'microbit_connected': {'_value': True}}`
- `/health` 후: `{'status': 'ok', 'service': 'actuation', 'mock_hardware': False, 'microbit_connected': {'_value': True}}`

| 시각 | 회차 | 명령 | HTTP(ms) | status | 회신 | **완료(s)** | 판정 | 비고 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 17:39:48 | 1 | G1 정지 | 801 | ok | `OK1` | 1.52 | 정상 |  |
| 17:39:54 | 1 | G2 서행 | 801 | ok | `OK2` | 1.43 | 정상 |  |
| 17:40:05 | 1 | G3 좌회전_유도 | 800 | ok | `OK3` | 1.90 | 정상 |  |
| 17:40:11 | 1 | G4 우회전_유도 | 803 | ok | `OK4` | 1.88 | 정상 |  |
| 17:40:17 | 1 | G5 확인_완료 | 797 | ok | `OK5` | 1.63 | 정상 |  |
| 17:40:24 | 1 | G6 후진 | 801 | ok | `OK6` | 1.64 | 정상 |  |
| 17:40:30 | 1 | G7 주의 | 800 | ok | `OK7` | 1.67 | 정상 |  |
| 17:40:42 | 1 | result correct | 27 | ok | `OK:CORRECT` | 0.70 | 정상 |  |
| 17:40:48 | 1 | result incorrect | 42 | ok | `OK:INCORRECT` | 0.78 | 정상 |  |
| 17:40:59 | 1 | progress 3/7 | 32 | ok | `OKP37` | 2.55 | 정상 |  |
| 17:41:07 | 1 | progress 1/7 | 36 | ok | `OKP17` | 1.51 | 정상 |  |


- **펌웨어 보고 완료**(G1~G7 HTTP): 중앙 801ms · 최대 803ms  (7건) — 회신이 손 동작 **이후**라 동작 시간 포함
- **완료**(육안): 중앙 1.63s · 최대 2.55s  (11건)
  > KPI 2.0초를 **어느 쪽으로 재느냐**가 팀 결정이다 (`proposals/picar_주행시간_스키마_변경안.md` 결정 2).

### AI Hand 검증 — 2026-09-23 18:15
- 실행 환경: **Rpi5 네이티브**
- micro:bit 재부팅 후 첫 회차: y
- `/health` 전: `{'status': 'ok', 'service': 'actuation', 'mock_hardware': False, 'microbit_connected': True}`
- `/health` 후: `{'status': 'ok', 'service': 'actuation', 'mock_hardware': False, 'microbit_connected': True}`

| 시각 | 회차 | 명령 | HTTP(ms) | status | 회신 | **완료(s)** | 판정 | 비고 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 18:14:19 | 1 | G1 정지 | 802 | ok | `OK1` | 1.55 | 정상 |  |
| 18:14:25 | 1 | G2 서행 | 796 | ok | `OK2` | 1.44 | 정상 |  |
| 18:14:31 | 1 | G3 좌회전_유도 | 801 | ok | `OK3` | 1.41 | 정상 |  |
| 18:14:39 | 1 | G4 우회전_유도 | 806 | ok | `OK4` | 1.41 | 정상 |  |
| 18:14:44 | 1 | G5 확인_완료 | 794 | ok | `OK5` | 1.87 | 정상 |  |
| 18:14:49 | 1 | G6 후진 | 800 | ok | `OK6` | 1.52 | 정상 |  |
| 18:14:55 | 1 | G7 주의 | 794 | ok | `OK7` | 1.89 | 정상 |  |
| 18:14:59 | 1 | result correct | 26 | ok | `OK:CORRECT` |  | 정상 |  |
| 18:15:03 | 1 | result incorrect | 41 | ok | `OK:INCORRECT` |  | 정상 |  |
| 18:15:09 | 1 | progress 3/7 | 33 | ok | `OKP37` |  | 정상 |  |
| 18:15:14 | 1 | progress 1/7 | 32 | ok | `OKP17` |  | 정상 |  |

- **펌웨어 보고 완료**(G1~G7 HTTP): 중앙 800ms · 최대 806ms  (7건) — 회신이 손 동작 **이후**라 동작 시간 포함
- **완료**(육안): 중앙 1.52s · 최대 1.89s  (7건)
  > KPI 2.0초를 **어느 쪽으로 재느냐**가 팀 결정이다 (`proposals/picar_주행시간_스키마_변경안.md` 결정 2).

### AI Hand 검증 — 2026-09-23 18:24

- 실행 환경: **auto**
- micro:bit 재부팅 후 첫 회차: auto
- `/health` 전: `{'status': 'ok', 'service': 'actuation', 'mock_hardware': False, 'microbit_connected': True}`
- `/health` 후: `{'status': 'ok', 'service': 'actuation', 'mock_hardware': False, 'microbit_connected': True}`

| 시각 | 회차 | 명령 | HTTP(ms) | status | 회신 | **완료(s)** | 판정 | 비고 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 18:23:55 | 1 | G1 정지 | 803 | ok | `OK1` |  | auto |  |
| 18:23:56 | 1 | G2 서행 | 806 | ok | `OK2` |  | auto |  |
| 18:23:57 | 1 | G3 좌회전_유도 | 806 | ok | `OK3` |  | auto |  |
| 18:23:57 | 1 | G4 우회전_유도 | 806 | ok | `OK4` |  | auto |  |
| 18:23:58 | 1 | G5 확인_완료 | 806 | ok | `OK5` |  | auto |  |
| 18:23:59 | 1 | G6 후진 | 806 | ok | `OK6` |  | auto |  |
| 18:24:00 | 1 | G7 주의 | 806 | ok | `OK7` |  | auto |  |
| 18:24:00 | 1 | result correct | 37 | ok | `OK:CORRECT` |  | auto |  |
| 18:24:01 | 1 | result incorrect | 1443 | ok | `OK:INCORRECT` |  | auto |  |
| 18:24:03 | 1 | progress 3/7 | 1425 | ok | `OKP37` |  | auto |  |
| 18:24:03 | 1 | progress 1/7 | 38 | ok | `OKP17` |  | auto |  |
| 18:24:04 | 2 | G1 정지 | 805 | ok | `OK1` |  | auto |  |
| 18:24:04 | 2 | G2 서행 | 806 | ok | `OK2` |  | auto |  |
| 18:24:05 | 2 | G3 좌회전_유도 | 806 | ok | `OK3` |  | auto |  |
| 18:24:06 | 2 | G4 우회전_유도 | 806 | ok | `OK4` |  | auto |  |
| 18:24:07 | 2 | G5 확인_완료 | 806 | ok | `OK5` |  | auto |  |
| 18:24:08 | 2 | G6 후진 | 806 | ok | `OK6` |  | auto |  |
| 18:24:08 | 2 | G7 주의 | 806 | ok | `OK7` |  | auto |  |
| 18:24:09 | 2 | result correct | 38 | ok | `OK:CORRECT` |  | auto |  |
| 18:24:10 | 2 | result incorrect | 1424 | ok | `OK:INCORRECT` |  | auto |  |
| 18:24:11 | 2 | progress 3/7 | 1424 | ok | `OKP37` |  | auto |  |
| 18:24:11 | 2 | progress 1/7 | 38 | ok | `OKP17` |  | auto |  |
| 18:24:12 | 3 | G1 정지 | 805 | ok | `OK1` |  | auto |  |
| 18:24:13 | 3 | G2 서행 | 806 | ok | `OK2` |  | auto |  |
| 18:24:14 | 3 | G3 좌회전_유도 | 806 | ok | `OK3` |  | auto |  |
| 18:24:15 | 3 | G4 우회전_유도 | 806 | ok | `OK4` |  | auto |  |
| 18:24:15 | 3 | G5 확인_완료 | 806 | ok | `OK5` |  | auto |  |
| 18:24:16 | 3 | G6 후진 | 806 | ok | `OK6` |  | auto |  |
| 18:24:17 | 3 | G7 주의 | 806 | ok | `OK7` |  | auto |  |
| 18:24:17 | 3 | result correct | 38 | ok | `OK:CORRECT` |  | auto |  |
| 18:24:19 | 3 | result incorrect | 1425 | ok | `OK:INCORRECT` |  | auto |  |
| 18:24:20 | 3 | progress 3/7 | 1424 | ok | `OKP37` |  | auto |  |
| 18:24:20 | 3 | progress 1/7 | 38 | ok | `OKP17` |  | auto |  |
| 18:24:21 | 4 | G1 정지 | 805 | ok | `OK1` |  | auto |  |
| 18:24:22 | 4 | G2 서행 | 806 | ok | `OK2` |  | auto |  |
| 18:24:22 | 4 | G3 좌회전_유도 | 806 | ok | `OK3` |  | auto |  |
| 18:24:23 | 4 | G4 우회전_유도 | 806 | ok | `OK4` |  | auto |  |
| 18:24:24 | 4 | G5 확인_완료 | 805 | ok | `OK5` |  | auto |  |
| 18:24:25 | 4 | G6 후진 | 806 | ok | `OK6` |  | auto |  |
| 18:24:26 | 4 | G7 주의 | 806 | ok | `OK7` |  | auto |  |
| 18:24:26 | 4 | result correct | 38 | ok | `OK:CORRECT` |  | auto |  |
| 18:24:27 | 4 | result incorrect | 1424 | ok | `OK:INCORRECT` |  | auto |  |
| 18:24:28 | 4 | progress 3/7 | 1425 | ok | `OKP37` |  | auto |  |
| 18:24:29 | 4 | progress 1/7 | 38 | ok | `OKP17` |  | auto |  |
| 18:24:29 | 5 | G1 정지 | 805 | ok | `OK1` |  | auto |  |
| 18:24:30 | 5 | G2 서행 | 806 | ok | `OK2` |  | auto |  |
| 18:24:31 | 5 | G3 좌회전_유도 | 806 | ok | `OK3` |  | auto |  |
| 18:24:32 | 5 | G4 우회전_유도 | 806 | ok | `OK4` |  | auto |  |
| 18:24:33 | 5 | G5 확인_완료 | 806 | ok | `OK5` |  | auto |  |
| 18:24:33 | 5 | G6 후진 | 806 | ok | `OK6` |  | auto |  |
| 18:24:34 | 5 | G7 주의 | 825 | ok | `OK7` |  | auto |  |
| 18:24:34 | 5 | result correct | 38 | ok | `OK:CORRECT` |  | auto |  |
| 18:24:36 | 5 | result incorrect | 1424 | ok | `OK:INCORRECT` |  | auto |  |
| 18:24:37 | 5 | progress 3/7 | 1425 | ok | `OKP37` |  | auto |  |
| 18:24:37 | 5 | progress 1/7 | 37 | ok | `OKP17` |  | auto |  |

- **펌웨어 보고 완료**(G1~G7 HTTP): 중앙 806ms · 최대 825ms  (35건) — 회신이 손 동작 **이후**라 동작 시간 포함

### AI Hand 검증 — 2026-09-25 22:39

- 실행 환경: **auto**
- micro:bit 재부팅 후 첫 회차: auto
- `/health` 전: `{'status': 'ok', 'service': 'actuation', 'mock_hardware': False, 'microbit_connected': True}`
- `/health` 후: `{'status': 'ok', 'service': 'actuation', 'mock_hardware': False, 'microbit_connected': True}`

| 시각 | 회차 | 명령 | HTTP(ms) | status | 회신 | **완료(s)** | 판정 | 비고 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 22:39:24 | 1 | G1 정지 | 807 | ok | `OK1` |  | auto |  |
| 22:39:25 | 1 | G2 서행 | 806 | ok | `OK2` |  | auto |  |
| 22:39:26 | 1 | G3 좌회전_유도 | 806 | ok | `OK3` |  | auto |  |
| 22:39:27 | 1 | G4 우회전_유도 | 804 | ok | `OK4` |  | auto |  |
| 22:39:28 | 1 | G5 확인_완료 | 806 | ok | `OK5` |  | auto |  |
| 22:39:28 | 1 | G6 후진 | 806 | ok | `OK6` |  | auto |  |
| 22:39:29 | 1 | G7 주의 | 806 | ok | `OK7` |  | auto |  |
| 22:39:29 | 1 | result correct | 38 | ok | `OK:CORRECT` |  | auto |  |
| 22:39:29 | 1 | result incorrect | 36 | ok | `OK:INCORRECT` |  | auto |  |
| 22:39:29 | 1 | progress 3/7 | 38 | ok | `OKP37` |  | auto |  |
| 22:39:29 | 1 | progress 1/7 | 37 | ok | `OKP17` |  | auto |  |
| 22:39:30 | 2 | G1 정지 | 806 | ok | `OK1` |  | auto |  |
| 22:39:31 | 2 | G2 서행 | 805 | ok | `OK2` |  | auto |  |
| 22:39:32 | 2 | G3 좌회전_유도 | 806 | ok | `OK3` |  | auto |  |
| 22:39:33 | 2 | G4 우회전_유도 | 805 | ok | `OK4` |  | auto |  |
| 22:39:33 | 2 | G5 확인_완료 | 806 | ok | `OK5` |  | auto |  |
| 22:39:34 | 2 | G6 후진 | 806 | ok | `OK6` |  | auto |  |
| 22:39:35 | 2 | G7 주의 | 806 | ok | `OK7` |  | auto |  |
| 22:39:35 | 2 | result correct | 38 | ok | `OK:CORRECT` |  | auto |  |
| 22:39:35 | 2 | result incorrect | 36 | ok | `OK:INCORRECT` |  | auto |  |
| 22:39:35 | 2 | progress 3/7 | 39 | ok | `OKP37` |  | auto |  |
| 22:39:35 | 2 | progress 1/7 | 35 | ok | `OKP17` |  | auto |  |
| 22:39:36 | 3 | G1 정지 | 804 | ok | `OK1` |  | auto |  |
| 22:39:37 | 3 | G2 서행 | 807 | ok | `OK2` |  | auto |  |
| 22:39:38 | 3 | G3 좌회전_유도 | 805 | ok | `OK3` |  | auto |  |
| 22:39:38 | 3 | G4 우회전_유도 | 805 | ok | `OK4` |  | auto |  |
| 22:39:39 | 3 | G5 확인_완료 | 806 | ok | `OK5` |  | auto |  |
| 22:39:40 | 3 | G6 후진 | 806 | ok | `OK6` |  | auto |  |
| 22:39:41 | 3 | G7 주의 | 806 | ok | `OK7` |  | auto |  |
| 22:39:41 | 3 | result correct | 38 | ok | `OK:CORRECT` |  | auto |  |
| 22:39:41 | 3 | result incorrect | 37 | ok | `OK:INCORRECT` |  | auto |  |
| 22:39:41 | 3 | progress 3/7 | 38 | ok | `OKP37` |  | auto |  |
| 22:39:41 | 3 | progress 1/7 | 36 | ok | `OKP17` |  | auto |  |

- **펌웨어 보고 완료**(G1~G7 HTTP): 중앙 806ms · 최대 807ms  (21건) — 회신이 손 동작 **이후**라 동작 시간 포함

### AI Hand 검증 — 2026-09-25 23:23

- 실행 환경: **auto**
- micro:bit 재부팅 후 첫 회차: auto
- `/health` 전: `{'status': 'ok', 'service': 'actuation', 'mock_hardware': False, 'microbit_connected': True}`
- `/health` 후: `{'status': 'ok', 'service': 'actuation', 'mock_hardware': False, 'microbit_connected': True}`

| 시각 | 회차 | 명령 | HTTP(ms) | status | 회신 | **완료(s)** | 판정 | 비고 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 23:23:19 | 1 | G1 정지 | 797 | ok | `OK1` |  | auto |  |
| 23:23:20 | 1 | G2 서행 | 806 | ok | `OK2` |  | auto |  |
| 23:23:20 | 1 | G3 좌회전_유도 | 806 | ok | `OK3` |  | auto |  |
| 23:23:21 | 1 | G4 우회전_유도 | 806 | ok | `OK4` |  | auto |  |
| 23:23:22 | 1 | G5 확인_완료 | 806 | ok | `OK5` |  | auto |  |
| 23:23:23 | 1 | G6 후진 | 806 | ok | `OK6` |  | auto |  |
| 23:23:24 | 1 | G7 주의 | 806 | ok | `OK7` |  | auto |  |
| 23:23:24 | 1 | result correct | 38 | ok | `OK:CORRECT` |  | auto |  |
| 23:23:24 | 1 | result incorrect | 37 | ok | `OK:INCORRECT` |  | auto |  |
| 23:23:24 | 1 | progress 3/7 | 38 | ok | `OKP37` |  | auto |  |
| 23:23:24 | 1 | progress 1/7 | 37 | ok | `OKP17` |  | auto |  |
| 23:23:25 | 2 | G1 정지 | 805 | ok | `OK1` |  | auto |  |
| 23:23:25 | 2 | G2 서행 | 806 | ok | `OK2` |  | auto |  |
| 23:23:26 | 2 | G3 좌회전_유도 | 806 | ok | `OK3` |  | auto |  |
| 23:23:27 | 2 | G4 우회전_유도 | 806 | ok | `OK4` |  | auto |  |
| 23:23:28 | 2 | G5 확인_완료 | 806 | ok | `OK5` |  | auto |  |
| 23:23:29 | 2 | G6 후진 | 806 | ok | `OK6` |  | auto |  |
| 23:23:30 | 2 | G7 주의 | 806 | ok | `OK7` |  | auto |  |
| 23:23:30 | 2 | result correct | 38 | ok | `OK:CORRECT` |  | auto |  |
| 23:23:30 | 2 | result incorrect | 37 | ok | `OK:INCORRECT` |  | auto |  |
| 23:23:30 | 2 | progress 3/7 | 37 | ok | `OKP37` |  | auto |  |
| 23:23:30 | 2 | progress 1/7 | 37 | ok | `OKP17` |  | auto |  |
| 23:23:30 | 3 | G1 정지 | 805 | ok | `OK1` |  | auto |  |
| 23:23:31 | 3 | G2 서행 | 806 | ok | `OK2` |  | auto |  |
| 23:23:32 | 3 | G3 좌회전_유도 | 806 | ok | `OK3` |  | auto |  |
| 23:23:33 | 3 | G4 우회전_유도 | 806 | ok | `OK4` |  | auto |  |
| 23:23:34 | 3 | G5 확인_완료 | 806 | ok | `OK5` |  | auto |  |
| 23:23:35 | 3 | G6 후진 | 806 | ok | `OK6` |  | auto |  |
| 23:23:35 | 3 | G7 주의 | 806 | ok | `OK7` |  | auto |  |
| 23:23:35 | 3 | result correct | 38 | ok | `OK:CORRECT` |  | auto |  |
| 23:23:35 | 3 | result incorrect | 37 | ok | `OK:INCORRECT` |  | auto |  |
| 23:23:35 | 3 | progress 3/7 | 37 | ok | `OKP37` |  | auto |  |
| 23:23:35 | 3 | progress 1/7 | 56 | ok | `OKP17` |  | auto |  |

- **펌웨어 보고 완료**(G1~G7 HTTP): 중앙 806ms · 최대 806ms  (21건) — 회신이 손 동작 **이후**라 동작 시간 포함