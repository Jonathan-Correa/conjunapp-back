from __future__ import annotations

from datetime import timezone

from app.ports import CalendarEvent, CalendarExportPort


class StubICalCalendarAdapter:
    """Minimal iCalendar exporter for reservation exports."""

    def to_ical(self, events: list[CalendarEvent]) -> str:
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//ConjunApp//Zonas Sociales//ES",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
        ]
        for event in events:
            start = _fmt(event.starts_at)
            end = _fmt(event.ends_at)
            lines.extend(
                [
                    "BEGIN:VEVENT",
                    f"UID:{event.uid}",
                    f"DTSTAMP:{start}",
                    f"DTSTART:{start}",
                    f"DTEND:{end}",
                    f"SUMMARY:{_escape(event.summary)}",
                    f"DESCRIPTION:{_escape(event.description)}",
                    f"LOCATION:{_escape(event.location)}",
                    "END:VEVENT",
                ]
            )
        lines.append("END:VCALENDAR")
        return "\r\n".join(lines) + "\r\n"


def _fmt(value) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


_: CalendarExportPort = StubICalCalendarAdapter()
