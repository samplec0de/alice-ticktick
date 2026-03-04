# Дизайн: комплексная фильтрация задач (FR-15, API v1)

**Дата:** 2026-03-04
**Ветка:** feat/briefing-grammars → новая ветка от main

---

## Контекст

PRD FR-15 требует комбинированной фильтрации: дата + приоритет + проект.
Теги (V2) — вне скоупа этого дизайна.

**Что уже есть:**
- `list_tasks`: дата + приоритет (AND)
- `project_tasks`: все задачи проекта (без фильтров)
- `overdue_tasks`: просроченные (без фильтров)

**Что добавляется:**
- `list_tasks`: поддержка диапазонов дат (эта неделя / следующая / этот месяц)
- `project_tasks`: фильтры по дате, диапазону дат и приоритету
- `overdue_tasks`: фильтр по приоритету

---

## Подход

Расширение трёх существующих интентов (Подход 1).
Без новых интентов — минимум NLU-изменений.

---

## Архитектура

### 1. Модель DateRange (`nlp/date_parser.py`)

```python
@dataclass
class DateRange:
    date_from: datetime.date
    date_to: datetime.date   # inclusive

def parse_date_range(value: str, user_tz: ZoneInfo) -> DateRange | None:
    """
    Поддерживаемые значения:
    - 'this_week'  → Пн–Вс текущей недели
    - 'next_week'  → Пн–Вс следующей недели
    - 'this_month' → 1..last_day текущего месяца
    Возвращает None при неизвестном значении.
    """
```

### 2. Утилита фильтрации (`handlers.py`)

```python
def _apply_task_filters(
    tasks: list[Task],
    *,
    date_filter: datetime.date | DateRange | None = None,
    priority_filter: TaskPriority | None = None,
    user_tz: ZoneInfo,
) -> list[Task]:
    """Применяет фильтры даты и приоритета. Используется в трёх хэндлерах."""
```

### 3. Изменения в intents.py

**`ListTasksSlots`** — добавить поле:
```python
date_range: str | None = None
```

**`ProjectTasksSlots`** — добавить поля:
```python
date: YandexDateTime | None = None
date_range: str | None = None
priority: str | None = None
```

**`OverdueTasksSlots`** (новый dataclass):
```python
@dataclass(frozen=True, slots=True)
class OverdueTasksSlots:
    priority: str | None = None
```

### 4. NLU-грамматики (Яндекс.Диалоги)

Три интента получают `date_range` / `priority` слоты с примерами:

**`date_range` слот (примеры для обучения):**
- "на этой неделе", "в эту неделю" → `this_week`
- "на следующей неделе", "на следующей неделе" → `next_week`
- "в этом месяце", "за этот месяц" → `this_month`

Грамматика слота: `date_range: .+` (валидация в Python).

### 5. Хэндлеры

**`handle_list_tasks`:**
- Если `slots.date_range` — строим DateRange, фильтруем диапазон
- Если `slots.date` — как сейчас (одиночная дата)
- Применяем `_apply_task_filters`

**`handle_project_tasks`:**
- Добавляем извлечение `date`, `date_range`, `priority` из слотов
- После получения задач проекта — `_apply_task_filters`
- Обновляем ответные сообщения с учётом активных фильтров

**`handle_overdue_tasks`:**
- Добавляем `OverdueTasksSlots`
- После сбора просроченных — фильтруем по приоритету
- Обновляем ответные сообщения

---

## Новые ответные строки (`responses.py`)

```
TASKS_FOR_WEEK = "На этой неделе {count} с {priority}: ..."
TASKS_NEXT_WEEK = "На следующей неделе ..."
TASKS_THIS_MONTH = "В этом месяце ..."
PROJECT_TASKS_WITH_FILTERS = "В проекте {project} {filters}: {count} задач(и)..."
OVERDUE_WITH_PRIORITY = "Просроченных с {priority} приоритетом: {count}..."
NO_TASKS_FOR_WEEK = "На этой неделе задач нет."
NO_TASKS_NEXT_WEEK = "На следующей неделе задач нет."
NO_TASKS_THIS_MONTH = "В этом месяце задач нет."
```

---

## Тесты

| Тест | Проверяет |
|------|-----------|
| `test_parse_date_range_this_week` | DateRange для текущей недели |
| `test_parse_date_range_next_week` | DateRange для следующей недели |
| `test_parse_date_range_this_month` | DateRange для текущего месяца |
| `test_parse_date_range_unknown` | None при неизвестном значении |
| `test_apply_task_filters_by_date` | Фильтрация по одиночной дате |
| `test_apply_task_filters_by_range` | Фильтрация по диапазону |
| `test_apply_task_filters_by_priority` | Фильтрация по приоритету |
| `test_apply_task_filters_combined` | Комбинация дата + приоритет |
| `test_list_tasks_this_week` | list_tasks с date_range=this_week |
| `test_list_tasks_this_week_with_priority` | list_tasks с date_range + priority |
| `test_list_tasks_next_week` | list_tasks с date_range=next_week |
| `test_project_tasks_with_date` | project_tasks с date |
| `test_project_tasks_with_date_range` | project_tasks с date_range |
| `test_project_tasks_with_priority` | project_tasks с priority |
| `test_project_tasks_with_date_and_priority` | project_tasks комбинация |
| `test_overdue_tasks_with_priority` | overdue_tasks с priority |
| `test_overdue_tasks_no_match_priority` | overdue_tasks — нет совпадений |

---

## Ограничения

- Теги (V2) — вне скоупа
- Комбинация "проект + неделя + приоритет" охватывается теми же слотами
- Диапазоны "следующий месяц", "эта неделя + N дней" — можно добавить позже
