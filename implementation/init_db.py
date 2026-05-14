from __future__ import annotations

import sqlite3
from pathlib import Path


DEFAULT_DB_PATH = Path(__file__).with_name("school.db")


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS enrollments;
DROP TABLE IF EXISTS courses;
DROP TABLE IF EXISTS students;

CREATE TABLE students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    cohort TEXT NOT NULL,
    age INTEGER NOT NULL CHECK (age > 0),
    gpa REAL NOT NULL CHECK (gpa >= 0 AND gpa <= 4),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    credits INTEGER NOT NULL CHECK (credits > 0)
);

CREATE TABLE enrollments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    score REAL NOT NULL CHECK (score >= 0 AND score <= 100),
    status TEXT NOT NULL DEFAULT 'active',
    enrolled_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
    UNIQUE (student_id, course_id)
);
"""


SEED_SQL = """
INSERT INTO students (name, email, cohort, age, gpa) VALUES
    ('An Nguyen', 'an.nguyen@example.edu', 'A1', 20, 3.75),
    ('Binh Tran', 'binh.tran@example.edu', 'A1', 21, 3.20),
    ('Chi Le', 'chi.le@example.edu', 'B2', 19, 3.90),
    ('Dung Pham', 'dung.pham@example.edu', 'B2', 22, 2.85),
    ('Ha Vo', 'ha.vo@example.edu', 'C3', 20, 3.45);

INSERT INTO courses (code, title, credits) VALUES
    ('MCP101', 'Model Context Protocol Basics', 3),
    ('SQL201', 'Practical SQLite', 4),
    ('AI305', 'Applied AI Systems', 3);

INSERT INTO enrollments (student_id, course_id, score, status) VALUES
    (1, 1, 92.5, 'active'),
    (1, 2, 88.0, 'active'),
    (2, 1, 81.0, 'active'),
    (2, 3, 79.5, 'active'),
    (3, 2, 95.0, 'active'),
    (3, 3, 97.5, 'active'),
    (4, 1, 70.0, 'active'),
    (5, 3, 86.5, 'active');
"""


def create_database(db_path: str | Path = DEFAULT_DB_PATH) -> Path:
    """Create a reproducible SQLite database and return its path."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.executescript(SEED_SQL)
        conn.commit()

    return path


if __name__ == "__main__":
    print(create_database())
