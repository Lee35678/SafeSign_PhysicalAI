// =========================================================
// AiHand 5손가락 제어 통합 버전
//  - 한 줄(TEST_MODE)만 바꿔서 production/test 모드 전환
//  - production(false): "G1"~"G7" 경량 명령만 처리 (실전 배포용)
//  - test(true): "IDX:", "HAND:", "G:" 명령까지 지원 (캘리브레이션/디버깅용)
//  - "correct"/"incorrect"(판정 결과)와 "P<current><total>"(진행 표시)는 TEST_MODE와 무관하게 항상 처리
// =========================================================

// =========================================================
// 🔴 절대 규칙 — bluetooth.startUartService() 이후 music.* 를 호출하지 않는다
//
// micro:bit v2에서 BLE SoftDevice와 music 라이브러리는 **같은 하드웨어 타이머/PWM 자원을
// 공유**하므로 함께 쓸 수 없다. music.playTone() 등을 호출하면 소리가 나야 할 바로 그 시점에
// 패닉 070(SD_ASSERT)이 발생하고 BLE가 끊긴다.
//
//   - 튜닝으로 우회할 수 있는 타이밍 버그가 **아니다.** 하드웨어 자원 충돌이라 조건을 바꿔도
//     재현된다 (2026-09-21 재현 + 이후 전용 검증으로 확정).
//   - 전례: StartbitV2_patched.ts:324 도 같은 이유로 music.playTone()을 LED 표시로 대체했다.
//   - 한때 이 파일에 BUZZER_ENABLED 플래그로 꺼둔 playResultTone()이 있었으나, **되살릴 수 없는
//     코드를 남겨두면 플래그 한 줄로 패닉을 부르게 되므로 삭제**했다.
//     (원래 의도: correct = 880Hz 1초 / incorrect = 880Hz 200ms 2회. 되살리지 말 것.)
//
// 소리 피드백이 필요하면 basic.showIcon() / basic.showLeds() / basic.showString() 등
// **LED 기반으로 대체**한다.
// =========================================================

const TEST_MODE = false;

const THUMB = 1;
const INDEX = 2;
const MIDDLE = 3;
const RING = 4;
const PINKY = 5;

// 손가락별 안전 가동범위 (실측 완료)
// 인덱스: 0=엄지, 1=검지, 2=중지, 3=약지, 4=소지
let fingerMinAngle: number[] = [60, 20, 25, 25, 30];
let fingerMaxAngle: number[] = [170, 135, 135, 125, 120];

function moveServo(index: number, angle: number) {
    let min = fingerMinAngle[index - 1];
    let max = fingerMaxAngle[index - 1];
    if (angle < min) angle = min;
    if (angle > max) angle = max;
    StartbitV2.setPwmServo(StartbitV2.startbit_servorange.range1, index, angle, 200);
}

// 검지/중지/약지/소지는 서보 장착 방향이 반대라서 각도를 뒤집어줌 (엄지는 정상 방향)
function moveInverted(index: number, angle: number) {
    moveServo(index, 180 - angle);
}

// 손가락 하나씩 순차 이동, 각 손가락 사이 200ms 텀
function setHand(thumb: number, index: number, middle: number, ring: number, pinky: number) {
    moveServo(THUMB, thumb);
    basic.pause(200);
    moveInverted(INDEX, index);
    basic.pause(200);
    moveInverted(MIDDLE, middle);
    basic.pause(200);
    moveInverted(RING, ring);
    basic.pause(200);
    moveInverted(PINKY, pinky);
    basic.pause(200);
}

// ==== 판정 결과 표시 (RESULT, 테스트/시연 공통) ====
// "correct" -> LED에 O 모양 + 부저 모스 '-'(1초 단일 톤), "incorrect" -> LED에 X 모양 + 부저 모스 '..'
// (1초 안에 짧은 두 번). LED는 2초간 표시 후 꺼짐 (부저 1초 재생 + 나머지 1초 LED만 유지)
function showResult(isCorrect: boolean) {
    if (isCorrect) {
        basic.showLeds(`
            . # # # .
            # . . . #
            # . . . #
            # . . . #
            . # # # .
        `);
    } else {
        basic.showLeds(`
            # . . . #
            . # . # .
            . . # . .
            . # . # .
            # . . . #
        `);
    }
    basic.pause(2000);   // 판정 결과 LED 표시 시간. 소리는 쓰지 않는다 (최상단 절대 규칙 참고)
    basic.clearScreen();
}

// ---- 체크리스트 7가지 손동작 ----
function gesture1() { setHand(0, 0, 0, 0, 0); }          // 다섯 손가락 펴기
function gesture2() { setHand(170, 0, 0, 170, 170); }    // 검지+중지 펴기
function gesture3() { setHand(0, 0, 170, 170, 170); }    // 엄지 펴기 + 검지펴기
function gesture4() { setHand(0, 170, 170, 170, 0); }    // 엄지 펴기 + 소지 펴기
function gesture5() { setHand(0, 170, 170, 170, 170); }  // 엄지만 펴기
function gesture6() { setHand(170, 0, 170, 170, 170); }  // 검지 펴기
function gesture7() { setHand(170, 170, 170, 170, 0); }  // 소지 펴기

StartbitV2.startbit_Init();
basic.pause(300);

// 시작할 때 주먹 쥔 형태로 초기 자세 설정
setHand(170, 170, 170, 170, 170);

bluetooth.startUartService();

basic.showIcon(IconNames.Diamond);
if (TEST_MODE) basic.showString("READY");

bluetooth.onBluetoothConnected(function () {
    basic.showIcon(IconNames.Yes);
});

bluetooth.onBluetoothDisconnected(function () {
    basic.showIcon(IconNames.No);
});

// ---- BLE 명령 수신 ----
// production: "G1"~"G7" 경량 형식만 처리 (문자코드 직접 비교)
// test: "IDX:", "HAND:", "G:" 형식까지 지원
bluetooth.onUartDataReceived(serial.delimiters(Delimiters.NewLine), function () {
    let msg = bluetooth.uartReadUntil(serial.delimiters(Delimiters.NewLine));

    // ==== 판정 결과 표시 (RESULT, TEST_MODE와 무관하게 항상 처리) ====
    if (msg == "correct") {
        showResult(true);
        bluetooth.uartWriteString("OK:CORRECT\n");
        return;
    }
    if (msg == "incorrect") {
        showResult(false);
        bluetooth.uartWriteString("OK:INCORRECT\n");
        return;
    }

    // ==== 진행 표시 (PROGRESS, TEST_MODE와 무관하게 항상 처리) ====
    // 형식: "P<current><total>" (둘 다 한 자리 숫자, 7종 고정이라 콜론/parseInt 없이 문자코드로 파싱)
    // 예) "P37" -> 3/7번째. LED 표시는 하지 않음(진행 표시는 화면(web) 쪽 담당) — 수신 확인만 회신.
    // 'P' = 80, '0'=48~'9'=57
    if (msg.charCodeAt(0) == 80 && msg.length == 3) {
        let current = msg.charCodeAt(1) - 48;
        let total = msg.charCodeAt(2) - 48;
        bluetooth.uartWriteString("OKP" + current + total + "\n");
        return;
    }

    if (TEST_MODE) {
        // ==== 테스트용 코드 (캘리브레이션/디버깅, 시연 때는 사용 안 함) ====
        // 개별 인덱스 raw 각도 테스트 (반전 없이 서보에 그대로 전달, 캘리브레이션용)
        // 예: "IDX:2,35" -> 검지 서보(index=2)에 물리적으로 35도 그대로 전달
        if (msg.substr(0, 4) == "IDX:") {
            let body = msg.substr(4, msg.length - 4);
            let parts = body.split(",");
            let idx = parseInt(parts[0]);
            let angle = parseInt(parts[1]);

            moveServo(idx, angle);
            basic.showString("IDX" + idx + ":" + angle);
            bluetooth.uartWriteString("OK:IDX" + idx + "=" + angle + "\n");
            return;
        }

        // 5손가락 동시 제어: "HAND:엄지,검지,중지,약지,소지"
        if (msg.substr(0, 5) == "HAND:") {
            let body = msg.substr(5, msg.length - 5);
            let angles = body.split(",");

            if (angles.length != 5) {
                bluetooth.uartWriteString("ERR:NEED_5_VALUES\n");
                return;
            }

            setHand(
                parseInt(angles[0]),
                parseInt(angles[1]),
                parseInt(angles[2]),
                parseInt(angles[3]),
                parseInt(angles[4])
            );

            basic.showString("HAND OK");
            bluetooth.uartWriteString("OK:HAND\n");
            return;
        }

        // 미리 정의된 제스처 번호 호출: "G:1" ~ "G:7"
        if (msg.substr(0, 2) == "G:") {
            let g = parseInt(msg.substr(2, msg.length - 2));

            if (g == 1) gesture1();
            else if (g == 2) gesture2();
            else if (g == 3) gesture3();
            else if (g == 4) gesture4();
            else if (g == 5) gesture5();
            else if (g == 6) gesture6();
            else if (g == 7) gesture7();
            else {
                bluetooth.uartWriteString("ERR:UNKNOWN_GESTURE\n");
                return;
            }

            basic.showString("G:" + g);
            bluetooth.uartWriteString("OK:G" + g + "\n");
            return;
        }
        return;
    }

    // ==== 시연용 코드 (실전 배포, TEST_MODE=false일 때 실행) ====
    // ---- production: "G1"~"G7" 형식만 처리 (문자코드 직접 비교, 힙 할당 최소화) ----
    // 'G' = 71
    if (msg.charCodeAt(0) != 71) return;

    // '0'=48 ~ '9'=57  ->  숫자 문자 하나를 바로 정수로 변환 (substr/parseInt 없이)
    let g = msg.charCodeAt(1) - 48;

    if (g == 1) gesture1();
    else if (g == 2) gesture2();
    else if (g == 3) gesture3();
    else if (g == 4) gesture4();
    else if (g == 5) gesture5();
    else if (g == 6) gesture6();
    else if (g == 7) gesture7();
    else return;

    bluetooth.uartWriteString("OK" + g + "\n");
});

// ==== 테스트용 코드 ====
if (TEST_MODE) {
    input.onButtonPressed(Button.B, function () {
        basic.showString("READY");
    });
}
