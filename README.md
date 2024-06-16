# Yandex Disk Manager Bot

## Описание

Телеграм бот для управления своим облачным хранилищем Яндекс Диск.
Небольшой пет-проект для практики.

## Начало работы

Создайте виртуальное окружение, активируйте его и установите файл зависимотей.
```bash
python -m venv venv
```

```bash
. venv/Scripts/activate
```

```bash
pip install -r requirements.txt
```

Создайте файл .env, укажите:
TELEGRAM_BOT_TOKEN=<токен бота>
ENCRYPTION_KEY='<ключ шифрования для пользовательких токенов Яндекс ID>', нужно получить один раз с помощью библиотеки cryptography==42.0.8
```python
from cryptography.fernet import Fernet

# Генерация ключа шифрования
key = Fernet.generate_key()

# Печать ключа
print("Ключ шифрования:", key.decode())
```
Полученый ключ вставляем в ковычках в .env

### 

Что нужно установить для работы с проектом (например, Python, библиотеки и т.д.)
