"""수신호 템플릿 DB(SQLite) 초기 스키마 생성.

담당: 김지훈
document/03_인터페이스계약서_v2.md §6 참고 — 수신호 등록(실시간 추가) 기능은 범위에서 제외되었으므로,
이 DB는 런타임에 조회만 되고 값은 항상 seed_templates.py로 오프라인 채워진다. 분야(field_id) 개념도
폐지되어 컬럼에서 제거했다.
"""
import os
import sqlite3

DB_PATH = os.getenv("DB_PATH", "/data/db/signdb.sqlite3")


def init_db(path: str = DB_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sign_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sign_name TEXT NOT NULL UNIQUE,  -- 02_설계문서_v2 §4 확정 7종 + negative 중 하나
            vector TEXT NOT NULL,  -- 63차원 랜드마크 벡터, JSON 문자열로 저장
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    conn.close()
    print(f"DB initialized at {path}")


if __name__ == "__main__":
    init_db()
