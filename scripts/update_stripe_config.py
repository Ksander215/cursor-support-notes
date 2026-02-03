#!/usr/bin/env python3
"""
Скрипт для автоматического обновления Stripe конфигурации в .env.production на VPS
"""

import os
import subprocess
import sys
from pathlib import Path


def read_tokens_file(tokens_file):
    """Читает токены из файла"""
    tokens = {}
    with open(tokens_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    if key.startswith("STRIPE_"):
                        tokens[key] = value
    return tokens


def update_env_on_vps(vps_host, vps_user, ssh_key, vps_path, tokens):
    """Обновляет .env.production на VPS"""
    env_file = f"{vps_path}/.env.production"

    # Создать backup
    print("📦 Создание backup...")
    backup_cmd = f"ssh -i {ssh_key} {vps_user}@{vps_host} 'cd {vps_path} && cp .env.production .env.production.backup.$(date +%Y%m%d_%H%M%S) && echo Backup создан'"
    result = subprocess.run(backup_cmd, shell=True, capture_output=True, text=True)
    print(result.stdout)

    # Обновить каждую переменную
    print("\n📝 Обновление переменных...")
    for key, value in tokens.items():
        if not value or value.endswith("..."):
            print(f"⚠️  Пропуск {key} (пустое значение или placeholder)")
            continue

        # Удалить старую строку и добавить новую
        update_cmd = f"""ssh -i {ssh_key} {vps_user}@{vps_host} 'cd {vps_path} && \\
            if grep -q "^${key}=" .env.production 2>/dev/null; then \\
                sed -i "/^${key}=/d" .env.production; \\
            fi && \\
            echo "{key}={value}" >> .env.production && \\
            echo "✅ {key} обновлен"'"""

        result = subprocess.run(update_cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print(result.stdout.strip())
        else:
            print(f"❌ Ошибка обновления {key}: {result.stderr}")

    # Перезапустить контейнеры
    print("\n🔄 Перезапуск контейнеров...")
    restart_cmd = f"ssh -i {ssh_key} {vps_user}@{vps_host} 'cd {vps_path} && docker compose -f docker-compose.prod.yml restart api worker'"
    result = subprocess.run(restart_cmd, shell=True, capture_output=True, text=True)
    print(result.stdout)

    # Проверить переменные
    print("\n✅ Проверка загруженных переменных...")
    check_cmd = f"ssh -i {ssh_key} {vps_user}@{vps_host} 'cd {vps_path} && docker compose -f docker-compose.prod.yml exec -T api env | grep STRIPE'"
    result = subprocess.run(check_cmd, shell=True, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    else:
        print("⚠️  Переменные не найдены в контейнере")


def main():
    project_root = Path(__file__).parent.parent
    tokens_file = project_root / "stripe_tokens.txt"

    if not tokens_file.exists():
        print(f"❌ Ошибка: файл {tokens_file} не найден")
        sys.exit(1)

    # Загрузить конфигурацию VPS
    vps_deploy_env = project_root / ".vps-deploy.env"
    if not vps_deploy_env.exists():
        print(f"❌ Ошибка: файл {vps_deploy_env} не найден")
        sys.exit(1)

    # Прочитать конфигурацию VPS
    vps_config = {}
    with open(vps_deploy_env) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                vps_config[key.strip()] = value.strip()

    vps_host = vps_config.get("VPS_HOST")
    vps_user = vps_config.get("VPS_USER", "root")
    ssh_key = vps_config.get("SSH_KEY", os.path.expanduser("~/.ssh/id_ed25519"))
    vps_path = vps_config.get("VPS_PATH", "/opt/sec-scanner")

    if not vps_host:
        print("❌ Ошибка: VPS_HOST не установлен в .vps-deploy.env")
        sys.exit(1)

    print("🔧 Обновление Stripe конфигурации на VPS")
    print("=" * 50)
    print(f"VPS: {vps_user}@{vps_host}")
    print(f"Путь: {vps_path}")
    print()

    # Прочитать токены
    tokens = read_tokens_file(tokens_file)

    if not tokens:
        print("❌ Ошибка: токены не найдены в файле")
        sys.exit(1)

    print("📋 Найденные токены:")
    for key, value in tokens.items():
        if value and not value.endswith("..."):
            masked = value[:20] + "..." if len(value) > 20 else value
            print(f"   {key}: {masked}")
    print()

    # Обновить на VPS
    update_env_on_vps(vps_host, vps_user, ssh_key, vps_path, tokens)

    print("\n✅ Готово! Stripe конфигурация обновлена на VPS")


if __name__ == "__main__":
    main()
