# Дизайн: Повторяющиеся задачи и напоминания (Phase 4)

Дата: 2026-03-01

## Обзор

Добавление поддержки повторяющихся задач (FR-13) и напоминаний (FR-14) через TickTick API v1.
Поля `repeatFlag` (RRULE, RFC 5545) и `reminders` (iCal TRIGGER) поддерживаются API v1.

## Решения

- Полный набор RRULE-паттернов: DAILY/WEEKLY/MONTHLY/YEARLY, INTERVAL, BYDAY, BYMONTHDAY, позиционный BYDAY
- Повторение: слот в `create_task` + отдельный интент `create_recurring_task`
- Напоминания: при создании задачи + к существующим (`add_reminder`)
- Редактирование/удаление повторения и напоминания через `edit_task`
- Подход к парсингу: несколько NLU-слотов в грамматике, серверный маппер слотов → RRULE/TRIGGER

---

## 1. NLU-интенты и грамматики

### 1.1 Модификация `create_task`

Новые слоты:

| Слот | Тип | Примеры значений |
|------|-----|-----------------|
| `rec_freq` | STRING | день, неделю, месяц, год, понедельник, будни |
| `rec_interval` | NUMBER | 3 (в "каждые 3 дня") |
| `rec_monthday` | NUMBER | 15 (в "каждое 15 число") |
| `reminder_value` | NUMBER | 30 (в "за 30 минут") |
| `reminder_unit` | STRING | минут, час, день |

Грамматика:
```
root:
    %lemma
    (создай|добавь|запиши|новая|поставь) (задачу|задача|напоминание)? $TaskName (в (проект|список|папку) $ProjectName)? (на $Date)? (с приоритетом (низкий|средний|высокий))? ($Recurrence)? (с напоминанием за $ReminderValue $ReminderUnit)?
    (создай|добавь|запиши|новая|поставь) (задачу|задача|напоминание)? $TaskName $Recurrence (на $Date)? (в (проект|список|папку) $ProjectName)?

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
    rec_freq:
        source: $RecFreq
        type: YANDEX.STRING
    rec_interval:
        source: $RecInterval
        type: YANDEX.NUMBER
    rec_monthday:
        source: $RecMonthday
        type: YANDEX.NUMBER
    reminder_value:
        source: $ReminderValue
        type: YANDEX.NUMBER
    reminder_unit:
        source: $ReminderUnit
        type: YANDEX.STRING

$TaskName:
    .+

$Date:
    $YANDEX.DATETIME

$ProjectName:
    .+

$Recurrence:
    (каждый|каждую|каждое) $RecFreq
    (каждые) $RecInterval $RecFreq
    (каждое) $RecMonthday (число)
    ежедневно
    еженедельно
    ежемесячно
    (по) $RecFreq

$RecFreq:
    .+

$RecInterval:
    $YANDEX.NUMBER

$RecMonthday:
    $YANDEX.NUMBER

$ReminderValue:
    $YANDEX.NUMBER

$ReminderUnit:
    .+
```

### 1.2 Новый интент `create_recurring_task`

Для фраз «напоминай каждый понедельник проверить отчёт»:
```
root:
    %lemma
    (напоминай|напоминать|повторяй) $Recurrence $TaskName

slots:
    task_name:
        source: $TaskName
        type: YANDEX.STRING
    rec_freq:
        source: $RecFreq
        type: YANDEX.STRING
    rec_interval:
        source: $RecInterval
        type: YANDEX.NUMBER
    rec_monthday:
        source: $RecMonthday
        type: YANDEX.NUMBER

$TaskName:
    .+

$Recurrence:
    (каждый|каждую|каждое) $RecFreq
    (каждые) $RecInterval $RecFreq
    (каждое) $RecMonthday (число)
    ежедневно
    еженедельно
    ежемесячно

$RecFreq:
    .+

$RecInterval:
    $YANDEX.NUMBER

$RecMonthday:
    $YANDEX.NUMBER
```

### 1.3 Новый интент `add_reminder`

Для «напомни о задаче X за час»:
```
root:
    %lemma
    (напомни|поставь напоминание) (о|про|на|для) (задаче|задачу|задача)? $TaskName за $ReminderValue $ReminderUnit

slots:
    task_name:
        source: $TaskName
        type: YANDEX.STRING
    reminder_value:
        source: $ReminderValue
        type: YANDEX.NUMBER
    reminder_unit:
        source: $ReminderUnit
        type: YANDEX.STRING

$TaskName:
    .+

$ReminderValue:
    $YANDEX.NUMBER

$ReminderUnit:
    .+
```

### 1.4 Модификация `edit_task`

Новые альтернативные паттерны:
```
    (убери|отмени|удали) (повторение|повтор) (у|для|задачи)? $TaskName
    (поменяй|измени) (повторение|повтор) (у|для|задачи)? $TaskName на $Recurrence
    (убери|отмени|удали) (напоминание) (у|для|задачи)? $TaskName
    (поменяй|измени|поставь) (напоминание) (у|для|задачи)? $TaskName на за $ReminderValue $ReminderUnit
```

С теми же слотами `rec_freq`, `rec_interval`, `rec_monthday`, `reminder_value`, `reminder_unit`.

---

## 2. Модели данных (TickTick)

### Task (чтение)
```python
repeat_flag: str | None = Field(default=None, alias="repeatFlag")
reminders: list[str] = Field(default_factory=list)
```

### TaskCreate (создание)
```python
repeat_flag: str | None = Field(default=None, alias="repeatFlag")
reminders: list[str] | None = None
```

### TaskUpdate (обновление)
```python
repeat_flag: str | None = Field(default=None, alias="repeatFlag")
reminders: list[str] | None = None
```

Удаление: `repeatFlag=""`, `reminders=[]` — `exclude_none=True` пропускает None, но отправляет пустые значения.

---

## 3. NLP-парсеры

### 3.1 `recurrence_parser.py`

`build_rrule(rec_freq, rec_interval, rec_monthday) -> str | None`

Маппинг rec_freq → RRULE:

| rec_freq | RRULE |
|---|---|
| день, дня, дней, ежедневно | FREQ=DAILY |
| неделя, недели, недель, еженедельно | FREQ=WEEKLY |
| месяц, месяца, месяцев, ежемесячно | FREQ=MONTHLY |
| год, года, лет, ежегодно | FREQ=YEARLY |
| понедельник | FREQ=WEEKLY;BYDAY=MO |
| вторник | FREQ=WEEKLY;BYDAY=TU |
| среда, среду | FREQ=WEEKLY;BYDAY=WE |
| четверг | FREQ=WEEKLY;BYDAY=TH |
| пятница, пятницу | FREQ=WEEKLY;BYDAY=FR |
| суббота, субботу | FREQ=WEEKLY;BYDAY=SA |
| воскресенье | FREQ=WEEKLY;BYDAY=SU |
| будни, будний, будням | FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR |
| выходные, выходным | FREQ=WEEKLY;BYDAY=SA,SU |

Комбинации:
- rec_interval + freq → `RRULE:FREQ=...;INTERVAL=N`
- rec_monthday → `RRULE:FREQ=MONTHLY;BYMONTHDAY=N`
- rec_interval + день недели → `RRULE:FREQ=MONTHLY;BYDAY=NXX` (позиционный)

`format_recurrence(rrule) -> str` — обратный маппинг для ответов.

### 3.2 `reminder_parser.py`

`build_trigger(value, unit) -> str | None`

| unit | Результат |
|---|---|
| минута, минут, минуты | TRIGGER:-PTNM |
| час, часа, часов | TRIGGER:-PTNH |
| день, дня, дней | TRIGGER:-PND |
| value=0 | TRIGGER:PT0S |

`format_reminder(trigger) -> str` — обратный маппинг для ответов.

---

## 4. Интенты и слоты (Python)

### Новые константы
```python
CREATE_RECURRING_TASK = "create_recurring_task"
ADD_REMINDER = "add_reminder"
```

### Расширение CreateTaskSlots
+`rec_freq`, `rec_interval`, `rec_monthday`, `reminder_value`, `reminder_unit`

### Новые dataclass
- `CreateRecurringTaskSlots` — task_name, rec_freq, rec_interval, rec_monthday
- `AddReminderSlots` — task_name, reminder_value, reminder_unit

### Расширение EditTaskSlots
+`rec_freq`, `rec_interval`, `rec_monthday`, `reminder_value`, `reminder_unit`, `remove_recurrence`, `remove_reminder`

---

## 5. Хендлеры

### handle_create_task — расширение
После парсинга приоритета: build_rrule() → repeatFlag, build_trigger() → reminders.
Передаём в TaskCreate. Новые шаблоны ответов с информацией о повторении/напоминании.

### handle_create_recurring_task — новый
Делегирует в handle_create_task. Дата по умолчанию — сегодня.

### handle_add_reminder — новый
Поиск задачи (fuzzy) → чтение существующих reminders → добавление нового trigger → TaskUpdate.

### handle_edit_task — расширение
Ветки: изменение/удаление повторения, изменение/удаление напоминания.
Удаление: repeatFlag="", reminders=[].

### router.py
+2 маршрута для create_recurring_task, add_reminder.

### responses.py
~10 новых шаблонов: TASK_CREATED_RECURRING, TASK_CREATED_WITH_REMINDER, REMINDER_ADDED, RECURRENCE_UPDATED, RECURRENCE_REMOVED, REMINDER_UPDATED, REMINDER_REMOVED и т.д.

### handle_help
Обновить текст помощи.

---

## 6. Тестирование

~70 новых тестов:

- `tests/test_recurrence_parser.py` — ~25 тестов build_rrule + format_recurrence
- `tests/test_reminder_parser.py` — ~10 тестов build_trigger + format_reminder
- `tests/test_handlers.py` — ~30 тестов хендлеров (create с повторением, create_recurring, add_reminder, edit с повторением/напоминанием)
- `tests/test_models.py` — ~5 тестов сериализации repeatFlag/reminders

---

## 7. Сводка изменений

| Файл | Действие |
|------|----------|
| `ticktick/models.py` | Изменение |
| `dialogs/nlp/recurrence_parser.py` | **Новый** |
| `dialogs/nlp/reminder_parser.py` | **Новый** |
| `dialogs/nlp/__init__.py` | Изменение |
| `dialogs/intents.py` | Изменение |
| `dialogs/handlers.py` | Изменение |
| `dialogs/responses.py` | Изменение |
| `dialogs/router.py` | Изменение |
| `docs/grammars/create_task.grammar` | Изменение |
| `docs/grammars/edit_task.grammar` | Изменение |
| `docs/grammars/create_recurring_task.grammar` | **Новый** |
| `docs/grammars/add_reminder.grammar` | **Новый** |
| `docs/grammars/tests.yaml` | Изменение |
| `tests/test_recurrence_parser.py` | **Новый** |
| `tests/test_reminder_parser.py` | **Новый** |
| `tests/test_handlers.py` | Изменение |
| `tests/test_models.py` | Изменение |

Ручная настройка в Яндекс Диалогах:
- Обновить грамматику create_task и edit_task
- Создать интенты create_recurring_task и add_reminder
- Опубликовать черновик
