import re
import unicodedata

# conjunción entre dos palabras (misma regla en la app: index.html y data.js)
CONJ = re.compile(r"(?<=\w)(?:\s*[&+]\s*|\s+(?:and|y|e|et|und)\s+)(?=\w)")


def norm(s: str) -> str:
    """Clave de comparación: sin tildes, mayúsculas ni signos ("Platero Y Tu" == "Platero y tú")."""
    s = unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()
    s = CONJ.sub(" ", s)  # «Fito y Fitipaldis» == «Fito & Fitipaldis» == «Fito and Fitipaldis»
    return re.sub(r"[^a-z0-9]+", "", s)
