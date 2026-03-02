"""Intent handlers for Alice skill."""

from __future__ import annotations

import asyncio
import datetime
import logging
import re
import time
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from aliceio.types import Directives, Message, Response, Update

if TYPE_CHECKING:
    from aliceio.fsm.context import FSMContext

from alice_ticktick.dialogs import responses as txt
from alice_ticktick.dialogs.intents import (
    extract_add_checklist_item_slots,
    extract_add_subtask_slots,
    extract_check_item_slots,
    extract_complete_task_slots,
    extract_create_task_slots,
    extract_delete_checklist_item_slots,
    extract_delete_task_slots,
    extract_edit_task_slots,
    extract_list_subtasks_slots,
    extract_list_tasks_slots,
    extract_search_task_slots,
    extract_show_checklist_slots,
)
from alice_ticktick.dialogs.nlp import (
    build_rrule,
    build_trigger,
    find_best_match,
    find_matches,
    format_recurrence,
    format_reminder,
    parse_priority,
    parse_yandex_datetime,
)
from alice_ticktick.dialogs.nlp.date_parser import ExtractedDates, extract_dates_from_nlu
from alice_ticktick.dialogs.states import DeleteTaskStates
from alice_ticktick.ticktick.client import TickTickClient
from alice_ticktick.ticktick.models import Project, Task, TaskCreate, TaskPriority, TaskUpdate

logger = logging.getLogger(__name__)

ALICE_RESPONSE_MAX_LENGTH = 1024

# Стоп-слова: NLU захватывает слово "задачу" как task_name при "создай задачу"
_TASK_NAME_STOPWORDS = frozenset(
    {
        "задачу",
        "задача",
        "задачи",
        "задаче",
        "напоминание",
        "напоминания",
    }
)

_REMINDER_SUFFIX_RE = re.compile(
    r"\s+с\s+напоминанием\s+за\s+(?:\d+\s+)?(?:минуту|минуты|минут|час|часа|часов|день|дня|дней)\s*$",
    re.IGNORECASE,
)

_FIXED_RECURRENCE_TOKENS = frozenset(
    {
        "ежедневно",
        "еженедельно",
        "ежемесячно",
        "ежегодно",
    }
)


def _infer_rec_freq_from_tokens(
    rec_freq: str | None,
    tokens: list[str] | None,
) -> str | None:
    """Если rec_freq не извлечён NLU, попробовать найти в токенах."""
    if rec_freq is not None:
        return rec_freq
    if not tokens:
        return None
    for token in tokens:
        if token.lower() in _FIXED_RECURRENCE_TOKENS:
            return token.lower()
    return None


def _auth_required_response(event_update: Update | None = None) -> Response:
    """Return a response that initiates Account Linking if supported."""
    supports_linking = False
    if event_update and event_update.meta and event_update.meta.interfaces:
        supports_linking = event_update.meta.interfaces.account_linking is not None
    if supports_linking:
        return Response(
            text=txt.AUTH_REQUIRED_LINKING,
            directives=Directives(start_account_linking={}),
        )
    return Response(text=txt.AUTH_REQUIRED_NO_LINKING)


def _get_user_tz(event_update: Update | None) -> ZoneInfo:
    """Extract user timezone from Alice event, default to UTC."""
    if event_update and event_update.meta and event_update.meta.timezone:
        try:
            return ZoneInfo(event_update.meta.timezone)
        except (KeyError, ValueError):
            pass
    return ZoneInfo("UTC")


def _to_user_date(dt: datetime.datetime, tz: ZoneInfo) -> datetime.date:
    """Convert a UTC datetime to user-local date."""
    return dt.astimezone(tz).date()


def _format_date(d: datetime.date | datetime.datetime, tz: ZoneInfo | None = None) -> str:
    """Format a date for display in Russian."""
    if tz is None:
        tz = ZoneInfo("UTC")
    today = datetime.datetime.now(tz=tz).date()
    day = _to_user_date(d, tz) if isinstance(d, datetime.datetime) else d

    if day == today:
        return "сегодня"
    if day == today + datetime.timedelta(days=1):
        return "завтра"
    if day == today - datetime.timedelta(days=1):
        return "вчера"
    return day.strftime("%d.%m.%Y")


def _format_task_line(idx: int, task: Task) -> str:
    """Format a single task for listing."""
    priority_label = {5: " [!]", 3: " [~]", 1: " [.]"}.get(task.priority, "")
    return f"{idx}. {task.title}{priority_label}"


def _truncate_response(text: str) -> str:
    """Truncate response to Alice's 1024-char limit."""
    if len(text) <= ALICE_RESPONSE_MAX_LENGTH:
        return text
    return text[: ALICE_RESPONSE_MAX_LENGTH - 1] + "…"


_cached_projects: list[Project] | None = None
_cached_projects_ts: float = 0.0
_PROJECT_CACHE_TTL = 60.0  # seconds

_cached_tasks: list[Task] | None = None
_cached_tasks_ts: float = 0.0
_TASK_CACHE_TTL = 15.0  # seconds — short-lived cache for sequential commands


def _reset_project_cache() -> None:
    """Reset all caches (for testing)."""
    global _cached_projects, _cached_projects_ts
    global _cached_tasks, _cached_tasks_ts
    _cached_projects = None
    _cached_projects_ts = 0.0
    _cached_tasks = None
    _cached_tasks_ts = 0.0


def _invalidate_task_cache() -> None:
    """Invalidate task cache after mutations (complete, create, delete, etc.)."""
    global _cached_tasks, _cached_tasks_ts
    _cached_tasks = None
    _cached_tasks_ts = 0.0


_GATHER_TIMEOUT = 4.0  # seconds — total budget for fetching all tasks


async def _get_cached_projects(client: TickTickClient) -> list[Project]:
    """Return cached project list, fetching from API if stale."""
    global _cached_projects, _cached_projects_ts

    now = time.monotonic()
    if _cached_projects is not None and now - _cached_projects_ts < _PROJECT_CACHE_TTL:
        return list(_cached_projects)

    projects = await client.get_projects()
    _cached_projects = projects
    _cached_projects_ts = time.monotonic()
    return projects


def _find_project_by_name(projects: list[Project], name: str) -> Project | None:
    """Find a project by fuzzy name match."""
    if not projects or not name:
        return None
    project_names = [p.name for p in projects]
    result = find_best_match(name, project_names)
    if result is None:
        return None
    _matched_name, idx = result
    return projects[idx]


async def _gather_all_tasks(client: TickTickClient) -> list[Task]:
    """Fetch tasks from all projects and inbox in parallel.

    Uses a short-lived task cache (15s) to avoid redundant API calls
    for sequential commands (e.g., "что на сегодня" → "закрой задачу").
    Also caches project list (60s) and applies a total time budget.
    """
    global _cached_tasks, _cached_tasks_ts

    now = time.monotonic()
    if _cached_tasks is not None and now - _cached_tasks_ts < _TASK_CACHE_TTL:
        age = now - _cached_tasks_ts
        logger.info("Using cached tasks (%d), age %.1fs", len(_cached_tasks), age)
        return list(_cached_tasks)

    all_tasks = await asyncio.wait_for(_gather_all_tasks_impl(client), timeout=_GATHER_TIMEOUT)
    _cached_tasks = all_tasks
    _cached_tasks_ts = time.monotonic()
    return all_tasks


async def _gather_all_tasks_impl(client: TickTickClient) -> list[Task]:
    global _cached_projects, _cached_projects_ts

    t0 = time.monotonic()

    now = time.monotonic()
    if _cached_projects is not None and now - _cached_projects_ts < _PROJECT_CACHE_TTL:
        projects = _cached_projects
        age = now - _cached_projects_ts
        logger.info("Using cached projects (%d), age %.1fs", len(projects), age)
    else:
        projects_result, inbox_tasks = await asyncio.gather(
            client.get_projects(),
            client.get_inbox_tasks(),
        )
        projects = projects_result
        _cached_projects = projects
        _cached_projects_ts = time.monotonic()
        elapsed = (time.monotonic() - t0) * 1000
        logger.info("Fetched projects (%d) + inbox in %.0fms", len(projects), elapsed)

        if projects:
            project_task_lists = await asyncio.gather(
                *(client.get_tasks(p.id) for p in projects),
            )
            all_tasks = list(inbox_tasks)
            for tasks in project_task_lists:
                all_tasks.extend(tasks)
        else:
            all_tasks = list(inbox_tasks)

        elapsed = (time.monotonic() - t0) * 1000
        logger.info("Total _gather_all_tasks: %.0fms, %d tasks", elapsed, len(all_tasks))
        return all_tasks

    # Warm path: projects cached, fetch inbox + project tasks all in parallel
    task_lists = await asyncio.gather(
        client.get_inbox_tasks(),
        *(client.get_tasks(p.id) for p in projects),
    )
    all_tasks = [t for tasks in task_lists for t in tasks]
    elapsed = (time.monotonic() - t0) * 1000
    logger.info("Total _gather_all_tasks (cached): %.0fms, %d tasks", elapsed, len(all_tasks))
    return all_tasks


def _get_access_token(message: Message) -> str | None:
    """Extract TickTick access token from user session."""
    if message.user is None:
        return None
    return message.user.access_token


def _format_ticktick_dt(dt: datetime.datetime) -> str:
    """Format datetime for TickTick API with proper timezone offset."""
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000%z")


def _extract_nlu_dates(message: Message, tz: ZoneInfo) -> ExtractedDates | None:
    """Try to extract dates from NLU entities (hybrid approach)."""
    if not message.nlu:
        return None
    # Count command tokens: "создай задачу" = 2, "создай" = 1, etc.
    # The grammar starts matching at token 0 (command word) and optional token 1 ("задачу")
    # We check token 1 to decide command_token_count
    tokens = message.nlu.tokens
    filler = {"задачу", "задачи", "напоминание", "напоминания", "встречу"}
    cmd_count = 1
    if len(tokens) > 1 and tokens[1] in filler:
        cmd_count = 2
    now = datetime.datetime.now(tz=tz)
    result = extract_dates_from_nlu(message.nlu, command_token_count=cmd_count, now=now)
    if result.start_date is None:
        return None
    return result


async def handle_welcome(message: Message) -> Response:
    """Handle new session greeting."""
    return Response(text=txt.WELCOME)


async def handle_help(message: Message) -> Response:
    """Handle help request."""
    return Response(text=txt.HELP)


async def handle_goodbye(message: Message) -> Response:
    """Handle goodbye / session end."""
    return Response(text=txt.GOODBYE, end_session=True)


async def handle_create_task(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
    event_update: Update | None = None,
) -> Response:
    """Handle create_task intent."""
    access_token = _get_access_token(message)
    if access_token is None:
        return _auth_required_response(event_update)

    slots = extract_create_task_slots(intent_data)

    if not slots.task_name:
        return Response(text=txt.TASK_NAME_REQUIRED)

    # Если task_name — это только стоп-слово, переспросить
    if slots.task_name.lower().strip() in _TASK_NAME_STOPWORDS:
        return Response(text=txt.TASK_NAME_REQUIRED)

    user_tz = _get_user_tz(event_update)
    start_date_str: str | None = None
    due_date_str: str | None = None
    is_all_day: bool | None = None
    date_display: str | None = None
    task_name = slots.task_name

    # Обрезать суффикс "с напоминанием за N единиц" из названия задачи
    if slots.reminder_unit is not None:
        task_name = _REMINDER_SUFFIX_RE.sub("", task_name).strip()
        if not task_name:
            return Response(text=txt.TASK_NAME_REQUIRED)

    # Hybrid approach: try NLU entities first for better date extraction,
    # fall back to grammar slots.
    nlu_dates = _extract_nlu_dates(message, user_tz)
    if nlu_dates and nlu_dates.start_date:
        # NLU entities found — use them and the cleaned task name
        if nlu_dates.task_name:
            task_name = nlu_dates.task_name

        parsed_start = nlu_dates.start_date
        date_display = _format_date(parsed_start, user_tz)

        if isinstance(parsed_start, datetime.datetime):
            start_date_str = _format_ticktick_dt(parsed_start)
            is_all_day = False
        else:
            dt_s = datetime.datetime.combine(parsed_start, datetime.time(), tzinfo=user_tz)
            start_date_str = _format_ticktick_dt(dt_s)
            is_all_day = True

        if nlu_dates.end_date:
            # Time range: startDate and dueDate are different
            parsed_end = nlu_dates.end_date
            if isinstance(parsed_end, datetime.datetime):
                due_date_str = _format_ticktick_dt(parsed_end)
            else:
                dt_e = datetime.datetime.combine(parsed_end, datetime.time(), tzinfo=user_tz)
                due_date_str = _format_ticktick_dt(dt_e)
        else:
            # Single date: only dueDate (no startDate for simple tasks)
            due_date_str = start_date_str
            start_date_str = None
    elif slots.date:
        # Fallback: grammar-based date extraction
        now_local = datetime.datetime.now(tz=user_tz)
        try:
            parsed_date = parse_yandex_datetime(slots.date, now=now_local)
            if isinstance(parsed_date, datetime.datetime):
                due_date_str = _format_ticktick_dt(parsed_date)
                is_all_day = False
            else:
                dt = datetime.datetime.combine(parsed_date, datetime.time(), tzinfo=user_tz)
                due_date_str = _format_ticktick_dt(dt)
                is_all_day = True
            date_display = _format_date(parsed_date, user_tz)
        except ValueError:
            pass

    # Parse optional priority
    priority_raw = parse_priority(slots.priority) or 0
    priority_value = TaskPriority(priority_raw)

    # Parse recurrence — fallback: проверить токены, если NLU не заполнил rec_freq
    _tokens = message.nlu.tokens if message.nlu else None
    effective_rec_freq = _infer_rec_freq_from_tokens(slots.rec_freq, _tokens)
    repeat_flag = build_rrule(
        rec_freq=effective_rec_freq,
        rec_interval=slots.rec_interval,
        rec_monthday=slots.rec_monthday,
    )

    # Parse reminder
    reminder_trigger = build_trigger(slots.reminder_value, slots.reminder_unit)
    reminders_list: list[str] | None = [reminder_trigger] if reminder_trigger else None

    factory = ticktick_client_factory or TickTickClient
    project_id: str | None = None
    project_name_display: str | None = None
    try:
        async with factory(access_token) as client:
            if slots.project_name:
                projects = await _get_cached_projects(client)
                project = _find_project_by_name(projects, slots.project_name)
                if project is None:
                    names = ", ".join(p.name for p in projects) if projects else "—"
                    return Response(
                        text=txt.PROJECT_NOT_FOUND.format(name=slots.project_name, projects=names)
                    )
                project_id = project.id
                project_name_display = project.name

            payload = TaskCreate(
                title=task_name,
                projectId=project_id,
                priority=priority_value,
                startDate=start_date_str,
                dueDate=due_date_str,
                isAllDay=is_all_day,
                repeatFlag=repeat_flag,
                reminders=reminders_list,
            )
            await client.create_task(payload)
            _invalidate_task_cache()
    except Exception:
        logger.exception("Failed to create task")
        return Response(text=txt.CREATE_ERROR)

    # Build response with recurrence/reminder info
    rec_display = format_recurrence(repeat_flag)
    rem_display = format_reminder(reminder_trigger)

    if rec_display and rem_display:
        return Response(
            text=txt.TASK_CREATED_RECURRING_WITH_REMINDER.format(
                name=task_name, recurrence=rec_display, reminder=rem_display
            )
        )
    if rec_display:
        return Response(
            text=txt.TASK_CREATED_RECURRING.format(name=task_name, recurrence=rec_display)
        )
    if rem_display:
        return Response(
            text=txt.TASK_CREATED_WITH_REMINDER.format(name=task_name, reminder=rem_display)
        )

    if project_name_display:
        if date_display:
            return Response(
                text=txt.TASK_CREATED_IN_PROJECT_WITH_DATE.format(
                    name=task_name, project=project_name_display, date=date_display
                )
            )
        return Response(
            text=txt.TASK_CREATED_IN_PROJECT.format(name=task_name, project=project_name_display)
        )
    if date_display:
        return Response(
            text=txt.TASK_CREATED_WITH_DATE.format(
                name=task_name,
                date=date_display,
            )
        )
    return Response(text=txt.TASK_CREATED.format(name=slots.task_name))


async def handle_create_recurring_task(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
    event_update: Update | None = None,
) -> Response:
    """Handle create_recurring_task intent ('напоминай каждый...')."""
    from alice_ticktick.dialogs.intents import extract_create_recurring_task_slots

    slots = extract_create_recurring_task_slots(intent_data)

    # Delegate to create_task with recurrence slots mapped
    create_intent_data: dict[str, Any] = {"slots": {}}
    if slots.task_name:
        create_intent_data["slots"]["task_name"] = {"value": slots.task_name}
    if slots.rec_freq:
        create_intent_data["slots"]["rec_freq"] = {"value": slots.rec_freq}
    if slots.rec_interval is not None:
        create_intent_data["slots"]["rec_interval"] = {"value": slots.rec_interval}
    if slots.rec_monthday is not None:
        create_intent_data["slots"]["rec_monthday"] = {"value": slots.rec_monthday}

    return await handle_create_task(
        message,
        create_intent_data,
        ticktick_client_factory=ticktick_client_factory,
        event_update=event_update,
    )


async def handle_add_reminder(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
    event_update: Update | None = None,
) -> Response:
    """Handle add_reminder intent ('напомни o задаче X за Y')."""
    from alice_ticktick.dialogs.intents import extract_add_reminder_slots

    access_token = _get_access_token(message)
    if access_token is None:
        return _auth_required_response(event_update)

    slots = extract_add_reminder_slots(intent_data)

    if not slots.task_name:
        return Response(text=txt.REMINDER_TASK_REQUIRED)

    if slots.reminder_unit is None:
        return Response(text=txt.REMINDER_VALUE_REQUIRED)

    trigger = build_trigger(slots.reminder_value, slots.reminder_unit)
    if trigger is None:
        return Response(text=txt.REMINDER_PARSE_ERROR)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            all_tasks = await _gather_all_tasks(client)

            active_tasks = [t for t in all_tasks if t.status == 0]
            if not active_tasks:
                return Response(text=txt.TASK_NOT_FOUND.format(name=slots.task_name))

            titles = [t.title for t in active_tasks]
            match_result = find_best_match(slots.task_name, titles)
            if match_result is None:
                return Response(text=txt.TASK_NOT_FOUND.format(name=slots.task_name))

            best_match, match_idx = match_result
            matched_task = active_tasks[match_idx]

            # Merge with existing reminders
            existing_reminders = list(matched_task.reminders)
            if trigger not in existing_reminders:
                existing_reminders.append(trigger)

            payload = TaskUpdate(
                id=matched_task.id,
                projectId=matched_task.project_id,
                reminders=existing_reminders,
            )
            await client.update_task(payload)
            _invalidate_task_cache()

            rem_display = format_reminder(trigger) or ""
            return Response(text=txt.REMINDER_ADDED.format(reminder=rem_display, name=best_match))
    except Exception:
        logger.exception("Failed to add reminder")
        return Response(text=txt.REMINDER_ERROR)


async def handle_list_tasks(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
    event_update: Update | None = None,
) -> Response:
    """Handle list_tasks intent."""
    access_token = _get_access_token(message)
    if access_token is None:
        return _auth_required_response(event_update)

    user_tz = _get_user_tz(event_update)
    slots = extract_list_tasks_slots(intent_data)

    # Determine target date (in user timezone)
    if slots.date:
        try:
            target_date = parse_yandex_datetime(slots.date)
            if isinstance(target_date, datetime.datetime):
                target_day = target_date.date()
            else:
                target_day = target_date
        except ValueError:
            target_day = datetime.datetime.now(tz=user_tz).date()
    else:
        target_day = datetime.datetime.now(tz=user_tz).date()

    date_display = _format_date(target_day, user_tz)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            all_tasks = await _gather_all_tasks(client)
    except Exception:
        logger.exception("Failed to list tasks")
        return Response(text=txt.API_ERROR)

    # Filter tasks for the target date (convert due_date to user timezone)
    day_tasks = [
        t
        for t in all_tasks
        if t.due_date is not None
        and _to_user_date(t.due_date, user_tz) == target_day
        and t.status == 0
    ]

    if not day_tasks:
        if target_day == datetime.datetime.now(tz=user_tz).date():
            return Response(text=txt.NO_TASKS_TODAY)
        return Response(text=txt.NO_TASKS_FOR_DATE.format(date=date_display))

    count_str = txt.pluralize_tasks(len(day_tasks))
    lines = [_format_task_line(i + 1, t) for i, t in enumerate(day_tasks[:5])]
    task_list = "\n".join(lines)

    return Response(
        text=_truncate_response(
            txt.TASKS_FOR_DATE.format(
                date=date_display,
                count=count_str,
                tasks=task_list,
            )
        )
    )


async def handle_overdue_tasks(
    message: Message,
    ticktick_client_factory: type[TickTickClient] | None = None,
    event_update: Update | None = None,
) -> Response:
    """Handle overdue_tasks intent."""
    access_token = _get_access_token(message)
    if access_token is None:
        return _auth_required_response(event_update)

    user_tz = _get_user_tz(event_update)
    factory = ticktick_client_factory or TickTickClient
    today = datetime.datetime.now(tz=user_tz).date()

    try:
        async with factory(access_token) as client:
            all_tasks = await _gather_all_tasks(client)
    except Exception:
        logger.exception("Failed to get overdue tasks")
        return Response(text=txt.API_ERROR)

    overdue = [
        t
        for t in all_tasks
        if t.due_date is not None and _to_user_date(t.due_date, user_tz) < today and t.status == 0
    ]

    if not overdue:
        return Response(text=txt.NO_OVERDUE)

    count_str = txt.pluralize_tasks(len(overdue))
    lines = [_format_task_line(i + 1, t) for i, t in enumerate(overdue[:5])]
    task_list = "\n".join(lines)

    return Response(
        text=_truncate_response(
            txt.OVERDUE_TASKS_HEADER.format(
                count=count_str,
                tasks=task_list,
            )
        )
    )


async def handle_complete_task(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
    event_update: Update | None = None,
) -> Response:
    """Handle complete_task intent."""
    access_token = _get_access_token(message)
    if access_token is None:
        return _auth_required_response(event_update)

    slots = extract_complete_task_slots(intent_data)

    if not slots.task_name:
        return Response(text=txt.COMPLETE_NAME_REQUIRED)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            all_tasks = await _gather_all_tasks(client)

            # Find task by fuzzy match
            active_tasks = [t for t in all_tasks if t.status == 0]
            if not active_tasks:
                return Response(text=txt.TASK_NOT_FOUND.format(name=slots.task_name))

            titles = [t.title for t in active_tasks]
            match_result = find_best_match(slots.task_name, titles)

            if match_result is None:
                return Response(text=txt.TASK_NOT_FOUND.format(name=slots.task_name))

            best_match, match_idx = match_result
            matched_task = active_tasks[match_idx]

            await client.complete_task(matched_task.id, matched_task.project_id)
            _invalidate_task_cache()

    except Exception:
        logger.exception("Failed to complete task")
        return Response(text=txt.COMPLETE_ERROR)

    return Response(text=txt.TASK_COMPLETED.format(name=best_match))


async def handle_search_task(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
    event_update: Update | None = None,
) -> Response:
    """Handle search_task intent."""
    access_token = _get_access_token(message)
    if access_token is None:
        return _auth_required_response(event_update)

    slots = extract_search_task_slots(intent_data)

    if not slots.query:
        return Response(text=txt.SEARCH_QUERY_REQUIRED)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            all_tasks = await _gather_all_tasks(client)
    except Exception:
        logger.exception("Failed to search tasks")
        return Response(text=txt.API_ERROR)

    active_tasks = [t for t in all_tasks if t.status == 0]
    if not active_tasks:
        return Response(text=txt.SEARCH_NO_RESULTS.format(query=slots.query))

    titles = [t.title for t in active_tasks]
    matches = find_matches(slots.query, titles, limit=5)

    if not matches:
        return Response(text=txt.SEARCH_NO_RESULTS.format(query=slots.query))

    matched_tasks = [active_tasks[idx] for _title, _score, idx in matches]

    count_str = txt.pluralize_tasks(len(matched_tasks))
    lines = [_format_task_line(i + 1, t) for i, t in enumerate(matched_tasks)]
    task_list = "\n".join(lines)

    return Response(
        text=_truncate_response(txt.SEARCH_RESULTS.format(count=count_str, tasks=task_list))
    )


async def handle_edit_task(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
    event_update: Update | None = None,
) -> Response:
    """Handle edit_task intent."""
    access_token = _get_access_token(message)
    if access_token is None:
        return _auth_required_response(event_update)

    slots = extract_edit_task_slots(intent_data)

    if not slots.task_name:
        return Response(text=txt.EDIT_NAME_REQUIRED)

    # Check that at least one change is specified
    has_priority = slots.new_priority is not None
    has_name = slots.new_name is not None
    has_project = slots.new_project is not None
    has_recurrence = slots.rec_freq is not None or slots.rec_monthday is not None
    has_reminder = slots.reminder_unit is not None
    has_remove_recurrence = slots.remove_recurrence
    has_remove_reminder = slots.remove_reminder

    # Hybrid approach: try NLU entities for date extraction (grammar .+ swallows dates)
    user_tz = _get_user_tz(event_update)
    now_local = datetime.datetime.now(tz=user_tz)
    nlu_dates = _extract_nlu_dates(message, user_tz)
    nlu_has_date = nlu_dates is not None and nlu_dates.start_date is not None
    has_date = slots.new_date is not None or nlu_has_date

    if (
        not has_date
        and not has_priority
        and not has_name
        and not has_project
        and not has_recurrence
        and not has_reminder
        and not has_remove_recurrence
        and not has_remove_reminder
    ):
        return Response(text=txt.EDIT_NO_CHANGES)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            all_tasks = await _gather_all_tasks(client)
            # Pre-fetch projects if move requested (reuses same client session)
            cached_projects = await _get_cached_projects(client) if has_project else None
    except Exception:
        logger.exception("Failed to fetch tasks for edit")
        return Response(text=txt.API_ERROR)

    active_tasks = [t for t in all_tasks if t.status == 0]
    if not active_tasks:
        return Response(text=txt.TASK_NOT_FOUND.format(name=slots.task_name))

    titles = [t.title for t in active_tasks]
    match_result = find_best_match(slots.task_name, titles)

    if match_result is None:
        return Response(text=txt.TASK_NOT_FOUND.format(name=slots.task_name))

    best_match, match_idx = match_result
    matched_task = active_tasks[match_idx]

    # Build update payload
    new_title: str | None = slots.new_name if has_name else None

    new_start_date: datetime.datetime | None = None
    new_due_date: datetime.datetime | None = None
    new_is_all_day: bool | None = None

    # Prefer NLU entities for dates (grammar .+ often swallows date tokens)
    if nlu_dates and nlu_dates.start_date:
        parsed_start = nlu_dates.start_date
        if isinstance(parsed_start, datetime.datetime):
            new_start_date = parsed_start
            new_is_all_day = False
        else:
            new_start_date = datetime.datetime.combine(
                parsed_start, datetime.time(), tzinfo=user_tz
            )
            new_is_all_day = True
        if nlu_dates.end_date:
            parsed_end = nlu_dates.end_date
            if isinstance(parsed_end, datetime.datetime):
                new_due_date = parsed_end
            else:
                new_due_date = datetime.datetime.combine(
                    parsed_end, datetime.time(), tzinfo=user_tz
                )
        else:
            new_due_date = new_start_date
    elif slots.new_date:
        try:
            parsed_date = parse_yandex_datetime(slots.new_date, now=now_local)
            if isinstance(parsed_date, datetime.datetime):
                new_start_date = parsed_date
                new_is_all_day = False
            else:
                new_start_date = datetime.datetime.combine(
                    parsed_date, datetime.time(), tzinfo=user_tz
                )
                new_is_all_day = True
            if slots.new_end_date:
                parsed_end = parse_yandex_datetime(slots.new_end_date, now=now_local)
                if isinstance(parsed_end, datetime.datetime):
                    new_due_date = parsed_end
                else:
                    new_due_date = datetime.datetime.combine(
                        parsed_end, datetime.time(), tzinfo=user_tz
                    )
            else:
                new_due_date = new_start_date
        except ValueError:
            logger.warning("Failed to parse date for edit: %s", slots.new_date)

    new_priority_value: TaskPriority | None = None
    if has_priority:
        raw = parse_priority(slots.new_priority)
        if raw is not None:
            new_priority_value = TaskPriority(raw)
        else:
            logger.warning("Unrecognized priority value: %s", slots.new_priority)

    # Build recurrence
    new_repeat_flag: str | None = None
    if has_remove_recurrence:
        new_repeat_flag = ""  # empty string = remove
    elif has_recurrence:
        new_repeat_flag = build_rrule(
            rec_freq=slots.rec_freq,
            rec_interval=slots.rec_interval,
            rec_monthday=slots.rec_monthday,
        )

    # Build reminder
    new_reminders: list[str] | None = None
    if has_remove_reminder:
        new_reminders = []  # empty list = remove
    elif has_reminder:
        trigger = build_trigger(slots.reminder_value, slots.reminder_unit)
        if trigger:
            new_reminders = [trigger]

    # Resolve target project if requested
    target_project_id: str | None = None
    target_project_name: str | None = None
    same_project_name: str | None = None
    if has_project and cached_projects is not None:
        project = _find_project_by_name(cached_projects, slots.new_project)  # type: ignore[arg-type]
        if project is None:
            names = ", ".join(p.name for p in cached_projects) if cached_projects else "—"
            return Response(
                text=txt.PROJECT_NOT_FOUND.format(name=slots.new_project, projects=names)
            )
        if project.id != matched_task.project_id:
            target_project_id = project.id
            target_project_name = project.name
        else:
            same_project_name = project.name

    # Check that at least one field was successfully parsed
    if (
        new_title is None
        and new_due_date is None
        and new_priority_value is None
        and target_project_id is None
        and new_repeat_flag is None
        and new_reminders is None
    ):
        if same_project_name:
            return Response(
                text=txt.TASK_ALREADY_IN_PROJECT.format(name=best_match, project=same_project_name)
            )
        return Response(text=txt.EDIT_NO_CHANGES)

    payload = TaskUpdate(
        id=matched_task.id,
        projectId=target_project_id or matched_task.project_id,
        title=new_title,
        priority=new_priority_value,
        startDate=new_start_date,
        dueDate=new_due_date,
        isAllDay=new_is_all_day,
        repeatFlag=new_repeat_flag,
        reminders=new_reminders,
    )
    try:
        async with factory(access_token) as client:
            await client.update_task(payload)
            _invalidate_task_cache()
    except Exception:
        logger.exception("Failed to edit task")
        return Response(text=txt.EDIT_ERROR)

    # Specific messages for recurrence/reminder changes
    if has_remove_recurrence and new_repeat_flag is not None:
        return Response(text=txt.RECURRENCE_REMOVED.format(name=best_match))
    if has_remove_reminder and new_reminders is not None and not new_reminders:
        return Response(text=txt.REMINDER_REMOVED.format(name=best_match))
    if has_recurrence and new_repeat_flag:
        rec_display = format_recurrence(new_repeat_flag)
        return Response(
            text=txt.RECURRENCE_UPDATED.format(name=best_match, recurrence=rec_display)
        )
    if has_reminder and new_reminders:
        rem_display = format_reminder(new_reminders[0])
        return Response(text=txt.REMINDER_UPDATED.format(name=best_match, reminder=rem_display))

    # Only project changed → specific move message
    only_project = (
        target_project_id is not None
        and new_title is None
        and new_due_date is None
        and new_priority_value is None
    )
    if only_project and target_project_name:
        return Response(text=txt.TASK_MOVED.format(name=best_match, project=target_project_name))
    return Response(text=txt.EDIT_SUCCESS.format(name=best_match))


async def handle_delete_task(
    message: Message,
    intent_data: dict[str, Any],
    state: FSMContext,
    ticktick_client_factory: type[TickTickClient] | None = None,
    event_update: Update | None = None,
) -> Response:
    """Handle delete_task intent — start confirmation flow."""
    access_token = _get_access_token(message)
    if access_token is None:
        return _auth_required_response(event_update)

    slots = extract_delete_task_slots(intent_data)

    if not slots.task_name:
        return Response(text=txt.DELETE_NAME_REQUIRED)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            all_tasks = await _gather_all_tasks(client)
    except Exception:
        logger.exception("Failed to fetch tasks for deletion")
        return Response(text=txt.API_ERROR)

    active_tasks = [t for t in all_tasks if t.status == 0]
    if not active_tasks:
        return Response(text=txt.TASK_NOT_FOUND.format(name=slots.task_name))

    titles = [t.title for t in active_tasks]
    match_result = find_best_match(slots.task_name, titles)

    if match_result is None:
        return Response(text=txt.TASK_NOT_FOUND.format(name=slots.task_name))

    best_match, match_idx = match_result
    matched_task = active_tasks[match_idx]

    await state.set_state(DeleteTaskStates.confirm)
    await state.set_data(
        {
            "task_id": matched_task.id,
            "project_id": matched_task.project_id,
            "task_name": best_match,
        }
    )

    return Response(text=txt.DELETE_CONFIRM.format(name=best_match))


async def handle_delete_confirm(
    message: Message,
    state: FSMContext,
    ticktick_client_factory: type[TickTickClient] | None = None,
    event_update: Update | None = None,
) -> Response:
    """Handle delete confirmation (user said 'yes')."""
    access_token = _get_access_token(message)
    if access_token is None:
        await state.clear()
        return _auth_required_response(event_update)

    data = await state.get_data()
    task_id = data.get("task_id", "")
    project_id = data.get("project_id", "")
    task_name = data.get("task_name", "")

    if not task_id or not project_id or not task_name:
        logger.error(
            "Invalid FSM state data in delete confirm: task_id=%r, project_id=%r, task_name=%r",
            task_id,
            project_id,
            task_name,
        )
        await state.clear()
        return Response(text=txt.DELETE_ERROR)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            await client.delete_task(task_id, project_id)
            _invalidate_task_cache()
    except Exception:
        logger.exception("Failed to delete task")
        await state.clear()
        return Response(text=txt.DELETE_ERROR)

    await state.clear()
    return Response(text=txt.DELETE_SUCCESS.format(name=task_name))


async def handle_delete_reject(message: Message, state: FSMContext) -> Response:
    """Handle delete rejection (user said 'no')."""
    await state.clear()
    return Response(text=txt.DELETE_CANCELLED)


async def handle_add_subtask(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
    event_update: Update | None = None,
) -> Response:
    """Handle add_subtask intent."""
    access_token = _get_access_token(message)
    if access_token is None:
        return _auth_required_response(event_update)

    slots = extract_add_subtask_slots(intent_data)

    if not slots.parent_name:
        return Response(text=txt.SUBTASK_PARENT_REQUIRED)

    if not slots.subtask_name:
        return Response(text=txt.SUBTASK_NAME_REQUIRED)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            all_tasks = await _gather_all_tasks(client)

            active_tasks = [t for t in all_tasks if t.status == 0]
            if not active_tasks:
                return Response(text=txt.TASK_NOT_FOUND.format(name=slots.parent_name))

            titles = [t.title for t in active_tasks]
            match_result = find_best_match(slots.parent_name, titles)

            if match_result is None:
                return Response(text=txt.TASK_NOT_FOUND.format(name=slots.parent_name))

            best_match, match_idx = match_result
            parent_task = active_tasks[match_idx]

            payload = TaskCreate(
                title=slots.subtask_name,
                projectId=parent_task.project_id,
                parentId=parent_task.id,
            )
            await client.create_task(payload)
            _invalidate_task_cache()

    except Exception:
        logger.exception("Failed to create subtask")
        return Response(text=txt.SUBTASK_ERROR)

    return Response(text=txt.SUBTASK_CREATED.format(name=slots.subtask_name, parent=best_match))


async def handle_list_subtasks(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
    event_update: Update | None = None,
) -> Response:
    """Handle list_subtasks intent."""
    access_token = _get_access_token(message)
    if access_token is None:
        return _auth_required_response(event_update)

    slots = extract_list_subtasks_slots(intent_data)

    if not slots.task_name:
        return Response(text=txt.LIST_SUBTASKS_NAME_REQUIRED)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            all_tasks = await _gather_all_tasks(client)
    except Exception:
        logger.exception("Failed to fetch tasks for subtask listing")
        return Response(text=txt.API_ERROR)

    active_tasks = [t for t in all_tasks if t.status == 0]
    if not active_tasks:
        return Response(text=txt.TASK_NOT_FOUND.format(name=slots.task_name))

    titles = [t.title for t in active_tasks]
    match_result = find_best_match(slots.task_name, titles)

    if match_result is None:
        return Response(text=txt.TASK_NOT_FOUND.format(name=slots.task_name))

    best_match, match_idx = match_result
    parent_task = active_tasks[match_idx]

    subtasks = [t for t in all_tasks if t.parent_id == parent_task.id and t.status == 0]

    if not subtasks:
        return Response(text=txt.NO_SUBTASKS.format(name=best_match))

    count_str = txt.pluralize_tasks(len(subtasks))
    lines = [_format_task_line(i + 1, t) for i, t in enumerate(subtasks[:5])]
    task_list = "\n".join(lines)

    return Response(
        text=_truncate_response(
            txt.SUBTASKS_HEADER.format(name=best_match, count=count_str, tasks=task_list)
        )
    )


async def handle_add_checklist_item(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
    event_update: Update | None = None,
) -> Response:
    """Handle add_checklist_item intent."""
    access_token = _get_access_token(message)
    if access_token is None:
        return _auth_required_response(event_update)

    slots = extract_add_checklist_item_slots(intent_data)

    if not slots.task_name:
        return Response(text=txt.CHECKLIST_TASK_REQUIRED)

    if not slots.item_name:
        return Response(text=txt.CHECKLIST_ITEM_REQUIRED)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            all_tasks = await _gather_all_tasks(client)

            active_tasks = [t for t in all_tasks if t.status == 0]
            if not active_tasks:
                return Response(text=txt.TASK_NOT_FOUND.format(name=slots.task_name))

            titles = [t.title for t in active_tasks]
            match_result = find_best_match(slots.task_name, titles)

            if match_result is None:
                return Response(text=txt.TASK_NOT_FOUND.format(name=slots.task_name))

            best_match, match_idx = match_result
            matched_task = active_tasks[match_idx]

            # Build updated items list
            existing_items: list[dict[str, Any]] = [
                {
                    "id": item.id,
                    "title": item.title,
                    "status": item.status,
                    "sortOrder": item.sort_order,
                }
                for item in matched_task.items
            ]
            new_item: dict[str, Any] = {"title": slots.item_name, "status": 0}
            updated_items = [*existing_items, new_item]

            payload = TaskUpdate(
                id=matched_task.id,
                projectId=matched_task.project_id,
                items=updated_items,
            )
            await client.update_task(payload)
            _invalidate_task_cache()

    except Exception:
        logger.exception("Failed to add checklist item")
        return Response(text=txt.CHECKLIST_ITEM_ERROR)

    return Response(
        text=txt.CHECKLIST_ITEM_ADDED.format(
            item=slots.item_name, task=best_match, count=len(updated_items)
        )
    )


async def handle_show_checklist(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
    event_update: Update | None = None,
) -> Response:
    """Handle show_checklist intent."""
    access_token = _get_access_token(message)
    if access_token is None:
        return _auth_required_response(event_update)

    slots = extract_show_checklist_slots(intent_data)

    if not slots.task_name:
        return Response(text=txt.SHOW_CHECKLIST_NAME_REQUIRED)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            all_tasks = await _gather_all_tasks(client)
    except Exception:
        logger.exception("Failed to fetch tasks for checklist")
        return Response(text=txt.API_ERROR)

    active_tasks = [t for t in all_tasks if t.status == 0]
    if not active_tasks:
        return Response(text=txt.TASK_NOT_FOUND.format(name=slots.task_name))

    titles = [t.title for t in active_tasks]
    match_result = find_best_match(slots.task_name, titles)

    if match_result is None:
        return Response(text=txt.TASK_NOT_FOUND.format(name=slots.task_name))

    best_match, match_idx = match_result
    matched_task = active_tasks[match_idx]

    if not matched_task.items:
        return Response(text=txt.CHECKLIST_EMPTY.format(name=best_match))

    lines: list[str] = []
    for i, item in enumerate(matched_task.items, 1):
        mark = "[x]" if item.status == 1 else "[ ]"
        lines.append(f"{i}. {mark} {item.title}")
    items_text = "\n".join(lines)

    return Response(
        text=_truncate_response(txt.CHECKLIST_HEADER.format(name=best_match, items=items_text))
    )


async def handle_check_item(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
    event_update: Update | None = None,
) -> Response:
    """Handle check_item intent."""
    access_token = _get_access_token(message)
    if access_token is None:
        return _auth_required_response(event_update)

    slots = extract_check_item_slots(intent_data)

    if not slots.task_name:
        return Response(text=txt.CHECKLIST_TASK_REQUIRED)

    if not slots.item_name:
        return Response(text=txt.CHECKLIST_ITEM_REQUIRED)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            all_tasks = await _gather_all_tasks(client)

            active_tasks = [t for t in all_tasks if t.status == 0]
            if not active_tasks:
                return Response(text=txt.TASK_NOT_FOUND.format(name=slots.task_name))

            titles = [t.title for t in active_tasks]
            match_result = find_best_match(slots.task_name, titles)

            if match_result is None:
                return Response(text=txt.TASK_NOT_FOUND.format(name=slots.task_name))

            best_match, match_idx = match_result
            matched_task = active_tasks[match_idx]

            if not matched_task.items:
                return Response(
                    text=txt.CHECKLIST_ITEM_NOT_FOUND.format(item=slots.item_name, task=best_match)
                )

            item_titles = [item.title for item in matched_task.items]
            item_match = find_best_match(slots.item_name, item_titles)

            if item_match is None:
                return Response(
                    text=txt.CHECKLIST_ITEM_NOT_FOUND.format(item=slots.item_name, task=best_match)
                )

            matched_item_title, item_idx = item_match

            # Build updated items list with matched item checked
            updated_items: list[dict[str, Any]] = []
            for i, item in enumerate(matched_task.items):
                item_dict: dict[str, Any] = {
                    "id": item.id,
                    "title": item.title,
                    "status": 1 if i == item_idx else item.status,
                    "sortOrder": item.sort_order,
                }
                updated_items.append(item_dict)

            payload = TaskUpdate(
                id=matched_task.id,
                projectId=matched_task.project_id,
                items=updated_items,
            )
            await client.update_task(payload)
            _invalidate_task_cache()

    except Exception:
        logger.exception("Failed to check item")
        return Response(text=txt.CHECKLIST_CHECK_ERROR)

    return Response(text=txt.CHECKLIST_ITEM_CHECKED.format(item=matched_item_title))


async def handle_delete_checklist_item(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
    event_update: Update | None = None,
) -> Response:
    """Handle delete_checklist_item intent."""
    access_token = _get_access_token(message)
    if access_token is None:
        return _auth_required_response(event_update)

    slots = extract_delete_checklist_item_slots(intent_data)

    if not slots.task_name:
        return Response(text=txt.CHECKLIST_TASK_REQUIRED)

    if not slots.item_name:
        return Response(text=txt.CHECKLIST_ITEM_REQUIRED)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            all_tasks = await _gather_all_tasks(client)

            active_tasks = [t for t in all_tasks if t.status == 0]
            if not active_tasks:
                return Response(text=txt.TASK_NOT_FOUND.format(name=slots.task_name))

            titles = [t.title for t in active_tasks]
            match_result = find_best_match(slots.task_name, titles)

            if match_result is None:
                return Response(text=txt.TASK_NOT_FOUND.format(name=slots.task_name))

            best_match, match_idx = match_result
            matched_task = active_tasks[match_idx]

            if not matched_task.items:
                return Response(
                    text=txt.CHECKLIST_ITEM_NOT_FOUND.format(item=slots.item_name, task=best_match)
                )

            item_titles = [item.title for item in matched_task.items]
            item_match = find_best_match(slots.item_name, item_titles)

            if item_match is None:
                return Response(
                    text=txt.CHECKLIST_ITEM_NOT_FOUND.format(item=slots.item_name, task=best_match)
                )

            matched_item_title, item_idx = item_match

            # Build updated items list without the matched item
            updated_items: list[dict[str, Any]] = [
                {
                    "id": item.id,
                    "title": item.title,
                    "status": item.status,
                    "sortOrder": item.sort_order,
                }
                for i, item in enumerate(matched_task.items)
                if i != item_idx
            ]

            payload = TaskUpdate(
                id=matched_task.id,
                projectId=matched_task.project_id,
                items=updated_items,
            )
            await client.update_task(payload)
            _invalidate_task_cache()

    except Exception:
        logger.exception("Failed to delete checklist item")
        return Response(text=txt.CHECKLIST_ITEM_DELETE_ERROR)

    return Response(
        text=txt.CHECKLIST_ITEM_DELETED.format(item=matched_item_title, task=best_match)
    )


async def handle_unknown(message: Message) -> Response:
    """Handle unrecognized commands."""
    return Response(text=txt.UNKNOWN)
