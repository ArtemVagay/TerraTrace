import hashlib

def to_sha256(s: str):
    """Отпечаток текста для группировки событий. Не хеширование паролей."""
    return hashlib.sha256(s.encode()).hexdigest()
