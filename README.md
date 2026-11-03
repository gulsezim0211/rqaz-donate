# RQAZ-DONATE MVP

Рабочий прототип системы донатов для Windows, OBS, TikTok LIVE Studio и Streamlabs.

## Что входит

- `server/` — FastAPI API, SQLite, регистрация/вход, приём донатов, статистика и SSE-виджеты.
- `windows_client/` — Windows-клиент с входом, тестовым донатом и чтением текста окна Phone Link через UI Automation.
- `build_windows.bat` — сборка клиента в `RQAZ-DONATE.exe` через PyInstaller.

## Быстрый запуск сервера

1. Установите Python 3.11+.
2. Откройте терминал в папке проекта.
3. Выполните:

```powershell
python -m server.main
```

Откройте `http://localhost:3000`. База создаётся автоматически в `server/rqaz.db`.

## Запуск Windows-клиента

```powershell
pip install -r windows_client\requirements.txt
python windows_client\app.py
```

Введите адрес сервера, email и пароль от сайта. Для проверки нажмите «Тестовый донат».

Для автоматического захвата откройте приложение Microsoft «Связь с телефоном», убедитесь, что в его окне видны уведомления Kaspi, затем включите переключатель «Следить за Phone Link».

## Сборка EXE

Запустите `build_windows.bat`. Готовый файл появится в `dist\RQAZ-DONATE.exe`.

В GitHub сборка запускается автоматически после загрузки файлов. Готовые
`RQAZ-DONATE.exe` и `RQAZ-DONATE-Setup.exe` находятся в артефакте
`RQAZ-DONATE-Windows` на странице Actions.

## Ограничение MVP

Phone Link не предоставляет стабильный публичный API для чтения всех уведомлений. MVP использует Windows UI Automation и ищет текст в окне приложения. После обновления Phone Link может потребоваться изменить имя окна или правила распознавания в `windows_client/app.py`.

## Формат распознавания

Клиент ищет уведомления, содержащие `Kaspi` и сумму вида `1 500 ₸`, `1500 тг` или `1500 KZT`. Ссылка YouTube в том же тексте помечает заказ как музыку.
