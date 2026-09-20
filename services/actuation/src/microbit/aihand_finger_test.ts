// =========================================================
// AiHand 손가락별 개별 테스트 코드
//  - 버튼만으로도 테스트 가능 (PC/BLE 없이도 사용 가능)
//  - BLE로도 원격 테스트 가능 (IDX 명령)
// =========================================================

const THUMB = 1;
const INDEX = 2;
const MIDDLE = 3;
const RING = 4;
const PINKY = 5;

// 손가락별 안전 가동범위 (실측 완료)
// 인덱스: 0=엄지, 1=검지, 2=중지, 3=약지, 4=소지
const fingerMinAngle: number[] = [60, 20, 25, 25, 30];
const fingerMaxAngle: number[] = [170, 135, 135, 125, 120];
const fingerNames: string[] = ["THUMB", "INDEX", "MIDDLE", "RING", "PINKY"];

function moveServo(index: number, angle: number) {
    let min = fingerMinAngle[index - 1];
    let max = fingerMaxAngle[index - 1];
    if (angle < min) angle = min;
    if (angle > max) angle = max;
    StartbitV2.setPwmServo(StartbitV2.startbit_servorange.range1, index, angle, 200);
}

StartbitV2.startbit_Init();
basic.pause(300);

bluetooth.startUartService();

// ---- 버튼만으로 오프라인 테스트 ----
// A버튼: 테스트할 손가락 인덱스 변경 (1 -> 2 -> 3 -> 4 -> 5 -> 1 ...)
// B버튼: 현재 선택된 손가락을 min/max 각도로 번갈아 이동
let currentIndex = 1;
let atMax = false;

basic.showNumber(currentIndex);

input.onButtonPressed(Button.A, function () {
    currentIndex += 1;
    if (currentIndex > 5) currentIndex = 1;
    atMax = false;
    basic.showString(fingerNames[currentIndex - 1]);
    basic.pause(300);
    basic.showNumber(currentIndex);
});

input.onButtonPressed(Button.B, function () {
    let angle = atMax ? fingerMaxAngle[currentIndex - 1] : fingerMinAngle[currentIndex - 1];
    atMax = !atMax;
    moveServo(currentIndex, angle);
    basic.showString(angle + "");
    basic.pause(300);
    basic.showNumber(currentIndex);
});

// ---- BLE로도 원격 테스트 가능: "IDX:인덱스,각도" ----
// 예: "IDX:1,90" -> 엄지 서보에 90도 (raw, 반전 없음)
bluetooth.onUartDataReceived(serial.delimiters(Delimiters.NewLine), function () {
    let msg = bluetooth.uartReadUntil(serial.delimiters(Delimiters.NewLine));

    if (msg.substr(0, 4) == "IDX:") {
        let body = msg.substr(4, msg.length - 4);
        let parts = body.split(",");
        let idx = parseInt(parts[0]);
        let angle = parseInt(parts[1]);

        moveServo(idx, angle);
        basic.showString(fingerNames[idx - 1] + ":" + angle);
        bluetooth.uartWriteString("OK:IDX" + idx + "=" + angle + "\n");
        basic.pause(300);
        basic.showNumber(currentIndex);
    }
});
