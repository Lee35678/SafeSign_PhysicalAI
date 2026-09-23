"""N프레임 연속 동일 클래스 확인 (판정 안정화).

document/05_모델카드_v3.md §3-6, §8-0 참고. 초기 기본값 N=3은 RPi5 CPU 추론 성능 가정에 근거한
잠정치이며, 카메라/실측 데이터 확보 후 재검증한다.

`LIVE_STREAM` 콜백이 비동기로 프레임을 흘려보내므로, 누적 판단은 스레드-세이프해야 한다
(05_모델카드_v3 §3-6).
"""
from __future__ import annotations

import os
import threading
from collections import deque
from typing import Optional

from cognition import model_store


def _resolve_n_frames() -> int:
    """N 결정 우선순위: 환경변수 N_FRAMES > 학습 번들에 기록된 값 > 기본값 3.

    번들에 담는 이유는 모델과 판정 파라미터가 따로 놀지 않게 하기 위함이다
    (거부 규칙도 같은 원칙 — classify.effective_rule 참고).
    """
    env = os.getenv("N_FRAMES")
    if env:
        return int(env)
    bundle = model_store.load_bundle()
    if bundle and bundle.get("n_frames"):
        return int(bundle["n_frames"])
    return 3


N_FRAMES = _resolve_n_frames()


class ConsecutiveVote:
    """최근 N개가 모두 같은 클래스일 때만 확정으로 보는 간단한 안정화기.

    `push(None)`은 "이번 프레임은 유효한 판정이 아니었다"는 뜻으로, 누적을 끊는다
    (손이 사라졌거나 τ 미달이라 미판정된 경우).
    """

    def __init__(self, n_frames: int = N_FRAMES) -> None:
        self.n_frames = max(1, int(n_frames))
        self._recent: deque[Optional[str]] = deque(maxlen=self.n_frames)
        self._lock = threading.Lock()

    def push_and_check(self, predicted_class: Optional[str]) -> bool:
        """클래스를 넣고, 최근 N개가 모두 동일(그리고 None 아님)이면 True."""
        with self._lock:
            if predicted_class is None:
                self._recent.clear()
                return False
            self._recent.append(predicted_class)
            return (
                len(self._recent) == self.n_frames
                and len(set(self._recent)) == 1
            )

    def reset(self) -> None:
        """수신호가 바뀌거나(다음 문제로 전환) 재시도할 때 누적 상태 초기화."""
        with self._lock:
            self._recent.clear()

    def streak(self) -> int:
        with self._lock:
            if not self._recent:
                return 0
            last = self._recent[-1]
            count = 0
            for item in reversed(self._recent):
                if item != last:
                    break
                count += 1
            return count


# 서비스 전역 인스턴스 (카메라 1대·학습자 1명 전제 — 01_프로젝트계획서_v4 제외 범위)
_default = ConsecutiveVote()


def push_and_check(predicted_class: Optional[str]) -> bool:
    return _default.push_and_check(predicted_class)


def reset() -> None:
    _default.reset()


def streak() -> int:
    return _default.streak()
