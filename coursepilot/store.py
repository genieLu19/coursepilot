import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS chunks (
                  id TEXT PRIMARY KEY, course TEXT, source TEXT, section TEXT,
                  page INTEGER, text TEXT, model TEXT, vector TEXT);
                CREATE INDEX IF NOT EXISTS ix_course ON chunks(course);
                CREATE TABLE IF NOT EXISTS embedding_cache (
                  key TEXT PRIMARY KEY, vector TEXT);
                CREATE TABLE IF NOT EXISTS messages (
                  id INTEGER PRIMARY KEY, session TEXT, course TEXT, role TEXT, content TEXT);
                CREATE TABLE IF NOT EXISTS quizzes (
                  id TEXT PRIMARY KEY, session TEXT, course TEXT, topic TEXT, data TEXT,
                  answers TEXT, score REAL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE IF NOT EXISTS plans (
                  id INTEGER PRIMARY KEY, session TEXT, course TEXT, data TEXT,
                  created_at TEXT DEFAULT CURRENT_TIMESTAMP);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def chunks(self, course):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM chunks WHERE course=? ORDER BY source,page,id", (course,)).fetchall()
        return [dict(row) for row in rows]

    def courses(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute(
                "SELECT course AS id, COUNT(*) AS chunks, COUNT(DISTINCT source) AS documents "
                "FROM chunks GROUP BY course")]

    def replace_document(self, course, source, chunks):
        with self.connect() as db:
            db.execute("DELETE FROM chunks WHERE course=? AND source=?", (course, source))
            db.executemany("INSERT INTO chunks VALUES (:id,:course,:source,:section,:page,:text,:model,:vector)", chunks)

    def cached_embedding(self, key):
        with self.connect() as db:
            row = db.execute("SELECT vector FROM embedding_cache WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def cache_embedding(self, key, vector):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO embedding_cache VALUES (?,?)", (key, json.dumps(vector)))

    def history(self, session, course):
        with self.connect() as db:
            rows = db.execute("SELECT role,content FROM messages WHERE session=? AND course=? "
                              "ORDER BY id DESC LIMIT 12", (session, course)).fetchall()
        return [dict(r) for r in reversed(rows)]

    def save_turn(self, session, course, user, assistant):
        with self.connect() as db:
            db.executemany("INSERT INTO messages(session,course,role,content) VALUES (?,?,?,?)",
                           [(session, course, "user", user), (session, course, "assistant", assistant)])

    def save_quiz(self, session, course, topic, data):
        quiz_id = str(uuid.uuid4())
        with self.connect() as db:
            db.execute("INSERT INTO quizzes(id,session,course,topic,data) VALUES (?,?,?,?,?)",
                       (quiz_id, session, course, topic, json.dumps(data, ensure_ascii=False)))
        return quiz_id

    def quiz(self, session, quiz_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM quizzes WHERE id=? AND session=?", (quiz_id, session)).fetchone()
        if not row:
            raise ValueError("Тест не найден в текущем профиле.")
        item = dict(row)
        item["data"] = json.loads(item["data"])
        return item

    def grade(self, session, quiz_id, answers):
        with self.connect() as db:
            row = db.execute("SELECT * FROM quizzes WHERE id=? AND session=?", (quiz_id, session)).fetchone()
            if not row:
                raise ValueError("Тест не найден в текущем профиле.")
            questions = json.loads(row["data"])["questions"]
            if len(answers) != len(questions) or any(type(a) is not int or not 0 <= a <= 3 for a in answers):
                raise ValueError("Выбери один ответ для каждого вопроса.")
            if row["answers"]:
                answers = json.loads(row["answers"])
            score = sum(a == q["correct"] for a, q in zip(answers, questions)) / len(questions)
            db.execute("UPDATE quizzes SET answers=?,score=? WHERE id=? AND session=?",
                       (json.dumps(answers), score, quiz_id, session))
        return {"score": score, "answers": answers, "questions": questions}

    def progress(self, session, course):
        with self.connect() as db:
            results = [dict(r) for r in db.execute(
                "SELECT id,topic,score,created_at FROM quizzes WHERE session=? AND course=? "
                "AND score IS NOT NULL ORDER BY created_at DESC", (session, course))]
            plan = db.execute("SELECT data FROM plans WHERE session=? AND course=? ORDER BY id DESC LIMIT 1",
                              (session, course)).fetchone()
        return {"results": results, "completed_quizzes": len(results),
                "average_score": sum(r["score"] for r in results) / len(results) if results else None,
                "plan": json.loads(plan[0]) if plan else None}

    def save_plan(self, session, course, data):
        with self.connect() as db:
            db.execute("INSERT INTO plans(session,course,data) VALUES (?,?,?)",
                       (session, course, json.dumps(data, ensure_ascii=False)))
