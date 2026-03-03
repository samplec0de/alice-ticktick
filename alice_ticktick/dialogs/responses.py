"""Response text constants for Alice skill (all in Russian)."""

# Welcome / help
WELCOME = "Слушаю!"
WELCOME_TTS = "Слушаю!"
WELCOME_BACK = "С возвращением!"
WELCOME_BACK_TTS = "С возвращением!"
HELP = (
    "Я умею:\n"
    "- Создать: «создай задачу купить молоко на завтра»\n"
    "- Повторяющуюся: «создай задачу каждый понедельник»\n"
    "- С напоминанием: «создай задачу с напоминанием за час»\n"
    "- Показать: «что на сегодня?»\n"
    "- По приоритету: «покажи срочные задачи на завтра»\n"
    "- Просроченные: «какие задачи просрочены?»\n"
    "- Найти: «найди задачу про отчёт»\n"
    "- Изменить: «перенеси задачу на завтра»\n"
    "- Удалить: «удали задачу купить молоко»\n"
    "- Завершить: «отметь задачу купить молоко»\n"
    "- Напоминание: «напомни о задаче за 30 минут»\n"
    "- Подзадача: «добавь подзадачу к задаче»\n"
    "- Проекты: «какие у меня проекты?», «задачи проекта Работа», «создай проект»\n"
    "- Чеклист: «добавь пункт в чеклист задачи»"
)

# Auth
AUTH_REQUIRED_LINKING = "Для работы нужно привязать аккаунт TickTick."
AUTH_REQUIRED_NO_LINKING = (
    "Для работы нужно привязать аккаунт TickTick. "
    "Откройте навык в приложении Яндекс, чтобы привязать аккаунт."
)

# Create task
TASK_CREATED = 'Готово! Задача "{name}" создана.'
TASK_CREATED_WITH_DATE = 'Готово! Задача "{name}" создана на {date}.'
TASK_CREATED_WITH_PRIORITY = 'Готово! Задача "{name}" создана, приоритет — {priority}.'
TASK_CREATED_WITH_DATE_AND_PRIORITY = (
    'Готово! Задача "{name}" создана на {date}, приоритет — {priority}.'
)
TASK_CREATED_IN_PROJECT = 'Готово! Задача "{name}" создана в проекте "{project}".'
TASK_CREATED_IN_PROJECT_WITH_DATE = (
    'Готово! Задача "{name}" создана в проекте "{project}" на {date}.'
)
TASK_CREATED_RECURRING = 'Готово! Задача "{name}" создана, {recurrence}.'
TASK_CREATED_WITH_REMINDER = 'Готово! Задача "{name}" создана с напоминанием {reminder}.'
TASK_CREATED_RECURRING_WITH_REMINDER = (
    'Готово! Задача "{name}" создана, {recurrence}, напоминание {reminder}.'
)
# Create task with duration/range
TASK_CREATED_WITH_DURATION = 'Добавила! "{name}" на {date}, {start_time} до {end_time}.'
TASK_CREATED_WITH_DURATION_AND_PRIORITY = (
    'Добавила! "{name}" на {date}, {start_time} до {end_time}, приоритет — {priority}.'
)
TASK_CREATED_WITH_DURATION_RECURRING = (
    'Добавила! "{name}" на {date}, {start_time} до {end_time}, {recurrence}.'
)
TASK_CREATED_WITH_DURATION_AND_REMINDER = (
    'Добавила! "{name}" на {date}, {start_time} до {end_time}, напоминание {reminder}.'
)
TASK_CREATED_WITH_DURATION_RECURRING_AND_REMINDER = (
    'Добавила! "{name}" на {date}, {start_time} до {end_time},'
    " {recurrence}, напоминание {reminder}."
)
DURATION_MISSING_START_TIME = "Во сколько начинается? Скажите время."
TASK_NAME_REQUIRED = "Как назвать задачу? Скажите название."
CREATE_ERROR = "Не удалось создать задачу. Попробуйте ещё раз."

# List tasks
NO_TASKS_FOR_DATE = "На {date} задач нет."
TASKS_FOR_DATE = "На {date} {count}:\n{tasks}"
NO_TASKS_TODAY = "На сегодня задач нет. Можно отдыхать!"

# Filter by priority
TASKS_FOR_DATE_WITH_PRIORITY = "На {date} с {priority}, {count}:\n{tasks}"
NO_TASKS_FOR_DATE_WITH_PRIORITY = "На {date} задач с {priority} нет."
NO_TASKS_TODAY_WITH_PRIORITY = "На сегодня задач с {priority} нет."

# Overdue tasks
NO_OVERDUE = "Просроченных задач нет. Отличная работа!"
OVERDUE_TASKS_HEADER = "Просроченных задач: {count}:\n{tasks}"

# Complete task
TASK_COMPLETED = 'Задача "{name}"{context} отмечена выполненной.'
TASK_NOT_FOUND = 'Задача "{name}" не найдена. Попробуйте сказать точнее.'
COMPLETE_NAME_REQUIRED = "Какую задачу отметить выполненной? Скажите название."
COMPLETE_ERROR = "Не удалось завершить задачу. Попробуйте ещё раз."

# Search
SEARCH_QUERY_REQUIRED = "Какую задачу найти? Скажите название или часть названия."
SEARCH_NO_RESULTS = 'По запросу "{query}" ничего не найдено.'
SEARCH_BEST_MATCH = "Лучшее совпадение — «{name}»{context}:"
SEARCH_BEST_MATCH_SINGLE = "Найдена задача «{name}»{context}:"
SEARCH_DESCRIPTION = "Описание: {description}"
SEARCH_ALSO_FOUND = "Также найдено:"
SEARCH_CHECKLIST_MORE = "…и ещё {count}"

# Edit
EDIT_NAME_REQUIRED = "Какую задачу изменить? Скажите название."
EDIT_NO_CHANGES = (
    "Не поняла, что изменить. Скажите, например: "
    "«перенеси на завтра» или «поменяй приоритет на высокий»."
)
TASK_MOVED = 'Задача "{name}" перемещена в проект "{project}".'
TASK_ALREADY_IN_PROJECT = 'Задача "{name}" уже в проекте "{project}".'
EDIT_SUCCESS = 'Задача "{name}" обновлена: {changes}.'
EDIT_SUCCESS_NO_DETAILS = 'Задача "{name}" обновлена.'
EDIT_ERROR = "Не удалось обновить задачу. Попробуйте ещё раз."

# Recurrence/reminder edit
RECURRENCE_UPDATED = 'Повторение задачи "{name}" изменено: {recurrence}.'
RECURRENCE_REMOVED = 'Повторение задачи "{name}" убрано.'
REMINDER_UPDATED = 'Напоминание задачи "{name}" изменено: {reminder}.'
REMINDER_REMOVED = 'Напоминание задачи "{name}" убрано.'

# Delete
DELETE_NAME_REQUIRED = "Какую задачу удалить? Скажите название."
DELETE_CONFIRM = 'Удалить задачу "{name}"{context}? Скажите да или нет.'
DELETE_SUCCESS = 'Задача "{name}"{context} удалена.'
DELETE_CANCELLED = "Отменила удаление."
DELETE_ERROR = "Не удалось удалить задачу. Попробуйте ещё раз."
DELETE_CONFIRM_PROMPT = 'Скажите "да" для удаления или "нет" для отмены.'

# Subtasks
SUBTASK_PARENT_REQUIRED = "Назовите задачу, к которой нужно добавить подзадачу."
SUBTASK_NAME_REQUIRED = "Как назвать подзадачу?"
SUBTASK_CREATED = "Подзадача «{name}» добавлена к задаче «{parent}»."
SUBTASK_ERROR = "Не удалось создать подзадачу. Попробуйте ещё раз."
NO_SUBTASKS = "У задачи «{name}» нет подзадач."
SUBTASKS_HEADER = "Подзадачи «{name}» ({count}):\n{tasks}"
LIST_SUBTASKS_NAME_REQUIRED = "Назовите задачу, подзадачи которой показать."

# Checklists
CHECKLIST_TASK_REQUIRED = "Назовите задачу для чеклиста."
CHECKLIST_ITEM_REQUIRED = "Что добавить в чеклист?"
CHECKLIST_ITEM_ADDED = "Добавила «{item}» в чеклист задачи «{task}». Всего пунктов: {count}."
CHECKLIST_ITEM_ERROR = "Не удалось добавить пункт в чеклист."
CHECKLIST_EMPTY = "Чеклист задачи «{name}» пуст."
CHECKLIST_HEADER = "Чеклист задачи «{name}»:\n{items}"
CHECKLIST_ITEM_CHECKED = "Пункт «{item}» в задаче «{task}» отмечен выполненным."
CHECKLIST_ITEM_NOT_FOUND = "Пункт «{item}» не найден в чеклисте задачи «{task}»."
CHECKLIST_ITEM_DELETED = "Пункт «{item}» удалён из чеклиста задачи «{task}»."
CHECKLIST_ITEM_DELETE_ERROR = "Не удалось удалить пункт из чеклиста."
CHECKLIST_CHECK_ERROR = "Не удалось отметить пункт."
SHOW_CHECKLIST_NAME_REQUIRED = "Назовите задачу, чеклист которой показать."

# Add reminder to existing task
REMINDER_ADDED = 'Напоминание {reminder} добавлено к задаче "{name}".'
REMINDER_TASK_REQUIRED = "К какой задаче добавить напоминание?"
REMINDER_VALUE_REQUIRED = "За сколько напомнить? Скажите, например, «за 30 минут» или «за час»."
REMINDER_PARSE_ERROR = (
    "Не поняла время напоминания. Скажите, например, «за 30 минут» или «за час»."
)
REMINDER_ERROR = "Не удалось добавить напоминание. Попробуйте ещё раз."

PROJECT_NOT_FOUND = 'Проект "{name}" не найден. Ваши проекты: {projects}.'

# Projects
PROJECTS_LIST = "Ваши проекты ({count}):\n{projects}"
NO_PROJECTS = "У вас пока нет проектов."
PROJECT_TASKS_HEADER = "Задачи проекта «{project}» ({count}):\n{tasks}"
PROJECT_NO_TASKS = "В проекте «{project}» задач нет."
PROJECT_CREATED = "Проект «{name}» создан."
PROJECT_NAME_REQUIRED = "Как назвать проект? Скажите название."
PROJECT_CREATE_ERROR = "Не удалось создать проект. Попробуйте ещё раз."
PROJECT_TASKS_NAME_REQUIRED = "Какой проект показать? Скажите название."

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
