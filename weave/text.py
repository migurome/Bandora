import re
import unicodedata


def norm(s: str) -> str:
    """Clave de comparación: sin tildes, mayúsculas ni signos ("Platero Y Tu" == "Platero y tú")."""
    s = unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", s)
