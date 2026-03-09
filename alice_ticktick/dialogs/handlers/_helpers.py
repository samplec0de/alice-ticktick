"""Shared helpers for intent handlers."""

from __future__ import annotations

import asyncio
import dataclasses
import datetime
import logging
import re
import time
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from aliceio.types import Directives, Response, Update

from alice_ticktick.dialogs import responses as txt
from alice_ticktick.dialogs.nlp import DateRange, find_best_match, find_matches
from alice_ticktick.dialogs.nlp.date_parser import ExtractedDates, extract_dates_from_nlu

if TYPE_CHECKING:
    from aliceio.types import Message

    from alice_ticktick.ticktick.client import TickTickClient
    from alice_ticktick.ticktick.models import Project, Task

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

_FUZZY_CONFIRM_THRESHOLD = 85


def _is_only_stopwords(name: str) -> bool:
    """Check if task name consists only of stopwords."""
    words = name.lower().split()
    return all(w in _TASK_NAME_STOPWORDS for w in words) if words else True


@dataclasses.dataclass
class _TaskMatch:
    """Result of a successful fuzzy task match."""

    task: Task
    score: float
    name: str


async def _find_active_task(
    client: TickTickClient,
    task_name: str,
    access_token: str,
    score_threshold: int = 60,
) -> _TaskMatch | Response:
    """Find best matching active task by name. Returns _TaskMatch or error Response."""
    all_tasks = await _gather_all_tasks(client, access_token)
    active_tasks = [t for t in all_tasks if t.status == 0]
    if not active_tasks:
        return Response(text=txt.TASK_NOT_FOUND.format(name=task_name))
    titles = [t.title for t in active_tasks]
    matches = find_matches(task_name, titles, threshold=score_threshold, limit=1)
    if not matches:
        return Response(text=txt.TASK_NOT_FOUND.format(name=task_name))
    best_name, best_score, best_idx = matches[0]
    task = active_tasks[best_idx]
    return _TaskMatch(task=task, score=best_score, name=best_name)


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

_KAZH_PREFIXES = frozenset({"каждый", "каждую", "каждое", "каждые"})
_FREQ_WORDS = frozenset(
    {
        "день", "дня", "дней",
        "неделю", "недели",
        "месяц", "месяца", "месяцев",
        "год", "года", "лет",
        "понедельник", "вторник", "среду", "четверг", "пятницу", "субботу", "воскресенье",
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
    # Check for fixed recurrence tokens (ежедневно etc.)
    for token in tokens:
        if token.lower() in _FIXED_RECURRENCE_TOKENS:
            return token.lower()
    # Check for "каждый <freq>" pattern
    lower_tokens = [t.lower() for t in tokens]
    for i, token in enumerate(lower_tokens):
        if token in _KAZH_PREFIXES and i + 1 < len(lower_tokens):
            next_token = lower_tokens[i + 1]
            if next_token in _FREQ_WORDS:
                return next_token
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
    """Extract user timezone from Alice event, default to Europe/Moscow."""
    if event_update and event_update.meta and event_update.meta.timezone:
        try:
            return ZoneInfo(event_update.meta.timezone)
        except (KeyError, ValueError):
            pass
    logger.warning("No timezone in request, falling back to Europe/Moscow")
    return ZoneInfo("Europe/Moscow")


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


def _format_priority_label(priority: int) -> str:
    """Format task priority as Russian text for voice output."""
    return {5: "высокий приоритет", 3: "средний приоритет", 1: "низкий приоритет"}.get(
        priority, ""
    )


def _format_priority_short(priority: int) -> str:
    """Format priority as short adjective: 'высокий', 'средний', 'низкий' or ''."""
    label = _format_priority_label(priority)
    return label.replace(" приоритет", "") if label else ""


def _format_task_context(task: Task, tz: ZoneInfo) -> str:
    """Format task date+priority as ' (завтра, высокий приоритет)' or ''."""
    parts: list[str] = []
    if task.due_date:
        parts.append(_format_date(task.due_date, tz))
    prio = _format_priority_label(task.priority)
    if prio:
        parts.append(prio)
    if not parts:
        return ""
    return " (" + ", ".join(parts) + ")"


def _apply_task_filters(
    tasks: list[Task],
    *,
    date_filter: datetime.date | DateRange | None = None,
    priority_filter: int | None = None,
    user_tz: ZoneInfo,
) -> list[Task]:
    """Filter active tasks by date (single day or range) and/or priority."""
    result = [t for t in tasks if t.status == 0]

    if date_filter is not None:
        if isinstance(date_filter, DateRange):
            result = [
                t
                for t in result
                if t.due_date is not None
                and date_filter.date_from
                <= _to_user_date(t.due_date, user_tz)
                <= date_filter.date_to
            ]
        else:
            result = [
                t
                for t in result
                if t.due_date is not None and _to_user_date(t.due_date, user_tz) == date_filter
            ]

    if priority_filter is not None:
        result = [t for t in result if t.priority == priority_filter]

    return result


def _truncate_response(text: str, limit: int = ALICE_RESPONSE_MAX_LENGTH) -> str:
    """Truncate response to Alice's 1024-char limit, breaking at last newline."""
    if len(text) <= limit:
        return text
    truncated = text[: limit - 1]
    last_newline = truncated.rfind("\n")
    if last_newline > limit // 2:
        return truncated[:last_newline] + "\n…"
    return truncated.rstrip() + "…"


MAX_BRIEFING_TASKS = 5


# Per-user caches keyed by access_token to prevent data leaks between users.
# Value: (monotonic_timestamp, data)
_projects_cache: dict[str, tuple[float, list[Project]]] = {}
_PROJECT_CACHE_TTL = 60.0  # seconds

_tasks_cache: dict[str, tuple[float, list[Task]]] = {}
_TASK_CACHE_TTL = 15.0  # seconds — short-lived cache for sequential commands


def _reset_project_cache() -> None:
    """Reset all caches (for testing)."""
    _projects_cache.clear()
    _tasks_cache.clear()


def _invalidate_task_cache(access_token: str) -> None:
    """Invalidate task cache after mutations (complete, create, delete, etc.)."""
    _tasks_cache.pop(access_token, None)


_GATHER_TIMEOUT = 8.0  # seconds — total budget for fetching all tasks (cold start may take 5s)


async def _get_cached_projects(client: TickTickClient, access_token: str) -> list[Project]:
    """Return cached project list, fetching from API if stale."""
    entry = _projects_cache.get(access_token)
    now = time.monotonic()
    if entry is not None:
        ts, projects = entry
        if now - ts < _PROJECT_CACHE_TTL:
            return list(projects)

    all_projects = await client.get_projects()
    projects = [p for p in all_projects if not p.closed]
    _projects_cache[access_token] = (time.monotonic(), projects)
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


async def _gather_all_tasks(client: TickTickClient, access_token: str) -> list[Task]:
    """Fetch tasks from all projects and inbox in parallel.

    Uses a short-lived per-user task cache (15s) to avoid redundant API calls
    for sequential commands (e.g., "что на сегодня" -> "закрой задачу").
    Also caches project list (60s) and applies a total time budget.
    """
    entry = _tasks_cache.get(access_token)
    now = time.monotonic()
    if entry is not None:
        ts, cached_tasks = entry
        if now - ts < _TASK_CACHE_TTL:
            age = now - ts
            logger.info("Using cached tasks (%d), age %.1fs", len(cached_tasks), age)
            return list(cached_tasks)

    all_tasks = await asyncio.wait_for(
        _gather_all_tasks_impl(client, access_token), timeout=_GATHER_TIMEOUT
    )
    _tasks_cache[access_token] = (time.monotonic(), all_tasks)
    return all_tasks


async def _gather_all_tasks_impl(client: TickTickClient, access_token: str) -> list[Task]:
    t0 = time.monotonic()

    proj_entry = _projects_cache.get(access_token)
    now = time.monotonic()
    if proj_entry is not None and now - proj_entry[0] < _PROJECT_CACHE_TTL:
        projects = proj_entry[1]
        age = now - proj_entry[0]
        logger.info("Using cached projects (%d), age %.1fs", len(projects), age)
    else:
        projects_result, inbox_tasks = await asyncio.gather(
            client.get_projects(),
            client.get_inbox_tasks(),
        )
        projects = projects_result
        _projects_cache[access_token] = (time.monotonic(), projects)
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


def _build_search_response(
    best_task: Task,
    other_tasks: list[Task],
    tz: ZoneInfo,
) -> str:
    """Build budget-aware search response with details for the best match."""
    budget = ALICE_RESPONSE_MAX_LENGTH
    parts: list[str] = []

    # 1. Header for best match
    context = _format_task_context(best_task, tz)
    if other_tasks:
        header = txt.SEARCH_BEST_MATCH.format(name=best_task.title, context=context)
    else:
        header = txt.SEARCH_BEST_MATCH_SINGLE.format(name=best_task.title, context=context)
    parts.append(header)
    budget -= len(header) + 1  # +1 for \n

    # 2. Description (priority over checklist)
    if best_task.content.strip():
        desc_line = txt.SEARCH_DESCRIPTION.format(description=best_task.content.strip())
        if len(desc_line) + 1 <= budget:
            parts.append(desc_line)
            budget -= len(desc_line) + 1
        else:
            # Truncate description to fit
            available = budget - len("Описание: ") - 2  # 1 for \n, 1 for ...
            if available > 20:
                parts.append("Описание: " + best_task.content.strip()[:available] + "\u2026")
                budget = 0

    # 3. Checklist
    if best_task.items and budget > 30:
        checklist_header = "Чеклист:"
        budget -= len(checklist_header) + 1

        shown = 0
        remaining = len(best_task.items)
        for i, item in enumerate(best_task.items, 1):
            mark = "[x]" if item.status == 1 else "[ ]"
            line = f"{i}. {mark} {item.title}"
            if len(line) + 1 <= budget:
                shown += 1
                remaining -= 1
                budget -= len(line) + 1
            else:
                break

        if shown == 0:
            # No items fit -- skip checklist section entirely
            budget += len(checklist_header) + 1
        else:
            parts.append(checklist_header)
            for i, item in enumerate(best_task.items[:shown], 1):
                mark = "[x]" if item.status == 1 else "[ ]"
                parts.append(f"{i}. {mark} {item.title}")

            if remaining > 0:
                more_line = txt.SEARCH_CHECKLIST_MORE.format(count=remaining)
                if len(more_line) + 1 <= budget:
                    parts.append(more_line)
                    budget -= len(more_line) + 1

    # 4. Other matches
    if other_tasks and budget > 20:
        parts.append(txt.SEARCH_ALSO_FOUND)
        budget -= len(txt.SEARCH_ALSO_FOUND) + 1

        for i, task in enumerate(other_tasks, 2):
            line = _format_task_line(i, task)
            if len(line) + 1 <= budget:
                parts.append(line)
                budget -= len(line) + 1
            else:
                break

    return "\n".join(parts)
