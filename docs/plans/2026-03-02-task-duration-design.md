# Дизайн: Задачи с длительностью (встречи)

## Цель

Поддержка создания задач с указанием длительности или временного диапазона — для встреч, совещаний, событий.

## Решения

### Подход: расширение `create_task`

Расширяем существующий интент `create_task` вместо создания отдельного `create_meeting`.
В TickTick встреча — это задача с `startDate` + `dueDate` + `isAllDay=false`.
Подход протестирован в Яндекс Диалогах — 100% точность и полнота.

### Голосовые паттерны

Два паттерна:

1. **Duration** — "на N часов/минут":
   - "создай встречу совещание завтра в 10 на 2 часа"
   - "добавь встречу ланч завтра в 12 на час"
   - "создай встречу стендап завтра в 10 на полчаса"

2. **Range** — "с X до Y":
   - "создай задачу митинг с 14 до 16"
   - "добавь встречу обед с 12 до 13"

### Комбинации

Поддерживаются все комбинации с существующими фичами:
- Duration/range + приоритет
- Duration/range + повторение
- Duration/range + напоминание

### Duration без start time

Если указана длительность без времени начала ("создай встречу совещание на час"):
- Спрашиваем: "Во сколько начинается? Скажите время."

## Грамматика

### Новые строки root

```
(создай|добавь|...) (задачу|...|встречу)? $TaskName (на $Date) на $DurationValue $DurationUnit (с приоритетом ...)? ($Recurrence)? (с напоминанием ...)?
(создай|добавь|...) (задачу|...|встречу)? $TaskName (на $Date) на $DurationUnit (с приоритетом ...)? ($Recurrence)? (с напоминанием ...)?
(создай|добавь|...) (задачу|...|встречу)? $TaskName с $RangeStart до $RangeEnd (с приоритетом ...)? ($Recurrence)? (с напоминанием ...)?
```

### Новые слоты

| Слот | Source | Type |
|------|--------|------|
| `duration_value` | `$DurationValue` | `YANDEX.NUMBER` |
| `duration_unit` | `$DurationUnit` | `YANDEX.STRING` |
| `range_start` | `$RangeStart` | `YANDEX.DATETIME` |
| `range_end` | `$RangeEnd` | `YANDEX.DATETIME` |

### Новые нетерминалы

```
$DurationValue: $YANDEX.NUMBER
$DurationUnit: час | минута | полчаса
$RangeStart: $YANDEX.DATETIME
$RangeEnd: $YANDEX.DATETIME
```

## Обработка в хендлере

### `CreateTaskSlots` — новые поля

- `duration_value: int | None`
- `duration_unit: str | None`
- `range_start: YandexDateTime | None`
- `range_end: YandexDateTime | None`

### Логика

Приоритет: range > duration > обычная дата

1. **Range** (`range_start` + `range_end`):
   - `startDate` = range_start, `dueDate` = range_end, `isAllDay = False`

2. **Duration** (`duration_unit` + `date`):
   - `startDate` = date, `dueDate` = date + duration, `isAllDay = False`

3. **Duration без date**:
   - Уточняющий вопрос: "Во сколько начинается? Скажите время."

4. **Обычная задача** — без изменений

### `parse_duration`

```python
def parse_duration(duration_value: int | None, duration_unit: str | None) -> timedelta | None
```

Маппинг: час → hours, минута → minutes, полчаса → 30 minutes.
Если `duration_value` is None → n=1 (кроме "полчаса").

## Ответы

Новый формат (только для задач с длительностью):

```
Добавила! "{name}" на {date}, {start_time} до {end_time}.
Добавила! "{name}" на {date}, {start_time} до {end_time}, приоритет — {priority}.
Добавила! "{name}" на {date}, {start_time} до {end_time}, {recurrence}.
Добавила! "{name}" на {date}, {start_time} до {end_time}, напоминание {reminder}.
```

Существующие шаблоны (`Готово! Задача "..." создана...`) не меняются.

## Тесты

- Парсинг длительности: час, 2 часа, 30 минут, полчаса
- Duration + date → корректные startDate/dueDate
- Range → корректные startDate/dueDate
- Duration без date → уточняющий вопрос
- Комбинации: duration + reminder, duration + recurrence, range + priority
- Формат ответов
- Регрессия

## Финализация

- Обновить PRD (FR-21)
- Обновить README с примерами
- Обновить docs/VOICE_TESTING.md
- Создать MR → ревью → мердж → настройка грамматик в UI
