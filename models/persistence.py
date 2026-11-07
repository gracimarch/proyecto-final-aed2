"""
persistence.py

Validación de un escenario guardado antes de cargarlo (§17 Persistencia).

Cómo funciona la persistencia del proyecto:
    - Guardar: el front arma el JSON del escenario (formato del Anexo A) y
      lo descarga como archivo. Si había waves o una simulación en curso,
      le agrega la sección opcional "estado" con las opciones elegidas y el
      frame en el que estaba la simulación.
    - Cargar: el front lee el archivo y, antes de mostrarlo, se lo manda al
      back (POST /api/escenario/validar). Este módulo decide si el escenario
      es válido. El front solo lo muestra si el back dice que sí.
    - Continuar la simulación: no se guardan las waves, los caminos ni los
      frames. Se recalculan a partir del escenario y de "estado", porque la
      generación de waves, BFS/A* y la simulación son deterministas: con la
      misma entrada dan siempre el mismo resultado.

Formato de la sección "estado" (todas las claves son opcionales):
    {
        "estrategia_wave": "por_pedido" | "por_cercania" | "solo_cercania",
        "estrategia":      "orden" | "cercania",
        "buscador":        "bfs" | "astar",
        "velocidad":       1..10   (ticks por frame con que se simuló),
        "frame":           índice del frame que se estaba mostrando, o null,
        "tick":            tick de ese frame (informativo), o null
    }
"""

from models.warehouse import Warehouse
from models.wave_manager import WaveManager


ESTRATEGIAS_WAVE = ("por_pedido", "por_cercania", "solo_cercania")
ESTRATEGIAS_RECORRIDO = ("orden", "cercania")
BUSCADORES = ("bfs", "astar")
VELOCIDAD_MIN = 1
VELOCIDAD_MAX = 10


def _is_integer(valor) -> bool:
    """True si es un int de verdad (en Python True/False también son int)."""
    return isinstance(valor, int) and not isinstance(valor, bool)


def _error_message(error: Exception) -> str:
    """
    Pasa una excepción de la carga a un mensaje entendible.

    Un KeyError con una sola palabra es una clave que falta en el JSON
    (por ejemplo data["warehouse"]). Si trae una frase, la frase ya explica
    el problema (por ejemplo, un producto que no existe).
    """
    if isinstance(error, KeyError) and len(error.args) > 0:
        texto = str(error.args[0])
        if " " not in texto:
            return f"Falta el dato '{texto}' en el archivo."
        return texto
    return str(error)


def validate_saved_state(estado) -> list[str]:
    """
    Controla la sección "estado" de un escenario guardado.

    Returns:
        La lista de errores encontrados (vacía si está todo bien).
    """
    if not isinstance(estado, dict):
        return ["La sección 'estado' tiene que ser un objeto."]

    errores = []

    opciones = [
        ("estrategia_wave", ESTRATEGIAS_WAVE),
        ("estrategia", ESTRATEGIAS_RECORRIDO),
        ("buscador", BUSCADORES),
    ]
    for clave, validas in opciones:
        valor = estado.get(clave)
        if valor is not None and valor not in validas:
            errores.append(
                f"'estado.{clave}' tiene un valor desconocido ({valor!r}). "
                f"Opciones: {', '.join(validas)}."
            )

    velocidad = estado.get("velocidad")
    if velocidad is not None:
        if not _is_integer(velocidad) or not VELOCIDAD_MIN <= velocidad <= VELOCIDAD_MAX:
            errores.append(
                f"'estado.velocidad' tiene que ser un entero entre "
                f"{VELOCIDAD_MIN} y {VELOCIDAD_MAX}."
            )

    for clave in ("frame", "tick"):
        valor = estado.get(clave)
        if valor is not None and (not _is_integer(valor) or valor < 0):
            errores.append(f"'estado.{clave}' tiene que ser un entero mayor o igual a 0.")

    # Para retomar una simulación hay que saber cómo se armaron las waves.
    if estado.get("frame") is not None and estado.get("estrategia_wave") is None:
        errores.append("'estado' trae un frame pero no dice la estrategia de waves.")

    return errores


def validate_scenario(data) -> dict:
    """
    Decide si un escenario guardado se puede cargar.

    Arma el Warehouse y el WaveManager igual que las demás rutas del back,
    así que se aplican las mismas validaciones (§16): elementos dentro del
    warehouse y sin solaparse, racks con un lado de 2, puertas en el borde,
    zona frente a cada puerta, productos dentro de un rack, pickers en un
    pasillo, pedidos con productos que existen, y que todos los productos
    se puedan ir a buscar y traer a la zona de despacho respetando los
    sentidos de los pasillos.

    Complejidad: O(n) para registrar los elementos en los diccionarios por
    id (tablas hash, búsqueda O(1)), más el chequeo de solapamientos sobre
    el mapa de celdas y dos BFS O(V + E) para la alcanzabilidad.

    Returns:
        {
            "valido":  bool,
            "errores": [str],  motivos por los que no se puede cargar,
            "avisos":  [str],  cosas que no impiden cargarlo (por ejemplo
                               pedidos sin stock suficiente)
        }
    """
    errores = []
    avisos = []

    if not isinstance(data, dict):
        errores.append("El archivo no contiene un escenario.")
        return {"valido": False, "errores": errores, "avisos": avisos}

    try:
        warehouse = Warehouse.from_dict(data)
        manager = WaveManager.from_dict(data, warehouse)
    except (KeyError, ValueError, TypeError, AttributeError) as e:
        errores.append(_error_message(e))
    else:
        for order, motivo in manager.unprocessable_orders:
            avisos.append(f"Pedido {order.order_id}: {motivo}.")

    if data.get("estado") is not None:
        errores.extend(validate_saved_state(data["estado"]))

    return {"valido": len(errores) == 0, "errores": errores, "avisos": avisos}
