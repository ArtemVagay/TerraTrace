"""Разбор лога без веб-сервера: analyze_log(text, filename) возвращает отчёт."""

from dataclasses import dataclass
from datetime import datetime, timezone
import ipaddress
import re
from uuid import uuid4

from schemas.log_schema import AnalysisReport, EventGroup, Summary
from security import to_sha256
from services.diagnostics import diagnose

MAX_BYTES = 5 * 1024 * 1024
MAX_LINES = 50_000
MAX_GROUPS = 200
LEVELS = {"FATAL": 0, "ERROR": 1, "WARN": 2}
SYSTEM_SOURCES = {"tml", "terraria", "network", "console", "statustext", "fna", "steam", "modloader", "unknown"}
HEADER = re.compile(r"^\[(?P<time>\d{1,2}:\d{2}:\d{2}(?:\.\d+)?)\]\s+\[(?P<thread>.*?)/(?P<level>TRACE|DEBUG|INFO|WARN|ERROR|FATAL)\]\s*(?:\[(?P<source>[^\]]+)\]:?\s*)?(?P<message>.*)$", re.I)
PLAIN_LEVEL = re.compile(r"^\s*(?:\[)?(ERROR|FATAL|WARN|WARNING)(?:\])?\s*:\s*(.*)$", re.I)
EXCEPTION = re.compile(r"\b(?:[A-Za-z_]\w*\.)*([A-Za-z_]\w*(?:Exception|Error))\b")
LOADED_MOD = re.compile(r"(?:Loading\s+(?:Mod\s*:|mod\s*:?)|Initializing\s+mod\s*:?)\s*([A-Za-z_]\w*)", re.I)
VERSION = re.compile(r"(?:Starting\s+tModLoader\s+(?:client|server)|tModLoader(?:\s+version)?\s*[:v]?)\s+([0-9][\w.+-]*)", re.I)


class LogInputError(ValueError):
    """Ошибка входных данных, которую роутер покажет пользователю."""


@dataclass
class LogEvent:
    level: str
    source: str
    time: str | None
    first_line: int
    last_line: int
    lines: list[str]


def decode_log(data: bytes) -> str:
    if not data:
        raise LogInputError("Файл пустой. Выбери журнал после тестового запуска.")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return data.decode("utf-16")
        except UnicodeError as exc:
            raise LogInputError("Не удалось прочитать файл UTF-16.") from exc
    if b"\x00" in data:
        raise LogInputError("Похоже, это двоичный файл. Нужен текстовый журнал .log или .txt.")
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            return data.decode(encoding)
        except UnicodeError:
            continue
    raise LogInputError("Не удалось прочитать кодировку. Сохрани файл в UTF-8.")


def mask_private_data(text: str) -> tuple[str, int]:
    """Маскируем типовые данные, сохраняя переносы и номера строк."""
    total = 0
    for pattern, replacement in [
        (r"(?i)([A-Z]:\\Users\\)[^\\\r\n]+", r"\1[USER]"),
        (r"((?:/home/|/Users/))[^/\s]+", r"\1[USER]"),
        (r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "[EMAIL]"),
        (r"(?i)(\b(?:password|api[_-]?key|access[_-]?token)\s*[:=]\s*)[^\s,;]+", r"\1[SECRET]"),
    ]:
        text, count = re.subn(pattern, replacement, text)
        total += count

    def mask_ip(match):
        nonlocal total
        # Четыре числа бывают также версией Terraria или библиотеки.
        before = text[max(0, match.start() - 55):match.start()]
        if re.search(r"(?i)(?:version\s*[=:]?\s*|(?:terraria|tmodloader)\s*v?)$", before):
            return match.group()
        try:
            ipaddress.IPv4Address(match.group())
        except ipaddress.AddressValueError:
            return match.group()
        total += 1
        return "[IP]"

    text = re.sub(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])", mask_ip, text)
    return text, total


def iter_events(lines: list[str]):
    """Заголовок события и следующие строки стека становятся одной записью."""
    current = None
    for number, line in enumerate(lines, 1):
        header = HEADER.match(line)
        plain = PLAIN_LEVEL.match(line) if not header else None
        if header or plain:
            if current is not None:
                yield current
            if header:
                current = LogEvent(header["level"].upper(), header["source"] or "unknown", header["time"], number, number, [header["message"]])
            else:
                current = LogEvent("WARN" if plain[1].upper() == "WARNING" else plain[1].upper(), "unknown", None, number, number, [plain[2]])
        elif current is not None:
            current.lines.append(line)
            current.last_line = number
        elif line.strip():
            current = LogEvent("ERROR" if EXCEPTION.search(line) else "INFO", "unknown", None, number, number, [line])
    if current is not None:
        yield current


def fingerprint(event: LogEvent) -> str:
    text = "\n".join(event.lines).strip()
    text = re.sub(r"(?i)(?:address|адрес)\s+0x[0-9a-f]+", "address [MEMORY]", text)
    text = re.sub(r":line\s+\d+", ":line [LINE]", text)
    return to_sha256(event.level + "|" + event.source + "|" + text)[:20]


def related_mods(event: LogEvent, loaded: set[str]) -> list[str]:
    text = "\n".join(event.lines)
    names = {name for name in loaded if re.search(r"\b" + re.escape(name) + r"\b", text)}
    if event.source.lower() not in SYSTEM_SOURCES:
        names.add(event.source)
    return sorted(names)


def analyze_log(text: str, filename: str = "client.log") -> AnalysisReport:
    """Обычный текст превращается в структурированный отчёт."""
    if not text.strip():
        raise LogInputError("В журнале нет текста для анализа.")
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise LogInputError("Текст больше 5 МиБ.")
    if any(ord(char) < 32 and char not in "\n\r\t" for char in text):
        raise LogInputError("В файле есть двоичные управляющие символы. Нужен текстовый лог.")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.splitlines()
    if len(lines) > MAX_LINES:
        raise LogInputError("В журнале больше 50 000 строк. Выбери более короткий файл.")
    if any(len(line) > 32_000 for line in lines):
        raise LogInputError("Встретилась слишком длинная строка. Проверь формат журнала.")
    text, redactions = mask_private_data(text)
    lines = text.splitlines()
    loaded = set(LOADED_MOD.findall(text))
    version_match = VERSION.search(text[:80_000])
    version = version_match[1] if version_match else None
    buckets = {}
    total_events = errors = warnings = recognized = 0
    for event in iter_events(lines):
        total_events += 1
        recognized += event.source != "unknown" or event.time is not None
        if event.level not in LEVELS:
            continue
        errors += event.level in {"ERROR", "FATAL"}
        warnings += event.level == "WARN"
        key = fingerprint(event)
        if key in buckets:
            buckets[key].count += 1
            buckets[key].last_line = event.last_line
            buckets[key].last_time = event.time
            continue
        message = next((line.strip() for line in event.lines if line.strip()), "Сообщение без текста")
        event_text = "\n".join(event.lines).strip()
        exception = EXCEPTION.search(event_text)
        buckets[key] = EventGroup(
            id=key, level=event.level, source=event.source, message=message[:500],
            exception_type=exception[0] if exception else None, count=1,
            first_line=event.first_line, last_line=event.last_line,
            first_time=event.time, last_time=event.time,
            related_mods=related_mods(event, loaded), excerpt=event_text[:6000], finding=diagnose(event_text),
        )
    groups = sorted(buckets.values(), key=lambda item: (LEVELS[item.level], item.first_line))
    all_mods = sorted(loaded | {name for group in groups for name in group.related_mods})
    notices = []
    if not recognized:
        notices.append("Заголовки tModLoader не распознаны. Показан разбор доступных текстовых сообщений.")
    if not errors:
        notices.append("Записей ERROR и FATAL не найдено. Это не доказывает отсутствие ошибки в поведении мода.")
    if len(groups) > MAX_GROUPS:
        notices.append(f"Показаны первые {MAX_GROUPS} групп. Остальные не включены в этот отчёт.")
    filename = filename.replace("\\", "/").rsplit("/", 1)[-1]
    filename = re.sub(r"[\x00-\x1f]", "", filename)[:150] or "client.log"
    return AnalysisReport(
        id=uuid4().hex, filename=filename, analyzed_at=datetime.now(timezone.utc).isoformat(),
        tml_version=version, mods=all_mods,
        summary=Summary(total_lines=len(lines), total_events=total_events, errors=errors, warnings=warnings, unique_errors=sum(group.level in {"ERROR", "FATAL"} for group in groups), problem_groups=len(groups)),
        groups=groups[:MAX_GROUPS], notices=notices, redactions=redactions, omitted_groups=max(0, len(groups) - MAX_GROUPS),
    )
