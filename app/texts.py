LANGS = ("en", "ro", "ru")

MESSAGES = {
    "not_found": {
        "en": "Document not found.",
        "ro": "Documentul nu a fost găsit.",
        "ru": "Документ не найден.",
    },
    "only_on_site": {
        "en": "This document can only be viewed on the website where it is published.",
        "ro": "Acest document poate fi vizualizat doar pe site-ul unde este publicat.",
        "ru": "Этот документ можно посмотреть только на сайте, где он опубликован.",
    },
    "bad_link": {
        "en": "Invalid link.",
        "ro": "Link invalid.",
        "ru": "Неверная ссылка.",
    },
    "expired": {
        "en": "This link has expired. Close the viewer and open the file again.",
        "ro": "Linkul a expirat. Închideți vizualizarea și deschideți fișierul din nou.",
        "ru": "Ссылка устарела. Закройте просмотр и откройте файл заново.",
    },
    "timeout": {
        "en": "The file takes too long to process. Download it instead.",
        "ro": "Procesarea fișierului durează prea mult. Descărcați-l.",
        "ru": "Файл слишком долго обрабатывается. Скачайте его.",
    },
    "broken": {
        "en": "The file could not be opened: it may be damaged or password-protected. Download it instead.",
        "ro": "Fișierul nu a putut fi deschis: poate fi deteriorat sau protejat cu parolă. Descărcați-l.",
        "ru": "Не удалось открыть файл: возможно, он повреждён или защищён паролем. Скачайте его.",
    },
}


def normalize_lang(code: str | None) -> str | None:
    if not code:
        return None
    short = code.replace("-", "_").split("_")[0].strip().lower()
    return short if short in LANGS else None


def lang_from_header(accept_language: str | None) -> str:
    for part in (accept_language or "").split(","):
        lang = normalize_lang(part.split(";")[0])
        if lang:
            return lang
    return "en"


def text(key: str, lang: str) -> str:
    return MESSAGES[key].get(lang) or MESSAGES[key]["en"]
