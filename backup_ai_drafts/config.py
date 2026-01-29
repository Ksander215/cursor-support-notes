🤖 Запрос: Создай конфигурационный файл config.py для приложения
===========================
```python
# config.py

class Config(object):
    """Конфиг для основной программы"""
    SECRET_KEY = 'your-secret-key'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///app.db'  # использование базы данных SQLite
    SQLALCHEMY_TRACK_MODIFICATIONS = False  # отключение уведомления о модификациях

class DevelopmentConfig(Config):
    """Конфиг для разработки"""
    DEBUG = True
    SQLALCHEMY_ECHO = True  # включает логирование SQL запросов в консоль

class ProductionConfig(Config):
    """Конфиг для продакшена"""
    pass
```
ai "Добавь валидацию в config.py" >> config.py


===========================
