# actuation — AI Hand + micro:bit 제어

교육장에서 학습자 앞에 고정해 두는 **Raspberry Pi 5**에서 실행하는 서비스다.
web(교육 진행 화면)의 요청을 받아 micro:bit v2에 **BLE**로 명령을 보내고, micro:bit가 AI Hand의
손가락 서보 5개를 움직인다. 판정 결과(O/X)는 micro:bit LED에 표시한다.

- 포트: **8002** (web이 `ACTUATION_URL=http://localhost:8002`로 호출)
- picar는 이 서비스가 맡지 않는다. picar는 RPi4B의 [services/picar](../picar/README.md)가 따로 제어한다.
- 전체 설치·실행 순서는 [루트 README](../../README.md) §4를 따른다. 이 문서는 actuation만 자세히 다룬다.

## 1. 하드웨어 연결

```
RPi5 (actuation :8002) ──BLE── micro:bit v2 ── StartbitV2 확장보드 ── 손가락 서보 5개 (AI Hand)
                                                       │
                                               7.5V 3A 어댑터
```

| 항목 | 내용 |
| --- | --- |
| 통신 | RPi5 ↔ micro:bit는 **BLE만** 쓴다. micro:bit는 하드웨어 UART가 1개라 확장보드 초기화(`startbit_Init()`) 뒤에는 USB 시리얼이 동작하지 않는다 |
| 서보 채널 | 1 엄지 · 2 검지 · 3 중지 · 4 약지 · 5 소지 |
| 서보 방향 | 엄지는 각도를 그대로, 검지~소지는 장착 방향이 반대라 펌웨어가 `180 - 각도`로 뒤집어 보낸다 |
| 전원 | 7.5V 3A 어댑터 하나가 확장보드를 거쳐 micro:bit와 서보를 **같은 레일**에서 먹인다 |

### 손가락별 가동 범위 (펌웨어에 고정)

범위를 벗어난 값은 펌웨어가 잘라 낸다. 서보 스톨을 막기 위해 실측으로 정한 값이다.

| 손가락 | 최소 | 최대 |
| --- | --- | --- |
| 엄지 | 60 | 170 |
| 검지 | 20 | 135 |
| 중지 | 25 | 135 |
| 약지 | 25 | 125 |
| 소지 | 30 | 120 |

### 손가락을 하나씩 움직이는 이유

손가락 서보(LFD-01)는 구속 전류가 개당 약 700mA라 5개를 한꺼번에 기동하면 3.5A로 어댑터 용량(3A)을 넘는다.
레일 전압이 떨어지면 같은 레일의 micro:bit가 리셋되어 BLE가 끊긴다. 그래서 펌웨어는 손가락을 **150ms 간격으로
하나씩** 출발시킨다(서보 이동 시간 200ms, 인접 2개만 50ms 겹침, 최악 약 1.74A). 제스처 1회는 약 0.8초 걸린다.

## 2. 파일 구성

| 경로 | 내용 |
| --- | --- |
| `src/app.py` | FastAPI 진입점 (HTTP API) |
| `src/aihand/controller.py` | 수신호 이름(`target_signal`) → 제스처 번호 `G1`~`G7` 변환 |
| `src/microbit/ble_bridge.py` | `bleak` 기반 BLE 연결·재연결, 명령 전송, 회신 대기, 버튼 입력 집계 |
| `src/firmware/aihand_control.ts` | micro:bit 펌웨어 (MakeCode에서 플래시) |
| `src/firmware/StartbitV2_patched.ts` | StartbitV2 확장 소스 수정본. BLE와 충돌하는 `music.playTone()`을 LED 표시로 바꾸고 RGB 조명 기능을 뺐다 |
| `src/firmware/StartbitRGBLight.ts` | StartbitV2의 RGB 조명 확장 소스 (수정본에서는 쓰지 않음) |
| `requirements.txt` | `fastapi`, `uvicorn[standard]`, `bleak==0.22.3` |

### 수신호 ↔ 제스처

| `target_signal` | 명령 | 손 모양 (펌웨어 기준) |
| --- | --- | --- |
| 정지 | `G1` | 다섯 손가락 펴기 |
| 서행 | `G2` | 검지+중지 펴기 |
| 좌회전_유도 | `G3` | 엄지+검지 펴기 |
| 우회전_유도 | `G4` | 엄지+소지 펴기 |
| 확인_완료 | `G5` | 주먹 |
| 후진 | `G6` | 검지 펴기 |
| 주의 | `G7` | 소지 펴기 |

## 3. 펌웨어 플래시

1. MakeCode(makecode.microbit.org)에서 **StartbitV2 확장이 들어 있는 프로젝트**를 연다.
2. JavaScript 보기에서 기존 내용을 모두 지우고 [`src/firmware/aihand_control.ts`](src/firmware/aihand_control.ts)를
   **통째로** 붙여 넣는다. 일부만 고쳐 넣지 않는다 — 저장소와 micro:bit 내용이 어긋나도 동작만 보고는 알기 어렵다.
3. micro:bit에 플래시한다. 켜지면 손이 주먹 자세가 되고 LED에 ◇가 뜬다.

파일 맨 위 `const TEST_MODE = false;`는 **그대로 둔다**. `true`는 서보 캘리브레이션용 모드
(`IDX:`/`HAND:`/`G:` 명령 처리, 시작 시 `READY` 표시)이며 운영에는 쓰지 않는다.

### micro:bit LED 표시

| 표시 | 의미 |
| --- | --- |
| ◇ | 전원 켜짐, BLE 연결 대기 |
| ✓ | RPi5와 BLE 연결됨 |
| ✗ | BLE 연결 끊김 |
| O / X (1초) | 판정 결과 정답 / 오답 |

버튼 A를 누르면 micro:bit가 `BTN:A`를 RPi5로 올린다. web 화면의 확인 버튼(스페이스바) 대신 쓸 수 있다.
버튼 A는 LED를 쓰지 않는다.

## 4. 설치 · 실행 (RPi5, 네이티브)

**최초 1회 — 가상환경** ([루트 README](../../README.md) §4.1 ③)

```bash
cd ~/git/SafeSign_PhysicalAI/services/actuation
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip show bleak | grep Version     # 0.22.3
```

`.venv`는 git에 포함되지 않는다. 저장소를 새로 받았거나 보드를 바꾸면 다시 만든다.

**실행 — 매번**

```bash
cd ~/git/SafeSign_PhysicalAI/services/actuation
source .venv/bin/activate          # 프롬프트 앞에 (.venv)가 붙어야 한다
MOCK_HARDWARE=false uvicorn app:app --app-dir src --host 0.0.0.0 --port 8002
```

콘솔에 `micro:bit BLE 연결됨: BBC micro:bit [...]`이 뜨고 micro:bit LED가 ✓로 바뀌면 정상이다.
`curl -s localhost:8002/health`에서 `mock_hardware: false`, `microbit_connected: true`를 확인한다.

평소에는 `scripts/rpi/start_all.sh`(tmux) 또는 systemd 유닛 `safesign-actuation`으로 다른 서비스와 함께 켠다
([루트 README](../../README.md) §4.2).

**종료**는 `Ctrl+C`로 한다(`systemctl`로 켰다면 `sudo systemctl stop safesign-actuation`). `kill -9`로 끄거나
SSH가 끊기면 BlueZ에 BLE 연결이 남아, 다음 실행 때 micro:bit가 스캔에 보이지 않는다(LED가 ✓ 그대로).
이때는 micro:bit를 리셋하거나 `bluetoothctl disconnect <MAC>`을 실행한다.

## 5. 환경변수

| 이름 | 기본값 | 설명 |
| --- | --- | --- |
| `MOCK_HARDWARE` | `true` | `true`면 BLE에 연결하지 않고 성공 응답(`"status": "mocked"`)만 돌려준다. **실물 운영은 반드시 `false`** |
| `MICROBIT_BLE_NAME` | `BBC micro:bit` | 스캔할 때 찾는 장치 이름(이 문자열이 이름에 들어 있으면 연결) |

고정값(코드): BLE 스캔 5초, 명령당 회신 대기 2초.

## 6. HTTP API

| 메서드 · 경로 | 입력 예 | 동작 |
| --- | --- | --- |
| `GET /health` | — | `status`, `service`, `mock_hardware`, `microbit_connected` |
| `POST /command` | `{"target_signal": "정지"}` | 해당 제스처 `G{n}` 전송, 회신 `OK{n}` 대기 |
| `POST /result` | `{"is_correct": true}` | `correct`/`incorrect` 전송 → LED O/X 1초. `is_correct`가 JSON `true`일 때만 정답. `match_score`는 무시 |
| `POST /progress` | `{"current": 3, "total": 7}` | `P37` 전송, 회신 `OKP37` 대기. LED 표시는 없다. 두 값 모두 0~9 정수만 허용 |
| `GET /button` | — | 버튼 A 누적 입력 `{"seq", "last_button", "last_at", "microbit_connected"}` |
| `POST /button/simulate` | `{"button": "A"}` (생략 가능) | micro:bit 없이 버튼 입력을 흉내 내 `seq`를 1 올린다. BLE는 건드리지 않는다 |

**응답 `status`**

| 값 | 의미 |
| --- | --- |
| `ok` | micro:bit가 맞는 회신을 보냄 (`reply`에 회신 내용) |
| `mocked` | `MOCK_HARDWARE=true`라 전송하지 않음 |
| `timeout` | 2초 안에 맞는 회신이 오지 않음. 맞지 않아 버린 회신은 `ignored`에 담긴다 |
| `error` | `reason`: `unknown_target_signal`(모르는 수신호), `invalid_progress`(범위 밖 값), `microbit_unreachable`(연결 실패), `write_failed`(재연결 후 재전송도 실패) |

- 전송 중 연결이 끊기면 한 번 재연결해 다시 보낸다.
- 요청이 동시에 들어와도 BLE 전송은 하나씩 순서대로 처리한다.
- `/button`의 `seq`는 서비스를 재시작하면 0부터 다시 센다. BLE가 끊긴 동안 누른 버튼은 기록되지 않는다.

## 7. BLE 문제 해결

| 증상 | 원인 | 조치 |
| --- | --- | --- |
| `uvicorn: command not found` | 가상환경이 활성화되지 않음 | `source .venv/bin/activate` |
| `pip install` 시 `error: externally-managed-environment` | 가상환경 밖의 시스템 pip가 실행됨 | 가상환경부터 활성화. `ls -d .venv`로 있는지 보고 없으면 "최초 1회"부터. **`--break-system-packages`는 쓰지 않는다**(OS의 Python이 깨질 수 있다) |
| `.venv`가 없다 | 다른 폴더나 다른 보드에 접속함 | `pwd`·`hostname` 확인. actuation은 **RPi5**에서 돈다 |
| `micro:bit BLE 연결 실패: TimeoutError` | 다른 프로그램의 BLE 스캔이 켜져 있음(스캔엔 잡히는데 연결만 시간 초과) | `bluetoothctl show \| grep Discovering`이 `yes`면 `scan on`을 켠 창에서 `scan off` 후 `quit`, 모르면 `pkill bluetoothctl`. 서버가 직접 스캔하므로 `scan on`은 필요 없다 |
| `micro:bit(...)가 스캔(5초)에 안 보임` | micro:bit가 이미 다른 쪽에 연결됨(✓ 표시), 또는 전원 문제 | `pgrep -af uvicorn`으로 이전 서버가 살아 있는지 확인. `bluetoothctl devices Connected`에 있으면 `bluetoothctl disconnect <MAC>`. micro:bit 리셋 후 ◇ 확인 |
| `/health`는 정상인데 `mock_hardware: true` | `MOCK_HARDWARE=false` 없이 실행함 | 서버를 끄고 4절 명령으로 다시 실행 |
| 손이 움직일 때 BLE가 끊김 | 서보 전류로 전원 레일 전압이 떨어져 micro:bit가 리셋됨 | 7.5V 3A 어댑터를 쓰는지 확인. 펌웨어가 저장소 파일(150ms 순차 출발) 그대로인지 확인하고, 아니면 3절대로 다시 플래시 |

micro:bit는 BLE 연결을 **하나만** 받는다. actuation 서버를 두 개 띄우거나 `bluetoothctl connect`로 직접 연결해 두면
서버가 micro:bit를 찾지 못한다.

## 8. 안전 · 주의

- **BLE 시작 뒤 `music.*`를 호출하지 않는다.** micro:bit v2에서 BLE와 `music`(부저)은 같은 하드웨어 자원을 써서,
  소리가 나는 순간 패닉 070이 나고 BLE가 끊긴다. 그래서 이 제품은 부저를 쓰지 않고 LED로만 피드백한다.
  펌웨어를 고칠 때 소리가 필요하면 `basic.showIcon()`/`basic.showLeds()` 등 LED로 대신한다.
- **손가락 출발 간격(150ms)을 줄이지 않는다.** 3개 이상이 겹쳐 움직이면 어댑터 용량을 넘을 수 있다.
- **가동 범위(1절 표)를 넓히지 않는다.** 실측한 스톨 방지 범위다.
- micro:bit 전원을 켜면 AI Hand가 곧바로 주먹 자세로 움직인다.
- 서비스를 끌 때는 `Ctrl+C`(또는 `systemctl stop`)를 쓴다. `kill -9`는 BLE 연결을 남긴다.

펌웨어 캘리브레이션 도구·테스트 코드 등 개발 자료는 dev 브랜치에 있다.
