"""N프레임 연속 동일 클래스 확인 (판정 안정화).

document/05_모델카드_v3 §3-6, §8-0 참고. 초기 기본값 N=3은 RPi5 CPU 추론 성능 가정에 근거한
잠정치이며, 카메라/실측 데이터 확보 후 재검증한다.
"""
import os
from collections import deque

N_FRAMES = int(os.getenv("N_FRAMES", "3"))

_recent: deque = deque(maxlen=N_FRAMES)


def push_and_check(predicted_class: str) -> bool:
    """최근 N_FRAMES개가 모두 동일 클래스면 True(판정 확정), 아니면 False."""
    _recent.append(predicted_class)
    return len(_recent) == N_FRAMES and len(set(_recent)) == 1


def reset() -> None:
    """수신호가 바뀌거나(다음 문제로 전환) 재시도할 때 누적 상태 초기화."""
    _recent.clear()
