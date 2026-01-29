#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для создания GitHub Issues из roadmap
Дата: 2026-01-28
"""

import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

try:
    import requests
except ImportError:
    print("❌ Установите requests: pip install requests")
    sys.exit(1)


class RoadmapParser:
    """Парсер roadmap файла для извлечения задач"""
    
    def __init__(self, roadmap_path: str):
        self.roadmap_path = Path(roadmap_path)
        if not self.roadmap_path.exists():
            raise FileNotFoundError(f"Roadmap файл не найден: {roadmap_path}")
    
    def parse(self) -> List[Dict]:
        """Парсит roadmap и возвращает список задач"""
        content = self.roadmap_path.read_text(encoding='utf-8')
        tasks = []
        
        # Паттерн для поиска секций с задачами
        # Ищем заголовки типа "#### 1.1 Улучшенная визуализация (P0)"
        section_pattern = r'#### (\d+\.\d+)\s+(.+?)\s+\(P(\d+)\)'
        
        # Паттерн для задач в чекбоксах
        task_pattern = r'- \[ \]\s+(.+?)(?=\n-|$)'
        
        sections = re.finditer(section_pattern, content, re.MULTILINE)
        
        for section_match in sections:
            section_num = section_match.group(1)
            section_title = section_match.group(2).strip()
            priority = f"P{section_match.group(3)}"
            
            # Находим начало и конец секции
            start_pos = section_match.end()
            next_section = re.search(
                r'#### \d+\.\d+',
                content[start_pos:],
                re.MULTILINE
            )
            end_pos = start_pos + next_section.start() if next_section else len(content)
            section_content = content[start_pos:end_pos]
            
            # Извлекаем описание и требования
            description_match = re.search(r'\*\*Требования:\*\*\s*\n((?:- .+\n?)+)', section_content)
            requirements = description_match.group(1) if description_match else ""
            
            # Извлекаем задачи
            tasks_in_section = re.findall(task_pattern, section_content, re.MULTILINE)
            
            # Извлекаем оценку времени
            estimate_match = re.search(r'\*\*Оценка:\*\*\s*(.+)', section_content)
            estimate = estimate_match.group(1).strip() if estimate_match else ""
            
            # Извлекаем статус
            status_match = re.search(r'\*\*Статус:\*\*\s*(.+)', section_content)
            status = status_match.group(1).strip() if status_match else ""
            
            if tasks_in_section:
                # Создаем одну issue для всей секции с подзадачами
                body = self._create_issue_body(
                    section_title,
                    requirements,
                    tasks_in_section,
                    estimate,
                    status,
                    section_content
                )
                
                tasks.append({
                    'title': f"[{priority}] {section_title}",
                    'body': body,
                    'labels': [priority, 'roadmap'],
                    'section_num': section_num,
                    'priority': priority
                })
        
        return tasks
    
    def _create_issue_body(
        self,
        title: str,
        requirements: str,
        tasks: List[str],
        estimate: str,
        status: str,
        full_content: str
    ) -> str:
        """Создает тело issue в формате Markdown"""
        body_parts = []
        
        if status:
            body_parts.append(f"**Статус:** {status}")
            body_parts.append("")
        
        if requirements:
            body_parts.append("## Требования")
            body_parts.append(requirements)
            body_parts.append("")
        
        if tasks:
            body_parts.append("## Задачи")
            for i, task in enumerate(tasks, 1):
                body_parts.append(f"- [ ] {task}")
            body_parts.append("")
        
        if estimate:
            body_parts.append(f"**Оценка времени:** {estimate}")
            body_parts.append("")
        
        # Добавляем ссылку на roadmap
        body_parts.append("---")
        body_parts.append(f"*Создано автоматически из [roadmap](UPGRADE_ROADMAP.md)*")
        
        return "\n".join(body_parts)


class GitHubIssuesCreator:
    """Создатель GitHub Issues через API"""
    
    def __init__(self, token: str, repo: str):
        self.token = token
        self.repo = repo
        self.base_url = "https://api.github.com"
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json"
        }
    
    def create_issue(self, title: str, body: str, labels: List[str]) -> Optional[Dict]:
        """Создает issue в GitHub"""
        url = f"{self.base_url}/repos/{self.repo}/issues"
        data = {
            "title": title,
            "body": body,
            "labels": labels
        }
        
        response = requests.post(url, json=data, headers=self.headers)
        
        if response.status_code == 201:
            return response.json()
        else:
            print(f"❌ Ошибка создания issue: {response.status_code}")
            print(f"   Ответ: {response.text}")
            return None
    
    def get_existing_issues(self) -> List[str]:
        """Получает список существующих issues"""
        url = f"{self.base_url}/repos/{self.repo}/issues"
        params = {"state": "all", "per_page": 100}
        
        response = requests.get(url, params=params, headers=self.headers)
        
        if response.status_code == 200:
            return [issue['title'] for issue in response.json()]
        return []
    
    def ensure_labels(self):
        """Создает необходимые labels если их нет"""
        labels = ['P0', 'P1', 'P2', 'roadmap', 'enhancement', 'bug']
        colors = {
            'P0': 'd73a4a',  # красный
            'P1': 'fb8500',  # оранжевый
            'P2': '0e8a16',  # зеленый
            'roadmap': '0052cc',  # синий
            'enhancement': 'a2eeef',
            'bug': 'd73a4a'
        }
        
        url = f"{self.base_url}/repos/{self.repo}/labels"
        
        for label in labels:
            label_url = f"{url}/{label}"
            # Проверяем существование
            check_response = requests.get(label_url, headers=self.headers)
            
            if check_response.status_code == 404:
                # Создаем label
                data = {
                    "name": label,
                    "color": colors.get(label, "ededed"),
                    "description": f"Label: {label}"
                }
                create_response = requests.post(url, json=data, headers=self.headers)
                if create_response.status_code == 201:
                    print(f"✅ Создан label: {label}")
                else:
                    print(f"⚠️  Не удалось создать label {label}: {create_response.status_code}")


def main():
    """Главная функция"""
    # Получаем токен из переменных окружения
    github_token = os.getenv('GITHUB_TOKEN') or os.getenv('GITHUB_PERSONAL_ACCESS_TOKEN')
    
    if not github_token:
        print("❌ GitHub token не найден!")
        print("Установите переменную окружения GITHUB_TOKEN или GITHUB_PERSONAL_ACCESS_TOKEN")
        print("Или добавьте в .env.mcp: GITHUB_TOKEN=ghp_...")
        sys.exit(1)
    
    # Получаем репозиторий из переменных окружения или запрашиваем
    repo = os.getenv('GITHUB_REPO')
    if not repo:
        repo = input("Введите GitHub репозиторий (owner/repo): ").strip()
        if not repo:
            print("❌ Репозиторий не указан")
            sys.exit(1)
    
    # Путь к roadmap
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    roadmap_path = project_root / "UPGRADE_ROADMAP.md"
    
    if not roadmap_path.exists():
        print(f"❌ Roadmap файл не найден: {roadmap_path}")
        sys.exit(1)
    
    print("🚀 Создание GitHub Issues из roadmap")
    print("=" * 50)
    print(f"Репозиторий: {repo}")
    print(f"Roadmap: {roadmap_path}")
    print("")
    
    # Парсим roadmap
    print("📖 Парсинг roadmap...")
    parser = RoadmapParser(str(roadmap_path))
    tasks = parser.parse()
    
    print(f"✅ Найдено задач: {len(tasks)}")
    print("")
    
    # Создаем GitHub клиент
    github = GitHubIssuesCreator(github_token, repo)
    
    # Создаем labels
    print("🏷️  Создание labels...")
    github.ensure_labels()
    print("")
    
    # Получаем существующие issues
    print("🔍 Проверка существующих issues...")
    existing_titles = github.get_existing_issues()
    print(f"✅ Найдено существующих issues: {len(existing_titles)}")
    print("")
    
    # Создаем issues
    print("📝 Создание issues...")
    created = 0
    skipped = 0
    
    for task in tasks:
        # Проверяем, не существует ли уже такой issue
        if task['title'] in existing_titles:
            print(f"⏭️  Пропущено (уже существует): {task['title']}")
            skipped += 1
            continue
        
        print(f"➕ Создание: {task['title']}")
        issue = github.create_issue(
            title=task['title'],
            body=task['body'],
            labels=task['labels']
        )
        
        if issue:
            print(f"   ✅ Создано: {issue['html_url']}")
            created += 1
        else:
            print(f"   ❌ Ошибка создания")
        
        print("")
    
    print("=" * 50)
    print(f"✅ Создано: {created}")
    print(f"⏭️  Пропущено: {skipped}")
    print("")
    print("🎉 Готово!")


if __name__ == "__main__":
    main()
