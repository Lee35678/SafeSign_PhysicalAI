# picar — 차체 제어 서비스 (RPi4B)

수신호 판정 결과에 따라 picar 차체의 **모터**(전진·후진·좌우 회전·정지)와 **외부 LED 4개**(적색 2, 황색 2)를
움직이는 서비스입니다.

- 실행 보드: **Raspberry Pi 4B**(picar 차체에 탑재). 카메라·AI Hand·micro:bit가 있는 RPi5와는 다른 보드입니다.
- 통신: RPi5(web)가 Wi-Fi로 `POST http://192.168.50.10:8000/picar`를 보냅니다. RPi5가 AP, picar는 고정 주소
  `192.168.50.10`입니다.
- 실행 방식: Docker 없이 가상환경 + uvicorn(포트 **8000**)으로 직접 띄웁니다.
- 보드를 나눈 이유: 카메라가 차 위에 있으면 주행할 때마다 카메라가 함께 움직여, 학습자가 차를 따라가며 손을
  다시 보여 줘야 했기 때문입니다.

전체 구성은 [루트 README](../../README.md) §4.0을 보세요.

## 1. 하드웨어

| 항목 | 내용 |
| --- | --- |
| 보드 | Raspberry Pi 4B |
| 모터 | Raspbot 차체의 모터 코프로세서를 **I2C 버스 1**(SCL=BCM3, SDA=BCM2)로 제어. 슬레이브 주소 **`0x16`** |
| LED | 외부 LED 4개를 GPIO 4핀으로 직접 구동 (아래 1.2) |
| 전원 | 차체 배터리 **3S 11.1V 2200mAh** → 강압 → 헤더 5V로 Pi까지 공급 (단일 계통) |

### 1.1 모터 (I2C)

Pi는 코프로세서에 레지스터 쓰기만 합니다. 프로토콜은 Yahboom 공식 드라이버(`YB_Pcb_Car.py`) 기준입니다.

| 레지스터 | 용도 | 데이터 |
| --- | --- | --- |
| `0x01` | 모터 구동 | `[좌_방향, 좌_속도, 우_방향, 우_속도]` — 방향 `0`=후진 / `1`=전진, 속도 `0~255` |
| `0x02` | 정지 | `0x00` 한 바이트 |

- API의 `speed`는 `0~100(%)`이고, 서비스가 `0~255`로 바꿔 보냅니다.
- 좌·우 회전은 **제자리 회전**(한쪽 바퀴 전진 + 반대쪽 후진)입니다. 교육 시범에서 회전이 잘 보이게 하려는 선택입니다.
- **Raspbot V2는 주소가 `0x2B`입니다.** 설치할 때 `i2cdetect -y 1`로 먼저 확인하고, `16`이 아니면
  `RASPBOT_I2C_ADDR` 환경변수로 바꿔 띄웁니다.

### 1.2 LED 배선

| 채널 (API 이름) | BCM | 물리 핀 | LED | GND (권장) |
| --- | --- | --- | --- | --- |
| `red` | **13, 19** | 33, 35 | 적색 2개 (핀마다 1개) | 34 |
| `yellow_left` | **5** | 29 | 황색 1개 | 30 |
| `yellow_right` | **6** | 31 | 황색 1개 | 30 |

- **적색 2개는 한 채널**입니다. 핀은 둘이지만 항상 함께 켜지고 함께 깜빡입니다. 수신호에서 적색 한쪽만 켜는
  경우가 없기 때문입니다. 핀을 나눈 것은 핀 하나당 전류를 줄이기 위해서입니다.
- 황색은 좌·우 회전 때 한쪽만 깜빡여야 해서 핀이 따로입니다.
- 보드 내장 LED(적색 BCM21, 청색 BCM20)는 쓰지 않습니다.

**배선 주의**

- 저항은 **LED마다 220Ω 하나씩** 답니다. 저항 하나를 여러 LED가 같이 쓰면 밝기가 고르지 않고 전류가 한쪽으로 쏠립니다.
- 220Ω이면 개당 약 5.9mA(적색) / 5.5mA(황색)로, 핀 기본 구동 한도 8mA 안입니다. **150Ω 이하는 쓰지 않습니다**(약 8.7mA로 한도 초과).
- GND는 쌍으로 묶어도 됩니다(황색 2개 → 물리 30번, 적색 2개 → 물리 34번). 단, **GND를 묶는 것과 저항을 묶는 것은 다릅니다.** 저항은 계속 LED마다 하나입니다.
- 아래 BCM 핀은 Raspbot 차체가 이미 쓰고 있으니 LED 배선에 쓰지 않습니다:
  2·3(I2C), 4·17·22·27(트래킹), 9·10·25(적외선 회피), 23·24(초음파), 12(부저), 16(적외선 수신), 20·21(내장 LED).

### 1.3 전원·안전

> **USB-C 어댑터와 차체 배터리를 동시에 연결하지 마세요.** RPi4B는 배터리에서 헤더 5V로 전원을 받는데,
> 이 핀에는 역류 방지가 없습니다. 어댑터를 쓰려면 배터리 스위치를 먼저 내립니다.

- GND는 항상 공통으로 유지합니다(I2C 기준 전위).
- 배터리 전압이 **9.0V 미만**으로 내려가지 않게 합니다.
- 배터리 스위치를 손 닿는 곳에 둡니다. 정지 명령이 듣지 않을 때의 비상 정지 수단입니다.
- 처음 켜거나 배선을 바꾼 뒤에는 **바퀴가 바닥에 닿지 않게 차를 들어 올린 상태**에서 확인합니다.

## 2. 설치 (최초 1회, RPi4B)

```bash
sudo raspi-config nonint do_i2c 0      # I2C 켜기
i2cdetect -y 1                         # 표에 16 이 보여야 한다 (모터 코프로세서 0x16)

cd ~/git/SafeSign_PhysicalAI/services/picar
python3 -m venv --system-site-packages .venv   # OS에 깔린 lgpio·gpiozero를 함께 쓴다
source .venv/bin/activate
pip install -r requirements.txt
```

- 실행 계정은 `i2c`·`gpio` 그룹에 있어야 합니다.
- 네트워크(AP·고정 IP)와 코드 받기는 [루트 README](../../README.md) §4.1을 따릅니다.

## 3. 실행

평소에는 RPi5에서 `bash scripts/rpi/start_all.sh`로 전체를 띄웁니다. 이 스크립트가 SSH로 RPi4B의 picar를
함께 띄우고 `/health`를 확인합니다([루트 README](../../README.md) §4.2).

RPi4B에서 직접 띄울 때:

```bash
cd ~/git/SafeSign_PhysicalAI/services/picar
source .venv/bin/activate
MOCK_HARDWARE=false uvicorn app:app --app-dir src --host 0.0.0.0 --port 8000
```

- **`MOCK_HARDWARE=false`를 꼭 붙입니다.** 기본값은 `true`(모의 모드)라서, 빠뜨리면 서버는 정상으로 떠도
  모터·LED가 움직이지 않습니다. `/health`의 `mock_hardware`가 `false`인지 확인하세요.
- 끌 때는 `Ctrl+C`로 끕니다. 서비스가 내려가면서 차를 세우고 LED를 끕니다. 전원을 끌 때는
  `sudo shutdown -h now` 후 배터리 스위치를 내립니다.
- 부팅 시 자동 실행이 필요하면 `sudo bash scripts/rpi/systemd/install.sh rpi4b --enable`(저장소 루트에서)로
  `safesign-picar` 서비스를 등록합니다. 아직 현장 검증 전이며, `start_all.sh`와 동시에 쓰지 않습니다(포트 충돌).

## 4. 환경변수

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `MOCK_HARDWARE` | `true` | `true`면 I2C·GPIO를 건드리지 않고 보낼 값만 응답합니다. **실물에서는 `false`** |
| `RASPBOT_I2C_ADDR` | `0x16` | 모터 코프로세서 I2C 주소(16진수). Raspbot V2면 `0x2B` |
| `PICAR_MAX_SPEED` | `50` | 속도 상한(%). 이보다 큰 요청은 상한으로 잘라 실행합니다 |
| `PICAR_MOTION_DURATION_S` | `2.0` | 주행 명령 뒤 자동 정지까지의 시간(초) |
| `PICAR_LED_HOLD_S` | `PICAR_MOTION_DURATION_S`와 같음 | LED를 켠 명령 뒤 자동 소등까지의 시간(초). 0 이하면 자동 소등 안 함 |
| `PICAR_STOP_RETRY` | `3` | 정지 명령 I2C 쓰기 재시도 횟수 |

### 속도 기준

| 용도 | `speed` |
| --- | --- |
| 서행 | 20 |
| 좌·우 회전, 후진 | 40 |
| 상한 | 50 (60은 바닥 주행에서 너무 빨라 쓰지 않음) |

### 자동 정지·자동 소등

- 명령에는 주행 시간을 지정하는 값이 없습니다. 그래서 주행 명령을 받으면 **2초 뒤 스스로 정지**합니다.
  주행을 끝내는 유일한 수단이니 끄지 마세요. 2초 안에 새 주행 명령이 오면 그 시점부터 다시 셉니다.
- LED를 하나라도 켠 명령 뒤에는 2초 뒤 **LED 3채널을 모두 끕니다.** 새 명령이 오면 이전 소등 예약은 취소됩니다.
- 모의 모드(`MOCK_HARDWARE=true`)에서는 두 타이머 모두 걸리지 않습니다.

## 5. HTTP API

### `GET /health`

```bash
curl -s http://192.168.50.10:8000/health | python3 -m json.tool
```

| 필드 | 정상 값 | 의미 |
| --- | --- | --- |
| `status` | `ok` | I2C 코프로세서가 응답하지 않으면 `degraded` |
| `mock_hardware` | `false` | 실물 모드 여부 |
| `hardware.i2c.reachable` | `true` | 코프로세서 응답 여부(모터를 돌리지 않는 확인 방식) |
| `hardware.max_speed_pct` | `50` | 현재 속도 상한 |
| `hardware.motion_duration_s` / `led_hold_s` | `2.0` | 자동 정지·소등 시간 |
| `hardware.motion_active` | — | 자동 정지 타이머가 돌고 있는지(바퀴가 실제로 도는지와는 다름) |
| `hardware.last_stop_error` | `null` | **`null`이 아니면 정지에 실패한 것입니다. 차가 계속 달릴 수 있으니 바로 확인하세요** |

### `POST /picar`

요청 예시 (서행):

```bash
curl -s -X POST http://192.168.50.10:8000/picar -H "Content-Type: application/json" -d '{
  "command": "slow", "target_signal": "서행",
  "motor": {"action": "forward", "speed": 20},
  "led": {"red": "off", "yellow_left": "off", "yellow_right": "off"}}'
```

정지 + LED 모두 끄기:

```bash
curl -s -X POST http://192.168.50.10:8000/picar -H "Content-Type: application/json" -d '{
  "command": "stop", "target_signal": "정지",
  "motor": {"action": "stop", "speed": 0},
  "led": {"red": "off", "yellow_left": "off", "yellow_right": "off"}}'
```

| 필드 | 값 |
| --- | --- |
| `motor.action` | `forward` / `backward` / `left` / `right` / `stop` |
| `motor.speed` | `0~100` (%). `PICAR_MAX_SPEED`를 넘으면 잘림. `stop`은 속도와 관계없이 항상 실행 |
| `led.red` / `led.yellow_left` / `led.yellow_right` | `off` / `on` / `blink` (0.3초 간격) |
| `command`, `target_signal` | 응답에 그대로 돌려줌 |

- `motor`가 없으면 정지, `led`의 채널이 빠지면 그 채널은 `off`로 처리합니다.

응답에서 볼 것:

| 필드 | 의미 |
| --- | --- |
| `status` | 모터 명령이 성공하면 `ok`, 실패하면 `partial` |
| `motor.speed_capped_from` | 속도가 상한으로 잘렸을 때 원래 요청값. 보내는 쪽 설정을 고칠 것 |
| `motor.reason` | `i2c_failed`(I2C 통신 실패), `invalid_speed`(숫자가 아닌 속도), `unknown_motor_action` |
| `led.<채널>.reason` | `gpio_failed`(GPIO 구동 실패, `detail`에 원인), `unknown_led_state` |
| `led_hold_s` | 자동 소등까지의 시간. `null`이면 소등 예약 없음 |

- LED가 실패해도 모터 명령(정지 포함)은 그대로 실행됩니다.
- LED를 결선하지 않아도 응답은 `ok`입니다. **LED는 눈으로 확인해야 합니다.**
- 이 서비스는 받은 명령을 실행만 합니다. 타임아웃·재시도는 보내는 쪽(web)이 맡습니다.

## 6. 설치 후 점검

차를 들어 올려 바퀴가 뜬 상태에서 순서대로 확인합니다.

1. `curl -s localhost:8000/health` → `status: ok`, `mock_hardware: false`, `hardware.i2c.reachable: true`
2. 위 "서행" 요청 → 바퀴가 전진 방향으로 돌고, **2초 뒤 스스로 멈추는지**
3. `action`을 `left`·`right`로 바꿔 → 회전 방향이 맞는지 (반대면 좌우 모터 배선이 뒤바뀐 것)
4. LED 채널마다 `on` / `blink` / `off` → 적색 2개가 함께 동작하는지, 황색 좌(BCM5)·우(BCM6)가 맞는 쪽인지
5. LED를 켠 뒤 2초가 지나면 꺼지는지

## 7. 문제 해결

| 증상 | 원인 | 조치 |
| --- | --- | --- |
| `/health`가 `degraded`, `i2c.reachable: false` | I2C 꺼짐, 배선 불량, 주소 다름 | `sudo raspi-config nonint do_i2c 0`, `i2cdetect -y 1`로 주소 확인 → 다르면 `RASPBOT_I2C_ADDR` |
| 응답은 `ok`인데 차가 안 움직임 | 모의 모드로 떠 있음 | `/health`의 `mock_hardware`가 `true`면 `MOCK_HARDWARE=false`로 다시 실행 |
| RPi5 화면에서 picar만 안 움직임 | web의 `PICAR_URL` 누락, AP 연결 끊김 | 루트 README §4.2의 web 실행 명령 확인, `ping 192.168.50.10` |
| `led.*.reason: gpio_failed` | GPIO 백엔드 문제 또는 권한 | `detail` 확인. 가상환경을 `--system-site-packages`로 만들었는지, 계정이 `gpio` 그룹인지 |
| LED가 안 켜지는데 응답은 `ok` | 결선·극성·저항 문제 | 1.2 배선표와 대조 |
| LED 밝기가 서로 다름 | 저항을 공유함 | LED마다 220Ω 하나씩 |
| `last_stop_error`가 `null`이 아님 | 정지 명령 I2C 쓰기 실패 | 배터리 스위치로 먼저 세운 뒤 I2C 배선·전압 확인 |
| 주행 중 응답이 늦거나 끊김 | 모터와 Pi가 한 전원 계통이라 노이즈·전압 강하 가능 | `vcgencmd get_throttled`(정상 `0x0`), 배터리 전압(9.0V 이상) 확인 |
| 포트 8000이 이미 사용 중 | picar가 이미 떠 있음(tmux 또는 systemd) | `pgrep -af uvicorn`, systemd면 `sudo systemctl stop safesign-picar` |

상태 확인·종료 절차는 [루트 README](../../README.md) §4.3·§4.5, 그 밖의 문제는 §4.6을 보세요.
개발용 자료(테스트 등)는 dev 브랜치에 있습니다.
