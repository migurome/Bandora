# Weave Bands

Explorador visual de música: escribes un artista, aparece su círculo y la red de grupos relacionados va
creciendo a tu alrededor. Todo en local.

## Arrancar

```bash
python -m weave.server          # http://localhost:8766
```

Requisitos: Python 3.12 (solo librería estándar) y conexión a internet para lo que aún no esté en la base de datos.

## Uso

| Acción | Cómo |
|---|---|
| Añadir artista | Escríbelo en la barra y elige una sugerencia |
| Seleccionar / abrir su menú | Clic en el círculo / clic otra vez |
| Menú del círculo | Desplegar relacionadas · ▶/❚❚ · siguiente canción · Deezer · Spotify |
| Desplegar relacionadas | Botón amarillo del menú o doble clic (máx. 5 conexiones por artista) |
| Quitar artista | Supr (se lleva la rama que colgaba de él) |
| Camino entre artistas | `/from Marea to Michael Jackson` (Tab completa los nombres) |
| Leyenda y filtro de géneros | `/label on` · `/label off` |
| Limpiar mapa y parar música | `/clear` o ✕ |

## Base de datos de artistas

`data/weave.db` (SQLite, fuera del repositorio). Se rellena sola al explorar y, de golpe, con:

```bash
python -m weave.ingest seed     # encola tus artistas del export de Spotify (resources/)
python -m weave.ingest crawl    # los completa (reanudable; Ctrl+C para parar)
python -m weave.ingest status
```

## Pruebas

```bash
python -m unittest discover -s tests -t . -v   # unitarias (sin red)
python -I tools/smoke.py                        # interfaz en Edge sin ventana (servidor arrancado)
```

## Estructura

| Ruta | Qué es |
|---|---|
| `weave/` | Paquete: servidor, base de datos, ingesta, grafo, clientes de Deezer y MusicBrainz |
| `weave/static/` | La página (HTML + D3) |
| `tests/` | Pruebas unitarias |
| `tools/` | Prueba de humo de la interfaz y la web de estadísticas de Spotify |
| `docs/` | Planes de cada fase |
| `ROADMAP.md` | Hoja de ruta |
