# Запуск на сервере с доменом

## 1. Домен

В панели DNS добавляете A-запись: имя - ваш поддомен, значение - IP сервера

## 2. Docker

На сервере:

```bash
curl -fsSL https://get.docker.com | sh
```

## 3. Проект и настройки

```bash
git clone https://github.com/RebStep/UchebrickToMAX.git /opt/uchebrik
cd /opt/uchebrik
cp .env.example .env
nano .env
```

Заполняете так, только домен везде свой:

```
MAX_BOT_TOKEN=токен бота
GIGACHAT_CREDENTIALS=ключ GigaChat
POSTGRES_PASSWORD=случайная строка
SESSION_SECRET=случайная строка
COMPOSE_PROFILES=prod
DOMAIN=uchebrik.example.ru
PUBLIC_URL=https://uchebrik.example.ru
WEBHOOK_URL=https://uchebrik.example.ru/webhook
WEBHOOK_SECRET=случайная строка из латиницы и цифр
```

Чтобы сохранить в nano: Ctrl+O, Enter, потом Ctrl+X

## 4. Запуск

```bash
docker compose up --build -d
```

## 5. Проверяем

1. Открываете в браузере `https://ваш-домен/api/health`, там должно быть `{"ok":true}`
2. В `docker compose logs bot` есть строчка `Webhook подписан`
3. Пишете боту в MAX `/start`, а потом любое задание

## 6. Мини-приложение в MAX

На [business.max.ru](https://business.max.ru/self) в настройках бота указываете адрес мини-приложения: `https://ваш-домен`. После этого кнопка «🗺️ Карта» открывает карту прямо в MAX

## Алиса

Это по желанию, шаги есть в [tokens.md](tokens.md), в разделе про Алису

## Как обновить

```bash
cd /opt/uchebrik
git pull
docker compose up --build -d
```
