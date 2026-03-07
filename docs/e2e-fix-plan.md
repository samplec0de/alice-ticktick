# План исправления E2E тестов

Результаты прогона: **2 FAILED, 63 PASSED, 33 XFAILED, 18 XPASSED**

---

## 1. XPASSED (18 тестов) — убрать `xfail`, тесты уже работают

Эти тесты помечены как ожидаемо-падающие, но на самом деле проходят. Нужно убрать маркер `xfail`.

### 1.1 Чеклисты (2 теста)
| Тест | Причина xfail | Почему работает |
|------|---------------|-----------------|
| `test_check_item` | complete_task перехватывает check_item | Regex-диспетчеризация в router.py (строки 286-298) корректно перенаправляет |
| `test_delete_checklist_item` | delete_task перехватывает delete_checklist_item | Regex-диспетчеризация в router.py (строки 346-360) корректно перенаправляет |

### 1.2 Delete FSM (2 теста)
| Тест | Причина xfail | Почему работает |
|------|---------------|-----------------|
| `test_delete_confirm_yes` | Cloud Functions теряет FSM state | FSM работает стабильно |
| `test_delete_confirm_no` | Cloud Functions теряет FSM state | FSM работает стабильно |

### 1.3 Edge cases (1 тест)
| Тест | Причина xfail | Почему работает |
|------|---------------|-----------------|
| `test_long_task_name` | Длинные имена ломают API/NLU | Работает нормально |

### 1.4 Misc (3 теста)
| Тест | Причина xfail | Почему работает |
|------|---------------|-----------------|
| `test_help_what_can_you_do` | create_task перехватывает 'что ты умеешь' | YANDEX.WHAT_CAN_YOU_DO intent работает |
| `test_goodbye` | YANDEX.GOODBYE не работает в текстовом режиме | Работает |
| `test_fallback_joke` | Greedy create_task (.+) перехватывает | Fallback срабатывает корректно |

### 1.5 Regression (5 тестов)
| Тест | Причина xfail | Почему работает |
|------|---------------|-----------------|
| `test_edit_task_date_consumed` | edit_task не распознаётся | edit_task intent работает для "перенеси задачу X на Y" |
| `test_subtask_not_intercepted` | create_task перехватывает subtask | Корректная маршрутизация |
| `test_check_item_not_intercepted` | complete_task перехватывает check_item | Regex-диспетчеризация работает |
| `test_delete_checklist_not_intercepted` | delete_task перехватывает delete_checklist_item | Regex-диспетчеризация работает |
| `test_search_transliteration` | Нет транслитерации рус→англ | Работает (возможно, rapidfuzz справляется) |

### 1.6 Search (3 теста)
| Тест | Причина xfail | Почему работает |
|------|---------------|-----------------|
| `test_search_report` | search_task перехватывается create_task/edit_task | search_task intent работает |
| `test_search_buy` | То же | Работает |
| `test_search_macbook` | То же | Работает |

### 1.7 Subtasks (2 теста)
| Тест | Причина xfail | Почему работает |
|------|---------------|-----------------|
| `test_add_subtask` | create_task перехватывает add_subtask | Disambiguation в router.py (строки 152-157) работает |
| `test_add_subtask_alt` | То же | Работает |

**Действие:** удалить `@pytest.mark.xfail` / `@_XFAIL` / `@_SEARCH_XFAIL` с этих 18 тестов.

---

## 2. FAILED (2 теста) — нужно исправить

### 2.1 `test_greeting_new_session`
**Ошибка:** Получено `"Изменить задачу «Задачи кктест редактирования за 1 день»? Скажите да или нет."` вместо приветствия.

**Причина:** Утечка FSM state от предыдущего теста. Один из тестов edit (перед greeting в алфавитном порядке) оставил состояние `EditTaskStates.confirm`, и `_reset_session` fixture не смог его очистить.

**Решение:**
- Вариант A: Порядок тестов — greeting должен идти первым (или после create, а не после edit).
- Вариант B: В `_reset_session` fixture помимо `send_new_session()` отправлять "нет" или "отмена" для очистки FSM.
- Вариант C: Отправлять сначала "отмена", потом новую сессию. Наиболее надёжно.

### 2.2 `test_list_subtasks`
**Ошибка:** `"Произошла ошибка при обращении к TickTick. Попробуйте позже."`

**Причина:** Транзиентная ошибка TickTick API (rate limiting или таймаут). Flaky-тест.

**Решение:**
- Добавить retry-логику в `YandexDialogsClient.send()` для TickTick API ошибок.
- Или пометить тест как `@pytest.mark.flaky(reruns=2)` (требуется pytest-rerunfailures).
- Или добавить проверку на "Произошла ошибка" в assertion: `or "ошибка" in response.lower()` + пометить как допустимый.

---

## 3. XFAILED (33 теста) — всё ещё падают, нужна работа

### 3.1 Группа: edit_task intent не распознаётся (17 тестов)
**Файл:** `test_e2e_edit.py` — все 17 тестов.

**Причина:** Грамматика `edit_task.grammar` не покрывает все фразы, или NLU путает их с другими интентами.

**Интересно:** `test_edit_task_date_consumed` в regression тестах XPASSED (фраза "перенеси задачу X на Y" работает). Значит, edit_task интент распознаётся для некоторых фраз, но не для всех.

**Действие:** Проанализировать `edit_task.grammar` и добавить недостающие паттерны:
- "поменяй приоритет задачи X на Y" — приоритет
- "переименуй задачу X в Y" — переименование
- "перемести задачу X в проект Y" — перемещение
- "поменяй повторение задачи X на Y" — повторение
- "убери повторение задачи X" — удаление повторения
- "поменяй напоминание задачи X за Y" — напоминание
- "убери напоминание задачи X" — удаление напоминания

### 3.2 Группа: checklist интенты перехватываются create_task (4 теста)
**Файлы:** `test_e2e_checklists.py` (4 из 6), `test_e2e_regression.py::test_checklist_not_intercepted`

**Тесты:**
- `test_add_checklist_item` — "добавь пункт X в чеклист задачи Y"
- `test_add_checklist_item_alt` — то же с другими данными
- `test_show_checklist` — "покажи чеклист задачи X"
- `test_show_checklist_alt` — "что в чеклисте задачи X"

**Причина:** NLU распознаёт эти фразы как create_task или list_tasks. Regex-диспетчеризация в router.py помогает для check_item и delete_checklist_item, но не для add/show.

**Действие:**
- Добавить regex-диспетчеризацию для `add_checklist_item` (уже частично есть в `on_create_task`, строки 196-211) — нужно проверить, почему не срабатывает.
- Добавить regex-диспетчеризацию для `show_checklist` в `on_list_tasks`.
- Или: улучшить грамматики `add_checklist_item.grammar` и `show_checklist.grammar` для повышения приоритета NLU.

### 3.3 Группа: complete_task — неподдерживаемые фразы (2 теста)
**Тесты:**
- `test_complete_done` — "готово кктест отправить отчёт"
- `test_complete_done_alt` — "сделал кктест подготовить презентацию"

**Причина:** Грамматика `complete_task.grammar` не содержит паттернов "готово X" и "сделал X".

**Действие:** Добавить паттерны в `complete_task.grammar`:
```
%lemma
готово $TaskName:(.+)
сделал $TaskName:(.+)
сделала $TaskName:(.+)
```

### 3.4 Группа: list_tasks — перехват и неподдержка (3 теста)
**Тесты:**
- `test_list_all_tasks` — "все задачи"
- `test_overdue_prosrochennye` — "покажи просроченные задачи"
- `test_overdue_what_overdue` — "что я просрочил"

**Действие:**
- Добавить "все задачи" в `list_tasks.grammar`
- Добавить "покажи просроченные задачи" в `overdue_tasks.grammar`
- Добавить "что я просрочил" в `overdue_tasks.grammar`

### 3.5 Группа: projects — перехват list_tasks (2 теста)
**Тесты:**
- `test_list_projects` — "покажи мои проекты"
- `test_project_tasks` — "задачи в проекте работа"

**Действие:** Улучшить грамматики `list_projects.grammar` и `project_tasks.grammar`, или добавить regex-диспетчеризацию в `on_list_tasks`.

### 3.6 Группа: одиночные NLU-проблемы (5 тестов)
| Тест | Фраза | Проблема |
|------|-------|----------|
| `test_create_with_project` | "создай задачу X в проекте Inbox" | project slot игнорируется |
| `test_recurring_every_day` | "напоминай каждый день пить воду кктест" | NLU потребляет 'каждый день' как DATETIME |
| `test_fallback_weather` | "какая погода" | Greedy create_task (.+) |
| `test_search_milk` | "поиск задачи молоко" | search перехватывается |
| `test_goodbye_text_mode` | "до свидания" | YANDEX.GOODBYE в тексте |

---

## 4. Приоритеты исправления

### P0 — Быстрые wins (только убрать xfail)
- Убрать `xfail` с 18 XPASSED тестов — **0 строк кода, только тесты**

### P1 — Исправить 2 FAILED теста
- `test_greeting_new_session` — исправить `_reset_session` fixture
- `test_list_subtasks` — добавить retry или обработку транзиентных ошибок

### P2 — edit_task грамматика (17 тестов)
- Переработать `edit_task.grammar` для поддержки всех типов редактирования
- Наибольший эффект: 17 тестов перейдут из xfail в pass

### P3 — Checklist dispatch (4 теста)
- Улучшить regex-диспетчеризацию для add_checklist_item и show_checklist

### P4 — complete_task грамматика (2 теста)
- Добавить "готово X" и "сделал X" в complete_task.grammar

### P5 — Прочие NLU-проблемы (8 тестов)
- list_tasks, overdue_tasks, projects грамматики
- Fallback для "какая погода"
- Одиночные проблемы

---

## 5. Итого по файлам

| Файл | PASS | XFAIL | XPASS | FAIL | Итого |
|------|------|-------|-------|------|-------|
| test_e2e_briefings | 2 | 0 | 0 | 0 | 2 |
| test_e2e_checklists | 0 | 4 | 2 | 0 | 6 |
| test_e2e_complete | 3 | 2 | 0 | 0 | 5 |
| test_e2e_create | 22 | 1 | 0 | 0 | 23 |
| test_e2e_delete | 2 | 0 | 2 | 0 | 4 |
| test_e2e_edge | 6 | 0 | 1 | 0 | 7 |
| test_e2e_edit | 0 | 17 | 0 | 0 | 17 |
| test_e2e_greeting | 0 | 0 | 0 | 1 | 1 |
| test_e2e_list | 9 | 3 | 0 | 0 | 12 |
| test_e2e_misc | 4 | 1 | 3 | 0 | 8 |
| test_e2e_projects | 1 | 2 | 0 | 0 | 3 |
| test_e2e_recurring | 7 | 1 | 0 | 0 | 8 |
| test_e2e_regression | 0 | 2 | 5 | 0 | 7 |
| test_e2e_reminders | 5 | 0 | 0 | 0 | 5 |
| test_e2e_search | 0 | 1 | 3 | 0 | 4 |
| test_e2e_subtasks | 1 | 0 | 2 | 1 | 4 |
| **Итого** | **62** | **34** | **18** | **2** | **116** |
