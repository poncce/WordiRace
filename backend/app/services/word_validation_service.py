"""
WordValidationService
─────────────────────
1. Check Redis cache      →  instant response if cached.
2. Check local word list  →  fast path for known words.
3. Call RAE API           →  for words not in local list.
4. On API failure         →  fallback to local wordlist (graceful degradation).
5. Cache API results      →  24 h TTL.
"""
from __future__ import annotations

import httpx
from app.core.config import get_settings
from app.core.logging import get_logger
from app.repositories.redis_repository import RedisRepository

log = get_logger(__name__)
settings = get_settings()

# Comprehensive local word list (all game lengths).
# Used as primary source (fast, no external call) AND as fallback when RAE API is unavailable.
# Includes all words from `_WORD_POOL` in game_manager.py plus common Spanish words.
LOCAL_WORDS: set[str] = {
    # 5 letters (pool + common)
    "PIANO", "BRUJA", "TIGRE", "FELIZ", "JUEGO", "PLAZA", "VIAJE", "DANZA",
    "FRESA", "HIELO", "LLAVE", "MUNDO", "NIEVE", "QUESO", "RIEGA", "SIETE",
    "TECHO", "VAPOR", "YERNO", "PLAYA", "GATOS", "LIBRO", "CASAS", "VIDAS",
    "PERRO", "LLAMA", "FICHA", "GRUTA", "JIRON", "OCEAN", "PAJAR", "UNICO",
    "AGUA", "ARBOL", "BAILE", "BARCO", "BRAZO", "CIELO", "COCHE", "COSAS",
    "CRUZ", "DEDOS", "DOLOR", "DONDE", "DUCHA", "FALDA", "FUEGO", "FUERA",
    "GOLPE", "GUSTO", "HABLA", "HACER", "HORAS", "HUESO", "IDEAS", "IGUAL",
    "JABON", "JOVEN", "JUNTO", "JUSTO", "LAGOS", "LAPIZ", "LARGO", "LEJOS",
    "LIMON", "LINDO", "LLENO", "LUCHA", "LUGAR", "LUNA", "MAGIA", "MAIZ",
    "MANOS", "MAR", "MARCO", "MATES", "MAYOR", "MENOR", "MESAS", "METRO",
    "MIEDO", "MIRAR", "MITAD", "MORIR", "MOVIL", "MUSEO", "NACER", "NADAR",
    "NAVES", "NEGRA", "NIVEL", "NOCHE", "NORMA", "NOTAS", "NUBES", "NUEVE",
    "NUEVO", "ODIAR", "OREJA", "OTROS", "PADRE", "PAGAR", "PANEL", "PARED",
    "PASOS", "PASTA", "PEDIR", "PENAS", "PIEZA", "PISTA", "PLANO", "PLATO",
    "PLUMA", "POCOS", "PODER", "POEMA", "POLVO", "PONER", "PRADO", "PRESA",
    "PRIMO", "PROSA", "PUNTA", "PUNTO", "RADIO", "REINA", "REINO", "RESTO",
    "RISAS", "ROBAR", "ROBLE", "ROBOT", "ROCIO", "ROJOS", "RONDA", "ROSAS",
    "RUBIO", "RUIDO", "RUMOR", "RUTAS", "SABER", "SACAR", "SALAS", "SALIR",
    "SALON", "SALUD", "SANGRE", "SECOS", "SEGUN", "SEÑAL", "SERIO", "SILLA",
    "SOBRE", "SOCIO", "SOLAR", "SOLOS", "SOMOS", "SUAVE", "SUBIR", "SUCIO",
    "SUENO", "SUPER", "SUTIL", "TABLA", "TALON", "TARDE", "TAREA", "TEMOR",
    "TENER", "TIENE", "TIGRE", "TIMON", "TINTA", "TIPOS", "TIRAR", "TOCAR",
    "TOMAR", "TOQUE", "TORRE", "TRAMA", "TRATO", "TRAER", "TRIGO", "TUNEL",
    "TURNO", "UNION", "USAR", "VALOR", "VAMOS", "VASOS", "VECES", "VELAS",
    "VENTA", "VERDE", "VERSO", "VIAJE", "VIDAS", "VIDRIO", "VIEJO", "VIENE",
    "VILLA", "VINOS", "VIRUS", "VISTA", "VIVIR", "VOCAL", "VOLAR", "VUELO",
    # 6 letters (pool + common)
    "FIESTA", "GRANJA", "CAMINO", "FRENOS", "BROCHA", "JARABE", "LADERA",
    "MUEBLE", "PISTOL", "RINCON", "DENTAL", "CABINA", "SALIDA", "NUBLAR",
    "BOSQUE", "CABEZA", "CARRIL", "CARTAS", "CEREAL", "COCINA", "COMIDA",
    "CUELLO", "DINERO", "DORMIR", "EJEMPL", "EMPEZ", "ENSAYO", "ENTRAR",
    "EQUIPO", "ESPERA", "FLORES", "FORMAR", "FUERTE", "FUERZA", "FUTBOL",
    "GANADO", "GENTE", "GRANDE", "GUERRA", "HABLAR", "HERMAN", "HIJOS",
    "HOMBRE", "HUEVOS", "HUMANO", "IMAGEN", "JARDIN", "LECHE", "LENGUA",
    "LIBRO", "LINEA", "LISTA", "LLEGAR", "LLENAR", "LLEVAR", "MADERA",
    "MADRE", "MANDAR", "MANERA", "MANZAN", "MARINO", "MEDICO", "MEDIDA",
    "MEDIO", "MEJOR", "MENTAL", "MERCAD", "MINUTO", "MIRADA", "MISMO",
    "MODELO", "MOMENT", "MONEDA", "MONTAR", "MOTOR", "MOVER", "MUERTE",
    "MUJER", "MUNDO", "MUSICA", "NACION", "NARIZ", "NIVEL", "NOMBRE",
    "NORMAL", "NOVELA", "NUEVOS", "NUNCA", "OBJETO", "OCEANO", "ORDEN",
    "PADRE", "PAGINA", "PAIS", "PAJARO", "PAPEL", "PARADA", "PARED",
    "PARQUE", "PARTE", "PASADO", "PASION", "PECHO", "PELOTA", "PENSAR",
    "PERDER", "PERRO", "PERSON", "PIANO", "PIEZA", "PILOTO", "PINTAR",
    "PINTOR", "PISO", "PISTA", "PLANTA", "PLATA", "PLATO", "PLAYA",
    "PLAZA", "PLUMA", "POBRE", "PODER", "POESIA", "POLICIA", "POLLO",
    "PONER", "PORTAL", "POSTRE", "PRECIO", "PRENSA", "PRIMER", "PRONTO",
    "PROPIO", "PRUEBA", "PUEBLO", "PUERTA", "PUESTO", "PUNTA", "PUNTO",
    "QUERER", "QUESO", "QUIEN", "RADIO", "RAIZ", "RAPIDO", "RATON", "RAZON",
    "REGION", "REINA", "RELOJ", "RINCON", "RIO", "RITMO", "ROBAR", "ROBOT",
    "ROPA", "ROSAS", "RUBIO", "RUEDA", "RUIDO", "SABER", "SABOR", "SACAR",
    "SALIDA", "SALIR", "SALON", "SALSA", "SALTO", "SALUD", "SALVAR",
    "SANGRE", "SECRET", "SEGURO", "SELVA", "SEMANA", "SENTIR", "SEÑAL",
    "SEÑOR", "SERIO", "SIEMPRE", "SIERRA", "SIETE", "SILLA", "SIMPLE",
    "SISTEM", "SITIO", "SOBRE", "SOCIAL", "SOLO", "SOMBRA", "SUAVE",
    "SUBIR", "SUCIO", "SUELO", "SUENO", "SUERTE", "SUFRIR", "SUPER",
    "TARDE", "TENER", "TIERRA", "TOCAR", "TOMAR", "TORRE", "TRABA",
    "TRAER", "TREN", "TRIBU", "TUNEL", "VACAS", "VALOR", "VAMOS",
    "VERDE", "VIAJE", "VIDAS", "VIEJO", "VILLA", "VIRUS", "VISTA",
    "VIVIR", "VOCAL", "VOLAR", "VUELO",
    # 7 letters (pool)
    "ABOGADO", "BELLEZA", "CIGARRA", "DEFENSA", "ESPACIO", "FUNCION",
    "GANADOR", "HORMIGA", "IGLESIA", "JUGADOR", "MONTAÑA", "PELOTAS",
    "SOLDADO",
    # 8 letters (pool)
    "ARMADURA", "DIAMANTE", "ESCALERA", "BALCONES", "GUITARRA",
    "PARACAID", "CANDADOS", "MADRUGAR", "JUBILADO", "PRINCESA",
}


class WordValidationService:
    def __init__(self, repo: RedisRepository):
        self._repo = repo
        self._client = httpx.AsyncClient(
            base_url=settings.RAE_API_BASE_URL,
            timeout=settings.RAE_API_TIMEOUT,
            headers={"X-API-Key": settings.RAE_API_KEY} if settings.RAE_API_KEY else {},
        )

    async def is_valid(self, word: str) -> bool:
        """
        Check if `word` is a valid Spanish word.
        Order: local word list (ground truth) → cache → RAE API → local fallback.
        """
        normalized = word.upper()

        # 1. Local word list — ground truth for known words, avoids stale cache
        if normalized in LOCAL_WORDS:
            log.debug("Local list hit for '%s'", normalized)
            await self._repo.set_word_cache(normalized, True)
            return True

        # 2. Cache hit (only for words NOT in our local list)
        cached = await self._repo.get_word_cache(normalized)
        if cached is not None:
            log.debug("Cache hit for '%s': %s", normalized, cached)
            return cached

        # 3. RAE API (for words not in our local list)
        try:
            valid = await self._query_rae(normalized)
            await self._repo.set_word_cache(normalized, valid)
            return valid
        except Exception as exc:
            log.warning("RAE API unavailable for '%s': %s — using fallback", normalized, exc)

        # 4. Fallback to local list (in case of API failure)
        valid = normalized in LOCAL_WORDS
        # Don't cache fallback results (API may recover)
        return valid

    async def _query_rae(self, word: str) -> bool:
        """
        Query RAE API. Returns True if the word exists in the DRAE.
        The RAE API returns 200 with {"ok": true, "data": {...}} when
        the word exists, and 404 with {"ok": false} when it doesn't.
        """
        response = await self._client.get(f"words/{word.lower()}")
        if response.status_code == 200:
            data = response.json()
            return data.get("ok", False)
        if response.status_code == 404:
            return False
        response.raise_for_status()
        return False

    async def get_random_word(self, min_length: int, max_length: int) -> str | None:
        """
        Fetch a random Spanish word from the RAE API within the given length range.
        Returns the word in UPPERCASE, or None if the API fails.
        """
        try:
            response = await self._client.get(
                "/api/random",
                params={"min_length": min_length, "max_length": max_length},
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("ok") and "data" in data:
                    return data["data"]["word"].upper()
            return None
        except Exception as exc:
            log.warning("RAE API random word failed: %s", exc)
            return None

    async def close(self) -> None:
        await self._client.aclose()
