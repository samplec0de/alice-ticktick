# Дизайн: FR-17 Управление проектами + фикс welcome TTS

## Баг-фикс: welcome TTS (бесконечная загрузка)

**Проблема:** `WELCOME_TTS` содержит только `<speaker audio="...">` без речевого текста. Алиса воспроизводит короткий звук, но не произносит ничего — визуально бесконечная загрузка.

**Фикс:** добавить текст после `<speaker>` тега:
```python
WELCOME_TTS = '<speaker audio="alice-sounds-things-bell-1"> Слушаю!'
WELCOME_BACK_TTS = '<speaker audio="alice-sounds-things-bell-1"> С возвращением!'
```

## FR-17: Управление проектами

### Новые интенты (Яндекс Диалоги)

1. **`list_projects`** — просмотр списка проектов
   - Примеры: «какие у меня проекты?», «покажи проекты», «мои списки»
   - Слоты: нет

2. **`project_tasks`** — задачи конкретного проекта
   - Примеры: «покажи задачи проекта Работа», «что в проекте Дом?»
   - Слоты: `project_name` (YANDEX.STRING)

3. **`create_project`** — создание проекта
   - Примеры: «создай проект Путешествие», «новый список Покупки»
   - Слоты: `project_name` (YANDEX.STRING)

### API клиент

Новый метод в `TickTickClient`:
```python
async def create_project(self, name: str) -> Project:
    """Create a new project."""
    response = await self._client.post("/project", json={"name": name})
    _raise_for_status(response)
    return Project.model_validate(response.json())
```

### Handlers

**`handle_list_projects`:**
- Получает все проекты через `get_projects()`
- Выводит нумерованным списком (до 10)
- При пустом списке — специальное сообщение

**`handle_project_tasks`:**
- Fuzzy search проекта по имени через `find_best_match`
- Получает задачи проекта через `get_tasks(project_id)`
- Фильтрует активные (status == 0)
- Пагинация: до 5 задач голосом, аналогично `list_tasks`
- При пустом проекте — «В проекте X задач нет»

**`handle_create_project`:**
- Создаёт проект через `POST /project`
- Подтверждение: «Проект X создан»

### Новые response-тексты

```python
# Projects
PROJECTS_LIST = "Ваши проекты ({count}):\n{projects}"
NO_PROJECTS = "У вас пока нет проектов."
PROJECT_TASKS_HEADER = "Задачи проекта «{project}» ({count}):\n{tasks}"
PROJECT_NO_TASKS = "В проекте «{project}» задач нет."
PROJECT_CREATED = "Проект «{name}» создан."
PROJECT_NAME_REQUIRED = "Как назвать проект? Скажите название."
PROJECT_CREATE_ERROR = "Не удалось создать проект. Попробуйте ещё раз."
PROJECT_TASKS_NAME_REQUIRED = "Какой проект показать? Скажите название."
```

### Обновление HELP

Добавить строку:
```
"- Проекты: «какие у меня проекты?», «задачи проекта Работа», «создай проект»\n"
```

### Тесты

Для каждого handler:
- Успешный сценарий
- Пустой список / проект не найден
- Ошибка API
- Отсутствие авторизации
- Fuzzy search проекта (для project_tasks)
