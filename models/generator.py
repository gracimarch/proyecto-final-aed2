"""
models/generator.py

Generación procedural de escenarios (consigna §16).

El objetivo es construir un warehouse completo y VÁLIDO a partir de unos
pocos parámetros: cantidad de racks, de pasillos, de productos, de pedidos,
máximo de productos por pedido y capacidad de las waves.

La estrategia de layout empaqueta los racks en filas. Cada fila contiene
solo racks de una misma orientación: las filas verticales tienen 2 celdas de
ancho y `largo_rack` de alto, mientras que las horizontales tienen
`largo_rack` de ancho y 2 de alto. Las filas se separan por pasillos y se
intercalan para que la orientación aleatoria quede distribuida por todo el
warehouse.

El usuario puede fijar el ancho y el alto del warehouse. Si no los indica,
se calculan automáticamente buscando una forma equilibrada (relación
ancho/alto cercana a 1). Si las dimensiones indicadas no alcanzan para
ubicar todos los racks con el largo preferido, se prueba con largos menores
(hasta 2) antes de lanzar un ValueError explicativo.

IMPORTANTE: el generador NO declara pasillos (Aisle). Todos los pasillos
quedan sin sentido asignado, por lo que el grafo los trata como AMBOS. El
usuario puede declarar pasillos manualmente después desde el editor. El
parámetro `cantidad_pasillos` indica cuántos pasillos verticales separan
las columnas de racks dentro de cada fila (P pasillos -> P + 1 racks por
fila), por lo que la separación entre racks no es un único hueco fijo.

Validación final:
    - se reconstruye el Warehouse con Warehouse.from_dict (valida solapes,
      bordes, racks con lado 2, puertas con zona, etc.);
    - se genera el grafo y se corre validate_reachability, que comprueba
      que todos los productos se puedan ir a buscar y volver desde la zona
      de despacho respetando los sentidos de circulación.

Si algo no cumple, se lanza ValueError y el endpoint devuelve HTTP 400.
"""

import math
import random

from algorithms.graph_builder import generate_graph
from algorithms.routing import validate_reachability
from models.warehouse import Warehouse


DISTRIBUCIONES = ("uniforme", "aleatoria", "concentrada")
ORIENTACIONES = ("vertical", "horizontal", "aleatorio")

# Márgenes verticales del layout:
#   y = 0        -> borde inferior (puertas)
#   y = 1..2     -> zonas de despacho (alto 2)
#   y = 3..4     -> pasillo horizontal inferior (AMBOS)
#   y = 5..      -> área de racks
Y_ZONAS = 1
ALTO_ZONA = 2
Y_PASILLO_INFERIOR = 3
ALTO_PASILLO_INFERIOR = 2
Y_RACKS = Y_PASILLO_INFERIOR + ALTO_PASILLO_INFERIOR

# Margen de pasillo alrededor de la grilla de racks.
MARGEN_LATERAL = 1
MARGEN_SUPERIOR = 1


def _entero(valor, nombre: str, minimo: int, maximo: int, por_defecto: int | None = None) -> int:
    """Convierte y valida un parámetro entero con rango cerrado."""
    if valor is None or valor == "":
        if por_defecto is None:
            raise ValueError(f"Falta el parámetro '{nombre}'.")
        valor = por_defecto
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        raise ValueError(f"El parámetro '{nombre}' debe ser un entero (recibido: {valor!r}).")
    if numero < minimo or numero > maximo:
        raise ValueError(
            f"El parámetro '{nombre}' debe estar entre {minimo} y {maximo} "
            f"(recibido: {numero})."
        )
    return numero


def _largo_rack(cantidad_productos: int, cantidad_racks: int) -> int:
    """
    Largo preferido de cada rack.  Se busca que haya suficientes celdas para
    repartir los productos sin apilar demasiados niveles z.  El valor real
    por fila puede variar (ver `_variar_largos_por_fila`).
    """
    objetivo = math.ceil(cantidad_productos / max(1, cantidad_racks * 2 * 2))
    return max(4, min(10, objetivo))


def _variar_largos_por_fila(
    n_filas: int,
    largo_base: int,
    rng: random.Random,
) -> list[int]:
    """
    Genera un largo de rack distinto para cada fila, creando variedad visual.

    La variación se mantiene dentro del rango [max(3, largo_base-4), largo_base]
    con una distribución que favorece los valores cercanos al base.  Siempre
    se devuelve al menos una fila con `largo_base` para que el layout no
    quede más chico de lo necesario.
    """
    if n_filas == 0:
        return []
    minimo = max(3, largo_base - 4)
    deltas = [-4, -3, -2, -2, -1, -1, 0, 0, 0]  # sesgo hacia el base
    largos = []
    for _ in range(n_filas):
        delta = rng.choice(deltas)
        largos.append(max(minimo, largo_base + delta))
    # Garantizar al menos una fila con el largo base (para no encoger todo)
    if max(largos) < largo_base:
        largos[rng.randrange(n_filas)] = largo_base
    return largos


def _layout_puertas(ancho: int, cantidad_puertas: int) -> list[tuple[int, int, int]]:
    """
    Distribuye puertas y zonas sobre el borde inferior.

    Returns:
        Lista de (door_x, zone_x, zone_w). Se intenta respetar la cantidad
        pedida; si no entran sin solaparse, se reduce automáticamente.
    """
    for n in range(cantidad_puertas, 0, -1):
        ancho_zona = max(2, min(5, (ancho - 1) // n))
        if ancho_zona > ancho:
            continue

        posiciones = []
        for i in range(n):
            centro = int((i + 0.5) * ancho / n)
            centro = max(0, min(ancho - 1, centro))
            zona_x = max(0, min(ancho - ancho_zona, centro - ancho_zona // 2))
            posiciones.append((centro, zona_x, ancho_zona))

        intervalos = sorted((zx, zx + zw - 1) for _, zx, zw in posiciones)
        solapan = False
        for i in range(len(intervalos) - 1):
            if intervalos[i][1] >= intervalos[i + 1][0]:
                solapan = True
                break

        puertas_x = [px for px, _, _ in posiciones]
        if not solapan and len(set(puertas_x)) == n:
            return posiciones

    # Fallback: una única puerta centrada.
    ancho_zona = min(3, ancho)
    centro = ancho // 2
    zona_x = max(0, min(ancho - ancho_zona, centro - ancho_zona // 2))
    return [(centro, zona_x, ancho_zona)]


def _aspect_score(ancho: int, alto: int) -> float:
    """Qué tan cuadrado es un layout (1.0 = cuadrado perfecto)."""
    return max(ancho, alto) / max(1, min(ancho, alto))


def _ancho_pasillo(cantidad_pasillos: int) -> int:
    """
    Ancho (en celdas) de cada pasillo. Se deriva de la cantidad de pasillos
    pedida para que los pasillos no sean demasiado angostos ni excesivos.
    """
    return max(1, min(3, math.ceil(cantidad_pasillos / 6)))


def _asignar_orientaciones(
    cantidad_racks: int,
    orientacion: str,
    rng: random.Random,
) -> list[str]:
    """
    Devuelve una lista de 'V' (vertical) / 'H' (horizontal) por rack.

    En modo aleatorio se garantiza al menos una de cada una cuando hay 2 o
    más racks, para que realmente sea una mezcla.
    """
    if orientacion == "vertical":
        return ["V"] * cantidad_racks
    if orientacion == "horizontal":
        return ["H"] * cantidad_racks

    orientaciones = [
        "V" if rng.random() < 0.5 else "H" for _ in range(cantidad_racks)
    ]
    if cantidad_racks >= 2 and len(set(orientaciones)) == 1:
        indice = rng.randrange(cantidad_racks)
        orientaciones[indice] = "H" if orientaciones[indice] == "V" else "V"
    return orientaciones


def _empaquetar_filas(
    cantidad_vertical: int,
    cantidad_horizontal: int,
    largo_rack: int,
    ancho_pasillo: int,
    cantidad_pasillos: int,
    ancho_x: int | None,
    largo_y: int | None,
) -> tuple[float, int, int, int, int, int, int] | None:
    """
    Busca cuántos racks poner por fila en cada grupo (vertical/horizontal)
    para que el layout entre en las dimensiones pedidas.

    `cantidad_pasillos` es la cantidad de pasillos verticales que separan
    las columnas de racks dentro de cada fila. Con P pasillos se colocan
    P + 1 racks por fila, por lo que la separación entre racks no es un único
    hueco fijo: la estructura del layout cambia según la cantidad de pasillos.

    Returns:
        (score, cols_v, cols_h, filas_v, filas_h, ancho_grid, alto_grid)
        o None si no entra.
    """
    racks_por_fila = cantidad_pasillos + 1

    filas_v = (
        math.ceil(cantidad_vertical / racks_por_fila)
        if cantidad_vertical > 0 else 0
    )
    # Ancho de una fila vertical: cada rack mide 2 de ancho
    ancho_v = racks_por_fila * 2 + cantidad_pasillos * ancho_pasillo if cantidad_vertical > 0 else 0

    filas_h = (
        math.ceil(cantidad_horizontal / racks_por_fila)
        if cantidad_horizontal > 0 else 0
    )
    # Ancho de una fila horizontal: cada rack mide largo_rack de ancho
    ancho_h = racks_por_fila * largo_rack + cantidad_pasillos * ancho_pasillo if cantidad_horizontal > 0 else 0

    # El ancho de la grilla solo tiene en cuenta los tipos de fila presentes
    anchos_presentes = [a for a in (ancho_v, ancho_h) if a > 0]
    ancho_grid = max(anchos_presentes) if anchos_presentes else 2

    filas_total = filas_v + filas_h
    alto_grid = (
        filas_v * largo_rack
        + filas_h * 2
        + max(0, filas_total - 1) * ancho_pasillo
    )
    total_ancho = ancho_grid + 2 * MARGEN_LATERAL
    total_alto = Y_RACKS + alto_grid + MARGEN_SUPERIOR

    if ancho_x is not None and total_ancho > ancho_x:
        return None
    if largo_y is not None and total_alto > largo_y:
        return None

    vacios = 0
    if cantidad_vertical > 0:
        vacios += racks_por_fila * filas_v - min(cantidad_vertical, racks_por_fila * filas_v)
    if cantidad_horizontal > 0:
        vacios += racks_por_fila * filas_h - min(cantidad_horizontal, racks_por_fila * filas_h)

    # Penalizar poco llenado: el score mejora (baja) cuanto más se aprovecha
    # el espacio.  rack_area ≈ celdas ocupadas; total_area = warehouse completo.
    rack_area = (cantidad_vertical * 2 * largo_rack) + (cantidad_horizontal * largo_rack * 2)
    total_area = total_ancho * total_alto
    fill_ratio = rack_area / max(1, total_area)
    score = _aspect_score(total_ancho, total_alto) + 0.03 * vacios - 0.5 * fill_ratio

    return (
        score, racks_por_fila, racks_por_fila,
        filas_v, filas_h, ancho_grid, alto_grid,
    )


def _construir_layout(
    cantidad_racks: int,
    cantidad_pasillos: int,
    largo_rack: int,
    orientacion: str,
    ancho_x: int | None,
    largo_y: int | None,
    rng: random.Random,
) -> tuple[list[dict], int, int, int, int, int, int, int]:
    """
    Asigna orientaciones y empaqueta los racks en filas.

    Las filas verticales tienen alto variable (ver `_variar_largos_por_fila`)
    y ancho 2.  Las horizontales tienen ancho variable y alto 2.
    Dentro de cada fila, `cantidad_pasillos` pasillos verticales separan
    las columnas de racks (P pasillos → P + 1 racks por fila).  Si las
    dimensiones fijas no alcanzan con el largo de rack preferido, se prueba
    con largos menores (hasta 2) antes de lanzar el error.

    Returns:
        (racks, ancho, alto, pasillos_totales, filas_total, max_columnas,
         ancho_pasillo, largo_rack_usado)
    """
    ancho_pasillo = _ancho_pasillo(cantidad_pasillos)
    orientaciones = _asignar_orientaciones(cantidad_racks, orientacion, rng)
    cantidad_vertical = orientaciones.count("V")
    cantidad_horizontal = cantidad_racks - cantidad_vertical

    mejor = None
    largo_usado = largo_rack
    racks_por_fila = cantidad_pasillos + 1
    for largo in range(largo_rack, 1, -1):
        empaquetado = _empaquetar_filas(
            cantidad_vertical,
            cantidad_horizontal,
            largo,
            ancho_pasillo,
            cantidad_pasillos,
            ancho_x,
            largo_y,
        )
        if empaquetado is not None:
            mejor = empaquetado
            largo_usado = largo
            break

    if mejor is None:
        # Ni con el largo mínimo entra: calcular un tamaño de referencia.
        referencia = _empaquetar_filas(
            cantidad_vertical, cantidad_horizontal, 2, ancho_pasillo,
            cantidad_pasillos, None, None,
        )
        _, _, _, _, _, ancho_ref, alto_ref = referencia
        min_ancho = ancho_ref + 2 * MARGEN_LATERAL
        min_alto = Y_RACKS + alto_ref + MARGEN_SUPERIOR
        if ancho_x is not None and largo_y is not None:
            dimensiones_texto = f"{ancho_x}x{largo_y}"
        elif ancho_x is not None:
            dimensiones_texto = f"ancho {ancho_x}"
        else:
            dimensiones_texto = f"alto {largo_y}"
        raise ValueError(
            f"No se pueden ubicar {cantidad_racks} racks con orientación "
            f"'{orientacion}' en un warehouse de {dimensiones_texto}. "
            f"Incluso con el largo de rack mínimo (2) se necesita al menos "
            f"{min_ancho}x{min_alto}. Ampliá las dimensiones o dejálas en "
            f"automático."
        )

    (
        _score, cols_v, cols_h, filas_v, filas_h,
        ancho_grid, alto_grid,
    ) = mejor

    ancho = ancho_x if ancho_x is not None else ancho_grid + 2 * MARGEN_LATERAL
    # alto se recalcula después con los largos variables reales

    # Cantidad de racks en cada fila (la última puede quedar incompleta).
    cantidades_v = []
    if filas_v > 0:
        for i in range(filas_v):
            inicio = i * racks_por_fila
            cantidades_v.append(
                min(racks_por_fila, cantidad_vertical - inicio)
            )
    cantidades_h = []
    if filas_h > 0:
        for i in range(filas_h):
            inicio = i * racks_por_fila
            cantidades_h.append(
                min(racks_por_fila, cantidad_horizontal - inicio)
            )

    # Variación de largo por fila: cada fila vertical puede tener un largo
    # distinto (dentro del rango [max(3, largo_usado-4), largo_usado]),
    # lo que da variedad visual.  Las filas horizontales tienen alto fijo 2.
    largos_v = _variar_largos_por_fila(filas_v, largo_usado, rng)
    largos_h = _variar_largos_por_fila(filas_h, largo_usado, rng)

    # Si hay dimensiones fijas, ajustar los largos para no exceder el alto.
    if largo_y is not None:
        alto_disponible = largo_y - Y_RACKS - MARGEN_SUPERIOR
        filas_total_tmp = filas_v + filas_h
        pasillo_total = max(0, filas_total_tmp - 1) * ancho_pasillo
        for _ in range(40):
            alto_usado = sum(largos_v) + sum(2 for _ in largos_h) + pasillo_total
            if alto_usado <= alto_disponible:
                break
            if largos_v and max(largos_v) > 2:
                i_max = largos_v.index(max(largos_v))
                largos_v[i_max] -= 1
            elif largos_h and max(largos_h) > 2:
                i_max = largos_h.index(max(largos_h))
                largos_h[i_max] -= 1
            else:
                break

    # Intercalar filas verticales y horizontales para que la mezcla se vea
    # distribuida en todo el warehouse.
    filas_data = []  # (tipo, cantidad, largo_fila)
    i_v = i_h = 0
    while i_v < len(cantidades_v) or i_h < len(cantidades_h):
        if i_v < len(cantidades_v):
            filas_data.append(("V", cantidades_v[i_v], largos_v[i_v]))
            i_v += 1
        if i_h < len(cantidades_h):
            filas_data.append(("H", cantidades_h[i_h], largos_h[i_h]))
            i_h += 1

    # Alto real del warehouse con los largos variables
    alto_grid_real = sum(
        lr if tipo == "V" else 2
        for tipo, _, lr in filas_data
    ) + max(0, len(filas_data) - 1) * ancho_pasillo

    alto = largo_y if largo_y is not None else Y_RACKS + alto_grid_real + MARGEN_SUPERIOR

    racks = []
    y = Y_RACKS
    max_columnas = 0
    for tipo, cantidad, largo_fila in filas_data:
        if tipo == "V":
            ancho_rack, alto_rack = 2, largo_fila
        else:
            ancho_rack, alto_rack = largo_fila, 2

        max_columnas = max(max_columnas, cantidad)
        # Pasillos internos entre los racks de esta fila
        pasillos_fila = max(0, cantidad - 1)
        ancho_fila = cantidad * ancho_rack + pasillos_fila * ancho_pasillo

        # Centrar la fila en el warehouse; respetar el margen lateral mínimo
        offset_x = max(MARGEN_LATERAL, (ancho - ancho_fila) // 2)

        for k in range(cantidad):
            x = offset_x + k * (ancho_rack + ancho_pasillo)
            racks.append({
                "id": f"RACK{len(racks) + 1:02d}",
                "ubicacion": {"x": x, "y": y},
                "ancho": ancho_rack,
                "alto": alto_rack,
            })

        y += alto_rack + ancho_pasillo

    filas_total = len(filas_data)
    pasillos_totales = cantidad_pasillos + (filas_total + 1)
    return (
        racks, ancho, alto, pasillos_totales, filas_total, max_columnas,
        ancho_pasillo, largo_usado,
    )


def _elegir_celdas(racks: list[dict], cantidad: int,
                   distribucion: str, rng: random.Random) -> list[tuple[int, int, str]]:
    """
    Elige una celda de rack para cada producto.

    Returns:
        Lista de (x, y, rack_id) de longitud `cantidad`.
    """
    celdas = []
    for rack in racks:
        x0 = rack["ubicacion"]["x"]
        y0 = rack["ubicacion"]["y"]
        for dy in range(rack["alto"]):
            for dx in range(rack["ancho"]):
                celdas.append((x0 + dx, y0 + dy, rack["id"]))

    if len(celdas) == 0:
        raise ValueError("No hay celdas de rack disponibles para ubicar productos.")

    if distribucion == "aleatoria":
        barajadas = list(celdas)
        rng.shuffle(barajadas)
        if cantidad <= len(barajadas):
            return barajadas[:cantidad]
        return [barajadas[i % len(barajadas)] for i in range(cantidad)]

    if distribucion == "concentrada":
        # Concentra los productos en el primer tercio de las celdas (los
        # primeros racks), dejando el resto del warehouse libre.
        limite = max(1, math.ceil(len(celdas) * 0.30))
        subconjunto = celdas[:limite]
        if cantidad <= len(subconjunto):
            paso = len(subconjunto) / cantidad
            return [subconjunto[int(i * paso)] for i in range(cantidad)]
        return [subconjunto[i % len(subconjunto)] for i in range(cantidad)]

    # "uniforme": reparte las celdas a lo largo de todo el warehouse.
    if cantidad <= len(celdas):
        paso = len(celdas) / cantidad
        return [celdas[int(i * paso)] for i in range(cantidad)]
    return [celdas[i % len(celdas)] for i in range(cantidad)]


def generate_scenario(
    nombre: str = "Escenario generado",
    cantidad_racks: int = 12,
    cantidad_pasillos: int = 6,
    cantidad_productos: int = 40,
    distribucion_productos: str = "uniforme",
    orientacion_racks: str = "vertical",
    ancho_x: int | None = None,
    largo_y: int | None = None,
    cantidad_pedidos: int = 15,
    max_productos_por_pedido: int = 3,
    wave_max_pedidos: int = 4,
    wave_max_productos: int | None = None,
    cantidad_puertas: int = 1,
    cantidad_pickers: int = 2,
    semilla: int | None = None,
) -> dict:
    """
    Genera un escenario completo listo para cargar en el editor.

    Returns:
        {
            "scenario": {...formato Scenario.toJSON()...},
            "meta": {...resumen y resultado de la validación...}
        }

    Raises:
        ValueError: Si un parámetro es inválido o el warehouse generado no
                    cumple las reglas de la consigna.
    """
    # ------------------------------------------------------------------
    # 1. Parámetros
    # ------------------------------------------------------------------
    cantidad_racks = _entero(cantidad_racks, "cantidad_racks", 1, 200)
    cantidad_pasillos = _entero(cantidad_pasillos, "cantidad_pasillos", 1, 60)
    cantidad_productos = _entero(cantidad_productos, "cantidad_productos", 1, 1000)
    cantidad_pedidos = _entero(cantidad_pedidos, "cantidad_pedidos", 1, 1000)
    max_productos_por_pedido = _entero(
        max_productos_por_pedido, "max_productos_por_pedido", 1, 50
    )
    wave_max_pedidos = _entero(wave_max_pedidos, "wave_max_pedidos", 1, 100)
    cantidad_puertas = _entero(cantidad_puertas, "cantidad_puertas", 1, 4)
    cantidad_pickers = _entero(cantidad_pickers, "cantidad_pickers", 1, 20)

    distribucion = str(distribucion_productos or "uniforme").strip().lower()
    if distribucion not in DISTRIBUCIONES:
        raise ValueError(
            f"La distribución de productos debe ser una de {DISTRIBUCIONES} "
            f"(recibida: {distribucion!r})."
        )

    orientacion = str(orientacion_racks or "vertical").strip().lower()
    if orientacion not in ORIENTACIONES:
        raise ValueError(
            f"La orientación de racks debe ser una de {ORIENTACIONES} "
            f"(recibida: {orientacion!r})."
        )

    ancho_x = _entero(ancho_x, "ancho_x", 1, 500) if ancho_x not in (None, "") else None
    largo_y = _entero(largo_y, "largo_y", 1, 500) if largo_y not in (None, "") else None

    if semilla is None or semilla == "":
        semilla = random.SystemRandom().randint(1, 2_147_483_647)
    else:
        semilla = _entero(semilla, "semilla", 0, 2_147_483_647)
    rng = random.Random(semilla)

    nombre = str(nombre or "Escenario generado").strip()[:60] or "Escenario generado"

    # Si no se indica capacidad de unidades, se calcula un valor coherente
    # con la cantidad de pedidos y el máximo de productos por pedido.
    if wave_max_productos is None or wave_max_productos == "":
        wave_max_productos = wave_max_pedidos * max_productos_por_pedido * 3
    wave_max_productos = _entero(wave_max_productos, "wave_max_productos", 1, 5000)

    # ------------------------------------------------------------------
    # 2. Layout de racks y pasillos
    # ------------------------------------------------------------------
    largo_rack = _largo_rack(cantidad_productos, cantidad_racks)
    (
        racks,
        ancho,
        alto,
        pasillos_totales,
        filas,
        columnas,
        ancho_pasillo,
        largo_rack_usado,
    ) = _construir_layout(
        cantidad_racks,
        cantidad_pasillos,
        largo_rack,
        orientacion,
        ancho_x,
        largo_y,
        rng,
    )

    # No se declaran pasillos: todos los pasillos quedan AMBOS por defecto
    # y el usuario puede definirlos manualmente en el editor.
    pasillos = []

    # ------------------------------------------------------------------
    # 3. Puertas y zonas de despacho
    # ------------------------------------------------------------------
    layout_puertas = _layout_puertas(ancho, cantidad_puertas)
    puertas = []
    zonas = []
    for i, (door_x, zone_x, zone_w) in enumerate(layout_puertas):
        door_id = f"DOOR{i + 1:02d}"
        if i == 0:
            tipo = "OUTBOUND"
        elif i == 1:
            tipo = "INBOUND"
        else:
            tipo = "AMBOS"
        puertas.append({
            "id": door_id,
            "tipo": tipo,
            "ubicacion": {"x": door_x, "y": 0},
        })
        zonas.append({
            "id": f"ZONE{i + 1:02d}",
            "puerta_id": door_id,
            "ubicacion": {"x": zone_x, "y": Y_ZONAS},
            "ancho": zone_w,
            "alto": ALTO_ZONA,
            "peso_max_kg": 500.0,  # se recalcula abajo con el peso real
        })

    # ------------------------------------------------------------------
    # 4. Productos
    # ------------------------------------------------------------------
    celdas_elegidas = _elegir_celdas(
        racks, cantidad_productos, distribucion, rng
    )

    productos = []
    uso_celdas = {}
    for i, (x, y, rack_id) in enumerate(celdas_elegidas):
        clave = (x, y)
        z = uso_celdas.get(clave, 0) + 1
        uso_celdas[clave] = z
        productos.append({
            "id": f"PRD{i + 1:03d}",
            "nombre": f"Producto {i + 1:03d}",
            "rack_id": rack_id,
            "ubicacion": {"x": x, "y": y, "z": z},
            "cantidad_disponible": 0,  # se recalcula después de los pedidos
            "peso_kg": round(rng.uniform(0.2, 5.0), 2),
        })

    peso_por_producto = {p["id"]: p["peso_kg"] for p in productos}

    # ------------------------------------------------------------------
    # 5. Pedidos
    # ------------------------------------------------------------------
    max_items = min(max_productos_por_pedido, cantidad_productos)
    pedidos = []
    demanda = {p["id"]: 0 for p in productos}
    for i in range(cantidad_pedidos):
        cantidad_items = rng.randint(1, max_items)
        indices = rng.sample(range(cantidad_productos), cantidad_items)
        items = []
        for indice in indices:
            producto_id = productos[indice]["id"]
            cantidad = rng.randint(1, 3)
            items.append({"producto_id": producto_id, "cantidad": cantidad})
            demanda[producto_id] += cantidad
        pedidos.append({
            "id": f"ORDR{i + 1:03d}",
            "prioridad": rng.randint(1, 5),
            "estado": "PENDIENTE",
            "items": items,
        })

    # Stock suficiente para cubrir toda la demanda (así ningún pedido queda
    # inviable por falta de stock) más un colchón aleatorio.
    for producto in productos:
        pedido_total = demanda[producto["id"]]
        if pedido_total > 0:
            producto["cantidad_disponible"] = pedido_total + rng.randint(5, 20)
        else:
            producto["cantidad_disponible"] = rng.randint(10, 30)

    # ------------------------------------------------------------------
    # 6. Pesos, pickers y capacidad de zonas
    # ------------------------------------------------------------------
    pesos_pedidos = []
    for pedido in pedidos:
        peso = 0.0
        for item in pedido["items"]:
            peso += peso_por_producto[item["producto_id"]] * item["cantidad"]
        pesos_pedidos.append(peso)

    peso_max_pedido = max(pesos_pedidos) if pesos_pedidos else 0.0
    peso_total_pedidos = sum(pesos_pedidos)

    capacidad_picker = max(100.0, round(peso_max_pedido * 1.2 + 10.0, 1))
    capacidad_zona = max(500.0, round(peso_total_pedidos * 1.2 + 100.0, 1))

    for zona in zonas:
        zona["peso_max_kg"] = capacidad_zona

    pickers_creados = min(cantidad_pickers, ancho)
    pickers = []
    usados = set()
    for i in range(pickers_creados):
        x = int((i + 0.5) * ancho / pickers_creados)
        x = max(0, min(ancho - 1, x))
        while x in usados and len(usados) < ancho:
            x = (x + 1) % ancho
        usados.add(x)
        pickers.append({
            "id": f"PICK{i + 1:02d}",
            "posicion_inicial": {"x": x, "y": Y_PASILLO_INFERIOR},
            "capacidad_carga_kg": capacidad_picker,
        })

    # ------------------------------------------------------------------
    # 7. Escenario completo
    # ------------------------------------------------------------------
    scenario = {
        "warehouse": {
            "dimensiones": {"ancho_x": ancho, "largo_y": alto},
            "puertas": puertas,
            "zonas_despacho": zonas,
            "racks": racks,
            "pasillos": pasillos,
        },
        "pickers": pickers,
        "productos": productos,
        "pedidos": pedidos,
        "configuracion": {
            "wave_max_pedidos": wave_max_pedidos,
            "wave_max_productos": wave_max_productos,
        },
        "_editor": {
            "id": "SCEN01",
            "name": nombre,
            "_nextPickerColorIdx": pickers_creados,
            "_nextPickerNum": pickers_creados + 1,
            "pickerColors": [],
        },
    }

    # ------------------------------------------------------------------
    # 8. Validación final (estructura + alcanzabilidad)
    # ------------------------------------------------------------------
    warehouse = Warehouse.from_dict(scenario)
    graph = generate_graph(warehouse)
    validate_reachability(warehouse, graph)

    # Controles extra de coherencia entre lo pedido y lo generado.
    if len(racks) != cantidad_racks:
        raise ValueError("La cantidad de racks generada no coincide con la pedida.")
    if len(pasillos) != 0:
        raise ValueError("El escenario generado no debe declarar pasillos.")
    if len(productos) != cantidad_productos:
        raise ValueError("La cantidad de productos generada no coincide con la pedida.")
    if len(pedidos) != cantidad_pedidos:
        raise ValueError("La cantidad de pedidos generada no coincide con la pedida.")

    # Verificar que todo pedido se pueda satisfacer con el stock disponible.
    for pedido in pedidos:
        for item in pedido["items"]:
            producto = warehouse.get_product(item["producto_id"])
            if item["cantidad"] > producto.cantidad_disponible:
                raise ValueError(
                    f"El pedido '{pedido['id']}' pide más stock del disponible "
                    f"para '{producto.product_id}'."
                )

    racks_verticales = sum(
        1 for rack in racks if rack["ancho"] == 2 and rack["alto"] > 2
    )
    racks_horizontales = sum(
        1 for rack in racks if rack["alto"] == 2 and rack["ancho"] > 2
    )

    return {
        "scenario": scenario,
        "meta": {
            "semilla": semilla,
            "dimensiones": {"ancho_x": ancho, "largo_y": alto},
            "dimensiones_fijas": ancho_x is not None or largo_y is not None,
            "racks": len(racks),
            "pasillos": 0,
            "pasillos_totales": pasillos_totales,
            "ancho_pasillo": ancho_pasillo,
            "largo_rack": largo_rack_usado,
            "largo_rack_preferido": largo_rack,
            "grilla": {"columnas": columnas, "filas": filas},
            "orientacion_racks": orientacion,
            "racks_verticales": racks_verticales,
            "racks_horizontales": racks_horizontales,
            "productos": len(productos),
            "pedidos": len(pedidos),
            "puertas": len(puertas),
            "pickers": len(pickers),
            "distribucion_productos": distribucion,
            "capacidad_picker_kg": capacidad_picker,
            "capacidad_zona_kg": capacidad_zona,
            "validacion": {
                "ok": True,
                "racks_con_lado_2": len(racks),
                "puertas_en_borde": len(puertas),
                "zonas_frente_a_puertas": len(zonas),
                "productos_alcanzables": len(productos),
            },
        },
    }
