#!/usr/bin/env python3
"""Google Calendar chat tools: list events (read) and create one (write, after the
user approves the card). Titles, descriptions, locations and attendee names read
back are third-party text."""
import re
from datetime import date, datetime, time, timedelta, timezone

from chat_tools.registry import Arg, READ, WRITE, Tool, ToolInputError, register, untrusted
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


_ADDRESS = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
_MAX_ATTENDEES = 20


def _offset_instant(text, label):
    """The user's own instant must carry an explicit UTC offset: a bare wall-clock
    time would silently be read in the wrong zone."""
    try:
        moment = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        raise ToolInputError(f"{label} must be an ISO date-time with a UTC offset") from None
    if moment.tzinfo is None or len(str(text)) <= 10:
        raise ToolInputError(f"{label} must include a UTC offset, e.g. 2026-10-12T15:00:00+08:00")
    return moment


def _create_event(connector, args):
    summary = str(args["summary"]).strip()
    if not summary or "\n" in summary or "\r" in summary:
        raise ToolInputError("summary must be a single non-empty line")
    start, end = _offset_instant(args["start"], "start"), _offset_instant(args["end"], "end")
    if end <= start:
        raise ToolInputError("end must be after start")
    attendees = [a.strip() for a in str(args.get("attendees") or "").replace(";", ",").split(",") if a.strip()]
    if len(attendees) > _MAX_ATTENDEES or not all(_ADDRESS.match(a) for a in attendees):
        raise ToolInputError(f"attendees must be up to {_MAX_ATTENDEES} plain email addresses, comma-separated")
    event = {"summary": summary, "start": start.isoformat(), "end": end.isoformat(),
             "description": str(args.get("description") or ""), "location": str(args.get("location") or "").strip(),
             "attendees": attendees}
    try:
        return connector.create_event(event)
    except ConnectorError as exc:  # connector messages are token-free by contract
        raise ToolInputError(str(exc)) from None


register(Tool(
    name="calendar.create_event", mode=WRITE, connector_type="google_calendar", handler=_create_event,
    description="Create a Google Calendar event (start/end: ISO date-time WITH a UTC offset; attendees: "
                "comma-separated emails who will be invited; needs the user's approval)",
    args=(Arg("summary"), Arg("start"), Arg("end"), Arg("attendees", required=False),
          Arg("description", required=False), Arg("location", required=False))))
