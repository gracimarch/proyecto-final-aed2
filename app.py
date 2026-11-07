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

Diseno stateless: el cliente envia el estado completo del escenario en cada
pedido. El servidor no guarda nada entre llamadas; cada request es
independiente.
"""

from flask import Flask, render_template, request, jsonify

from models.warehouse import Warehouse
from models.wave_manager import WaveManager
from algorithms.graph_builder import generate_graph
from algorithms.routing import plan_route, compare_strategies, compare_all_combinations
from models.simulation import Simulation


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
        estrategia_wave = data.get("estrategia_wave", "por_pedido")
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
    Genera las waves con ambas estrategias ("por_pedido" y "por_cercania")
    sobre el mismo escenario y devuelve los resultados comparados, para que
    el front pueda mostrar dos tablas y elegir la que mejor convenga.

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
            }
        ]
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
    for estrategia in ("por_pedido", "por_cercania"):
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

            comparacion.append({
                "estrategia":               estrategia,
                "total_waves":              len(waves_info),
                "total_unidades":           total_unidades,
                "total_peso_kg":            round(total_peso, 3),
                "distancia_estimada_total": round(distancia_estimada, 2),
                "promedio_unidades_por_wave": round(total_unidades / len(waves_info), 2) if len(waves_info) > 0 else 0,
                "waves": waves_info,
            })
        except (ValueError, KeyError) as e:
            return jsonify({"error": f"Estrategia '{estrategia}': {str(e)}"}), 400

    # Marcar si ambos modos dieron exactamente el mismo resultado, para que
    # el front pueda mostrar un aviso en vez de dos tablas idénticas.
    mismo_resultado = (
        len(comparacion) == 2
        and comparacion[0]["total_waves"] == comparacion[1]["total_waves"]
        and comparacion[0]["total_unidades"] == comparacion[1]["total_unidades"]
        and comparacion[0]["total_peso_kg"] == comparacion[1]["total_peso_kg"]
        and comparacion[0]["distancia_estimada_total"] == comparacion[1]["distancia_estimada_total"]
        and [ (w["wave_id"], w["pedidos"], w["unidades"]) for w in comparacion[0]["waves"] ]
        == [ (w["wave_id"], w["pedidos"], w["unidades"]) for w in comparacion[1]["waves"] ]
    )

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
    estrategia_wave = body.get("estrategia_wave", "por_pedido")

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
    estrategia_wave = body.get("estrategia_wave", "por_pedido")

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
# Punto de entrada
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True)
