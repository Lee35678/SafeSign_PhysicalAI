// =========================================================
// AiHand 제어 - 운영용 최종 버전 (경량화)
//  - 캘리브레이션용 IDX/HAND 명령 제거 (테스트 완료 후 불필요)
//  - "G:N" 형식만 지원, 문자코드 직접 비교로 substr/split/parseInt 최소화
//  - 명령 형식: "G1" ~ "G7" (콜론도 생략해서 한 글자라도 더 가볍게)
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

function moveServo(index: number, angle: number) {
    let min = fingerMinAngle[index - 1];
    let max = fingerMaxAngle[index - 1];
    if (angle < min) angle = min;
    if (angle > max) angle = max;
    StartbitV2.setPwmServo(StartbitV2.startbit_servorange.range1, index, angle, 100);
}

// 검지/중지/약지/소지는 서보 장착 방향이 반대라서 각도를 뒤집어줌 (엄지는 정상 방향)
function moveInverted(index: number, angle: number) {
    moveServo(index, 180 - angle);
}

// 손가락 하나씩 순차 이동, 각 손가락 사이 100ms 텀
function setHand(thumb: number, index: number, middle: number, ring: number, pinky: number) {
    moveServo(THUMB, thumb);
    basic.pause(100);
    moveInverted(INDEX, index);
    basic.pause(100);
    moveInverted(MIDDLE, middle);
    basic.pause(100);
    moveInverted(RING, ring);
    basic.pause(100);
    moveInverted(PINKY, pinky);
    basic.pause(100);
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

bluetooth.startUartService();

basic.showIcon(IconNames.Diamond);

bluetooth.onBluetoothConnected(function () {
    basic.showIcon(IconNames.Yes);
});

bluetooth.onBluetoothDisconnected(function () {
    basic.showIcon(IconNames.No);
});

// ---- BLE 명령 수신: "G1" ~ "G7" 형식만 처리 (문자코드 직접 비교, 힙 할당 최소화) ----
bluetooth.onUartDataReceived(serial.delimiters(Delimiters.NewLine), function () {
    let msg = bluetooth.uartReadUntil(serial.delimiters(Delimiters.NewLine));

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
