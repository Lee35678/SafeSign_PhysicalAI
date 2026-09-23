# AiHand 사용법 — micro:bit 펌웨어 올리고 PC에서 제어하기

> 처음 세팅하는 사람이 **이 문서만 보고** AI Hand를 움직일 수 있게 쓴 실습 가이드입니다.
> 설계 근거·제약의 배경은 [services/actuation/README.md](../README.md)와
> [document/11_하드웨어설계서_v1.md](../../../document/11_하드웨어설계서_v1.md) §4를 보세요.
>
> 대상: micro:bit v2 + Startbit/Hiwonder 확장보드 + AI Hand(손가락 서보 5개), 조작 PC는 Windows 기준.

---

## 0. 준비물 체크

| 구분 | 항목 | 확인 |
| --- | --- | --- |
| 하드웨어 | AI Hand 본체 (손가락 서보 5개가 확장보드 서보 포트 **1~5**에 연결) | ⬜ |
| | micro:bit **v2** (v1 불가 — BLE + 이 펌웨어를 올리기엔 RAM이 부족) | ⬜ |
| | micro:bit 확장보드 (Startbit/Hiwonder, 서보 컨트롤러 내장) | ⬜ |
| | **7.5V 3A 어댑터** (DC 3.5×1.35) — 서보 전원 | ⬜ |
| | micro:bit용 USB 케이블 (**데이터 전송용**. 충전 전용 케이블이면 인식 안 됨) | ⬜ |
| PC | 블루투스(BLE) 지원 — 내장 또는 USB 동글 | ⬜ |
| | Python 3.9+ 와 `bleak` (`pip install bleak`) | ⬜ |
| | Edge 또는 Chrome (MakeCode WebUSB 다운로드에 필요) | ⬜ |

**서보 채널 배정** (펌웨어 `moveServo()`의 index와 동일)

| 채널 | 1 | 2 | 3 | 4 | 5 |
| --- | --- | --- | --- | --- | --- |
| 손가락 | 엄지 | 검지 | 중지 | 약지 | 소지 |
| 안전 가동범위 | 60~170 | 20~135 | 25~135 | 25~125 | 30~120 |

> 손목 서보(LD-1501MG)는 이번 범위에서 사용하지 않습니다.

---

## 1. micro:bit에 펌웨어 올리기

### 1-1. MakeCode 접속
<https://makecode.microbit.org/> — **Edge 또는 Chrome** 권장(WebUSB 다운로드가 되는 브라우저).

### 1-2. 로그인
Microsoft 계정으로 로그인하면 프로젝트가 클라우드에 남아 다음에 수정하기 쉽습니다. (건너뛰어도 동작에는 지장 없음)

### 1-3. 새 프로젝트 생성
이름은 자유 (예: `aihand_control`).

### 1-4. 블루투스 확장 추가
좌측 블록 목록 맨 아래 **고급(Advanced) → 확장(Extensions)** → `bluetooth` 검색 후 추가.

> ⚠️ **"radio 확장이 제거됩니다"** 경고가 뜨면 그대로 진행하세요. micro:bit는 bluetooth와 radio를
> 동시에 쓸 수 없는데, 이 프로젝트는 **radio를 쓰지 않습니다.**

### 1-5. 🔴 프로젝트 설정에서 페어링 끄기 (빠뜨리면 PC가 연결 못 함)
톱니바퀴 ⚙️ → **프로젝트 설정(Project Settings)** 에서:

- **No Pairing Required: Anyone can connect via Bluetooth** → **켜기(ON)**

이걸 켜지 않으면 micro:bit가 페어링을 요구해서, 2장의 `aihand_control_pc.py`가 스캔에는 성공해도
**연결 또는 첫 전송에서 실패**합니다. 설정을 바꾼 뒤에는 **반드시 다시 다운로드**해야 적용됩니다.

### 1-6. StartbitV2 확장 추가 (우리 포크 사용)
**고급 → 확장** 화면의 검색창에 아래 **GitHub 주소를 그대로 붙여넣고** 엔터 → 나타나는 카드를 클릭해 추가.

```
https://github.com/SeunghoSong/StartbitV2.git
```

> 🔴 **MakeCode 갤러리의 공식 StartbitV2를 쓰면 안 됩니다.** 원본은 저전압 경고에서
> `music.playTone()`을 호출하는데, BLE와 같은 타이머/PWM 자원을 써서 **패닉 070**이 나고 BLE가 끊깁니다.
> 위 포크는 그 호출을 LED 표시로 바꾸고, 컴파일 문제를 일으키던 RGB 의존성을 제거한 버전입니다.
>
> **확인 방법**: 확장 추가 후 좌측 파일 목록의 `StartbitV2.ts`를 열어 `startbit_Init()` 안에
> `music.playTone(` 이 **없는지** 확인하세요. 있으면 원본이 붙은 것이니 확장을 지우고 다시 추가합니다.
> (리포의 [`src/firmware/StartbitV2_patched.ts`](../src/firmware/StartbitV2_patched.ts),
> [`StartbitRGBLight.ts`](../src/firmware/StartbitRGBLight.ts)는 포크 내용의 참고용 사본입니다 —
> 확장을 추가하면 자동으로 들어오므로 **따로 붙여넣지 마세요.**)

### 1-7. 펌웨어 코드 붙여넣기
상단 **블록 / JavaScript** 토글에서 **JavaScript**를 선택하고, 편집기 내용을 전부 지운 뒤
[`services/actuation/src/firmware/aihand_control.ts`](../src/firmware/aihand_control.ts) 전체를 붙여넣습니다.

**TEST_MODE 확인** (파일 상단, 기본값 `false`):

| 값 | 모드 | 처리하는 명령 | 언제 |
| --- | --- | --- | --- |
| `false` | 운영(시연) | `G1`~`G7` | 평소 · 시연 · 파이프라인 연동 |
| `true` | 테스트/캘리브레이션 | `IDX:` `HAND:` `G:` 추가 | 각도 조정 · 손가락별 진단 |

`correct` / `incorrect` / `P<현재><전체>`는 **두 모드 모두** 동작합니다.

> ⚠️ 2장에서 실행할 `aihand_control_pc.py`의 `TEST_MODE`와 **값을 반드시 똑같이** 맞추세요.
> 어긋나면 명령 형식이 달라 micro:bit가 조용히 무시합니다(에러도 안 납니다).

> 🔴 **여기서 `music.*`을 추가하지 마세요.** `bluetooth.startUartService()` 이후 소리를 내면
> 패닉 070이 뜨고 BLE가 끊깁니다. 타이밍 조정으로 우회 불가 — 피드백이 필요하면 `basic.showIcon()`
> 등 **LED로 대체**합니다. (2026-09-21 실측 확정, README의 "절대 규칙" 참고)

### 1-8. micro:bit를 PC에 USB로 연결
탐색기에 **`MICROBIT` 드라이브**가 보이면 정상입니다.

### 1-9. 다운로드
좌측 하단 **다운로드** 버튼 클릭.

- 브라우저가 기기 선택 창을 띄우면 `BBC micro:bit CMSIS-DAP`를 선택 → **연결**.
- **자동 업로드가 안 될 때**: `.hex` 파일이 다운로드 폴더에 저장되니, 그 파일을 **`MICROBIT` 드라이브에
  복사**하세요. micro:bit 뒷면 노란 LED가 깜빡이다 멈추고 드라이브가 다시 마운트되면 완료입니다.

> ⚠️ **손 주의**: 업로드가 끝나면 펌웨어가 곧바로 `startbit_Init()` 후 **주먹 자세로 초기화**합니다.
> 손가락 사이에 손·케이블이 끼어 있지 않은지 확인하고 올리세요.

### 1-10. 전원 넣고 정상 동작 확인
**7.5V 어댑터를 확장보드에 연결하고 확장보드 전원 스위치를 켭니다.** (서보는 micro:bit의 USB 5V가 아니라
어댑터에서 전원을 받습니다. 어댑터 없이 USB만 꽂으면 서보가 안 움직이거나 힘없이 떨립니다.)

**LED 매트릭스로 보는 상태 신호**

| micro:bit LED | 의미 |
| --- | --- |
| ◆ 다이아몬드 | 부팅 완료, BLE 광고 중 (연결 대기) |
| `READY` 글자 | `TEST_MODE = true`로 올라간 상태 (운영 모드면 안 나옴) |
| ✔ 체크 | **BLE 연결됨** |
| ✘ 엑스 | BLE 끊김 |
| 작은 다이아몬드가 계속 깜빡임 | **저전압 경고** — 어댑터/전원 스위치 확인 |
| 슬픈 얼굴 + 숫자 | 펌웨어 패닉 (→ 5장 문제 해결) |

---

## 2. PC에서 사용해보기

### 2-0. 준비
```powershell
pip install bleak
```

### 2-1. PC 블루투스 켜기
Windows 설정 → Bluetooth 및 장치 → **켜기**.

> ⚠️ **Windows에서 micro:bit를 "장치 추가"로 페어링하지 마세요.** 1-5에서 "No Pairing Required"로
> 올렸기 때문에 페어링이 필요 없고, 오히려 이미 페어링된 항목이 있으면 연결이 실패할 수 있습니다.
> 목록에 micro:bit가 있으면 **장치 제거** 후 진행하세요.
>
> MakeCode 웹 페이지가 micro:bit에 블루투스로 붙어 있어도 충돌합니다. **탭을 닫고** 실행하세요.

### 2-2. 스크립트 실행
```powershell
cd services\actuation\tests
python aihand_control_pc.py
```

> 스크립트 상단의 `TEST_MODE` 값이 **1-7에서 올린 펌웨어의 값과 같은지** 먼저 확인하세요.

정상이면 이렇게 나옵니다:
```
micro:bit 스캔 중... (5초)
연결 시도: BBC micro:bit [zozig] (XX:XX:XX:XX:XX:XX)
연결 성공! (연결 상태: True)
```
이때 micro:bit LED에 **✔ 체크**가 떠야 합니다.

### 2-3. 명령 입력해서 동작 확인

#### 운영 모드 (`TEST_MODE = False`)

| 입력 | 동작 | micro:bit 회신 |
| --- | --- | --- |
| `1` ~ `7` | 제스처 실행 | `OK1` ~ `OK7` |
| `loop` | 1~7번을 1초 간격으로 **5회 반복** (내구성·안정성 확인) | 각 `OK{n}` |
| `correct` | LED에 **O** 1초 표시 (회신이 먼저 옴) | `OK:CORRECT` |
| `incorrect` | LED에 **X** 1초 표시 (회신이 먼저 옴) | `OK:INCORRECT` |
| `progress 3 7` | 진행 표시 전송 (LED 표시 없음, 수신 확인만) | `OKP37` |
| `q` | 종료 | — |

**제스처 7종**

| # | 손모양 | 수신호 의미(PRD §3.2) |
| --- | --- | --- |
| 1 | 다섯 손가락 펴기 | 정지 |
| 2 | 검지+중지 펴기 | 서행 |
| 3 | 엄지+검지 펴기 | 좌회전_유도 |
| 4 | 엄지+소지 펴기 | 우회전_유도 |
| 5 | 엄지만 펴기 | 확인_완료 |
| 6 | 검지만 펴기 | 후진 |
| 7 | 소지만 펴기 | 주의 |

#### 테스트/캘리브레이션 모드 (`TEST_MODE = True`)

| 입력 | 동작 |
| --- | --- |
| `idx 2 35` | 2번(검지) 서보에 **raw 35도** 직접 전달 (반전 없음 — 채널 확인·캘리브레이션용) |
| `g 3` | 제스처 3번 실행 (`G:3` 형식) |
| `hand 0,170,170,170,170` | 엄지,검지,중지,약지,소지 순서로 5개 각도 지정 (0=펴짐 / 170=굽힘) |
| `correct` / `incorrect` / `progress` / `q` | 운영 모드와 동일 |

> `hand`의 0/170은 손가락별 실측 min/max로 **자동 clamp**되므로 raw 각도를 직접 계산할 필요가 없습니다.
> 손모양별 기대 입력값은 [`aihand_gesture_checklist_final.md`](aihand_gesture_checklist_final.md) 참고.

### 2-4. 여기까지 되면 성공
- 숫자 1~7 입력 → 손가락이 **하나씩 순차로**(0.2초 간격) 움직이고 `[수신] OK{n}`이 찍힌다
- `correct` → LED에 O, `incorrect` → LED에 X
- `loop` 35회 동안 끊김·패닉 없음

---

## 3. 꼭 지켜야 할 것 (안 지키면 고장·불안정)

1. **손가락 서보를 한꺼번에 움직이지 않는다.** 펌웨어는 손가락을 150ms 간격으로 하나씩 출발시킵니다
   (인접 2개가 50ms 겹침 — 2026-09-23 연속 실측으로 확정). **간격을 더 줄이지 마세요** — 3개 이상 겹칩니다.
   동시 기동하면 5개 × 700mA = 3.5A로 어댑터 용량(3A)을 넘겨 전압이 떨어지고, 같은 레일의 micro:bit가
   브라운아웃되어 **BLE가 끊깁니다.** (`README.md` "공통 전제")
2. **BLE 시작 후 `music.*` 금지.** 패닉 070. 소리 대신 LED.
3. **안전 가동범위를 넘기지 않는다.** `idx` 명령도 펌웨어에서 clamp되지만, 범위 밖 각도를 계속
   밀어넣으면 서보가 스톨(구속) 상태로 발열합니다. 서보가 "윙" 하고 계속 울면 즉시 전원을 내리세요.
4. **P8 / P12 핀을 쓰지 않는다.** 서보 컨트롤러 시리얼 전용입니다.
5. **USB 시리얼로 통신하려 하지 않는다.** `startbit_Init()`이 하나뿐인 하드웨어 UART를 서보 쪽으로
   가져가므로 USB 시리얼은 죽습니다. PC 통신은 **BLE 전용**입니다.

---

## 4. 알려진 제약 (고장 아님)

- **엄지 서보 하드웨어 고장 — 교체하지 않기로 확정**(2026-09-21). 펌웨어의 엄지 각도는 그대로 두므로
  명령은 정상 전송되지만 **엄지는 물리적으로 움직이지 않습니다.**
- 그 결과 `G3`↔`G6`, `G4`↔`G7`은 **엄지 외 4손가락 조합이 같아 육안으로 구별되지 않습니다.**
  제스처 재설계는 하지 않기로 했고, 시연에서는 web 화면의 목표 수신호 이름으로 학습자가 구분합니다.
  인식·판정 경로와 무관하므로 KPI에는 영향이 없습니다.
- **부저는 쓰지 않습니다.** 판정 결과 피드백은 **LED O/X 단독**이고 소리는 나지 않습니다. BLE 시작 후
  `music.*`을 부르면 패닉 070이 나기 때문입니다 — 예전 문서·주석에 남아 있던 "부저 모스 `-`/`..`"
  설명은 2026-09-22 정리했습니다.
- ~~`correct`/`incorrect` 처리 중 LED 표시 동안 다른 BLE 명령이 처리되지 않는다~~ → **2026-09-23 해소.**
  LED 표시를 백그라운드로 돌려 표시 중에도 다음 명령을 바로 받습니다(이전엔 result 직후 명령이 1.4초
  밀렸음). 재검증 대기 — `aihand_test.py --auto`에서 result·progress가 300ms를 넘으면 🔴로 표시됩니다.

---

## 5. 문제 해결

| 증상 | 원인 / 조치 |
| --- | --- |
| `micro:bit를 찾지 못했습니다.` | ① micro:bit 전원 확인(LED에 ◆ 표시) ② PC 블루투스 ON ③ MakeCode 탭 닫기 ④ 다른 프로그램/휴대폰 앱이 이미 연결 중이면 해제 ⑤ micro:bit 뒷면 리셋 버튼 한 번 |
| 스캔은 되는데 **연결/전송 실패** | 1-5의 **No Pairing Required**가 꺼진 채 올라갔을 가능성이 큼 → 설정 켜고 **다시 다운로드**. Windows에 페어링된 micro:bit 항목이 있으면 제거 |
| `characteristic does not support notifications` | 보드/펌웨어가 바뀌어 UUID가 다를 수 있음 → `python tests/ble_debug_services.py`로 실제 UUID 확인 후 상수 갱신 |
| 명령을 보내도 **아무 반응 없음**(에러도 없음) | PC와 micro:bit의 **`TEST_MODE` 값 불일치**가 1순위. 운영 모드 펌웨어는 `G1` 형식만, 테스트 모드는 `G:1` 형식을 받습니다 |
| 슬픈 얼굴 + **070** | BLE 동작 중 `music.*` 호출 (SD_ASSERT). 소리 코드를 모두 제거하고 LED로 대체 |
| 슬픈 얼굴 + **020** | 메모리 부족 — 불필요한 확장/코드를 줄이세요 |
| 서보가 떨리거나 중간에 BLE가 끊김 | 전원 문제. 7.5V 어댑터 연결·스위치 확인, 동시 구동 코드가 들어가지 않았는지 확인 |
| 작은 다이아몬드가 계속 깜빡임 | 확장보드 저전압 경고 — 어댑터 용량/접촉 불량 확인 |
| 손가락이 **반대 방향**으로 움직임 | 검지~소지는 서보 장착 방향이 반대라 펌웨어가 `moveInverted()`(180-각도)로 보냅니다. `idx` 명령만은 **반전 없이 raw로** 나가므로 방향이 반대로 보이는 게 정상입니다 |
| 특정 손가락만 무반응 | `idx` 명령으로 해당 채널 단독 확인 → 정상 서보를 그 채널에 바꿔 꽂아 **스왑 테스트**(움직이면 채널 정상 = 서보 고장) |
| MakeCode 다운로드 버튼이 기기를 못 찾음 | Edge/Chrome 사용 확인, 데이터 전송용 USB 케이블인지 확인, 안 되면 `.hex`를 `MICROBIT` 드라이브에 직접 복사 |

---

## 6. 다음 단계 — 서비스로 돌리기

위 수동 테스트가 끝나면, 같은 BLE 경로를 FastAPI로 감싼 운영 서비스로 넘어갑니다
(RPi5에서 실행, `TEST_MODE = false` 펌웨어 기준).

```bash
cd services/actuation/src
uvicorn app:app --reload --port 8002
# 또는
docker compose up --build actuation
```

| 엔드포인트 | 역할 |
| --- | --- |
| `GET /health` | `mock_hardware`, `microbit_connected` 확인 |
| `POST /command` | `target_signal`(정지/서행/…) → `G{n}` 변환 후 BLE 전송 |
| `POST /result` | `is_correct` → `correct`/`incorrect` (LED O/X) |
| `POST /progress` | `current`/`total` → `P<current><total>` |

> 실물 없이 매핑·프로토콜만 검증하려면: `cd services/actuation && python -m pytest tests -q`
> (BLE를 건드리지 않습니다). 자세한 내용은 [README.md](../README.md).
