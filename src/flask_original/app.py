# Открываем текущий app.py и ищем функцию audit_history
# Но проще - создадим патч

import os
import sqlite3
import threading
import time
import uuid
from datetime import datetime

from flask import Flask, jsonify, redirect, render_template, request, url_for

from security_agent.core_v2 import SecurityAgentV2

app = Flask(__name__)
app.config["DATABASE"] = os.path.join(
    os.path.abspath(os.path.dirname(__file__)), "instance", "security_dashboard.db"
)


# Инициализация БД
def init_db():
    os.makedirs("instance", exist_ok=True)
    conn = sqlite3.connect(app.config["DATABASE"])
    cursor = conn.cursor()

    # Таблица доменов
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS domains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    # Таблица аудитов
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS audits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain_id INTEGER,
            task_id TEXT,
            status TEXT,
            overall_score REAL,
            risk_level TEXT,
            critical_issues INTEGER,
            warnings INTEGER,
            recommendations TEXT,
            report_path TEXT,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            FOREIGN KEY (domain_id) REFERENCES domains (id)
        )
    """
    )

    conn.commit()
    conn.close()


# Хранилище задач (в памяти)
tasks = {}


def get_db():
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    return conn


def run_audit_task(task_id, domain_id, domain_url, mode="safe"):
    """Запуск аудита в фоновом потоке"""
    try:
        print(f"[Task {task_id}] Starting audit for {domain_url}")

        # Обновляем статус в БД
        db = get_db()
        db.execute(
            "INSERT INTO audits (domain_id, task_id, status, started_at) VALUES (?, ?, ?, ?)",
            (domain_id, task_id, "running", datetime.now().isoformat()),
        )
        db.commit()

        # Запускаем аудит
        agent = SecurityAgentV2(mode=mode)
        result = agent.audit_domain(domain_url)

        # Сохраняем результат в БД
        db.execute(
            """
            UPDATE audits SET
                status = ?, overall_score = ?, risk_level = ?,
                critical_issues = ?, warnings = ?,
                recommendations = ?, completed_at = ?
            WHERE task_id = ?
        """,
            (
                "completed",
                result["overall_score"],
                result["risk_level"],
                len(result.get("critical_issues", [])),
                len(result.get("warnings", [])),
                "; ".join(result.get("recommendations", [])[:3]),
                datetime.now().isoformat(),
                task_id,
            ),
        )
        db.commit()
        db.close()

        # Обновляем задачу в памяти
        tasks[task_id].update(
            {"status": "completed", "result": result, "completed_at": time.time()}
        )

        print(f"[Task {task_id}] Audit completed. Score: {result['overall_score']}/100")

    except Exception as e:
        print(f"[Task {task_id}] Audit failed: {e}")
        db = get_db()
        db.execute(
            "UPDATE audits SET status = ?, completed_at = ? WHERE task_id = ?",
            ("failed", datetime.now().isoformat(), task_id),
        )
        db.commit()
        db.close()

        tasks[task_id].update({"status": "failed", "error": str(e)})


@app.route("/")
def index():
    return redirect(url_for("domains_list"))


@app.route("/domains")
def domains_list():
    db = get_db()
    domains = db.execute("SELECT * FROM domains ORDER BY created_at DESC").fetchall()

    # Получаем все аудиты для отображения
    audits = db.execute(
        """
        SELECT a.* FROM audits a
        INNER JOIN (
            SELECT domain_id, MAX(started_at) as max_date
            FROM audits
            WHERE status = 'completed'
            GROUP BY domain_id
        ) latest ON a.domain_id = latest.domain_id AND a.started_at = latest.max_date
        ORDER BY a.started_at DESC
    """
    ).fetchall()

    db.close()
    return render_template("domains_fixed.html", domains=domains, audits=audits)


@app.route("/domain/<int:domain_id>")
def domain_detail(domain_id):
    db = get_db()
    domain = db.execute("SELECT * FROM domains WHERE id = ?", (domain_id,)).fetchone()

    if not domain:
        db.close()
        return "Domain not found", 404

    # Получаем последние аудиты для этого домена
    audits = db.execute(
        """
        SELECT * FROM audits
        WHERE domain_id = ?
        ORDER BY started_at DESC
        LIMIT 10
    """,
        (domain_id,),
    ).fetchall()

    db.close()

    # Используем исправленный шаблон
    return render_template(
        "domain_detail_fixed.html", domain=dict(domain), audits=audits, tasks=tasks
    )


@app.route("/domain/add", methods=["GET", "POST"])
def add_domain():
    if request.method == "POST":
        # Получаем данные из формы (используем правильные имена полей)
        name = request.form.get("domain_name", "").strip()
        url = request.form.get(
            "domain_name", ""
        ).strip()  # Используем то же поле для URL

        if not name:
            return "Domain name is required", 400

        # Добавляем https:// если нет протокола
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        db = get_db()
        cursor = db.execute(
            "INSERT INTO domains (name, url) VALUES (?, ?)", (name, url)
        )
        domain_id = cursor.lastrowid
        db.commit()
        db.close()

        return redirect(url_for("domain_detail", domain_id=domain_id))

    return render_template("add_domain_simple.html")


@app.route("/domain/<int:domain_id>/audit", methods=["POST"])
def start_audit(domain_id):
    db = get_db()
    domain = db.execute("SELECT * FROM domains WHERE id = ?", (domain_id,)).fetchone()
    db.close()

    if not domain:
        return jsonify({"error": "Domain not found"}), 404

    # Создаем задачу
    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        "id": task_id,
        "domain_id": domain_id,
        "domain_url": domain["url"],
        "status": "running",
        "started_at": time.time(),
        "result": None,
    }

    # Запускаем в фоне
    thread = threading.Thread(
        target=run_audit_task, args=(task_id, domain_id, domain["url"], "safe")
    )
    thread.daemon = True
    thread.start()

    return jsonify(
        {
            "task_id": task_id,
            "status": "started",
            "message": f"Audit started for {domain['url']}",
            "redirect": url_for("domain_detail", domain_id=domain_id),
        }
    )


@app.route("/audit/status/<task_id>")
def audit_status(task_id):
    task = tasks.get(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404

    return render_template("audit_status.html", task=task)


@app.route("/domain/<int:domain_id>/history")
def audit_history(domain_id):
    db = get_db()
    domain = db.execute("SELECT * FROM domains WHERE id = ?", (domain_id,)).fetchone()
    audits = db.execute(
        """
        SELECT * FROM audits
        WHERE domain_id = ?
        ORDER BY started_at DESC
    """,
        (domain_id,),
    ).fetchall()
    db.close()

    if not domain:
        return "Domain not found", 404

    # Используем исправленный шаблон
    return render_template("history_fixed.html", domain=dict(domain), audits=audits)


@app.route("/api/audit/status/<task_id>")
def api_audit_status(task_id):
    task = tasks.get(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404

    return jsonify(task)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()
    # Безопасный запуск
    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() in ("true", "1", "t")
    app.run(
        host=os.environ.get("FLASK_HOST", "127.0.0.1"),
        port=int(os.environ.get("FLASK_PORT", 5000)),
        debug=debug_mode,
    )

# Health check endpoints
from health_bp import health_bp

app.register_blueprint(health_bp)
