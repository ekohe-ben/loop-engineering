#!/usr/bin/env python3
"""calendar.list_events: events from the user's Google Calendar (read-only; the
connector's OAuth scope is calendar.readonly, so there is no create tool).
Titles, descriptions, locations and attendee names are third-party text."""
from datetime import date, datetime, time, timedelta, timezone

from chat_tools.registry import Arg, READ, Tool, ToolInputError, register, untrusted
from connectors.base import ConnectorError

_MAX_EVENTS = 50
_DEFAULT_DAYS = 7


def _instant(text, label):
    """RFC 3339 instant for a YYYY-MM-DD date or an ISO date-time (UTC if naive)."""
    try:
        if len(text) == 10:
            moment = datetime.combine(date.fromisoformat(text), time.min)
        else:
            moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise ToolInputError(f"{label} must be an ISO date (YYYY-MM-DD) or date-time") from None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _list_events(connector, args):
    start = _instant(str(args.get("start") or ""), "start") if args.get("start") else datetime.now(timezone.utc)
    end = _instant(str(args["end"]), "end") if args.get("end") else start + timedelta(days=_DEFAULT_DAYS)
    if end <= start:
        raise ToolInputError("end must be after start")
    try:
        events = connector.list_events(start.isoformat(), end.isoformat(), max_results=_MAX_EVENTS)
    except ConnectorError as exc:  # connector messages are token-free by contract
        raise ToolInputError(str(exc)) from None
    return {"events": [{
        "summary": untrusted(e["summary"]), "start": e["start"], "end": e["end"],
        "location": untrusted(e["location"]), "description": untrusted(e["description"]),
        "join_url": e["join_url"], "html_link": e["html_link"],
        "organizer": e["organizer"], "attendees_count": e["attendees_count"],
        "attendees": [{"name": untrusted(a["name"]), "email": a["email"], "response": a["response"]}
                      for a in e["attendees"]],
        "my_response": e["self_response"]} for e in events]}


register(Tool(
    name="calendar.list_events", mode=READ, connector_type="google_calendar", handler=_list_events,
    description="List Google Calendar events between two dates (start/end: YYYY-MM-DD or ISO "
                "date-time; default: the next 7 days). Read-only",
    args=(Arg("start", required=False), Arg("end", required=False))))
