"""오프라인 템플릿 시드: 전처리된 학습 데이터에서 클래스별 대표 벡터를 만들어 DB에 저장.

담당: 김지훈
document/03_인터페이스계약서_v2.md §6 — 수신호 등록(실시간 추가) 기능은 범위에서 제외되었으므로,
수신호 템플릿 DB는 항상 이 스크립트로 배치 생성한다(런타임에는 조회만 발생).

TODO(김지훈):
- datasets/processed/{class_name}/*.json (랜드마크 시퀀스, 04_데이터셋명세서_v2 §6)을 읽어
  클래스별 63차원 벡터의 평균(centroid) 또는 대표 샘플을 계산
- init_db.py로 만든 sign_templates 테이블에 클래스당 1행씩 upsert
- 02_설계문서_v2 §4 확정 7종 + negative, 총 8개 클래스 전부 채워야 vision의 cosine similarity가 동작
"""
import os

PROCESSED_DIR = os.getenv("PROCESSED_DIR", "/data/datasets/processed")
DB_PATH = os.getenv("DB_PATH", "/data/db/signdb.sqlite3")

# 04_데이터셋명세서_v2 §1과 동일 순서
SIGN_CLASSES = [
    "정지",
    "서행",
    "좌회전_유도",
    "우회전_유도",
    "확인_완료",
    "후진",
    "주의",
    "negative",
]


def seed_templates(processed_dir: str = PROCESSED_DIR, db_path: str = DB_PATH) -> None:
    raise NotImplementedError(
        "전처리 데이터(랜드마크 시퀀스) 준비 및 04_데이터셋명세서_v2 §6 폴더 구조 확정 후 구현"
    )


if __name__ == "__main__":
    seed_templates()
