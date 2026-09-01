# Child bot — щоденник годувань і сну

Телеграм-бот для запису режиму дня немовляти: годування (ліва/права), сон
(заснула/встала). Після кожного запису бот надсилає повний розпорядок дня.

## Модель даних

Дитина завжди в одному зі станів: **годується**, **спить**, **не спить**.
Кожна подія відкриває новий стан і завершує попередній, тож тривалість запису —
це час до наступного запису. Доба календарна, 00:00–24:00, часовий пояс
`Europe/Kyiv`; нічний сон через північ показується в обох добах, а підсумки
рахуються по перетину з добою.

## Можливості

- Меню: 🍼 Годування (Ліва / Права) і 😴 Сон (Заснула / Встала)
- Час вводиться руками (`14:30`, `1430`, `9:05`, `31.08 23:50`, `вчора 22:10`)
  або кнопкою «Зараз». Запис уночі про вечірній час автоматично йде на вчора.
- Після кожної події — повний розпорядок дня новим повідомленням, з підсумками
  (кількість годувань ліва/права, час на грудях, сон, найдовший сон, скільки
  минуло від останнього годування)
- `/fix` — змінити час, змінити тип або видалити будь-який із останніх записів;
  кнопка «↩️ Скасувати останній» під кожним зведенням
- `/yesterday`, `/week` — розпорядок учора й підсумки за 7 днів
- Спільний журнал: перший, хто натисне `/start`, стає власником, решту він
  підтверджує кнопкою. Записи спільні, зведення розсилається всім (`BROADCAST`).

## Локальний запуск

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env      # вписати BOT_TOKEN від @BotFather
.venv/bin/python -m bot
```

Офлайн-перевірка сценаріїв без мережі:

```bash
.venv/bin/python tests/smoke.py
```

## Деплой на VPS (systemd, long polling)

```bash
git clone <repo> /home/ubuntu/child_bot
cd /home/ubuntu/child_bot
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env && chmod 600 .env   # вписати BOT_TOKEN
sudo cp deploy/child-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now child-bot
journalctl -u child-bot -f
```

Юніт написаний під `User=ubuntu` і каталог `/home/ubuntu/child_bot` — якщо шлях
інший, поправ `WorkingDirectory`, `ExecStart` і `ReadWritePaths`.

Навантаження: один процес, long polling, ~60–80 МБ RSS, у спокої близько нуля
CPU. `Nice=10` + `CPUWeight=20` віддають пріоритет солверу на тому ж ядрі,
`MemoryMax=300M` страхує від витоку.

## Змінні оточення (`.env`)

| Змінна | Призначення |
| --- | --- |
| `BOT_TOKEN` | токен від @BotFather |
| `ALLOWED_USER_IDS` | необов'язковий білий список id через кому; порожньо — працює схема «власник підтверджує» |
| `BROADCAST` | `1` — зведення отримують усі підтверджені користувачі, `0` — тільки автор запису |
| `DB_PATH` | шлях до файлу SQLite (типово `data/child_bot.db`) |

## База

SQLite-файл `data/child_bot.db` (WAL). Таблиці: `events` (ts, kind, автор) і
`users` (доступ). Бекап — звичайне копіювання файлу:

```bash
sqlite3 data/child_bot.db ".backup '/home/ubuntu/backup/child_bot.db'"
```

## Структура

```
bot/
  __main__.py        запуск polling
  config.py          .env, часовий пояс
  models.py          типи подій і стани
  db.py              SQLite
  access.py          доступ: власник підтверджує решту
  keyboards.py       меню
  handlers/
    common.py        /start, /today, /yesterday, /week, доступ
    entry.py         додавання запису
    edit.py          виправлення й видалення
  services/
    timeparse.py     розбір часу, тривалості, українські форми
    report.py        розпорядок дня і підсумки
    notify.py        розсилка зведення
deploy/child-bot.service
tests/smoke.py
```
