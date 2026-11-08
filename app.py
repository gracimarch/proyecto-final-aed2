"""
app.py

Servidor Flask de la aplicacion Warehouse Simulator.

Rutas:
    GET  /                      -> Devuelve la pagina principal (index.html).

    POST /api/waves/generate    -> Recibe el JSON del escenario y devuelve las
                                   waves generadas con sus pickers asignados.

    POST /api/routes/plan       -> Recibe el JSON del escenario, el id de la
                                   wave y la estrategia de recorrido; devuelve
                                   el camino calculado y sus metricas.

    POST /api/routes/compare    -> Igual que /plan pero corre todas las
                                   estrategias y devuelve una comparacion.

    POST /api/simulacion        -> Recibe el JSON del escenario, la estrategia
                                   y el buscador; corre la simulacion completa
                                   con todos los pickers y devuelve un frame
                                   por tick. El frontend solo los dibuja.

    POST /api/escenario/validar -> Recibe un escenario guardado (archivo .json)
                                   y dice si se puede cargar. El frontend solo
                                   lo muestra si el back lo acepta.

Diseno stateless: el cliente envia el estado completo del escenario en cada
pedido. El servidor no guarda nada entre llamadas; cada request es
independiente.
"""

from flask import Flask, render_template, request, jsonify

from models.warehouse import Warehouse
from models.wave_manager import WaveManager
from models.generator import generate_scenario
from algorithms.graph_builder import generate_graph
from algorithms.routing import plan_route, compare_strategies, compare_all_combinations
from models.simulation import Simulation
from models.persistence import validate_scenario


app = Flask(__name__)


# ---------------------------------------------------------------------------
# Helpers: armar el estado del backend a partir del JSON del cliente
# ---------------------------------------------------------------------------

def _build_warehouse(data: dict) -> Warehouse:
    """
    Construye el Warehouse desde el diccionario que envia el frontend.

    El frontend llama toJSON() sobre su Scenario, y el resultado tiene la
    clave "warehouse" con todas las sub-estructuras (racks, pasillos, etc.).
    Warehouse.from_dict espera justamente ese diccionario completo.
    """
    return Warehouse.from_dict(data)


def _build_wave_manager(data: dict, warehouse: Warehouse) -> WaveManager:
    """
    Construye el WaveManager a partir del diccionario completo del escenario.
    Si el JSON trae pedidos ya procesados (en waves), los reconstruye en el
    mismo estado guardado. Si no, solo carga los pedidos pendientes.
    """
    return WaveManager.from_dict(data, warehouse)


def _picker_start(wave):
    """
    Celda donde arranca el recorrido de la wave: la posicion actual de su
    picker. Si la wave todavia no tiene picker, devuelve None y el recorrido
    arranca al lado de la zona de despacho.
    """
    if wave.picker is None:
        return None
    return wave.picker.posicion_actual


# ---------------------------------------------------------------------------
# Pagina principal
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


# ---------------------------------------------------------------------------
# POST /api/scenarios/generate
# ---------------------------------------------------------------------------

@app.route("/api/scenarios/generate", methods=["POST"])
def api_scenarios_generate():
    """
    Genera un escenario completo (warehouse + productos + pedidos) de forma
    procedural a partir de unos pocos parámetros.

    Cuerpo esperado (application/json):
    {
        "nombre": "Mi escenario",
        "cantidad_racks": 12,
        "cantidad_pasillos": 6,        // cantidad de pasillos (entre racks)
        "cantidad_productos": 40,
        "distribucion_productos": "uniforme",   // uniforme | aleatoria | concentrada
        "orientacion_racks": "vertical",        // vertical | horizontal | aleatorio
        "ancho_x": 30,                          // opcional; si falta se calcula
        "largo_y": 22,                          // opcional; si falta se calcula
        "cantidad_pedidos": 15,
        "max_productos_por_pedido": 3,
        "wave_max_pedidos": 4,
        "wave_max_productos": 36,               // opcional
        "cantidad_puertas": 1,                  // opcional
        "cantidad_pickers": 2,                  // opcional
        "generar_pasillos": false,              // opcional: declarar pasillos con sentido
        "semilla": 12345                        // opcional
    }

    Respuesta exitosa (200):
    {
        "scenario": { ...formato Scenario.toJSON()... },
        "meta": {
            "semilla": 12345,
            "dimensiones": {"ancho_x": 31, "largo_y": 15},
            "dimensiones_fijas": false,
            "racks": 12, "pasillos": 0, "pasillos_totales": 10,
            "generar_pasillos": false,
            "ancho_pasillo": 1,
            "largo_rack": 4, "largo_rack_preferido": 4,
            "grilla": {"columnas": 6, "filas": 2},
            "orientacion_racks": "vertical",
            "racks_verticales": 12, "racks_horizontales": 0,
            "productos": 40, "pedidos": 15,
            "validacion": {"ok": true, ...}
        }
    }

    Respuesta de error (400):
    { "error": "mensaje explicativo" }
    """
    body = request.get_json(silent=True)
    if body is None:
        return jsonify({"error": "El cuerpo de la peticion debe ser JSON."}), 400
    if not isinstance(body, dict):
        return jsonify({"error": "El cuerpo de la peticion debe ser un objeto JSON."}), 400

    try:
        resultado = generate_scenario(
            nombre=body.get("nombre", "Escenario generado"),
            cantidad_racks=body.get("cantidad_racks", 12),
            cantidad_pasillos=body.get("cantidad_pasillos", 6),
            cantidad_productos=body.get("cantidad_productos", 40),
            distribucion_productos=body.get("distribucion_productos", "uniforme"),
            orientacion_racks=body.get("orientacion_racks", "vertical"),
            ancho_x=body.get("ancho_x"),
            largo_y=body.get("largo_y"),
            cantidad_pedidos=body.get("cantidad_pedidos", 15),
            max_productos_por_pedido=body.get("max_productos_por_pedido", 3),
            wave_max_pedidos=body.get("wave_max_pedidos", 4),
            wave_max_productos=body.get("wave_max_productos"),
            cantidad_puertas=body.get("cantidad_puertas", 1),
            cantidad_pickers=body.get("cantidad_pickers", 2),
            generar_pasillos=body.get("generar_pasillos", False),
            semilla=body.get("semilla"),
        )
    except (ValueError, KeyError, TypeError) as e:
        return jsonify({"error": str(e)}), 400

    return jsonify(resultado)


# ---------------------------------------------------------------------------
# POST /api/waves/generate
# ---------------------------------------------------------------------------

@app.route("/api/waves/generate", methods=["POST"])
def api_waves_generate():
    """
    Recibe el escenario completo en JSON, genera las waves y asigna pickers.

    Cuerpo esperado (application/json): el resultado de Scenario.toJSON()
    del frontend.

    Respuesta exitosa (200):
    {
        "waves": [
            {
                "wave_id":   "WAVE01",
                "status":    "ABIERTA",
                "picker_ids": ["PICK01"],
                "picker_id": "PICK01",
                "prioridad": 5,
                "pedidos":   ["ORDR01", "ORDR02"],
                "unidades":  3,
                "peso_kg":   7.7
            },
            ...
        ]
    }

    Respuesta de error (400):
    { "error": "mensaje explicativo" }
    """
    data = request.get_json()
    if data is None:
        return jsonify({"error": "El cuerpo de la peticion debe ser JSON."}), 400

    try:
        warehouse = _build_warehouse(data)
        manager   = _build_wave_manager(data, warehouse)
        estrategia_wave = data.get("estrategia_wave", "por_cercania")
        manager.generate_waves(estrategia_wave=estrategia_wave)
        manager.assign_pickers()
    except (ValueError, KeyError) as e:
        return jsonify({"error": str(e)}), 400

    waves_dict = []
    for wave in manager.get_waves():
        picker_ids = [p.picker_id for p in wave.pickers]

        pedidos_ids = []
        for entry in wave.entries:
            pedidos_ids.append(entry.order.order_id)

        waves_dict.append({
            "wave_id":         wave.wave_id,
            "status":          wave.status.value,
            "picker_ids":      picker_ids,
            "picker_id":       picker_ids[0] if picker_ids else None,  # compat
            "prioridad":       wave.priority(),
            "pedidos":         pedidos_ids,
            "unidades":        wave.current_units(),
            "peso_kg":         round(wave.total_weight(), 3),
            "estrategia_wave": estrategia_wave,
        })

    return jsonify({"waves": waves_dict, "estrategia_wave": estrategia_wave})


# ---------------------------------------------------------------------------
# POST /api/waves/compare
# ---------------------------------------------------------------------------

@app.route("/api/waves/compare", methods=["POST"])
def api_waves_compare():
    """
    Genera las waves con las tres estrategias ("por_pedido", "por_cercania"
    y "solo_cercania") sobre el mismo escenario y devuelve los resultados
    comparados, para que el front pueda mostrar una tabla por estrategia.

    Cuerpo esperado (application/json):
    {
        "escenario":  { ...Scenario.toJSON()... }
    }

    Respuesta exitosa (200):
    {
        "comparacion": [
            {
                "estrategia": "por_pedido",
                "total_waves": 3,
                "total_ticks": 42,
                "total_unidades": 12,
                "total_peso_kg": 24.5,
                "waves": [ {...}, {...}, {...} ]
            },
            {
                "estrategia": "por_cercania",
                "total_waves": 2,
                "total_unidades": 12,
                "total_peso_kg": 24.5,
                "waves": [ {...}, {...} ]
            },
            { "estrategia": "solo_cercania", ... }
        ],
        "mismo_resultado": false
    }

    Respuesta de error (400):
    { "error": "mensaje explicativo" }
    """
    body = request.get_json()
    if body is None:
        return jsonify({"error": "El cuerpo de la peticion debe ser JSON."}), 400

    escenario = body.get("escenario")
    if escenario is None:
        return jsonify({"error": "Falta la clave 'escenario' en el cuerpo."}), 400

    comparacion = []
    for estrategia in ("por_pedido", "por_cercania", "solo_cercania"):
        try:
            warehouse = _build_warehouse(escenario)
            manager   = _build_wave_manager(escenario, warehouse)
            manager.generate_waves(estrategia_wave=estrategia)
            manager.assign_pickers()

            waves_info = []
            total_unidades = 0
            total_peso = 0.0
            distancia_estimada = 0
            graph = generate_graph(warehouse)
            for wave in manager.get_waves():
                picker_ids = [p.picker_id for p in wave.pickers]
                pedidos_ids = [entry.order.order_id for entry in wave.entries]
                unidades = wave.current_units()
                peso = wave.total_weight()
                total_unidades = total_unidades + unidades
                total_peso = total_peso + peso

                # Distancia estimada del recorrido de esta wave (BFS, estrategia cercanía).
                dist_wave = 0
                try:
                    ruta = plan_route(wave, warehouse, graph, "cercania", "bfs")
                    dist_wave = ruta.distancia_total
                except (ValueError, KeyError):
                    dist_wave = 0
                distancia_estimada = distancia_estimada + dist_wave

                waves_info.append({
                    "wave_id":            wave.wave_id,
                    "status":             wave.status.value,
                    "picker_ids":         picker_ids,
                    "pedidos":            pedidos_ids,
                    "unidades":           unidades,
                    "peso_kg":            round(peso, 3),
                    "distancia_estimada": dist_wave,
                })

            # Ticks totales que tarda este armado de waves en completarse.
            # Se simula con cercanía + BFS, la misma combinación usada para
            # calcular la distancia estimada de cada wave.
            sim = Simulation(warehouse, manager, "cercania", "bfs")
            sim.run()
            total_ticks = sim.metrics()["ticks"]

            comparacion.append({
                "estrategia":               estrategia,
                "total_waves":              len(waves_info),
                "total_ticks":              total_ticks,
                "total_unidades":           total_unidades,
                "total_peso_kg":            round(total_peso, 3),
                "distancia_estimada_total": round(distancia_estimada, 2),
                "promedio_unidades_por_wave": round(total_unidades / len(waves_info), 2) if len(waves_info) > 0 else 0,
                "waves": waves_info,
            })
        except (ValueError, KeyError) as e:
            return jsonify({"error": f"Estrategia '{estrategia}': {str(e)}"}), 400

    # Marcar si todos los modos dieron exactamente el mismo resultado, para
    # que el front pueda mostrar un aviso en vez de tablas idénticas.
    def _resumen(c):
        return (
            c["total_waves"], c["total_unidades"], c["total_peso_kg"],
            c["distancia_estimada_total"],
            [(w["wave_id"], w["pedidos"], w["unidades"]) for w in c["waves"]],
        )

    mismo_resultado = True
    for c in comparacion[1:]:
        if _resumen(c) != _resumen(comparacion[0]):
            mismo_resultado = False

    return jsonify({
        "comparacion": comparacion,
        "mismo_resultado": mismo_resultado,
    })


# ---------------------------------------------------------------------------
# POST /api/routes/plan
# ---------------------------------------------------------------------------

@app.route("/api/routes/plan", methods=["POST"])
def api_routes_plan():
    """
    Calcula el recorrido de una wave con la estrategia y buscador elegidos.

    Cuerpo esperado (application/json):
    {
        "escenario":  { ...Scenario.toJSON()... },
        "wave_id":    "WAVE01",
        "estrategia": "orden" | "cercania",
        "buscador":   "bfs"   | "astar"
    }

    Respuesta exitosa (200): RouteResult.to_dict(), que incluye
        path, paradas, descargas, distancia_total, nodos_visitados, aristas_recorridas,
        nodos_expandidos, tiempo_ms.

    Respuesta de error (400):
    { "error": "mensaje explicativo" }
    """
    body = request.get_json()
    if body is None:
        return jsonify({"error": "El cuerpo de la peticion debe ser JSON."}), 400

    escenario  = body.get("escenario")
    wave_id    = body.get("wave_id")
    estrategia = body.get("estrategia", "cercania")
    buscador   = body.get("buscador",   "bfs")
    estrategia_wave = body.get("estrategia_wave", "por_cercania")

    if escenario is None:
        return jsonify({"error": "Falta la clave 'escenario' en el cuerpo."}), 400
    if wave_id is None:
        return jsonify({"error": "Falta la clave 'wave_id' en el cuerpo."}), 400

    try:
        warehouse = _build_warehouse(escenario)
        manager   = _build_wave_manager(escenario, warehouse)
        manager.generate_waves(estrategia_wave=estrategia_wave)
        manager.assign_pickers()
    except (ValueError, KeyError) as e:
        return jsonify({"error": str(e)}), 400

    wave = None
    for w in manager.get_waves():
        if w.wave_id == wave_id:
            wave = w
            break

    if wave is None:
        return jsonify({"error": f"No existe la wave '{wave_id}'."}), 400

    try:
        graph     = generate_graph(warehouse)
        resultado = plan_route(wave, warehouse, graph, estrategia, buscador,
                               inicio=_picker_start(wave))
    except (ValueError, KeyError) as e:
        return jsonify({"error": str(e)}), 400

    return jsonify(resultado.to_dict())


# ---------------------------------------------------------------------------
# POST /api/routes/compare
# ---------------------------------------------------------------------------

@app.route("/api/routes/compare", methods=["POST"])
def api_routes_compare():
    """
    Corre todas las estrategias de recorrido sobre la misma wave y devuelve
    los resultados comparados.

    Cuerpo esperado (application/json):
    {
        "escenario": { ...Scenario.toJSON()... },
        "wave_id":   "W1",
        "buscador":  "bfs" | "astar"
    }

    Respuesta exitosa (200):
    {
        "orden":    { ...RouteResult.to_dict()... },
        "cercania": { ...RouteResult.to_dict()... }
    }

    Respuesta de error (400):
    { "error": "mensaje explicativo" }
    """
    body = request.get_json()
    if body is None:
        return jsonify({"error": "El cuerpo de la peticion debe ser JSON."}), 400

    escenario = body.get("escenario")
    wave_id   = body.get("wave_id")
    buscador  = body.get("buscador", "bfs")
    todas     = body.get("todas_combinaciones", False) or body.get("all_combinations", False)

    if escenario is None:
        return jsonify({"error": "Falta la clave 'escenario' en el cuerpo."}), 400

    if todas:
        try:
            combinaciones_resultado = []
            combos = [
                ("cercania", "bfs"),
                ("cercania", "astar"),
                ("orden", "bfs"),
                ("orden", "astar"),
            ]
            total_waves = 0
            for est, bus in combos:
                wh = _build_warehouse(escenario)
                wm = _build_wave_manager(escenario, wh)
                wm.generate_waves()
                wm.assign_pickers()
                total_waves = len(wm.get_waves())
                sim = Simulation(wh, wm, est, bus)
                sim.run()
                metr = sim.metrics()
                metr["estrategia"] = est
                metr["buscador"] = bus
                if sim.error:
                    metr["error"] = sim.error
                combinaciones_resultado.append(metr)

            return jsonify({
                "tipo": "todas_waves",
                "total_waves": total_waves,
                "combinaciones": combinaciones_resultado,
            })
        except (ValueError, KeyError) as e:
            return jsonify({"error": str(e)}), 400

    if wave_id is None:
        return jsonify({"error": "Falta la clave 'wave_id' en el cuerpo."}), 400

    try:
        warehouse = _build_warehouse(escenario)
        manager   = _build_wave_manager(escenario, warehouse)
        manager.generate_waves()
        manager.assign_pickers()
    except (ValueError, KeyError) as e:
        return jsonify({"error": str(e)}), 400

    wave = None
    for w in manager.get_waves():
        if w.wave_id == wave_id:
            wave = w
            break

    if wave is None:
        return jsonify({"error": f"No existe la wave '{wave_id}'."}), 400

    try:
        graph  = generate_graph(warehouse)
        inicio = _picker_start(wave)
        combinaciones = compare_all_combinations(wave, warehouse, graph, inicio=inicio)
        return jsonify({
            "wave_id": wave_id,
            "combinaciones": [r.to_dict() for r in combinaciones]
        })
    except (ValueError, KeyError) as e:
        return jsonify({"error": str(e)}), 400


# ---------------------------------------------------------------------------
# POST /api/simulacion
# ---------------------------------------------------------------------------

@app.route("/api/simulacion", methods=["POST"])
def api_simulacion():
    """
    Corre la simulacion completa (todas las waves, todos los pickers a la
    vez, con colisiones) y devuelve lo que el frontend tiene que dibujar.

    Cuerpo esperado (application/json):
    {
        "escenario":  { ...Scenario.toJSON()... },
        "estrategia": "orden" | "cercania",
        "buscador":   "bfs"   | "astar"
    }

    Respuesta exitosa (200): Simulation.to_dict()
    {
        "frames":   [ {"tick", "pickers", "zonas", "eventos"}, ... ],
        "metricas": { "ticks", "distancia_total", "esperas", "desvios", ... },
        "rutas":    [ metricas de cada recorrido calculado ],
        "error":    null o mensaje si la simulacion no pudo terminar
    }

    Respuesta de error (400):
    { "error": "mensaje explicativo" }
    """
    body = request.get_json()
    if body is None:
        return jsonify({"error": "El cuerpo de la peticion debe ser JSON."}), 400

    escenario  = body.get("escenario")
    estrategia = body.get("estrategia", "cercania")
    buscador   = body.get("buscador",   "bfs")
    velocidad  = body.get("velocidad", 1)   # multiplicador de ticks por frame (1..10)
    estrategia_wave = body.get("estrategia_wave", "por_cercania")

    if escenario is None:
        return jsonify({"error": "Falta la clave 'escenario' en el cuerpo."}), 400

    try:
        velocidad = int(velocidad)
        if velocidad < 1 or velocidad > 10:
            raise ValueError("La velocidad debe estar entre 1 y 10.")
    except (ValueError, TypeError) as e:
        return jsonify({"error": str(e)}), 400

    try:
        warehouse = _build_warehouse(escenario)
        manager   = _build_wave_manager(escenario, warehouse)
        manager.generate_waves(estrategia_wave=estrategia_wave)
        manager.assign_pickers()
        simulacion = Simulation(
            warehouse, manager, estrategia, buscador,
            speed_multiplier=velocidad,
        )
        simulacion.run()
    except (ValueError, KeyError) as e:
        return jsonify({"error": str(e)}), 400

    return jsonify(simulacion.to_dict())


# ---------------------------------------------------------------------------
# POST /api/escenario/validar
# ---------------------------------------------------------------------------

@app.route("/api/escenario/validar", methods=["POST"])
def api_escenario_validar():
    """
    Valida un escenario guardado antes de cargarlo (§17 Persistencia).

    El frontend lee el archivo .json que eligió el usuario y lo manda tal
    cual. El back es el que decide: arma el Warehouse y el WaveManager con
    las mismas validaciones que usan las demás rutas y revisa la sección
    opcional "estado" (la simulación guardada).

    Cuerpo esperado (application/json): el contenido del archivo guardado,
    es decir Scenario.toJSON() más, opcionalmente, "estado".

    Respuesta (200), aunque el escenario no sea válido:
    {
        "valido":  true | false,
        "errores": ["motivo", ...],
        "avisos":  ["cosas que no impiden cargarlo", ...]
    }

    Respuesta de error (400): el cuerpo no es JSON.
    """
    body = request.get_json(silent=True)
    if body is None:
        return jsonify({"error": "El cuerpo de la peticion debe ser JSON."}), 400

    return jsonify(validate_scenario(body))


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True)
