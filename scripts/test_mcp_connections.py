#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для тестирования подключений MCP серверов
Дата: 2026-01-28
"""

import os
import sys
import subprocess
from pathlib import Path
from typing import Dict, Optional


def test_github(token: Optional[str]) -> Dict[str, any]:
    """Тестирует подключение к GitHub"""
    if not token:
        return {"status": "skipped", "message": "Токен не указан"}
    
    try:
        import requests
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
        response = requests.get("https://api.github.com/user", headers=headers, timeout=5)
        
        if response.status_code == 200:
            user_data = response.json()
            return {
                "status": "success",
                "message": f"Подключено как: {user_data.get('login', 'unknown')}",
                "data": user_data
            }
        else:
            return {
                "status": "error",
                "message": f"Ошибка API: {response.status_code}",
                "error": response.text
            }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Ошибка подключения: {str(e)}"
        }


def test_postgres(connection_string: Optional[str]) -> Dict[str, any]:
    """Тестирует подключение к PostgreSQL"""
    if not connection_string:
        return {"status": "skipped", "message": "Строка подключения не указана"}
    
    # Проверяем наличие SQLAlchemy
    try:
        from sqlalchemy import create_engine, text
    except ImportError:
        return {
            "status": "error",
            "message": "SQLAlchemy не установлен. Запустите: bash scripts/fix_mcp_dependencies.sh",
            "fix": "Установите зависимости: bash scripts/fix_mcp_dependencies.sh"
        }
    
    # Проверяем, это SQLite или PostgreSQL
    if connection_string.startswith("sqlite"):
        # Тестируем SQLite
        try:
            from sqlalchemy import create_engine, text
            engine = create_engine(connection_string)
            with engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                result.fetchone()
            return {
                "status": "success",
                "message": "SQLite подключение успешно",
                "type": "sqlite"
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Ошибка SQLite: {str(e)}"
            }
    else:
        # Тестируем PostgreSQL
        try:
            from sqlalchemy import create_engine, text
            engine = create_engine(connection_string, connect_args={"connect_timeout": 5})
            with engine.connect() as conn:
                result = conn.execute(text("SELECT version()"))
                version = result.fetchone()[0]
            return {
                "status": "success",
                "message": f"PostgreSQL подключение успешно",
                "type": "postgresql",
                "version": version
            }
        except ImportError as e:
            return {
                "status": "error",
                "message": f"Ошибка импорта: {str(e)}",
                "fix": "Установите psycopg: pip install psycopg[binary]"
            }
        except Exception as e:
            error_msg = str(e)
            if "timeout" in error_msg.lower() or "connection" in error_msg.lower():
                return {
                    "status": "error",
                    "message": f"Ошибка подключения к PostgreSQL: {error_msg}",
                    "fix": "Проверьте:\n  1. Запущен ли PostgreSQL (docker-compose up db)\n  2. Правильность строки подключения в .env.mcp\n  3. Доступность порта 5432"
                }
            return {
                "status": "error",
                "message": f"Ошибка PostgreSQL: {error_msg}"
            }


def test_docker() -> Dict[str, any]:
    """Тестирует доступность Docker"""
    try:
        # Увеличиваем timeout для WSL окружения
        result = subprocess.run(
            ["docker", "ps"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            # Подсчитываем запущенные контейнеры
            lines = result.stdout.strip().split('\n')
            container_count = max(0, len(lines) - 1)  # Минус заголовок
            
            return {
                "status": "success",
                "message": f"Docker доступен, запущено контейнеров: {container_count}",
                "containers": container_count
            }
        else:
            error_msg = result.stderr.strip() if result.stderr else "Неизвестная ошибка"
            return {
                "status": "error",
                "message": f"Docker недоступен: {error_msg}",
                "fix": "Проверьте:\n  1. Запущен ли Docker Desktop (Windows) или Docker daemon (Linux)\n  2. Доступен ли Docker из WSL: wsl -d Ubuntu -e docker ps\n  3. Правильно ли настроен Docker для WSL2"
            }
    except FileNotFoundError:
        return {
            "status": "error",
            "message": "Docker не установлен или не в PATH",
            "fix": "Установите Docker Desktop для Windows или Docker для Linux"
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "message": "Docker команда превысила timeout (10 секунд)",
            "fix": "Проверьте:\n  1. Не перегружен ли Docker daemon\n  2. Попробуйте запустить из WSL терминала напрямую: docker ps\n  3. Перезапустите Docker Desktop"
        }
    except Exception as e:
        error_msg = str(e)
        return {
            "status": "error",
            "message": f"Ошибка проверки Docker: {error_msg}",
            "fix": "Попробуйте запустить скрипт из WSL терминала: wsl -d Ubuntu"
        }


def test_redis(url: Optional[str]) -> Dict[str, any]:
    """Тестирует подключение к Redis"""
    if not url:
        return {"status": "skipped", "message": "URL Redis не указан"}
    
    try:
        import redis
    except ImportError:
        return {
            "status": "skipped",
            "message": "Библиотека redis не установлена. Запустите: bash scripts/fix_mcp_dependencies.sh"
        }
    
    try:
        r = redis.from_url(url, socket_connect_timeout=5)
        r.ping()
        info = r.info()
        return {
            "status": "success",
            "message": "Redis подключение успешно",
            "version": info.get('redis_version', 'unknown')
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Ошибка Redis: {str(e)}"
        }


def load_env_file(env_path: Path) -> Dict[str, str]:
    """Загружает переменные из .env.mcp"""
    env_vars = {}
    if env_path.exists():
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip().strip('"').strip("'")
    return env_vars


def main():
    """Главная функция"""
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    env_file = project_root / ".env.mcp"
    
    print("🧪 Тестирование подключений MCP серверов")
    print("=" * 50)
    print("")
    
    # Загружаем переменные окружения
    env_vars = load_env_file(env_file)
    
    # Загружаем из системных переменных тоже
    github_token = os.getenv('GITHUB_TOKEN') or os.getenv('GITHUB_PERSONAL_ACCESS_TOKEN') or env_vars.get('GITHUB_TOKEN')
    postgres_url = os.getenv('POSTGRES_CONNECTION_STRING') or env_vars.get('POSTGRES_CONNECTION_STRING')
    redis_url = os.getenv('REDIS_URL') or env_vars.get('REDIS_URL')
    
    results = {}
    
    # Тест GitHub
    print("1️⃣  Тестирование GitHub...")
    results['github'] = test_github(github_token)
    status_icon = "✅" if results['github']['status'] == 'success' else "❌" if results['github']['status'] == 'error' else "⏭️"
    print(f"   {status_icon} {results['github']['message']}")
    print("")
    
    # Тест PostgreSQL/SQLite
    print("2️⃣  Тестирование PostgreSQL/SQLite...")
    results['postgres'] = test_postgres(postgres_url)
    status_icon = "✅" if results['postgres']['status'] == 'success' else "❌" if results['postgres']['status'] == 'error' else "⏭️"
    print(f"   {status_icon} {results['postgres']['message']}")
    if results['postgres'].get('version'):
        print(f"      Версия: {results['postgres']['version']}")
    print("")
    
    # Тест Docker
    print("3️⃣  Тестирование Docker...")
    results['docker'] = test_docker()
    status_icon = "✅" if results['docker']['status'] == 'success' else "❌" if results['docker']['status'] == 'error' else "⏭️"
    print(f"   {status_icon} {results['docker']['message']}")
    if results['docker'].get('containers'):
        print(f"      Контейнеров запущено: {results['docker']['containers']}")
    print("")
    
    # Тест Redis
    print("4️⃣  Тестирование Redis...")
    results['redis'] = test_redis(redis_url)
    status_icon = "✅" if results['redis']['status'] == 'success' else "❌" if results['redis']['status'] == 'error' else "⏭️"
    print(f"   {status_icon} {results['redis']['message']}")
    if results['redis'].get('version'):
        print(f"      Версия: {results['redis']['version']}")
    print("")
    
    # Итоги
    print("=" * 50)
    success_count = sum(1 for r in results.values() if r['status'] == 'success')
    error_count = sum(1 for r in results.values() if r['status'] == 'error')
    skipped_count = sum(1 for r in results.values() if r['status'] == 'skipped')
    
    print(f"✅ Успешно: {success_count}")
    print(f"❌ Ошибки: {error_count}")
    print(f"⏭️  Пропущено: {skipped_count}")
    print("")
    
    if error_count > 0:
        print("💡 Рекомендации:")
        for name, result in results.items():
            if result['status'] == 'error':
                print(f"   - {name}: {result.get('message', 'Ошибка')}")
                if result.get('fix'):
                    print(f"     Решение: {result['fix']}")
        print("")
        print("📝 Для исправления проблем:")
        print("   1. Установите зависимости: pip install -r requirements.txt")
        print("   2. Запустите скрипт из WSL: wsl -d Ubuntu -e bash -c 'cd /home/alex/fastapi-project && python3 scripts/test_mcp_connections.py'")
        print("   3. Проверьте Docker: docker ps (из WSL терминала)")
        print("")
    
    if success_count > 0:
        print("🎉 Некоторые подключения работают! Перезапустите Cursor IDE для применения MCP.")
    else:
        print("⚠️  Нет успешных подключений. Проверьте конфигурацию.")


if __name__ == "__main__":
    main()
