"""Task-related intent handlers."""

from __future__ import annotations

import dataclasses
import datetime
import logging
from typing import TYPE_CHECKING, Any

from aliceio.types import Response, Update

from alice_ticktick.dialogs import responses as txt
from alice_ticktick.dialogs.intents import (
    extract_complete_task_slots,
    extract_delete_task_slots,
    extract_edit_task_slots,
    extract_list_tasks_slots,
    extract_search_task_slots,
)
from alice_ticktick.dialogs.nlp import (
    build_rrule,
    build_trigger,
    find_best_match,
    find_matches,
    format_recurrence,
    format_reminder,
    parse_date_range,
    parse_duration,
    parse_priority,
    parse_yandex_datetime,
)
from alice_ticktick.dialogs.states import CompleteTaskStates, DeleteTaskStates, EditTaskStates
from alice_ticktick.ticktick.client import TickTickClient, TickTickUnauthorizedError
from alice_ticktick.ticktick.models import TaskCreate, TaskPriority, TaskUpdate

from ._helpers import (
    _FUZZY_CONFIRM_THRESHOLD,
    _REMINDER_SUFFIX_RE,
    _TASK_NAME_STOPWORDS,
    _apply_task_filters,
    _auth_required_response,
    _build_search_response,
    _extract_nlu_dates,
    _find_active_task,
    _find_project_by_name,
    _format_date,
    _format_priority_label,
    _format_priority_short,
    _format_task_context,
    _format_task_line,
    _format_ticktick_dt,
    _gather_all_tasks,
    _get_access_token,
    _get_cached_projects,
    _get_user_tz,
    _infer_rec_freq_from_tokens,
    _invalidate_task_cache,
    _is_only_stopwords,
    _to_user_date,
    _truncate_response,
)

if TYPE_CHECKING:
    from aliceio.fsm.context import FSMContext
    from aliceio.types import Message

logger = logging.getLogger(__name__)


def _build_create_task_response(
    name: str,
    date_str: str | None,
    priority_str: str | None,
    project_name: str | None,
    recurrence_str: str | None,
    reminder_str: str | None,
    has_duration: bool,
    start_time_str: str | None,
    end_time_str: str | None,
) -> str:
    """Build response text for task creation based on what was set."""
    # --- Duration/range response ---
    if has_duration and start_time_str and end_time_str:
        if recurrence_str and reminder_str:
            return txt.TASK_CREATED_WITH_DURATION_RECURRING_AND_REMINDER.format(
                name=name,
                date=date_str,
                start_time=start_time_str,
                end_time=end_time_str,
                recurrence=recurrence_str,
                reminder=reminder_str,
            )
        if recurrence_str:
            return txt.TASK_CREATED_WITH_DURATION_RECURRING.format(
                name=name,
                date=date_str,
                start_time=start_time_str,
                end_time=end_time_str,
                recurrence=recurrence_str,
            )
        if reminder_str:
            return txt.TASK_CREATED_WITH_DURATION_AND_REMINDER.format(
                name=name,
                date=date_str,
                start_time=start_time_str,
                end_time=end_time_str,
                reminder=reminder_str,
            )
        if priority_str:
            return txt.TASK_CREATED_WITH_DURATION_AND_PRIORITY.format(
                name=name,
                date=date_str,
                start_time=start_time_str,
                end_time=end_time_str,
                priority=priority_str,
            )
        return txt.TASK_CREATED_WITH_DURATION.format(
            name=name,
            date=date_str,
            start_time=start_time_str,
            end_time=end_time_str,
        )

    if recurrence_str and reminder_str:
        return txt.TASK_CREATED_RECURRING_WITH_REMINDER.format(
            name=name, recurrence=recurrence_str, reminder=reminder_str
        )
    if recurrence_str:
        return txt.TASK_CREATED_RECURRING.format(name=name, recurrence=recurrence_str)
    if reminder_str:
        return txt.TASK_CREATED_WITH_REMINDER.format(name=name, reminder=reminder_str)

    if project_name:
        if date_str:
            resp = txt.TASK_CREATED_IN_PROJECT_WITH_DATE.format(
                name=name, project=project_name, date=date_str
            )
        else:
            resp = txt.TASK_CREATED_IN_PROJECT.format(name=name, project=project_name)
        if priority_str:
            resp = resp.rstrip(".") + f", приоритет — {priority_str}."
        return resp

    if date_str and priority_str:
        return txt.TASK_CREATED_WITH_DATE_AND_PRIORITY.format(
            name=name, date=date_str, priority=priority_str
        )
    if date_str:
        return txt.TASK_CREATED_WITH_DATE.format(name=name, date=date_str)
    if priority_str:
        return txt.TASK_CREATED_WITH_PRIORITY.format(name=name, priority=priority_str)
    return txt.TASK_CREATED.format(name=name)


async def handle_create_task(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
    event_update: Update | None = None,
) -> Response:
    """Handle create_task intent."""
    from alice_ticktick.dialogs.intents import extract_create_task_slots

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
    task_name = (
        slots.task_name[:1].upper() + slots.task_name[1:] if slots.task_name else slots.task_name
    )

    # Обрезать суффикс "с напоминанием за N единиц" из названия задачи
    if slots.reminder_unit is not None:
        task_name = _REMINDER_SUFFIX_RE.sub("", task_name).strip()
        if not task_name:
            return Response(text=txt.TASK_NAME_REQUIRED)

    # --- Duration / Range handling ---
    duration = parse_duration(slots.duration_value, slots.duration_unit)

    # Hybrid approach: try NLU entities first for better date extraction,
    # fall back to grammar slots.
    nlu_dates = _extract_nlu_dates(message, user_tz)

    # Duration without date -> ask for start time
    if duration and not slots.date and (not nlu_dates or not nlu_dates.start_date):
        return Response(text=txt.DURATION_MISSING_START_TIME)
    if nlu_dates and nlu_dates.start_date:
        # NLU entities found -- use them and the cleaned task name
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

    # --- Compute start/end from range or duration slots ---
    has_duration_or_range = False
    start_time_display: str | None = None
    end_time_display: str | None = None

    if slots.range_start and slots.range_end:
        now_local = datetime.datetime.now(tz=user_tz)
        try:
            parsed_rs = parse_yandex_datetime(slots.range_start, now=now_local)
            parsed_re = parse_yandex_datetime(slots.range_end, now=now_local)
            if isinstance(parsed_rs, datetime.date) and not isinstance(
                parsed_rs, datetime.datetime
            ):
                parsed_rs = datetime.datetime.combine(parsed_rs, datetime.time(), tzinfo=user_tz)
            if isinstance(parsed_re, datetime.date) and not isinstance(
                parsed_re, datetime.datetime
            ):
                parsed_re = datetime.datetime.combine(parsed_re, datetime.time(), tzinfo=user_tz)
            start_date_str = _format_ticktick_dt(parsed_rs)
            due_date_str = _format_ticktick_dt(parsed_re)
            is_all_day = False
            date_display = _format_date(parsed_rs, user_tz)
            start_time_display = parsed_rs.strftime("%H:%M")
            end_time_display = parsed_re.strftime("%H:%M")
            has_duration_or_range = True
        except ValueError:
            pass
    elif duration and (start_date_str or due_date_str):
        # Duration with a start datetime: compute end = start + duration
        if (
            nlu_dates
            and nlu_dates.start_date
            and isinstance(nlu_dates.start_date, datetime.datetime)
        ):
            start_dt = nlu_dates.start_date
        elif slots.date:
            now_local = datetime.datetime.now(tz=user_tz)
            parsed = parse_yandex_datetime(slots.date, now=now_local)
            start_dt = (
                parsed
                if isinstance(parsed, datetime.datetime)
                else datetime.datetime.combine(parsed, datetime.time(), tzinfo=user_tz)
            )
        else:
            start_dt = None

        if start_dt:
            end_dt = start_dt + duration
            start_date_str = _format_ticktick_dt(start_dt)
            due_date_str = _format_ticktick_dt(end_dt)
            is_all_day = False
            date_display = _format_date(start_dt, user_tz)
            start_time_display = start_dt.strftime("%H:%M")
            end_time_display = end_dt.strftime("%H:%M")
            has_duration_or_range = True

    # Parse optional priority
    priority_raw = parse_priority(slots.priority) or 0
    priority_value = TaskPriority(priority_raw)

    # Parse recurrence -- fallback: check tokens if NLU didn't fill rec_freq
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
                projects = await _get_cached_projects(client, access_token)
                project = _find_project_by_name(projects, slots.project_name)
                if project is None:
                    names = ", ".join(p.name for p in projects) if projects else "\u2014"
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
            _invalidate_task_cache(access_token)
    except TickTickUnauthorizedError:
        return _auth_required_response(event_update)
    except Exception:
        logger.exception("Failed to create task")
        return Response(text=txt.CREATE_ERROR)

    # Build response with recurrence/reminder info
    rec_display = format_recurrence(repeat_flag)
    rem_display = format_reminder(reminder_trigger)
    priority_short = _format_priority_short(priority_value)

    response_text = _build_create_task_response(
        name=task_name,
        date_str=date_display,
        priority_str=priority_short or None,
        project_name=project_name_display,
        recurrence_str=rec_display,
        reminder_str=rem_display,
        has_duration=has_duration_or_range,
        start_time_str=start_time_display,
        end_time_str=end_time_display,
    )
    return Response(text=response_text)


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
            all_tasks = await _gather_all_tasks(client, access_token)

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
            _invalidate_task_cache(access_token)

            rem_display = format_reminder(trigger) or ""
            return Response(text=txt.REMINDER_ADDED.format(reminder=rem_display, name=best_match))
    except TickTickUnauthorizedError:
        return _auth_required_response(event_update)
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

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            all_tasks = await _gather_all_tasks(client, access_token)
    except TickTickUnauthorizedError:
        return _auth_required_response(event_update)
    except Exception:
        logger.exception("Failed to list tasks")
        return Response(text=txt.API_ERROR)

    # Date range path (week/month) -- early return
    if slots.date_range:
        date_range_filter = parse_date_range(
            slots.date_range,
            now=datetime.datetime.now(tz=user_tz).date(),
            tz=user_tz,
        )
        priority_filter = parse_priority(slots.priority) if slots.priority else None
        priority_label = (
            txt.format_priority_instrumental(_format_priority_label(priority_filter))
            if priority_filter is not None
            else None
        )

        filtered = _apply_task_filters(
            all_tasks,
            date_filter=date_range_filter,
            priority_filter=priority_filter,
            user_tz=user_tz,
        )

        _range_txt_map = {
            "this_week": (
                txt.TASKS_FOR_WEEK,
                txt.TASKS_FOR_WEEK_WITH_PRIORITY,
                txt.NO_TASKS_FOR_WEEK,
                txt.NO_TASKS_FOR_WEEK_WITH_PRIORITY,
            ),
            "next_week": (
                txt.TASKS_FOR_NEXT_WEEK,
                txt.TASKS_FOR_NEXT_WEEK_WITH_PRIORITY,
                txt.NO_TASKS_FOR_NEXT_WEEK,
                txt.NO_TASKS_FOR_NEXT_WEEK_WITH_PRIORITY,
            ),
            "this_month": (
                txt.TASKS_FOR_MONTH,
                txt.TASKS_FOR_MONTH_WITH_PRIORITY,
                txt.NO_TASKS_FOR_MONTH,
                txt.NO_TASKS_FOR_MONTH_WITH_PRIORITY,
            ),
        }
        tmpl_found, tmpl_found_p, tmpl_none, tmpl_none_p = _range_txt_map.get(
            slots.date_range,
            (
                txt.TASKS_FOR_WEEK,
                txt.TASKS_FOR_WEEK_WITH_PRIORITY,
                txt.NO_TASKS_FOR_WEEK,
                txt.NO_TASKS_FOR_WEEK_WITH_PRIORITY,
            ),
        )

        if not filtered:
            if priority_label:
                return Response(text=tmpl_none_p.format(priority=priority_label))
            return Response(text=tmpl_none)

        count_str = txt.pluralize_tasks(len(filtered))
        lines = [_format_task_line(i + 1, t) for i, t in enumerate(filtered[:5])]
        task_list = "\n".join(lines)

        if priority_label:
            return Response(
                text=_truncate_response(
                    tmpl_found_p.format(priority=priority_label, count=count_str, tasks=task_list)
                )
            )
        return Response(
            text=_truncate_response(tmpl_found.format(count=count_str, tasks=task_list))
        )

    # Single-day path
    if slots.date:
        now_local = datetime.datetime.now(tz=user_tz)
        try:
            target_date = parse_yandex_datetime(slots.date, now=now_local)
            if isinstance(target_date, datetime.datetime):
                target_day = target_date.date()
            else:
                target_day = target_date
        except ValueError:
            target_day = datetime.datetime.now(tz=user_tz).date()
    else:
        target_day = datetime.datetime.now(tz=user_tz).date()

    date_display = _format_date(target_day, user_tz)

    # Filter tasks for the target date (convert due_date to user timezone)
    day_tasks = [
        t
        for t in all_tasks
        if t.due_date is not None
        and _to_user_date(t.due_date, user_tz) == target_day
        and t.status == 0
    ]

    # Apply priority filter if provided
    priority_filter = parse_priority(slots.priority) if slots.priority else None
    priority_label = (
        txt.format_priority_instrumental(_format_priority_label(priority_filter))
        if priority_filter is not None
        else None
    )

    if priority_filter is not None:
        day_tasks = [t for t in day_tasks if t.priority == priority_filter]

    if not day_tasks:
        if priority_label:
            if target_day == datetime.datetime.now(tz=user_tz).date():
                return Response(
                    text=txt.NO_TASKS_TODAY_WITH_PRIORITY.format(priority=priority_label)
                )
            return Response(
                text=txt.NO_TASKS_FOR_DATE_WITH_PRIORITY.format(
                    date=date_display, priority=priority_label
                )
            )
        if target_day == datetime.datetime.now(tz=user_tz).date():
            return Response(text=txt.NO_TASKS_TODAY)
        return Response(text=txt.NO_TASKS_FOR_DATE.format(date=date_display))

    count_str = txt.pluralize_tasks(len(day_tasks))
    lines = [_format_task_line(i + 1, t) for i, t in enumerate(day_tasks[:5])]
    task_list = "\n".join(lines)

    if priority_label:
        return Response(
            text=_truncate_response(
                txt.TASKS_FOR_DATE_WITH_PRIORITY.format(
                    date=date_display,
                    priority=priority_label,
                    count=count_str,
                    tasks=task_list,
                )
            )
        )

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
    intent_data: dict[str, Any] | None = None,
    ticktick_client_factory: type[TickTickClient] | None = None,
    event_update: Update | None = None,
) -> Response:
    """Handle overdue_tasks intent."""
    from alice_ticktick.dialogs.intents import extract_overdue_tasks_slots

    access_token = _get_access_token(message)
    if access_token is None:
        return _auth_required_response(event_update)

    slots = extract_overdue_tasks_slots(intent_data or {})
    priority_filter = parse_priority(slots.priority) if slots.priority else None
    priority_label = (
        txt.format_priority_instrumental(_format_priority_label(priority_filter))
        if priority_filter is not None
        else None
    )

    user_tz = _get_user_tz(event_update)
    factory = ticktick_client_factory or TickTickClient
    today = datetime.datetime.now(tz=user_tz).date()

    try:
        async with factory(access_token) as client:
            all_tasks = await _gather_all_tasks(client, access_token)
    except TickTickUnauthorizedError:
        return _auth_required_response(event_update)
    except Exception:
        logger.exception("Failed to get overdue tasks")
        return Response(text=txt.API_ERROR)

    candidates = [
        t
        for t in all_tasks
        if t.due_date is not None and _to_user_date(t.due_date, user_tz) < today
    ]
    overdue = _apply_task_filters(
        candidates,
        priority_filter=priority_filter,
        user_tz=user_tz,
    )

    if not overdue:
        if priority_label:
            return Response(text=txt.NO_OVERDUE_WITH_PRIORITY.format(priority=priority_label))
        return Response(text=txt.NO_OVERDUE)

    count_str = txt.pluralize_tasks(len(overdue))
    lines = [_format_task_line(i + 1, t) for i, t in enumerate(overdue[:5])]
    task_list = "\n".join(lines)

    if priority_label:
        return Response(
            text=_truncate_response(
                txt.OVERDUE_WITH_PRIORITY.format(
                    priority=priority_label, count=count_str, tasks=task_list
                )
            )
        )
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
    state: FSMContext,
    ticktick_client_factory: type[TickTickClient] | None = None,
    event_update: Update | None = None,
) -> Response:
    """Handle complete_task intent."""
    access_token = _get_access_token(message)
    if access_token is None:
        return _auth_required_response(event_update)

    slots = extract_complete_task_slots(intent_data)

    if not slots.task_name or _is_only_stopwords(slots.task_name):
        return Response(text=txt.COMPLETE_NAME_REQUIRED)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            result = await _find_active_task(client, slots.task_name, access_token)
            if isinstance(result, Response):
                return result

            # Low score -> ask for confirmation
            if result.score < _FUZZY_CONFIRM_THRESHOLD:
                user_tz = _get_user_tz(event_update)
                context = _format_task_context(result.task, user_tz)
                await state.set_state(CompleteTaskStates.confirm)
                await state.set_data(
                    {
                        "task_id": result.task.id,
                        "project_id": result.task.project_id,
                        "task_name": result.name,
                        "task_context": context,
                    }
                )
                return Response(text=txt.COMPLETE_CONFIRM.format(name=result.name))

            await client.complete_task(result.task.id, result.task.project_id)
            _invalidate_task_cache(access_token)

    except TickTickUnauthorizedError:
        return _auth_required_response(event_update)
    except Exception:
        logger.exception("Failed to complete task")
        return Response(text=txt.COMPLETE_ERROR)

    user_tz = _get_user_tz(event_update)
    context = _format_task_context(result.task, user_tz)
    return Response(text=txt.TASK_COMPLETED.format(name=result.name, context=context))


async def handle_complete_confirm(
    message: Message,
    state: FSMContext,
    ticktick_client_factory: type[TickTickClient] | None = None,
    event_update: Update | None = None,
) -> Response:
    """Handle complete confirmation (user said 'yes')."""
    access_token = _get_access_token(message)
    if access_token is None:
        await state.clear()
        return _auth_required_response(event_update)

    data = await state.get_data()
    task_id = data.get("task_id", "")
    project_id = data.get("project_id", "")
    task_name = data.get("task_name", "")
    task_context = data.get("task_context", "")

    if not task_id or not project_id or not task_name:
        await state.clear()
        return Response(text=txt.COMPLETE_ERROR)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            await client.complete_task(task_id, project_id)
            _invalidate_task_cache(access_token)
    except TickTickUnauthorizedError:
        await state.clear()
        return _auth_required_response(event_update)
    except Exception:
        logger.exception("Failed to complete task")
        await state.clear()
        return Response(text=txt.COMPLETE_ERROR)

    await state.clear()
    return Response(text=txt.TASK_COMPLETED.format(name=task_name, context=task_context))


async def handle_complete_reject(message: Message, state: FSMContext) -> Response:
    """Handle complete rejection (user said 'no')."""
    await state.clear()
    return Response(text=txt.COMPLETE_CANCELLED)


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
            all_tasks = await _gather_all_tasks(client, access_token)
    except TickTickUnauthorizedError:
        return _auth_required_response(event_update)
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
    best_task = matched_tasks[0]
    other_tasks = matched_tasks[1:]

    user_tz = _get_user_tz(event_update)
    response_text = _build_search_response(best_task, other_tasks, user_tz)

    return Response(text=response_text)


async def handle_edit_task(
    message: Message,
    intent_data: dict[str, Any],
    state: FSMContext,
    ticktick_client_factory: type[TickTickClient] | None = None,
    event_update: Update | None = None,
    *,
    _skip_confirm: bool = False,
) -> Response:
    """Handle edit_task intent."""
    access_token = _get_access_token(message)
    if access_token is None:
        return _auth_required_response(event_update)

    slots = extract_edit_task_slots(intent_data)

    if not slots.task_name or _is_only_stopwords(slots.task_name):
        return Response(text=txt.EDIT_NAME_REQUIRED)

    # Hybrid approach: try NLU entities for date extraction (grammar .+ swallows dates)
    user_tz = _get_user_tz(event_update)
    now_local = datetime.datetime.now(tz=user_tz)
    nlu_dates = _extract_nlu_dates(message, user_tz)
    nlu_has_date = nlu_dates is not None and nlu_dates.start_date is not None

    # Defence: grammar "(в $NewName)?" splits task names containing "в"
    # (e.g. "сходить в озон" -> task_name="сходить", new_name="озон на сегодня").
    # If the verb is NOT "переименуй" and new_name is set, merge it back into
    # task_name so fuzzy search works on the full name.
    tokens = message.nlu.tokens if message.nlu else []
    is_rename_verb = len(tokens) > 0 and tokens[0] in {"переименуй"}
    if slots.new_name is not None and not is_rename_verb:
        merged_name = f"{slots.task_name} в {slots.new_name}"
        slots = dataclasses.replace(slots, task_name=merged_name, new_name=None)

    # Check that at least one change is specified
    has_priority = slots.new_priority is not None
    has_name = slots.new_name is not None
    has_project = slots.new_project is not None
    has_recurrence = slots.rec_freq is not None or slots.rec_monthday is not None
    has_reminder = slots.reminder_unit is not None
    has_remove_recurrence = slots.remove_recurrence
    has_remove_reminder = slots.remove_reminder

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
            all_tasks = await _gather_all_tasks(client, access_token)
            # Pre-fetch projects if move requested (reuses same client session)
            cached_projects = (
                await _get_cached_projects(client, access_token) if has_project else None
            )
    except TickTickUnauthorizedError:
        return _auth_required_response(event_update)
    except Exception:
        logger.exception("Failed to fetch tasks for edit")
        return Response(text=txt.API_ERROR)

    active_tasks = [t for t in all_tasks if t.status == 0]
    # When NLU entities extracted a clean task name (date was removed), prefer it for search.
    # Grammar .+ may swallow date tokens, making the slot value dirty
    # (e.g. "купить хлеб на завтра").
    task_name: str = slots.task_name  # type: ignore[assignment]  # guaranteed by early return
    if (
        nlu_dates is not None
        and nlu_has_date
        and nlu_dates.task_name
        and not _is_only_stopwords(nlu_dates.task_name)
    ):
        task_name = nlu_dates.task_name
    if not active_tasks:
        return Response(text=txt.TASK_NOT_FOUND.format(name=task_name))

    titles = [t.title for t in active_tasks]
    match_results = find_matches(task_name, titles, limit=1)

    if not match_results:
        return Response(text=txt.TASK_NOT_FOUND.format(name=task_name))

    best_match, match_score, match_idx = match_results[0]
    matched_task = active_tasks[match_idx]

    # Low score -> ask for confirmation before editing
    if not _skip_confirm and match_score < _FUZZY_CONFIRM_THRESHOLD:
        await state.set_state(EditTaskStates.confirm)
        await state.set_data(
            {
                "task_id": matched_task.id,
                "project_id": matched_task.project_id,
                "task_name": best_match,
                "intent_data": intent_data,
            }
        )
        return Response(text=txt.EDIT_CONFIRM.format(name=best_match))

    # Build update payload
    new_title: str | None = (
        slots.new_name[:1].upper() + slots.new_name[1:] if has_name and slots.new_name else None
    )

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
            names = ", ".join(p.name for p in cached_projects) if cached_projects else "\u2014"
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

    has_other_changes = not (
        new_title is None
        and new_start_date is None
        and new_due_date is None
        and new_is_all_day is None
        and new_priority_value is None
        and new_repeat_flag is None
        and new_reminders is None
    )
    update_payload: TaskUpdate | None = None
    if has_other_changes:
        update_payload = TaskUpdate(
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
    if target_project_id is not None:
        try:
            async with factory(access_token) as client:
                await client.move_task(matched_task.id, matched_task.project_id, target_project_id)
            _invalidate_task_cache(access_token)
        except TickTickUnauthorizedError:
            return _auth_required_response(event_update)
        except Exception:
            logger.exception(
                "Failed to move task: task_id=%s, from=%s, to=%s",
                matched_task.id,
                matched_task.project_id,
                target_project_id,
            )
            return Response(text=txt.MOVE_ERROR)

    if update_payload is not None:
        try:
            async with factory(access_token) as client:
                await client.update_task(update_payload)
            _invalidate_task_cache(access_token)
        except TickTickUnauthorizedError:
            return _auth_required_response(event_update)
        except Exception:
            if target_project_id is not None:
                logger.exception(
                    "Partial failure: task %s moved to %s but update failed",
                    matched_task.id,
                    target_project_id,
                )
                return Response(
                    text=txt.EDIT_PARTIAL_ERROR.format(
                        name=best_match, project=target_project_name
                    )
                )
            logger.exception(
                "Failed to edit task: task_id=%s, project_id=%s",
                matched_task.id,
                matched_task.project_id,
            )
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

    # Only project changed -> specific move message
    only_project = (
        target_project_id is not None
        and new_title is None
        and new_due_date is None
        and new_priority_value is None
    )
    if only_project and target_project_name:
        return Response(text=txt.TASK_MOVED.format(name=best_match, project=target_project_name))

    # Build detailed confirmation of what changed
    user_tz = _get_user_tz(event_update)
    changes: list[str] = []
    if new_due_date is not None:
        changes.append(f"дата изменена на {_format_date(new_due_date, user_tz)}")
    if new_priority_value is not None:
        prio_short = _format_priority_short(new_priority_value)
        if prio_short:
            changes.append(f"приоритет — {prio_short}")
        else:
            changes.append("приоритет убран")
    if new_title is not None:
        changes.append(f'название изменено на "{new_title}"')
    if target_project_name:
        changes.append(f'перемещена в проект "{target_project_name}"')

    if changes:
        return Response(text=txt.EDIT_SUCCESS.format(name=best_match, changes=", ".join(changes)))
    return Response(text=txt.EDIT_SUCCESS_NO_DETAILS.format(name=best_match))


async def handle_edit_confirm(
    message: Message,
    state: FSMContext,
    ticktick_client_factory: type[TickTickClient] | None = None,
    event_update: Update | None = None,
) -> Response:
    """Handle edit confirmation (user said 'yes') -- re-run edit with forced match."""
    data = await state.get_data()
    intent_data = data.get("intent_data", {})
    await state.clear()

    return await handle_edit_task(
        message,
        intent_data,
        state,
        ticktick_client_factory=ticktick_client_factory,
        event_update=event_update,
        _skip_confirm=True,
    )


async def handle_edit_reject(message: Message, state: FSMContext) -> Response:
    """Handle edit rejection (user said 'no')."""
    await state.clear()
    return Response(text=txt.EDIT_CANCELLED)


async def handle_delete_task(
    message: Message,
    intent_data: dict[str, Any],
    state: FSMContext,
    ticktick_client_factory: type[TickTickClient] | None = None,
    event_update: Update | None = None,
) -> Response:
    """Handle delete_task intent -- start confirmation flow."""
    access_token = _get_access_token(message)
    if access_token is None:
        return _auth_required_response(event_update)

    slots = extract_delete_task_slots(intent_data)

    if not slots.task_name or _is_only_stopwords(slots.task_name):
        return Response(text=txt.DELETE_NAME_REQUIRED)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            result = await _find_active_task(client, slots.task_name, access_token)
    except TickTickUnauthorizedError:
        return _auth_required_response(event_update)
    except Exception:
        logger.exception("Failed to fetch tasks for deletion")
        return Response(text=txt.API_ERROR)

    if isinstance(result, Response):
        return result

    user_tz = _get_user_tz(event_update)
    context = _format_task_context(result.task, user_tz)

    await state.set_state(DeleteTaskStates.confirm)
    await state.set_data(
        {
            "task_id": result.task.id,
            "project_id": result.task.project_id,
            "task_name": result.name,
            "task_context": context,
        }
    )

    return Response(text=txt.DELETE_CONFIRM.format(name=result.name, context=context))


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
    task_context = data.get("task_context", "")

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
            _invalidate_task_cache(access_token)
    except TickTickUnauthorizedError:
        await state.clear()
        return _auth_required_response(event_update)
    except Exception:
        logger.exception("Failed to delete task")
        await state.clear()
        return Response(text=txt.DELETE_ERROR)

    await state.clear()
    return Response(text=txt.DELETE_SUCCESS.format(name=task_name, context=task_context))


async def handle_delete_reject(message: Message, state: FSMContext) -> Response:
    """Handle delete rejection (user said 'no')."""
    await state.clear()
    return Response(text=txt.DELETE_CANCELLED)
