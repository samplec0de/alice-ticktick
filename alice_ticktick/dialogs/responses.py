"""Response text constants for Alice skill (all in Russian)."""

# Welcome / help
WELCOME = (
    "Привет! Я помогу управлять задачами в TickTick. "
    'Скажите "что на сегодня", "создай задачу" или "помощь".'
)
WELCOME_BACK = 'С возвращением! Скажите "что на сегодня" или "создай задачу".'
HELP = (
    "Я умею:\n"
    "- Создать: «создай задачу купить молоко на завтра»\n"
    "- Показать: «что на сегодня?»\n"
    "- Просроченные: «какие задачи просрочены?»\n"
    "- Найти: «найди задачу про отчёт»\n"
    "- Изменить: «перенеси задачу на завтра»\n"
    "- Удалить: «удали задачу купить молоко»\n"
    "- Завершить: «отметь задачу купить молоко»"
)

# Auth
AUTH_REQUIRED = (
    "Для работы с TickTick нужно привязать аккаунт. "
    "Откройте навык в приложении Яндекс и привяжите аккаунт."
)

# Create task
TASK_CREATED = 'Готово! Задача "{name}" создана.'
TASK_CREATED_WITH_DATE = 'Готово! Задача "{name}" создана на {date}.'
TASK_NAME_REQUIRED = "Как назвать задачу? Скажите название."
CREATE_ERROR = "Не удалось создать задачу. Попробуйте ещё раз."

# List tasks
NO_TASKS_FOR_DATE = "На {date} задач нет."
TASKS_FOR_DATE = "На {date} {count}:\n{tasks}"
NO_TASKS_TODAY = "На сегодня задач нет. Можно отдыхать!"

# Overdue tasks
NO_OVERDUE = "Просроченных задач нет. Отличная работа!"
OVERDUE_TASKS_HEADER = "Просроченных задач: {count}:\n{tasks}"

# Complete task
TASK_COMPLETED = 'Задача "{name}" отмечена выполненной.'
TASK_NOT_FOUND = 'Задача "{name}" не найдена. Попробуйте сказать точнее.'
COMPLETE_NAME_REQUIRED = "Какую задачу отметить выполненной? Скажите название."
COMPLETE_ERROR = "Не удалось завершить задачу. Попробуйте ещё раз."

# Search
SEARCH_QUERY_REQUIRED = "Какую задачу найти? Скажите название или часть названия."
SEARCH_NO_RESULTS = 'По запросу "{query}" ничего не найдено.'
SEARCH_RESULTS = "Найдено {count}:\n{tasks}"
SEARCH_SINGLE = 'Нашла задачу: "{name}" в проекте, дедлайн — {date}.'

# Edit
EDIT_NAME_REQUIRED = "Какую задачу изменить? Скажите название."
EDIT_NO_CHANGES = (
    "Не поняла, что изменить. Скажите, например: "
    "«перенеси на завтра» или «поменяй приоритет на высокий»."
)
EDIT_SUCCESS = 'Задача "{name}" обновлена.'
EDIT_ERROR = "Не удалось обновить задачу. Попробуйте ещё раз."

# Delete
DELETE_NAME_REQUIRED = "Какую задачу удалить? Скажите название."
DELETE_CONFIRM = 'Удалить задачу "{name}"? Скажите да или нет.'
DELETE_SUCCESS = 'Задача "{name}" удалена.'
DELETE_CANCELLED = "Отменила удаление."
DELETE_ERROR = "Не удалось удалить задачу. Попробуйте ещё раз."
DELETE_CONFIRM_PROMPT = 'Скажите "да" для удаления или "нет" для отмены.'

# Unknown
UNKNOWN = "Не поняла команду. Скажите «помощь», чтобы узнать, что я умею."

# Errors
API_ERROR = "Произошла ошибка при обращении к TickTick. Попробуйте позже."
GOODBYE = "До встречи! Удачного дня!"


def pluralize_tasks(count: int) -> str:
    """Pluralize 'задача' in Russian: 1 задача, 2 задачи, 5 задач."""
    if count % 10 == 1 and count % 100 != 11:
        return f"{count} задача"
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return f"{count} задачи"
    return f"{count} задач"
