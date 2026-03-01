# Настройка навыка «ТикТик» — пошаговая инструкция

Документ описывает воспроизводимые шаги настройки навыка Алисы для TickTick.

## 1. Создание репозитория

```bash
gh repo create samplec0de/alice-ticktick --public --description "Навык Яндекс Алисы для голосового управления задачами в TickTick"
```

Репозиторий: https://github.com/samplec0de/alice-ticktick

## 2. Получение ключей TickTick

1. Перейти на https://developer.ticktick.com/manage
2. Создать OAuth-приложение
3. Указать **Redirect URI**: `http://localhost:8080/callback`
4. Сохранить `client_id` и `client_secret` в `.env`

```env
TICKTICK_CLIENT_ID=...
TICKTICK_CLIENT_SECRET=...
```

## 3. Создание навыка в Яндекс Диалогах

1. Перейти на https://dialogs.yandex.ru/developer
2. Создать новый навык типа **«Навык в Алисе»**
3. Заполнить:
   - **Имя навыка**: Tick Tick (или ТикТик при публикации)
   - **Фраза активации**: ТикТик
   - **Backend**: webhook URL (настраивается позже)
4. Сохранить `skill_id` в `.env`:

```env
ALICE_SKILL_ID=d3f073db-dece-42b8-9447-87511df30c83
```

## 4. Настройка интентов (NLU)

Страница: `Черновик → Интенты`

URL: https://dialogs.yandex.ru/developer/skills/{skill_id}/draft/settings/intents

### 4.1. create_task — Создание задачи

**Название:** Создание задачи
**ID:** `create_task`

**Грамматика:**
```
root:
    %lemma
    (создай|добавь|запиши|новая|поставь) (задачу|задача|напоминание)? $TaskName (в (проект|список|папку) $ProjectName)? (на $Date)? (с приоритетом (низкий|средний|высокий))?

slots:
    task_name:
        source: $TaskName
        type: YANDEX.STRING
    date:
        source: $Date
        type: YANDEX.DATETIME
    project_name:
        source: $ProjectName
        type: YANDEX.STRING

$TaskName:
    .+

$Date:
    $YANDEX.DATETIME

$ProjectName:
    .+
```

**Положительные тесты:**
```
создай задачу купить молоко
добавь задачу написать отчёт на завтра
запиши задачу позвонить маме
новая задача подготовить презентацию
поставь задачу оплатить счёт на пятницу
создай задачу купить молоко в проект Покупки
добавь задачу отчёт в список Работа на завтра
```

**Отрицательные тесты:**
```
покажи задачи на сегодня
какие задачи просрочены
отметь задачу купить хлеб
```

### 4.2. list_tasks — Просмотр задач

**Название:** Просмотр задач
**ID:** `list_tasks`

**Грамматика:**
```
root:
    %lemma
    (покажи|какие|что|список|расскажи) (мои|все)? (задачи|задача|дела|дело|планы|план) (на $Date)?

slots:
    date:
        source: $Date
        type: YANDEX.DATETIME

$Date:
    $YANDEX.DATETIME
```

**Положительные тесты:**
```
покажи задачи на сегодня
какие задачи на завтра
что запланировано на понедельник
список задач на эту неделю
расскажи мои дела на сегодня
```

**Отрицательные тесты:**
```
создай задачу купить хлеб
отметь задачу выполненной
удали задачу
```

### 4.3. overdue_tasks — Просроченные задачи

**Название:** Просроченные задачи
**ID:** `overdue_tasks`

**Грамматика:**
```
root:
    %lemma
    (какие|покажи|есть|что) (задачи|задача|дела)? (просрочены|просроченные|просрочено|не выполнены|пропущены|пропущенные|опоздал|забыл)
```

**Положительные тесты:**
```
какие задачи просрочены
покажи просроченные задачи
есть просроченные дела
что я просрочил
какие задачи не выполнены
```

**Отрицательные тесты:**
```
покажи задачи на сегодня
создай задачу купить хлеб
завершить задачу
```

### 4.4. complete_task — Завершение задачи

**Название:** Завершение задачи
**ID:** `complete_task`

**Грамматика:**
```
root:
    %lemma
    (отметь|завершить|выполнить|готово|сделал|закрой|закончить|выполнена|сделано|закрыть) (задачу|задача)? $TaskName (выполненной|готовой|сделанной)?

slots:
    task_name:
        source: $TaskName
        type: YANDEX.STRING

$TaskName:
    $YANDEX.STRING
```

**Положительные тесты:**
```
отметь задачу купить молоко
завершить задачу написать отчёт
готово сделать презентацию
закрой задачу позвонить маме
сделал отправить письмо
```

**Отрицательные тесты:**
```
создай задачу купить хлеб
покажи задачи на сегодня
какие задачи просрочены
```

### 4.5. search_task — Поиск задачи (Phase 2)

**ID:** `search_task`
**Слоты:** `task_name` (YANDEX.STRING)
**Примеры:** «найди задачу про отчёт», «поиск задачи молоко»

### 4.6. edit_task — Редактирование задачи (Phase 2)

**ID:** `edit_task`
**Слоты:** `task_name` (YANDEX.STRING), `new_date` (YANDEX.DATETIME), `new_priority` (YANDEX.STRING), `new_name` (YANDEX.STRING), `new_project` (YANDEX.STRING)
**Примеры:** «перенеси задачу на завтра», «поменяй приоритет на высокий», «перенеси задачу в проект Работа»

Грамматика должна включать альтернативный паттерн для перемещения:
```
(перенеси|перемести|переложи|перекинь|отправь) (задачу|задача)? $TaskName в (проект|список|папку) $ProjectName
```

Слот:
```
new_project:
    source: $ProjectName
    type: YANDEX.STRING
```

### 4.7. delete_task — Удаление задачи (Phase 2)

**ID:** `delete_task`
**Слоты:** `task_name` (YANDEX.STRING)
**Примеры:** «удали задачу купить молоко», «убери задачу про отчёт»

### 4.8. add_subtask — Добавление подзадачи (Phase 3)

**ID:** `add_subtask`
**Слоты:** `parent_name` (YANDEX.STRING), `subtask_name` (YANDEX.STRING)
**Примеры:** «добавь подзадачу купить муку к задаче испечь торт»

### 4.9. list_subtasks — Просмотр подзадач (Phase 3)

**ID:** `list_subtasks`
**Слоты:** `task_name` (YANDEX.STRING)
**Примеры:** «покажи подзадачи задачи испечь торт»

### 4.10. add_checklist_item — Добавление пункта чеклиста (Phase 3)

**ID:** `add_checklist_item`
**Слоты:** `task_name` (YANDEX.STRING), `item_name` (YANDEX.STRING)
**Примеры:** «добавь пункт молоко в чеклист задачи покупки»

### 4.11. show_checklist — Просмотр чеклиста (Phase 3)

**ID:** `show_checklist`
**Слоты:** `task_name` (YANDEX.STRING)
**Примеры:** «покажи чеклист задачи покупки»

### 4.12. check_item — Отметка пункта чеклиста (Phase 3)

**ID:** `check_item`
**Слоты:** `task_name` (YANDEX.STRING), `item_name` (YANDEX.STRING)
**Примеры:** «отметь пункт молоко в задаче покупки»

### 4.13. delete_checklist_item — Удаление пункта чеклиста (Phase 3)

**ID:** `delete_checklist_item`
**Слоты:** `task_name` (YANDEX.STRING), `item_name` (YANDEX.STRING)
**Примеры:** «удали пункт молоко из чеклиста задачи покупки»

## 5. Связка аккаунтов (Account Linking)

Настраивается в `Черновик → Связка аккаунтов`:

- **Тип авторизации**: OAuth 2.0
- **URL авторизации**: `https://ticktick.com/oauth/authorize`
- **URL для получения токена**: `https://ticktick.com/oauth/token`
- **Client ID / Client Secret**: из шага 2

> Настройка будет выполнена на этапе реализации авторизации (Phase 1).

## 6. CI/CD

GitHub Actions настроен в `.github/workflows/ci.yml`:
- **lint**: ruff check + format
- **typecheck**: mypy strict mode
- **test**: pytest с покрытием + codecov
- **deploy** (только main): сборка deploy.zip → загрузка в Object Storage (`alice-ticktick-deploy`) → деплой в YC Functions (`python312`)

## 7. Локальная разработка

```bash
# Установка зависимостей
uv sync --extra dev

# Запуск тестов
uv run pytest -v

# Линтинг и форматирование
uv run ruff check .
uv run ruff format .

# Проверка типов
uv run mypy alice_ticktick/
```

## Прогресс

| Фаза | Статус | Описание |
|------|--------|----------|
| Phase 0 — Инфраструктура | ✅ Готово | Репозиторий, CI/CD, структура проекта, PRD |
| Phase 0 — Интенты NLU | ✅ Готово | 4 MVP интента настроены и опубликованы |
| Phase 0 — CD | ✅ Готово | Деплой в YC Functions через GitHub Actions |
| Phase 1 — MVP | ✅ Готово | TickTick клиент, NLP, обработчики Алисы (PR #1) |
| Phase 2 — Поиск, редактирование | ✅ Готово | Fuzzy search, изменение, удаление задач, 158 тестов (PR #2) |
| Phase 2 — Интенты NLU | ✅ Готово | search_task, edit_task, delete_task настроены |
| Phase 3 — Подзадачи, чеклисты | ✅ Готово | 6 обработчиков, 239 тестов (PR #3) |
| Phase 3 — Интенты NLU | ✅ Готово | add_subtask, list_subtasks, add_checklist_item, show_checklist, check_item, delete_checklist_item |
| Phase 3 — CD + деплой | ✅ Готово | Object Storage, python312 runtime, linux-совместимые бинарники (PR #4) |
| Phase 3 — Помощь / прощание | ✅ Готово | Обработчики YANDEX.HELP, YANDEX.WHAT_CAN_YOU_DO, YANDEX.GOODBYE (PR #5) |
| Phase 4 — Теги, повтор. задачи | ⬜ В очереди | Теги, RRULE, напоминания, фильтрация |
| Phase 5 — Kanban, проекты | ⬜ В очереди | Колонки, перемещение карточек |
| Phase 6 — Привычки, статистика | ⬜ В очереди | Серии, привычки, брифинги |
| Phase 7 — Публикация | ⬜ В очереди | Модерация, каталог Алисы |
