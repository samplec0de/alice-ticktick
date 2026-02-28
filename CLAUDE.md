# Alice-TickTick

Навык Яндекс Алисы для голосового управления задачами в TickTick.

## Команды

- `uv sync --extra dev` — установка зависимостей
- `uv run pytest -v` — запуск тестов
- `uv run ruff check .` — линтинг
- `uv run ruff format .` — форматирование
- `uv run mypy alice_ticktick/` — проверка типов

## Правила разработки

- Весь новый функционал должен быть покрыт тестами (pytest + pytest-asyncio)
- Тесты пишутся одновременно с кодом, не после
- Минимальное покрытие: каждый публичный метод/функция, каждый обработчик интента
- Используй моки для внешних API (TickTick, Alice)
- Запускай `uv run pytest -v` перед коммитом

## Структура

- `alice_ticktick/` — основной пакет
  - `alice/` — модели и утилиты Алисы
  - `dialogs/` — роутеры, интенты, FSM, сцены
  - `dialogs/nlp/` — парсинг дат, приоритетов, fuzzy search
  - `ticktick/` — клиенты API v1 + v2
  - `storage/` — хранение токенов
  - `config.py` — настройки (pydantic-settings)
- `tests/` — тесты (pytest + pytest-asyncio)
- `docs/PRD.md` — Product Requirements Document
- `docs/SETUP.md` — пошаговая настройка навыка и прогресс

## Стек

Python 3.12+, aliceio, httpx, rapidfuzz, pydantic, ruff, mypy, pytest

## Язык

Код, комментарии, коммиты — на русском (пользовательские строки) и английском (код).
Документация и PRD — на русском.
