# SafeSign PhysicalAI — 심기일전

산업 안전 수신호 교육용 피지컬 AI (AI Hand + picar + micro:bit + Raspberry Pi 5 + Raspberry Pi 4B 8GB)

**개발 착수 시 반드시 먼저 읽을 문서**: [document/10_PRD_v2.md](document/10_PRD_v2.md) — 번호 문서를
종합한 최신 요구사항입니다. 문서 전체 지도는 [document/README.md](document/README.md)에 있습니다.

---

## 1. 디렉터리 구조 (담당자별 컨테이너 분리)

`document/10_PRD_v2.md` §4 시스템 아키텍처와 `document/01_프로젝트계획서_v4.md` §역할 및 책임(RACI)을 기준으로 5개 서비스로
나눴습니다. 각자 자기 서비스 폴더 안에서만 작업하면 다른 사람 코드와 충돌 없이 개발할 수 있고,
마지막에 `docker compose up`으로 전부 합쳐서 로컬 통합 구동을 확인합니다.

```
SafeSign_PhysicalAI/
├── document/              # 기획/설계/계약 문서 (README.md = 색인, 10_PRD_v2.md = 종합본)
├── services/
│   ├── vision/             ← 이동혁 담당 (Perception + Cognition, 판정로직 R) — Raspberry Pi 5
│   ├── actuation/          ← 송승호 담당 (AI Hand + micro:bit, 하드웨어 R) — Raspberry Pi 5
│   ├── picar/              ← 송승호 담당 (picar 전용 컨트롤러, 하드웨어 R) — Raspberry Pi 4B 8GB (신규)
│   ├── web/                ← 조은수 담당 (프론트엔드 + 교육 상태머신 백엔드, 웹 R)
│   └── data/                ← 김지훈 담당 (데이터 수집 스크립트 + 수신호 템플릿 DB, 데이터수집 R)
├── shared/                 # 5개 서비스 공통: 03_인터페이스계약서_v2 기반 스키마 (필드명 그대로 코드 변수명에 사용)
├── docker-compose.yml      # 5개 서비스 통합 실행
├── .env.example
└── .gitignore
```

담당 외 서비스도 A/C/I 역할로 참고는 하되, 실제 코드 작업은 본인 폴더 위주로 진행하고
인터페이스는 `shared/schemas/`에 정의된 스키마로만 주고받으세요. 스키마를 바꿔야 하면
`shared/schemas/` 파일과 `document/03_인터페이스계약서_v2.md`를 함께 갱신하고 팀에 공유합니다.

## 2. 확정된 하드웨어/아키텍처 (2026-09-18, PRD §1.3·§11 기준)

- **보드 2대로 분리**: picar가 주행하면 카메라도 함께 이동해버리는 문제 때문에, **Raspberry Pi 5**
  (카메라·AI Hand·micro:bit, 학습자 앞 **고정**)와 **Raspberry Pi 4B 8GB**(picar 차체에 탑재, **이동**)
  로 나누고 **Wi-Fi(HTTP)** 로 통신합니다. `services/vision`·`services/actuation`은 RPi5에,
  `services/picar`는 RPi4B에 배포됩니다.
- **카메라**: Raspberry Pi Camera Module 3, **CSI** 직결 (범용 USB 웹캠 아님)
- **picar 통신**: RPi5 → RPi4B, HTTP POST, **타임아웃 500ms + 1회 재시도**, 실패 시 picar 없이
  AI Hand + micro:bit로 진행 (보조 출력으로 간주)
- **MediaPipe 실행 모드**: `LIVE_STREAM`(비동기 콜백) — 개발 편의보다 실시간 성능 우선
- **판정 임계값/프레임 수 초기값**: τ=0.75, N=3프레임 (하드웨어 제약 근거 초기값, 실물 도착 후 재검증)
- **서보 각도 초기값**: 펴짐=170°, 굽힘=10°, 손목중립=90°
- **수신호 등록(실시간 추가) 기능은 범위에서 제외** — 경량 분류기(SVM)는 고정 클래스만 예측 가능해
  재학습 없는 실시간 등록이 성립하지 않음. DB 템플릿은 `services/data/src/seed_templates.py`로
  오프라인 시드

## 3. 로컬 실행 (개발 PC, mock)

하드웨어 없이 개발 PC에서 5개 서비스를 한꺼번에 띄운다. 카메라·서보·모터는 전부 목업 응답이다.
**실물(RPi5 + RPi4B)로 돌리려면 [4. 실물 실행](#4-실물-실행--네이티브-rpi5--rpi4b)을 볼 것.**

```bash
docker compose up --build
```

- vision    → http://localhost:8001/health , http://localhost:8001/latest
- actuation → http://localhost:8002/health
- picar     → http://localhost:8003/health
- web       → http://localhost:8000

데이터 수집/DB 초기화 도구는 상시 구동 서비스가 아니라 필요할 때만 실행합니다.

```bash
docker compose --profile tools run --rm data-tools python src/init_db.py
docker compose --profile tools run --rm data-tools python src/seed_templates.py
```

> ⚠️ Windows Docker Desktop은 CSI 카메라·GPIO·I2C·BLE 장치 전달을 지원하지 않으므로, 개발 PC에서는
> `MOCK_CAMERA=true`, `MOCK_HARDWARE=true`(둘 다 기본값)로 목업 응답을 받으며 개발한다. 로컬
> docker-compose에서 `web`이 `picar`를 호출하는 것은 실물 배포에서의 **Wi-Fi 통신을 흉내 낸 것**이다.

## 4. 실물 실행 — 네이티브 (RPi5 + RPi4B)

실물은 **Docker 없이 각 보드에서 서비스를 직접 띄우는 방식(네이티브)** 이 기준 경로다. 2026-09-25 전 구간
통합 테스트를 이 방식으로 통과했다. (Docker 실물 구성 `docker-compose.hw.yml`은 준비됐지만 아직 실물
미검증 — 각 서비스 README의 "실물 실행 (Docker)" 참고.)

### 4.0 구성 한눈에

```
 [시연 PC] ──UTP── [RPi5 (고정 스테이션)] ──Wi-Fi(AP)── [RPi4B (picar 차체)]
  브라우저            vision    :8001                       picar :8000
                      actuation :8002 ──BLE── micro:bit ── AI Hand
                      web       :8000
```

| 보드 | 서비스 | 폴더 | 포트 | 주소 |
| --- | --- | --- | --- | --- |
| RPi4B | picar | `services/picar` | 8000 | `192.168.50.10` (AP 고정) |
| RPi5 | actuation | `services/actuation` | 8002 | `localhost` |
| RPi5 | vision | `services/vision` | 8001 | `localhost` |
| RPi5 | web | `services/web` | 8000 | PC에서 `http://<RPi5 eth0 주소>:8000` |

- RPi5 ↔ RPi4B 무선(AP) 구성은 [document/네트워크설정법.md](document/네트워크설정법.md)를 먼저 끝낸다.
- **PC ↔ RPi5 유선(UTP) 대역은 현장마다 다르다.** 조건은 하나 — picar AP 대역 `192.168.50.x`와 겹치지 않을 것
  (`document/11_하드웨어설계서_v1.md` §6.1). web은 `0.0.0.0`에 뜨므로 코드는 바꿀 필요가 없다.

### 4.1 최초 1회 준비

**① 두 보드에 같은 코드 받기**

```bash
# RPi5와 RPi4B 각각에서
cd ~/git/SafeSign_PhysicalAI
git pull
git log --oneline -1          # 두 보드의 커밋이 같아야 한다
```

**② RPi4B — I2C 켜기 + picar 가상환경**

```bash
sudo raspi-config nonint do_i2c 0
i2cdetect -y 1                # 16 이 보여야 한다 (모터 코프로세서 0x16)

cd ~/git/SafeSign_PhysicalAI/services/picar
python3 -m venv --system-site-packages .venv   # OS에 깔린 lgpio·gpiozero를 함께 쓴다
source .venv/bin/activate
pip install -r requirements.txt
```

**③ RPi5 — 서비스마다 가상환경 (3개)**

```bash
# 카메라 라이브러리는 pip가 아니라 apt로 설치한다
sudo apt update && sudo apt install -y python3-picamera2 fonts-nanum
rpicam-hello --list-cameras   # imx708 (Camera Module 3) 이 보여야 한다

cd ~/git/SafeSign_PhysicalAI/services/vision
python3 -m venv --system-site-packages .venv   # ⚠️ 이 옵션이 있어야 venv 안에서 picamera2가 보인다
source .venv/bin/activate && pip install -r requirements.txt && deactivate

cd ~/git/SafeSign_PhysicalAI/services/actuation
python3 -m venv .venv
source .venv/bin/activate && pip install -r requirements.txt && deactivate

cd ~/git/SafeSign_PhysicalAI/services/web
python3 -m venv .venv
source .venv/bin/activate && pip install -r requirements.txt && deactivate
```

> 🔴 `pip install`에서 `error: externally-managed-environment`가 나면 **가상환경이 켜지지 않은 것**이다.
> `source .venv/bin/activate`부터 하고, **`--break-system-packages`는 쓰지 않는다**(OS의 Python이 깨질 수 있다).

**④ RPi5 — 판정 모델 파일 복사** (`svm_classifier.joblib`은 git에 없다)

```bash
# 모델이 있는 PC에서
scp services/vision/models/svm_classifier.joblib <사용자>@<RPi5 주소>:~/git/SafeSign_PhysicalAI/services/vision/models/
```

**⑤ micro:bit — 펌웨어 플래시**

MakeCode(makecode.microbit.org)에서 **StartbitV2 확장이 들어 있는 기존 프로젝트**를 열고, JavaScript 보기에서
기존 내용을 지운 뒤 [services/actuation/src/firmware/aihand_control.ts](services/actuation/src/firmware/aihand_control.ts)를
**통째로 붙여 넣어** 플래시한다. 켜면 LED에 ◇가 뜬다.

> ⚠️ 일부만 고쳐 넣지 말 것 — 엄지 서보가 고장이라 손모양 차이가 **눈으로 안 보이는** 경우가 있어,
> 저장소와 micro:bit가 어긋나도 모를 수 있다(2026-09-25 `gesture5` 사례).

### 4.2 실행 — 매번 (터미널 4개, 이 순서대로)

**터미널 1 — RPi4B: picar**

```bash
cd ~/git/SafeSign_PhysicalAI/services/picar
source .venv/bin/activate
MOCK_HARDWARE=false uvicorn app:app --app-dir src --host 0.0.0.0 --port 8000
```

- 🔴 RPi4B는 차체 배터리에서 급전받는다. **USB-C 어댑터를 동시에 꽂지 않는다**(헤더 5V에 역류 방지 없음).
- 배터리 스위치를 손 닿는 곳에 둔다.

**터미널 2 — RPi5: actuation (AI Hand + micro:bit)**

```bash
bluetoothctl show | grep Discovering   # → no 여야 한다. yes면 scan on 켠 창에서 scan off / 모르면 pkill bluetoothctl

cd ~/git/SafeSign_PhysicalAI/services/actuation
source .venv/bin/activate
MOCK_HARDWARE=false uvicorn app:app --app-dir src --host 0.0.0.0 --port 8002
```

콘솔에 `micro:bit BLE 연결됨: BBC micro:bit [...]`이 뜨고 micro:bit LED가 ✓로 바뀌면 성공이다.

**터미널 3 — RPi5: vision (카메라 + 판정)**

```bash
cd ~/git/SafeSign_PhysicalAI/services/vision
bash scripts/run_rpi5.sh       # 가상환경을 알아서 켜고 CSI 카메라로 :8001에 뜬다
```

"`svm_classifier.joblib` 이 없습니다" 경고가 나오면 4.1 ④를 먼저 한다.

**터미널 4 — RPi5: web**

```bash
cd ~/git/SafeSign_PhysicalAI/services/web     # ⚠️ 이 폴더에서 실행해야 화면 파일(frontend/)을 찾는다
source .venv/bin/activate
PICAR_URL=http://192.168.50.10:8000 uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

`PICAR_URL`을 빼면 기본값(`localhost:8003`)으로 가서 picar가 움직이지 않는다.

**PC — 브라우저**

```bash
# RPi5에서 유선 주소 확인
ip -4 addr show eth0
```

PC 브라우저에서 `http://<위 주소>:8000` → SC-01 화면. 상단 장치 상태가 전부 정상이어야 한다.

### 4.3 한 번에 상태 확인 (RPi5의 새 터미널)

```bash
curl -s localhost:8001/health | python3 -m json.tool           # model.loaded: true, camera.state: running
curl -s localhost:8002/health                                  # microbit_connected: true
curl -s 192.168.50.10:8000/health | python3 -m json.tool       # status: ok, hardware.i2c.reachable: true, max_speed_pct: 50
curl -s localhost:8000/api/state | python3 -m json.tool        # devices 3개 모두 ok
```

진행 중 이상하면 `/api/state`의 `last_dispatch`(어느 장치로 보낸 명령이 실패했는지)와 `live_judgment`를 본다.
`ok: true`여도 `body.status`가 `timeout`·`partial`이면 실패다.

### 4.4 (선택) web 없이 하드웨어만 통합 확인

web에서 문제가 나면 **하드웨어 쪽인지 web 쪽인지** 가르기 위해 web 없이 돌린다. 터미널 1~3만 띄운 상태에서:

```bash
cd ~/git/SafeSign_PhysicalAI/services/actuation
source .venv/bin/activate
python3 scripts/aihand_vision_picar_demo.py --picar http://192.168.50.10:8000
```

AI Hand 시범 → (3초 보기) → 학습자가 따라 하기 → 판정 → picar·micro:bit 반응 순으로 7종을 진행하고, 끝나면
요약 표와 CSV를 남긴다. 보는 시간은 `--observe`, 오답 확정 시간은 `--wrong-confirm`으로 조절한다.

장치별 단독 확인은 각 서비스 폴더의 스크립트를 쓴다:
`services/actuation/scripts/aihand_test.py --auto --repeat 1` · `services/picar/scripts/load_test.py --url http://localhost:8000 --pattern spin --speed 40 --duration 15`

### 4.5 모니터링 · 종료

```bash
# RPi5 — 온도·스로틀링 (2026-09-25 86.2°C 기록, 액티브 쿨러 필요)
watch -n2 'vcgencmd measure_temp; vcgencmd get_throttled'   # get_throttled=0x0 이어야 정상
```

**종료는 역순으로, 반드시 `Ctrl+C`로** 한다: web → vision → actuation → picar.
actuation을 `kill -9`로 끄거나 SSH가 끊기면 **BlueZ에 BLE 연결이 남아** 다음 실행 때 micro:bit가 스캔에 안
보인다(micro:bit가 ✓ 그대로). 그때는 micro:bit 리셋 또는 `bluetoothctl disconnect <MAC>`.
picar는 끝나면 배터리 스위치를 내린다(정상 종료가 필요하면 `sudo shutdown -h now` 후).

### 4.6 자주 겪는 문제

| 증상 | 원인 | 조치 |
| --- | --- | --- |
| `uvicorn: command not found` | 가상환경이 안 켜짐 | `source .venv/bin/activate` |
| `externally-managed-environment` | 가상환경 밖 pip | 위와 같음. `--break-system-packages` 금지 |
| `micro:bit BLE 연결 실패: TimeoutError` | 다른 BLE 스캔이 켜져 있음 | `bluetoothctl show \| grep Discovering` → `no`로 |
| micro:bit가 스캔에 안 보임 | 이전 서버·bluetoothctl이 연결을 잡고 있음(✓ 표시) | `pgrep -af uvicorn`, micro:bit 리셋 |
| vision `model_not_loaded`로 화면이 계속 대기 | 모델 파일 없음 | 4.1 ④ |
| vision `camera.error: picamera2…` | apt 미설치 또는 venv를 `--system-site-packages` 없이 만듦 | 4.1 ③ 다시 |
| picar가 안 움직임 | web의 `PICAR_URL` 누락, 또는 AP 끊김 | 4.2 터미널 4 · `ping 192.168.50.10` |
| `get_throttled`가 `0x0`이 아님 | RPi5 과열 | 쿨러·통풍, 온도 확인 |

더 자세한 내용: [services/actuation/README.md](services/actuation/README.md)(BLE 문제 해결) ·
[services/vision/README.md](services/vision/README.md)(카메라) · [services/picar/README.md](services/picar/README.md)(모터·LED·속도) ·
[document/네트워크설정법.md](document/네트워크설정법.md)(AP·SSH).

## 5. Git / 브랜치 전략 (제안)

- 각자 자기 서비스 폴더(`services/<본인담당>/`)를 중심으로 작업 브랜치를 나눕니다.
  예: `feat/vision-classifier`, `feat/actuation-aihand`, `feat/picar-motor`, `feat/web-sc03`,
  `feat/data-collection`
- `shared/schemas/`를 변경하는 PR은 반드시 관련자 전원 리뷰(C) 후 머지합니다.
- 통합 확인은 `main`에 머지 후 `docker compose up --build`로 5개 서비스가 함께 뜨는지 확인합니다.

## 6. 문서 연동 체크

- 서비스 간 메시지 필드/스키마 변경 시 → `document/03_인터페이스계약서_v2.md` 갱신
- 아키텍처/범위가 바뀌면 → `document/10_PRD_v2.md`도 함께 갱신 (개별 문서만 고치고 PRD를 방치하지 않기)
- 통합 7종 수신호 목록은 `document/02_설계문서_v2.md` §4·§4-1 · `document/04_데이터셋명세서_v2.md` §1 ·
  `shared/schemas/aihand_command.schema.json` · `shared/schemas/picar_command.schema.json`에서
  동일하게 유지
