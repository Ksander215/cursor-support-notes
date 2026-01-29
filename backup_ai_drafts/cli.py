🤖 Запрос: Создай CLI утилиту на Python для управления проектом
===========================
Создать CLI утилиту с возможностью управлять проектами выглядит примерно так. Для этого, вам нужно использовать библиотеку `argparse` в Python для парсинга аргументов командной строки и методы `os.system()` или `subprocess` для управления проектами. 

```python
import argparse
import os

# Создаем парсер аргументов командной строки
parser = argparse.ArgumentParser(description='Управление вашим проєктом')

# Добавляем аргументы, которые мы будем использовать для управления проектами
parser.add_argument('--run', help='Запустить проект')
parser.add_argument('--test', help='Протестировать проект')
parser.add_argument('--build', help='Собрать проект')
parser.add_argument('--lint', help='Проверить стиль кода в проекте')

args = parser.parse_args()

if args.run:
    os.system(f"python {args.run}")  # Запуск файла, если он написан на Python
elif args.test:
    os.system(f'pytest {args.test}')  # Если проект написан на Python с использованием pytest для тестирования
elif args.build:
    os<｜begin▁of▁sentence｜>.system(f'python setup.py build {args.build}')  # Сборка проекта, если он написан на Python и имеет файл setup.py
elif args.lint:
    os.system(f'pylint {args.lint}')  # Линтинг кода в проекте, если он написан на Python с использованием pylint
else:
    print("Укажите действие для управления вашим проєктом")
```

Вы можете запустить эту утилиту в терминале следующим образом: 

`python manage.py --run main.py` - это будет запускать файл `main.py`  
`python manage.py --test test_project` - это будет прогонять тесты в папке с именем `test_project`, если они написаны на Python и используют библиотеку pytest

Вам придется указать путь к файлу или директории в аргументах.

Прежде чем продолжить, обязательно создайте виртуальное окружение для вашего проекта с помощью команды `python -m venv env` и активируйте его командой `source env/bin/activate` (на Windows это будет `.\env\Scripts\Activate`). Установите все необходимые пакеты в виртуальном окружении.



===========================
