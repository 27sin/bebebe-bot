# Деплой на cloud.ru (24/7)

Репозиторий: https://github.com/27sin/bebebe-bot

После настройки каждый `git push` в ветку `main` автоматически обновляет бота на сервере.

## 1. Создать VPS на cloud.ru

1. [Создать виртуальную машину](https://cloud.ru/docs/virtual-machines/ug/topics/guides__create-vm)
2. Ubuntu 22.04 / 24.04, 1 vCPU, 1 GB RAM
3. Публичный IP + SSH-ключ при создании
4. В security group: входящий SSH (22) с вашего IP

## 2. Первичная настройка сервера

Подключитесь по SSH:

```bash
ssh ubuntu@ВАШ_IP
```

Склонируйте репозиторий и установите зависимости:

```bash
sudo apt update && sudo apt install -y git
git clone https://github.com/27sin/bebebe-bot.git /tmp/bebebe-bot
cd /tmp/bebebe-bot
sudo bash scripts/setup-server.sh
```

Отредактируйте `.env`:

```bash
nano /opt/telegram-parody-bot/.env
```

Минимум:

```env
BOT_TOKEN=ваш_токен
OPENAI_API_KEY=
RANDOM_REPLY_PROBABILITY=0.95
DEFAULT_REPLY_COOLDOWN_SECONDS=1
```

Запустите бота:

```bash
sudo systemctl start telegram-parody-bot
sudo systemctl status telegram-parody-bot
journalctl -u telegram-parody-bot -f
```

**Важно:** остановите локальный запуск бота на ПК — одновременно может работать только один экземпляр.

## 3. SSH-ключ для GitHub Actions

На **вашем ПК** создайте отдельный ключ для деплоя:

```powershell
ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\bebebe-bot-deploy -C "github-deploy"
```

Публичный ключ добавьте на сервер:

```bash
mkdir -p ~/.ssh
nano ~/.ssh/authorized_keys
# вставьте содержимое bebebe-bot-deploy.pub
chmod 600 ~/.ssh/authorized_keys
```

## 4. Секреты в GitHub

Репозиторий → **Settings → Secrets and variables → Actions → New repository secret**

| Secret | Значение |
|--------|----------|
| `SSH_HOST` | публичный IP сервера |
| `SSH_USER` | `ubuntu` (или ваш пользователь) |
| `SSH_PRIVATE_KEY` | содержимое `bebebe-bot-deploy` (приватный ключ) |
| `SSH_PORT` | `22` (опционально) |

## 5. Как обновлять бота

1. Правите код локально в Cursor
2. Коммит и push в `main`:

```powershell
git add .
git commit -m "описание изменений"
git push origin main
```

3. GitHub Actions → workflow **Deploy to cloud.ru** → должен стать зелёным
4. Проверяете бота в Telegram

Ручной деплой на сервере:

```bash
cd /opt/telegram-parody-bot
bash deploy.sh
```

## 6. Что не в Git

- `.env` — токены (только на сервере)
- `data/settings.json` — настройки чатов (`/chance`, `/cooldown`)
- `data/analytics.db` — аналитика для владельца (`/adminstats`)

Подробнее: [rules/ANALYTICS.md](rules/ANALYTICS.md)

## 7. Полезные команды

```bash
sudo systemctl restart telegram-parody-bot
sudo systemctl stop telegram-parody-bot
journalctl -u telegram-parody-bot -f
```

## 8. Логи: сохранение и скачивание

Бот пишет логи в файл **`/opt/telegram-parody-bot/logs/bot.log`** (ротация: до 5 файлов по 5 MB).  
Параллельно остаётся вывод в systemd (`journalctl`).

**На сервере:**

```bash
tail -f /opt/telegram-parody-bot/logs/bot.log
ls -la /opt/telegram-parody-bot/logs/
bash /opt/telegram-parody-bot/scripts/export-logs.sh
# путь к архиву выведется в /tmp/bebebe-bot-logs-*.tar.gz
```

**Скачать на Windows (PowerShell, из папки проекта):**

```powershell
.\scripts\download-logs.ps1
# другой ключ: .\scripts\download-logs.ps1 -Key "D:\path\to\id_rsa"
```

Файлы попадут в `downloaded-logs\YYYYMMDD-HHMMSS\`.

**Скачать архив с сервера вручную:**

```powershell
scp -i D:\VibeCode\SSH\bebebe-bot\id_rsa iziashnyi@85.208.86.166:/tmp/bebebe-bot-logs-*.tar.gz .
```

После первого деплоя с этой функцией создайте каталог логов на сервере (если его ещё нет):

```bash
mkdir -p /opt/telegram-parody-bot/logs
sudo chown iziashnyi:iziashnyi /opt/telegram-parody-bot/logs
sudo systemctl restart telegram-parody-bot
```

## 9. Бот не отвечает на cloud.ru

Если в логах `Request timeout error` — DNS отдаёт заблокированный IP Telegram.

```bash
echo "149.154.167.220 api.telegram.org" | sudo tee -a /etc/hosts
sudo systemctl restart telegram-parody-bot
```
