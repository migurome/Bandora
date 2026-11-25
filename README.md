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
| Abrir / cerrar su menú | Clic en el círculo |
| Menú del círculo | Desplegar relacionadas · conector · ▶/❚❚ · siguiente canción · quitar · Spotify |
| Desplegar relacionadas | Botón amarillo del menú (máx. 5 conexiones por artista) |
| Conectar dos artistas | Arrastra el conector del menú hasta otro círculo |
| Quitar artista | Papelera del menú o Supr (se lleva la rama que colgaba de él) |
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
