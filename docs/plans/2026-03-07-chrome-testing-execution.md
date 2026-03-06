# Chrome Testing Execution Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Execute full test suite for TickTick skill through Yandex Dialogs browser interface, documenting results for all 116 test scenarios.

**Architecture:** Browser automation using mcp__claude-in-chrome__ tools. Load test page from docs/CHROME_TESTING.md, execute scenarios sequentially per section (greetings → create_task → list_tasks → etc.), record pass/fail for each, identify blockers and known bugs.

**Tech Stack:** Chrome automation MCP, Yandex Dialogs skill testing interface, TickTick API backend.

---

## Task 1: Setup Browser Session & Navigate to Test Page

**Files:**
- Reference: `docs/CHROME_TESTING.md` (sections 1.1-1.2)
- Target: `https://dialogs.yandex.ru/developer/skills/d3f073db-dece-42b8-9447-87511df30c83/draft/test`

**Step 1: Initialize browser context**

Run: `mcp__claude-in-chrome__tabs_context_mcp`
Expected: Get current tab group context. If empty or creating new session, note tab IDs.

**Step 2: Create new testing tab**

Run: `mcp__claude-in-chrome__tabs_create_mcp`
Expected: New empty tab created. Record tab ID for subsequent operations.

**Step 3: Navigate to test page**

Run: `mcp__claude-in-chrome__navigate` with URL `https://dialogs.yandex.ru/developer/skills/d3f073db-dece-42b8-9447-87511df30c83/draft/test`
Expected: Page loads, displays chat interface with input field.

**Step 4: Take screenshot and verify page loaded**

Run: `mcp__claude-in-chrome__computer action=screenshot`
Expected: Screenshot shows Yandex Dialogs chat interface ready for input.

**Step 5: Commit preparation**

Record in memory:
- Tab ID for testing
- Timestamp of session start (2026-03-07)
- Screenshot of initial state

---

## Task 2: Execute Section 3.1 - Greeting Test

**Files:**
- Test spec: `docs/CHROME_TESTING.md` lines 68-73
- Result tracking: Create `docs/test-results/2026-03-07-greeting.md`

**Step 1: Refresh page (new session)**

Run: `mcp__claude-in-chrome__navigate` to same URL with page refresh
Expected: Page refreshes, new session created for skill.

**Step 2: Wait for greeting response**

Run: `mcp__claude-in-chrome__computer action=wait duration=2`
Expected: Skill automatically sends greeting on new session.

**Step 3: Read greeting response**

Run: `mcp__claude-in-chrome__get_page_text`
Expected: Response contains greeting text matching pattern: "Привет! Я помогу управлять задачами в TickTick..."

**Step 4: Record result**

Record in test results:
- Test 3.1.1: Status [OK/WARN/FAIL]
- Expected: Greeting message present
- Actual: [Response text]
- Notes: [Any deviations]

---

## Task 3: Execute Section 3.2 - Create Task (Basic)

**Files:**
- Test spec: `docs/CHROME_TESTING.md` lines 76-90
- Result tracking: Update `docs/test-results/2026-03-07-create-basic.md`

**Step 1: Test 3.2.1 - Create task "купить хлеб"**

Run command: `mcp__claude-in-chrome__form_input` with text "создай задачу тестирование купить хлеб"
Run: `mcp__claude-in-chrome__computer action=key text=Return`
Wait: `mcp__claude-in-chrome__computer action=wait duration=2`
Read response: `mcp__claude-in-chrome__get_page_text`
Expected: "Задача «купить хлеб» создана" (or similar confirmation)
Record: Test 3.2.1 result

**Step 2: Test 3.2.2 - Create task with date "на завтра"**

Run command: Input "добавь задачу тестирование позвонить маме на завтра"
Expected: "Задача создана на завтра"
Record: Test 3.2.2 result

**Step 3: Test 3.2.3 - Create task with date "на пятницу"**

Run command: Input "запиши задачу тестирование подготовить отчёт на пятницу"
Expected: "Задача создана на пятницу"
Record: Test 3.2.3 result

**Step 4: Test 3.2.4 - Create task with priority**

Run command: Input "создай задачу тестирование оплатить счёт с высоким приоритетом"
Expected: "Задача создана с приоритетом"
Record: Test 3.2.4 result

**Step 5: Test 3.2.5-3.2.8 - Variants and edge cases**

Repeat same pattern for:
- 3.2.5: "новая задача написать письмо"
- 3.2.6: "поставь задачу тестирование купить молоко на послезавтра"
- 3.2.7: "создай задачу" (expect "Как назвать задачу?")
- 3.2.8: "создай задачу тестирование презентация в проект работа"

Record all results with status and actual response.

---

## Task 4: Execute Section 3.2 - Recurring Tasks (Tests 3.2.9-3.2.14)

**Files:**
- Test spec: `docs/CHROME_TESTING.md` lines 91-101
- Result tracking: Update `docs/test-results/2026-03-07-recurring.md`

**Pattern for each test:**
1. Input command from spec
2. Wait 2 seconds
3. Read response with `get_page_text`
4. Check if response indicates recurrence created (daily, bi-weekly, monthly, specific date, etc.)
5. Record status + actual response

**Commands to execute:**
- 3.2.9: `создай задачу тестирование полить цветы каждый день`
- 3.2.10: `создай задачу тестирование оплатить аренду каждое 15 число`
- 3.2.11: `создай задачу тестирование пробежка каждые 2 дня`
- 3.2.12: `создай задачу тестирование совещание каждый понедельник`
- 3.2.13: `создай задачу тестирование отчёт ежемесячно`
- 3.2.14: `создай задачу тестирование уборка каждые 2 недели`

Expected pattern: "Задача создана, [frequency]"

---

## Task 5: Execute Section 3.2 - Tasks with Reminders (Tests 3.2.15-3.2.17)

**Files:**
- Test spec: `docs/CHROME_TESTING.md` lines 102-109
- Result tracking: Update `docs/test-results/2026-03-07-reminders.md`

**Commands to execute:**
- 3.2.15: `создай задачу тестирование встреча на завтра с напоминанием за 30 минут`
- 3.2.16: `создай задачу тестирование позвонить врачу с напоминанием за час`
- 3.2.17: `создай задачу тестирование зарядка ежедневно с напоминанием за 15 минут`

Expected: "Задача с [датой и] напоминанием" or similar confirmation.

Record all results.

---

## Task 6: Execute Section 3.2 - Meetings/Events (Tests 3.2.18-3.2.23)

**Files:**
- Test spec: `docs/CHROME_TESTING.md` lines 110-120
- Result tracking: Update `docs/test-results/2026-03-07-meetings.md`

**Commands to execute:**
- 3.2.18: `создай встречу тестирование совещание завтра в 10 на 2 часа` → expect "10:00 до 12:00"
- 3.2.19: `добавь встречу тестирование ланч завтра в 12 на час` → expect "12:00 до 13:00"
- 3.2.20: `создай встречу тестирование стендап завтра в 10 на полчаса` → expect "10:00 до 10:30"
- 3.2.21: `создай задачу тестирование митинг с 14 до 16` → expect "14:00 до 16:00"
- 3.2.22: `создай встречу тестирование на час` → expect clarification "Во сколько начинается?"
- 3.2.23: `создай встречу тестирование совещание завтра в 10 на 2 часа с напоминанием за 15 минут` → expect meeting + reminder

Record all results.

---

## Task 7: Execute Section 3.3 - List Tasks (Tests 3.3.1-3.3.6)

**Files:**
- Test spec: `docs/CHROME_TESTING.md` lines 123-133
- Result tracking: Update `docs/test-results/2026-03-07-list.md`

**Commands to execute:**
- 3.3.1: `что на сегодня` → expect list of today's tasks
- 3.3.2: `покажи задачи на завтра` → expect list of tomorrow's tasks
- 3.3.3: `какие задачи на понедельник` → expect list of Monday's tasks
- 3.3.4: `что запланировано на пятницу` → expect list of Friday's tasks
- 3.3.5: `список задач на эту неделю` → expect week list
- 3.3.6: `покажи все задачи` → expect today's tasks (default)

For each: verify response contains task names created in earlier sections.

---

## Task 8: Execute Section 3.4 - Task Filtering (Tests 3.4.1-3.4.3)

**Files:**
- Test spec: `docs/CHROME_TESTING.md` lines 136-143
- Result tracking: Update `docs/test-results/2026-03-07-filtering.md`

**Commands to execute:**
- 3.4.1: `покажи задачи на эту неделю с высоким приоритетом`
- 3.4.2: `какие срочные задачи на завтра`
- 3.4.3: `задачи с низким приоритетом на следующую неделю`

Verify filtered results match expected criteria.

---

## Task 9: Execute Section 3.5 - Overdue Tasks (Tests 3.5.1-3.5.4)

**Files:**
- Test spec: `docs/CHROME_TESTING.md` lines 146-154
- Result tracking: Update `docs/test-results/2026-03-07-overdue.md`

**Commands to execute:**
- 3.5.1: `какие задачи просрочены` → expect list or "Просроченных задач нет"
- 3.5.2: `покажи просроченные задачи` → same
- 3.5.3: `что я пропустил` → same
- 3.5.4: `что я просрочил` → same

Record whether list is empty or contains items.

---

## Task 10: Execute Section 3.6 - Complete Task (Tests 3.6.1-3.6.5)

**Files:**
- Test spec: `docs/CHROME_TESTING.md` lines 157-166
- Result tracking: Update `docs/test-results/2026-03-07-complete.md`

**Commands to execute (mark created tasks as done):**
- 3.6.1: `отметь задачу тестирование купить хлеб` → expect "выполнена"
- 3.6.2: `завершить задачу тестирование написать отчёр` → expect "выполнена"
- 3.6.3: `готово тестирование позвонить маме` → expect "выполнена"
- 3.6.4: `сделал тестирование отправить письмо` → expect "выполнена"
- 3.6.5: `закрой задачу тестирование оплатить счёт` → expect "выполнена"

For each: verify correct task was marked complete.

---

## Task 11: Execute Section 3.7 - Search Tasks (Tests 3.7.1-3.7.4)

**Files:**
- Test spec: `docs/CHROME_TESTING.md` lines 169-177
- Result tracking: Update `docs/test-results/2026-03-07-search.md`

**Commands to execute:**
- 3.7.1: `найди задачу про тестирование` or `найди задачу про отчёт`
- 3.7.2: `поиск задачи тестирование молоко`
- 3.7.3: `найди задачу тестирование купить`
- 3.7.4: `найди задачу про макбук` → Known issue: transliteration (MacBook won't match)

Record search results.

---

## Task 12: Execute Section 3.8 - Edit Task (Tests 3.8.1-3.8.16)

**Files:**
- Test spec: `docs/CHROME_TESTING.md` lines 180-233
- Result tracking: Update `docs/test-results/2026-03-07-edit.md`

**Subtask 12a: Date & Priority (3.8.1-3.8.3)**
- 3.8.1: `перенеси задачу тестирование купить хлеб на завтра`
- 3.8.2: `поменяй приоритет задачи тестирование отчёт на высокий`
- 3.8.3: `перенеси задачу тестирование встреча на понедельник`

**Subtask 12b: Rename (3.8.4)**
- 3.8.4: `переименуй задачу тестирование купить хлеб в купить батон`

**Subtask 12c: Move between projects (3.8.5-3.8.6)**
- 3.8.5: `перемести задачу тестирование отчёт в проект Работа`
- 3.8.6: `перекинь задачу тестирование покупки в список Дом`

**Subtask 12d: Change recurrence (3.8.7-3.8.9)**
- 3.8.7: `поменяй повторение задачи тестирование зарядка на каждый день`
- 3.8.8: `измени повтор задачи тестирование уборка на каждую неделю`
- 3.8.9: `поменяй повторение задачи тестирование оплата на каждое 15 число`

**Subtask 12e: Remove recurrence (3.8.10-3.8.11)**
- 3.8.10: `убери повторение задачи тестирование зарядка`
- 3.8.11: `отмени повтор задачи тестирование уборка`

**Subtask 12f: Change reminder (3.8.12-3.8.14)**
- 3.8.12: `поменяй напоминание задачи тестирование встреча за 30 минут`
- 3.8.13: `измени напоминание задачи тестирование отчёт за час`
- 3.8.14: `поставь напоминание задачи тестирование покупки за 1 день`

**Subtask 12g: Remove reminder (3.8.15-3.8.16)**
- 3.8.15: `убери напоминание задачи тестирование встреча`
- 3.8.16: `отмени напоминание задачи тестирование отчёт`

Record all results with pass/fail status.

---

## Task 13: Execute Section 3.9 - Delete Task (Tests 3.9.1-3.9.4)

**Files:**
- Test spec: `docs/CHROME_TESTING.md` lines 235-245
- Result tracking: Update `docs/test-results/2026-03-07-delete.md`

**Note:** Tests 3.9.1-3.9.4 require two-step dialog (request confirmation, then confirm/deny).

**Step 1: Test 3.9.1 - Delete with confirmation**
- Input: `удали задачу тестирование купить батон`
- Wait for confirmation request
- Input: `да`
- Expected: "Задача удалена"
- Record: Status

**Step 2: Test 3.9.2 - Delete with denial**
- Input: `удали задачу тестирование [name]`
- Wait for confirmation request
- Input: `нет`
- Expected: "Удаление отменено"
- Record: Status

**Step 3: Test 3.9.3 - Confirmation request**
- Input: `убери задачу тестирование [name]`
- Expected: Confirmation request appears
- Record: Status

**Step 4: Test 3.9.4 - Multiple invalid responses (3x "не знаю")**
- Input: `удали задачу тестирование [name]`
- Input: `не знаю` (3 times)
- Expected: After 3rd response, deletion cancelled
- Record: Status

---

## Task 14: Execute Section 3.10 - Recurring Tasks via "напоминай" (Tests 3.10.1-3.10.8)

**Files:**
- Test spec: `docs/CHROME_TESTING.md` lines 248-260
- Result tracking: Update `docs/test-results/2026-03-07-remind.md`

**Commands to execute:**
- 3.10.1: `напоминай каждый понедельник тестирование проверить отчёт`
- 3.10.2: `напоминай каждый день тестирование пить воду`
- 3.10.3: `напоминай ежедневно тестирование делать зарядку`
- 3.10.4: `напоминай еженедельно тестирование проверить почту`
- 3.10.5: `напоминай ежемесячно тестирование оплатить аренду`
- 3.10.6: `напоминай каждые 2 дня тестирование поливать цветы`
- 3.10.7: `напоминай каждое 15 число тестирование оплатить счёт`
- 3.10.8: `повторяй каждую среду тестирование уборка`

Expected pattern: "Задача создана, [frequency]"

---

## Task 15: Execute Section 3.11 - Add Reminder to Existing Task (Tests 3.11.1-3.11.5)

**Files:**
- Test spec: `docs/CHROME_TESTING.md` lines 263-272
- Result tracking: Update `docs/test-results/2026-03-07-add-reminder.md`

**Commands to execute:**
- 3.11.1: `напомни о задаче тестирование встреча за 30 минут`
- 3.11.2: `напомни про задачу тестирование отчёт за час`
- 3.11.3: `напомни о задаче тестирование покупки за 1 день`
- 3.11.4: `поставь напоминание о задаче тестирование оплата за 2 часа`
- 3.11.5: `напомни о задаче тестирование врач за день`

Expected: "Напоминание добавлено"

---

## Task 16: Execute Section 3.12 - Subtasks (Tests 3.12.1-3.12.4)

**Files:**
- Test spec: `docs/CHROME_TESTING.md` lines 275-283
- Result tracking: Update `docs/test-results/2026-03-07-subtasks.md`

**Commands to execute:**
- 3.12.1: `добавь подзадачу тестирование купить муку к задаче тестирование испечь торт`
- 3.12.2: `добавь подзадачу тестирование написать введение к задаче тестирование подготовить отчёт`
- 3.12.3: `покажи подзадачи задачи тестирование испечь торт`
- 3.12.4: `какие подзадачи у задачи тестирование отчёт`

Expected: Subtasks created and listed successfully.

---

## Task 17: Execute Section 3.13 - Checklists (Tests 3.13.1-3.13.6)

**Files:**
- Test spec: `docs/CHROME_TESTING.md` lines 286-296
- Result tracking: Update `docs/test-results/2026-03-07-checklists.md`

**Commands to execute:**
- 3.13.1: `добавь пункт тестирование молоко в чеклист задачи тестирование покупки`
- 3.13.2: `добавь пункт тестирование купить мыло в чеклист задачи тестирование сменить полотенца`
- 3.13.3: `покажи чеклист задачи тестирование покупки`
- 3.13.4: `что в чеклисте задачи тестирование покупки`
- 3.13.5: `отметь пункт тестирование молоко в чеклисте задачи тестирование покупки`
- 3.13.6: `удали пункт тестирование молоко из чеклиста задачи тестирование покупки`

Expected: Checklist items added, viewed, marked, deleted successfully.

---

## Task 18: Execute Section 3.14 - Projects (Tests 3.14.1-3.14.3)

**Files:**
- Test spec: `docs/CHROME_TESTING.md` lines 299-306
- Result tracking: Update `docs/test-results/2026-03-07-projects.md`

**Commands to execute:**
- 3.14.1: `покажи мои проекты` → list projects
- 3.14.2: `задачи в проекте тестирование работа` → list tasks in project
- 3.14.3: `создай проект тестирование учёба` → create new project

Expected: Projects viewed, filtered, created successfully.

---

## Task 19: Execute Section 3.15 - Briefings (Tests 3.15.1-3.15.2)

**Files:**
- Test spec: `docs/CHROME_TESTING.md` lines 309-315
- Result tracking: Update `docs/test-results/2026-03-07-briefings.md`

**Commands to execute:**
- 3.15.1: `доброе утро` → morning briefing
- 3.15.2: `вечерний брифинг` → evening briefing

Expected: Briefing responses with task summaries.

---

## Task 20: Execute Section 3.16 - Service Commands (Tests 3.16.1-3.16.5)

**Files:**
- Test spec: `docs/CHROME_TESTING.md` lines 318-327
- Result tracking: Update `docs/test-results/2026-03-07-service.md`

**Commands to execute:**
- 3.16.1: `помощь` → command list
- 3.16.2: `что ты умеешь` → command list
- 3.16.3: `помоги` → command list
- 3.16.4: `до свидания` → goodbye (known bug: may not work in text mode)
- 3.16.5: `пока` → goodbye

Expected: Service command responses appear.

---

## Task 21: Execute Section 3.17 - Fallback / Unknown Commands (Tests 3.17.1-3.17.3)

**Files:**
- Test spec: `docs/CHROME_TESTING.md` lines 330-337
- Result tracking: Update `docs/test-results/2026-03-07-fallback.md`

**Commands to execute:**
- 3.17.1: `расскажи анекдот` → fallback response
- 3.17.2: `какая погода` → fallback response
- 3.17.3: `алиса` → fallback response

Expected: "Команда не распознана..." or similar fallback message.

---

## Task 22: Execute Section 3.18 - Edge Cases (Tests 3.18.1-3.18.7)

**Files:**
- Test spec: `docs/CHROME_TESTING.md` lines 340-368
- Result tracking: Update `docs/test-results/2026-03-07-edge-cases.md`

**Subtask 22a: Long names (3.18.1-3.18.2)**
- 3.18.1: `создай задачу тестирование подготовить подробный план действий на следующий квартал по модернизации инфраструктуры` → check if truncated
- 3.18.2: `отметь задачу тестирование подготовить подробный план действий на следующий квартал` → fuzzy match test

**Subtask 22b: Numbers in names (3.18.3-3.18.4)**
- 3.18.3: `создай задачу тестирование купить 3 литра молока` → number as part of name
- 3.18.4: `найди задачу про тестирование 10 страницу` → number in search

**Subtask 22c: Empty list (3.18.5-3.18.6)**
- 3.18.5: `что на сегодня` (check for empty list message) → expect "На сегодня задач нет. Можно отдыхать!"
- 3.18.6: `какие задачи просрочены` (no overdue) → expect "Просроченных задач нет. Отличная работа!"

**Subtask 22g: Similar names (3.18.7)**
- 3.18.7: `отметь задачу тестирование купить` (with multiple "купить" tasks) → check best match logic

---

## Task 23: Execute Section 5 - Known Bugs / Regression Tests (Tests 5.1-5.7)

**Files:**
- Test spec: `docs/CHROME_TESTING.md` lines 371-384
- Result tracking: Update `docs/test-results/2026-03-07-regression.md`

**Regression tests (document current behavior, known issues):**
- 5.1: `перенеси задачу тестирование сменить полотенца на завтра` → Known: `.+` in grammar absorbs "на завтра"
- 5.2: `добавь подзадачу тестирование купить средство к задаче тестирование сменить полотенца` → Known: create_task intercepts
- 5.3: `добавь пункт тестирование купить мыло в чеклист задачи тестирование сменить полотенца` → Known: create_task intercepts
- 5.4: `отметь пункт тестирование поменять полотенца в чеклисте задачи тестирование сменить полотенца` → Known: complete_task intercepts
- 5.5: `удали пункт тестирование купить мыло из чеклиста задачи тестирование сменить полотенца` → Known: delete_task intercepts
- 5.6: `до свидания` → Known: doesn't work in text mode
- 5.7: `найди задачу про тестирование макбук` → Known: no Cyrillic↔Latin transliteration

For each: document whether bug still exists or has been fixed.

---

## Task 24: Cleanup and Summarize Results

**Files:**
- Create: `docs/test-results/2026-03-07-SUMMARY.md`
- Update: `docs/CHROME_TESTING.md` section 7 (Test Report Template)

**Step 1: Aggregate all test results**

Compile counts:
- Total tests executed: 116
- Total tests passed: [count]
- Total tests with warnings: [count]
- Total tests failed: [count]

**Step 2: Fill in summary table**

```markdown
## Результаты тестирования 2026-03-07

| Раздел | Всего | OK | WARN | FAIL | Заметки |
|--------|-------|----|------|------|---------|
| 3.1 Приветствие | 1 | [count] | [count] | [count] | [notes] |
| 3.2 Создание задач | 23 | [count] | [count] | [count] | [notes] |
| 3.3 Просмотр задач | 6 | [count] | [count] | [count] | [notes] |
... (all sections)
| **ИТОГО** | **116** | [count] | [count] | [count] | |
```

**Step 3: Document blockers and known issues**

For each FAIL or WARN, provide:
- Section and test number
- Command/expected vs actual
- Root cause (if identified)
- Severity (critical/high/medium/low)
- Reproducibility (always/sometimes/rare)

**Step 4: Cleanup test tasks**

Search for all tasks with "тестирование" in name using: `найди задачу тестирование`
Then issue: `удали задачу тестирование [name]` for each found (with `да` confirmation)

**Step 5: Commit test results**

```bash
git add docs/test-results/2026-03-07-*.md
git add docs/CHROME_TESTING.md
git commit -m "test: полное тестирование навыка через Chrome (116 тестов)"
```

---

## Execution Notes

- **Duration estimate:** 2-3 hours (116 tests × ~1-2 min per test setup + response read + record)
- **Browser stability:** If tab becomes unresponsive, use tabs_context_mcp to verify tab ID and refresh if needed
- **Test task cleanup:** IMPORTANT: Use "тестирование" keyword convention to easily identify and remove test tasks after session
- **Screenshot intervals:** Take screenshots at: session start (Task 1), after each major section, and final state before cleanup
- **Known issues tracking:** Section 5 documents known bugs — during testing, determine if any have been fixed
- **Parallel execution:** Tests are **sequential** by design — they build on created tasks; do not attempt to parallelize

---
