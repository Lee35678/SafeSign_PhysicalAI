"""수신호 템플릿 DB(SQLite) 초기 스키마 생성.

담당: 김지훈
03_인터페이스계약서_v1.md §6 (수신호 등록 기능 인터페이스) 참고.
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
            sign_name TEXT NOT NULL,
            field_id TEXT NOT NULL,
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
