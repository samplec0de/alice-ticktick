# NLU-грамматики интентов

Актуальные грамматики из Яндекс Диалогов (дата выгрузки: 2026-03-01).

Каждый `.grammar` файл содержит грамматику одного интента в формате Яндекс NLU.
Тесты (положительные и отрицательные) — в `tests.yaml`.

## Интенты

| Файл | ID | Название |
|------|----|----------|
| `add_checklist_item.grammar` | `add_checklist_item` | Добавление пункта чеклиста |
| `add_subtask.grammar` | `add_subtask` | Добавление подзадачи |
| `check_item.grammar` | `check_item` | Отметка пункта чеклиста |
| `complete_task.grammar` | `complete_task` | Завершение задачи |
| `create_task.grammar` | `create_task` | Создание задачи |
| `create_recurring_task.grammar` | `create_recurring_task` | Создание повторяющейся задачи |
| `add_reminder.grammar` | `add_reminder` | Добавление напоминания к задаче |
| `delete_checklist_item.grammar` | `delete_checklist_item` | Удаление пункта чеклиста |
| `delete_task.grammar` | `delete_task` | Удаление задачи |
| `edit_task.grammar` | `edit_task` | Редактирование задачи |
| `list_subtasks.grammar` | `list_subtasks` | Просмотр подзадач |
| `list_tasks.grammar` | `list_tasks` | Просмотр задач |
| `overdue_tasks.grammar` | `overdue_tasks` | Просроченные задачи |
| `search_task.grammar` | `search_task` | Поиск задачи |
| `show_checklist.grammar` | `show_checklist` | Просмотр чеклиста |
