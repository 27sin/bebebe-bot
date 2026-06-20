# Аналитика для владельца бота

## Настройка

1. В `.env` на сервере добавь свой Telegram user id:

```env
ADMIN_USER_IDS=123456789
```

Несколько id через запятую. Узнать id: [@userinfobot](https://t.me/userinfobot).

2. Перезапусти бота — создастся `data/analytics.db`.

## Команда

```
/adminstats          — сводка за 7 дней
/adminstats day      — за 24 часа
/adminstats month    — за 30 дней
/adminstats all      — за всё время
```

Доступна **только** пользователям из `ADMIN_USER_IDS`. Для остальных команда молча игнорируется.

## Что пишется в SQLite

Файл: `data/analytics.db`

| Событие | Когда |
|---------|--------|
| `reply_sent` | Бот ответил (source, attachment_type) |
| `reply_skipped` | Rate limit |
| `command` | Любая команда `/...` |
| `menu_shown` | Показано подменю команды |
| `menu_action` | Нажата inline-кнопка |
| `llm_call` | Вызов OpenAI (success, latency_ms) |
| `session_start` / `session_end` / `guess_attempt` / `correct_guess` | Игры |
| `setting_changed` | chance / cooldown |
| `easter_egg_unlock` | Новая пасхалка |

Раз в сутки при старте бота считаются **daily rollups** (таблица `daily_metrics`).

## Еженедельный отчёт в личку

На сервере (подставь своего пользователя systemd):

```bash
sudo sed 's/__SERVICE_USER__/iziashnyi/' scripts/telegram-parody-bot-analytics.service \
  | sudo tee /etc/systemd/system/telegram-parody-bot-analytics.service
sudo cp scripts/telegram-parody-bot-analytics.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now telegram-parody-bot-analytics.timer
```

Ручной запуск:

```bash
cd /opt/telegram-parody-bot
source .venv/bin/activate
python scripts/send_weekly_analytics.py
```

По умолчанию таймер шлёт отчёт **каждый понедельник в 09:00** (время сервера).

## Код

- `bot/services/analytics.py` — track(), отчёты, rollup
- `bot/handlers/admin_commands.py` — `/adminstats`
- `bot/middleware/analytics.py` — лог всех команд
