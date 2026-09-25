# web ↔ picar/actuation 통신 신뢰성 개선안

**작성일**: 2026-09-21 · **작성자**: 송승호 (하드웨어·로봇동작 R)
**대상 파일**: `services/web/backend/state_machine.py` — **조은수(web 담당) 검토·적용 요청**
**관련**: `11_하드웨어설계서_v1.md` §6.1 · `03_인터페이스계약서_v2.md` §5-2·§7

> picar 실물 구동을 구현하면서, **장치가 조용히 죽어도 web이 알 수 없는 구조**라는 걸 발견했습니다.
> picar 쪽에서 감지에 필요한 정보는 이미 제공하도록 고쳐뒀고(§2), **web에서 그걸 읽어주기만 하면**
> 됩니다. 담당 파일이라 제가 직접 수정하지 않고 변경안으로 정리합니다.

> ✅ **2026-09-25 반영 현황** (web `6f82886`, feature/picar 통합 `6f5d0ca`)
>
> | # | 항목 | 상태 |
> | --- | --- | --- |
> | 변경 1 | `_post_with_retry` 결과 반환 + 4xx/5xx 실패 처리 | ✅ 반영. ⚠️ 단 **HTTP 200이면 `ok: true`** — 본문 `status`(actuation `timeout`, picar `partial`)는 아직 안 본다 |
> | 변경 2 | 전송 결과를 `/api/state`의 `last_dispatch`로 노출 | ✅ 반영 |
> | 변경 3 | `/health` 주기 확인 + 장치 상태 표시 | ✅ 반영 (화면 상단에 BLE 끊김·I2C 무응답 표시) |
> | §4 | 폴링 블로킹 — **C′안**(엔드포인트별 타임아웃 `/command` 1.5초, 나머지 0.5초) | ✅ 반영. C안(0.6초)은 철회 |
> | §5 | `PICAR_URL` 고정 IP | ✅ 2026-09-25 실물 통합에서 `PICAR_URL=http://192.168.50.10:8000`으로 동작 |
>
> 2026-09-25 전 구간 통합에서 드러난 **판정 타이밍 문제**(시범 전·직후 판정)는 통신 신뢰성과 별개라
> 이 문서가 아니라 `11_하드웨어설계서_v1` §10 #22에서 다룬다.

> 📌 **2026-09-23 갱신 — 읽기 전에 확인해 주세요**
>
> 1. **아래에 인용한 `state_machine.py` 코드는 이제 없습니다.** 파이프라인 mock 검증용 임시 구현이었고,
>    2026-09-23 커밋 `bfc6ab1`로 원래 stub으로 되돌렸습니다. 이 문서는 **"이 줄을 고쳐 주세요"가 아니라
>    본 구현 때 지켜야 할 요구사항**으로 읽어 주세요(§3의 코드는 예시입니다).
> 2. 🔴 **§4의 C안(타임아웃 0.6초)은 철회합니다.** AI Hand 실측 결과 `/command`는 손 동작이 끝난 뒤
>    회신하므로 **0.80초**가 걸립니다. 0.6초로 줄이면 **모든 제스처 명령이 timeout**됩니다.
> 3. **actuation은 한 번에 하나씩 호출해 주세요**(§4 참고). 동시에 보내도 이제 actuation이 줄 세워
>    처리하지만(2026-09-23 수정), micro:bit가 명령을 하나씩 처리하므로 병렬로 보내 얻는 이득이 없습니다.

---

## 1. 문제 — 지금은 "조용한 실패"를 감지할 수 없습니다

### 1-1. 응답을 아무도 읽지 않습니다

```python
def _post_with_retry(url: str, json: dict, timeout_s: float) -> None:
    for _ in range(2):
        try:
            httpx.post(url, json=json, timeout=timeout_s)   # ← 반환값을 버립니다
            return
        except httpx.HTTPError:
            continue
```

이 코드는 **HTTP 요청이 예외 없이 끝나면 성공으로 칩니다.** 그래서 아래 경우를 전부 놓칩니다:

| 실제 상황 | 지금 web의 인식 |
| --- | --- |
| picar가 `{"status": "partial", "motor": {"reason": "i2c_failed"}}` 반환 | ✅ 성공 |
| picar가 HTTP 500 반환 | ✅ 성공 (`httpx.post`는 4xx/5xx에 예외를 던지지 않습니다) |
| actuation이 `{"status": "timeout"}` (BLE 무응답) 반환 | ✅ 성공 |

**시연 중 picar 모터가 안 돌아도 화면은 정상으로 보입니다.** 발표 중에 이게 터지면 원인을 찾을
단서가 아무것도 없습니다.

### 1-2. 장치 생존 여부를 알 방법이 없습니다

web → 장치 단방향 호출뿐이고, 세 서비스 모두 `/health`를 갖고 있지만 **아무도 호출하지 않습니다.**
picar가 부팅에 실패했는지, Wi-Fi가 끊겼는지, micro:bit BLE가 빠졌는지 화면에 표시할 근거가 없습니다.

### 1-3. (부차) 폴링 스레드가 최대 십수 초 멈출 수 있습니다

`_dispatch_feedback`이 POST 4번을 **순차 동기 호출**합니다. 최악의 경우
`actuation 3회 × (2초 × 2시도) + picar(0.5초 × 2시도) ≈ 13초` 동안 vision 폴링이 멈춥니다.
로컬 호출이라 평소엔 드러나지 않지만, BLE가 늘어지면 파이프라인 전체가 정지합니다.

> **정상 시 소요 (2026-09-23 RPi5 실측)**: `/command` 0.80초 + `/result` 0.04초 + `/progress` 0.04초
> + picar 0.05초 ≈ **0.93초**. 최악 13초는 BLE가 응답하지 않을 때만 해당합니다.

---

## 2. picar 쪽은 이미 준비돼 있습니다 (2026-09-21 반영)

web이 읽어주기만 하면 되도록 아래를 제공합니다.

### `GET /health` — `status` 한 필드로 판정 가능

```json
{
  "status": "degraded",
  "service": "picar",
  "mock_hardware": false,
  "hardware": {
    "i2c": { "bus": 1, "addr": "0x16", "reachable": false, "reason": "OSError: ..." },
    "leds": { "led_red": 13, "led_yellow_left": 5, "led_yellow_right": 6 },
    "leds_unassigned": [],
    "motion_duration_s": 2.0,
    "motion_active": false
  }
}
```

- **`status`: `"ok"` | `"degraded"`** — 프로세스는 살아 있어도 I2C 코프로세서가 응답하지 않으면
  `degraded`입니다. 즉 **"떠 있다"와 "동작한다"를 구분**합니다.
- I2C 프로브는 `write_quick`(주소만 전송)이라 **모터를 돌리지 않는 비파괴 검사**입니다. 마음 편히
  주기적으로 호출하셔도 됩니다.

### `POST /picar` — 응답에 부분 실패가 담깁니다

```json
{
  "status": "partial",
  "motor": { "status": "error", "reason": "i2c_failed", "detail": "..." },
  "led":   { "red": {...}, "yellow_left": {...}, "yellow_right": {...} }
}
```

`status`는 `"ok"` | `"partial"`입니다. LED는 되는데 모터가 죽은 경우 `partial`이 나옵니다.

### 참고 — 다른 서비스도 비슷하게 제공합니다

| 서비스 | `/health`에서 볼 필드 |
| --- | --- |
| actuation | `status`, **`microbit_connected`** (BLE 연결 여부) |
| vision | `status`, `model.loaded` (분류기 적재 여부) |
| picar | `status` (`ok`/`degraded`), `hardware.i2c.reachable` |

---

## 3. 제안하는 변경 (3건)

### 변경 1 — `_post_with_retry`가 결과를 돌려주도록 (필수)

실패해도 **계속 진행하는 정책은 그대로 유지**하되(§7), 결과만 반환합니다.

```python
def _post_with_retry(url: str, json: dict, timeout_s: float) -> dict:
    """실패해도 예외를 삼키고 계속 진행하되, **결과는 돌려준다**.

    03_인터페이스계약서_v2 §7 — 장치 실패가 학습 흐름을 막지 않는다는 정책은 그대로다.
    다만 '무슨 일이 있었는지'를 호출부가 알 수 있어야 화면·로그에 남길 수 있다.
    """
    last_error = None
    for _ in range(2):
        try:
            response = httpx.post(url, json=json, timeout=timeout_s)
        except httpx.HTTPError as exc:
            last_error = type(exc).__name__
            continue

        if response.status_code >= 400:          # httpx는 4xx/5xx에 예외를 던지지 않는다
            last_error = f"http_{response.status_code}"
            continue

        try:
            body = response.json()
        except ValueError:
            body = None
        return {"ok": True, "body": body}

    return {"ok": False, "error": last_error}
```

> **주의**: `httpx.post()`는 4xx/5xx에 예외를 던지지 않습니다. 지금 코드가 서버 오류를 성공으로
> 세는 가장 직접적인 원인입니다.

### 변경 2 — 전송 결과를 세션 상태에 남기고 `/api/state`로 노출 (필수)

```python
def _dispatch_feedback(target_signal: str, is_correct: bool, judgment: dict) -> None:
    ...
    results = {
        "aihand":   _post_with_retry(f"{ACTUATION_URL}/command", {...}, ACTUATION_TIMEOUT_S),
        "result":   _post_with_retry(f"{ACTUATION_URL}/result",  {...}, ACTUATION_TIMEOUT_S),
        "progress": _post_with_retry(f"{ACTUATION_URL}/progress",{...}, ACTUATION_TIMEOUT_S),
    }
    if is_correct:
        results["picar"] = _post_with_retry(
            f"{PICAR_URL}/picar", {...}, PICAR_TIMEOUT_MS / 1000)

    with _lock:
        _session["last_dispatch"] = results
```

`GET /api/state` 응답에 `last_dispatch`를 포함시키면, 화면에서 "AI Hand ✅ / picar ❌(i2c_failed)"
같은 표시가 가능해집니다. **최소한 로그로라도 남으면 시연 중 원인 추적이 됩니다.**

### 변경 3 — 장치 생존 주기 확인 (권장)

```python
DEVICE_HEALTH_INTERVAL_S = float(os.getenv("DEVICE_HEALTH_INTERVAL_S", "5.0"))

def _check_devices(client: httpx.Client) -> dict:
    """5초마다 세 서비스의 /health를 확인. 실패해도 학습 흐름에는 영향 없음."""
    status = {}
    for name, url in (("vision", VISION_URL), ("actuation", ACTUATION_URL), ("picar", PICAR_URL)):
        try:
            body = client.get(f"{url}/health", timeout=1.0).json()
        except (httpx.HTTPError, ValueError):
            status[name] = {"status": "unreachable"}
            continue
        entry = {"status": body.get("status", "unknown")}
        if name == "actuation":
            entry["microbit_connected"] = body.get("microbit_connected")
        status[name] = entry
    return status
```

폴링 루프에 `DEVICE_HEALTH_INTERVAL_S` 간격으로 끼워 넣고 `_session["devices"]`에 저장 →
`/api/state`로 노출하면 됩니다. 화면 구석에 장치 3개 상태등만 있어도 시연 중 대응이 달라집니다.

---

## 4. (선택) 폴링 블로킹 — 판단 요청

§1-3 문제입니다. 해결안이 둘인데 **web 설계 판단 영역이라 결정을 요청드립니다.**

| 안 | 내용 | 장점 | 단점 |
| --- | --- | --- | --- |
| A | 그대로 둔다 | 코드 변경 없음, 순서 보장 | 최악 13초 폴링 정지 |
| B | `_dispatch_feedback`을 워커 스레드로 분리 | 폴링이 멈추지 않음 | 명령 순서·중복 방지 로직 재검토 필요 |
| ~~C~~ | ~~`ACTUATION_TIMEOUT_S`를 2.0 → 0.6초로 축소~~ | — | 🔴 **철회(2026-09-23)** — `/command` 실측 0.80초라 모든 제스처가 timeout |
| C′ | **엔드포인트별 타임아웃** — `/command` **1.5초**, `/result`·`/progress` **0.5초** | 최악 시간 약 1/2, 정상 명령은 포기하지 않음 | 값을 두 개 관리 |

**실측값 (2026-09-23, RPi5 네이티브, `services/actuation/scripts/aihand_test.py`)**

| 엔드포인트 | 정상 응답 | 권장 타임아웃 | 근거 |
| --- | --- | --- | --- |
| `/command` | **794~825ms** (49건) | **≥ 1.5초** | 손 동작이 끝난 **뒤** 회신. 여유 약 2배 |
| `/result` | 26~42ms | 0.5초 | LED 표시 전에 회신(ACK-first) |
| `/progress` | 32~38ms | 0.5초 | |

> ⚠️ actuation 내부의 micro:bit 응답 대기(`ACK_TIMEOUT_S`)가 2.0초라, web 쪽 타임아웃이 이보다 길면
> actuation이 먼저 `{"status": "timeout"}`을 돌려줍니다. **HTTP 200이어도 본문 `status`를 확인해 주세요**(§3 변경 1).

**저(송승호)의 의견**: **C′로 완화**하는 것이 좋겠습니다. 정상 경로는 0.93초로 충분히 빨라서 B(스레드
분리)까지 갈 필요는 없어 보입니다. B를 택하시더라도 **actuation 호출끼리는 순서대로** 보내 주세요 —
micro:bit가 명령을 하나씩 처리하므로 병렬로 보내도 빨라지지 않습니다.

---

## 5. 함께 알아두실 변경 — picar 주소가 고정 IP로 바뀝니다

RPi5 ↔ picar를 **공유기 없이 1:1 무선 직결**(RPi5가 AP)로 확정했습니다
(`11_하드웨어설계서_v1.md` §6.1, 2026-09-21).

```
PICAR_URL=http://192.168.50.10:8000     # 실물 배포 시
```

`.env.example`에 주석으로 반영해뒀습니다. **코드 변경은 필요 없고**(이미 환경변수로 받고 있음),
실물 배포 때 값만 바꾸면 됩니다.

---

## 6. 요약

| # | 변경 | 우선도 | 비고 |
| --- | --- | --- | --- |
| 1 | `_post_with_retry` 결과 반환 (+ 4xx/5xx 처리) | 🔴 필수 | 지금은 서버 오류를 성공으로 셉니다 |
| 2 | 전송 결과를 `/api/state`에 노출 | 🔴 필수 | 시연 중 원인 추적 가능해짐 |
| 3 | `/health` 주기 확인 + 장치 상태 노출 | 🟡 권장 | picar 쪽 준비 완료 |
| 4 | 폴링 블로킹 완화 (A/B/C′ 택1) | 🟡 판단 요청 | 저는 C′ 선호 — **C(0.6초)는 철회**, `/command` ≥ 1.5초 필수 |
| 5 | `PICAR_URL` 고정 IP | ℹ️ 정보 | 코드 변경 불필요 |

1·2번만 적용해도 **"조용한 실패"는 사라집니다.** 적용 중 picar 쪽에서 필요한 정보가 더 있으면
말씀해 주세요 — `/health` 응답에 추가하겠습니다.
