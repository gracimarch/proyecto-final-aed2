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

Diseno stateless: el cliente envia el estado completo del escenario en cada
pedido. El servidor no guarda nada entre llamadas; cada request es
independiente.
"""

from flask import Flask, render_template, request, jsonify

from models.warehouse import Warehouse
from models.wave_manager import WaveManager
from algorithms.graph_builder import generate_graph
from algorithms.routing import plan_route, compare_strategies


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
                "wave_id": "W1",
                "status":  "ABIERTA",
                "picker_id": "PK_01",
                "prioridad": 5,
                "pedidos":  ["PED_01", "PED_02"],
                "unidades": 3,
                "peso_kg":  7.7
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
        manager.generate_waves()
        manager.assign_pickers()
    except (ValueError, KeyError) as e:
        return jsonify({"error": str(e)}), 400

    waves_dict = []
    for wave in manager.get_waves():
        picker_id = None
        if wave.picker is not None:
            picker_id = wave.picker.picker_id

        pedidos_ids = []
        for entry in wave.entries:
            pedidos_ids.append(entry.order.order_id)

        waves_dict.append({
            "wave_id":   wave.wave_id,
            "status":    wave.status.value,
            "picker_id": picker_id,
            "prioridad": wave.priority(),
            "pedidos":   pedidos_ids,
            "unidades":  wave.current_units(),
            "peso_kg":   round(wave.total_weight(), 3),
        })

    return jsonify({"waves": waves_dict})


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
        "wave_id":    "W1",
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

    if escenario is None:
        return jsonify({"error": "Falta la clave 'escenario' en el cuerpo."}), 400
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

    if escenario is None:
        return jsonify({"error": "Falta la clave 'escenario' en el cuerpo."}), 400
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
        graph       = generate_graph(warehouse)
        comparacion = compare_strategies(wave, warehouse, graph, buscador,
                                         inicio=_picker_start(wave))
    except (ValueError, KeyError) as e:
        return jsonify({"error": str(e)}), 400

    resultado = {}
    for estrategia, route_result in comparacion.items():
        resultado[estrategia] = route_result.to_dict()

    return jsonify(resultado)


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True)
