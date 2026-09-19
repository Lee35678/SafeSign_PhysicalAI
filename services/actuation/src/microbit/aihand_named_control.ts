// =========================================================
// AiHand 5손가락 제어 (매핑 확정 버전)
//  index=1: 엄지 / index=2: 검지 / index=3: 중지 / index=4: 약지 / index=5: 소지
//
//  명령 형식: "HAND:엄지,검지,중지,약지,소지" (각도 0~180, 콤마 구분)
//  예: "HAND:0,180,180,180,180"  -> 검지~소지 펴고 엄지만 접기 등
// =========================================================

const THUMB = 1;
const INDEX = 2;
const MIDDLE = 3;
const RING = 4;
const PINKY = 5;

StartbitV2.startbit_Init();
basic.pause(300);

bluetooth.startUartService();

basic.showIcon(IconNames.Diamond);
basic.showString("READY");

bluetooth.onBluetoothConnected(function () {
    basic.showIcon(IconNames.Yes);
});

bluetooth.onBluetoothDisconnected(function () {
    basic.showIcon(IconNames.No);
});

// 손가락별 안전 가동범위 (실측 완료)
// 인덱스: 0=엄지, 1=검지, 2=중지, 3=약지, 4=소지
let fingerMinAngle: number[] = [60, 20, 25, 25, 30];
let fingerMaxAngle: number[] = [170, 135, 135, 125, 120];

function moveServo(index: number, angle: number) {
    let min = fingerMinAngle[index - 1];
    let max = fingerMaxAngle[index - 1];
    if (angle < min) angle = min;
    if (angle > max) angle = max;
    StartbitV2.setPwmServo(StartbitV2.startbit_servorange.range1, index, angle, 150);
}

// 검지/중지/약지/소지는 서보 장착 방향이 반대라서 각도를 뒤집어줌 (엄지는 정상 방향)
function moveInverted(index: number, angle: number) {
    moveServo(index, 180 - angle);
}

// 손가락 이름으로 한번에 지정 (다른 코드에서도 재사용하기 편하게 함수로 분리)
// 2개씩 묶어서 동시 이동: (엄지+검지) -> 150ms -> (중지+약지) -> 150ms -> 소지
function setHand(thumb: number, index: number, middle: number, ring: number, pinky: number) {
    moveServo(THUMB, thumb);
    moveInverted(INDEX, index);
    basic.pause(150);
    moveInverted(MIDDLE, middle);
    moveInverted(RING, ring);
    basic.pause(150);
    moveInverted(PINKY, pinky);
    basic.pause(150);
}

// ---- 체크리스트 7가지 손동작 (표와 번호 그대로 매칭) ----
function gesture1() { setHand(0, 0, 0, 0, 0); }          // 다섯 손가락 펴기
function gesture2() { setHand(170, 0, 0, 170, 170); }    // 검지+중지 펴기
function gesture3() { setHand(0, 0, 170, 170, 170); }    // 엄지 펴기 + 검지펴기
function gesture4() { setHand(0, 170, 170, 170, 0); }    // 엄지 펴기 + 소지 펴기
function gesture5() { setHand(0, 170, 170, 170, 170); }  // 엄지만 펴기
function gesture6() { setHand(170, 0, 170, 170, 170); }  // 검지 펴기
function gesture7() { setHand(170, 170, 170, 170, 0); }  // 소지 펴기

// ---- BLE 명령 수신 ----
bluetooth.onUartDataReceived(serial.delimiters(Delimiters.NewLine), function () {
    let msg = bluetooth.uartReadUntil(serial.delimiters(Delimiters.NewLine));

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
});

input.onButtonPressed(Button.B, function () {
    basic.showString("READY");
});
