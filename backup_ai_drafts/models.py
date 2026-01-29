🤖 Запрос: Создай модель Pydantic для User
===========================
Pydantic это Python 3 - асинхронная библиотека с обратной совместимостью с стандартной библиотекой dataclasses. Он предлагает простой, быстрый и безопасный способ работы с данными. 

Вот пример модели Pydantic для User:

```python
from typing import Optional
from pydantic import BaseModel

class UserBase(BaseModel):
    email: str

class UserCreate(UserBase):
    password: str

class User(UserBase):
    id: int
    is_active: bool = True

class UserUpdate(UserBase):
    password: Optional[str] = None
```

- `UserBase` наследуется от `BaseModel` и содержит общие атрибуты (email) пользователя. 
- `UserCreate` используется для создания нового пользователя, также содержащий пароль.
- `User` представляет обновленные данные о пользователе с идентификатором. Он также наследуется от UserBase и может иметь дополнительное поле "is_active" со значением по умолчанию True.
- `UserUpdate` используется для обновления пользовательских данных, включая возможность изменять пароль (которая может быть None).



===========================
