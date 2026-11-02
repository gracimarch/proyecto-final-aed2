/* ================================================================
   API.JS
   Funciones que se comunican con el servidor Flask.

   Todas devuelven una Promise que resuelve con el dato pedido, o
   rechaza con un objeto { error: "..." } si algo falla (sea un
   error de red o un error de negocio devuelto por el servidor).

   Cada funcion espera como argumento el escenario completo tal y
   como lo devuelve Scenario.toJSON(), de modo que el servidor
   pueda reconstruir el Warehouse en Python.
================================================================ */


// ---------------------------------------------------------------------------
// Helper interno: hace el fetch y normaliza errores de red y de negocio.
// ---------------------------------------------------------------------------

async function _post(url, body) {
    let response;
    try {
        response = await fetch(url, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify(body),
        });
    } catch (networkError) {
        // fetch rechaza la Promise si no hay conexion con el servidor.
        throw { error: 'No se pudo conectar con el servidor.' };
    }

    const data = await response.json();

    // El servidor devuelve { error: "..." } con HTTP 4xx cuando algo sale mal.
    if (!response.ok) {
        throw data;          // data.error tiene el mensaje
    }

    return data;
}


// ---------------------------------------------------------------------------
// Generar waves
// ---------------------------------------------------------------------------

/**
 * Le pide al servidor que genere las waves para el escenario dado.
 *
 * @param {Object} escenario  Resultado de Scenario.toJSON().
 * @returns {Promise<Object[]>} Array de objetos wave con los campos:
 *     wave_id, status, picker_id, prioridad, pedidos, unidades, peso_kg.
 */
async function apiGenerateWaves(escenario) {
    const data = await _post('/api/waves/generate', escenario);
    return data.waves;
}


// ---------------------------------------------------------------------------
// Planificar recorrido de una wave
// ---------------------------------------------------------------------------

/**
 * Le pide al servidor el recorrido de una wave con la estrategia elegida.
 *
 * @param {Object} escenario   Resultado de Scenario.toJSON().
 * @param {string} waveId      ID de la wave a recorrer (ej. "WAVE01").
 * @param {string} estrategia  "orden" o "cercania".
 * @param {string} buscador    "bfs" o "astar".
 * @returns {Promise<Object>}  RouteResult serializado con los campos:
 *     estrategia, buscador, path, paradas,
 *     distancia_total, aristas_recorridas, nodos_visitados,
 *     nodos_expandidos, tiempo_ms.
 */
async function apiPlanRoute(escenario, waveId, estrategia, buscador) {
    return await _post('/api/routes/plan', {
        escenario,
        wave_id:    waveId,
        estrategia: estrategia,
        buscador:   buscador,
    });
}


// ---------------------------------------------------------------------------
// Comparar todas las estrategias de recorrido
// ---------------------------------------------------------------------------

/**
 * Corre todas las combinaciones de estrategias y algoritmos
 * (Cercanía y Orden con BFS y A*) sobre la wave seleccionada.
 *
 * @param {Object} escenario  Resultado de Scenario.toJSON().
 * @param {string} waveId     ID de la wave.
 * @returns {Promise<Object>} Objeto { wave_id, combinaciones: [ RouteResult, ... ] }.
 */
async function apiCompareStrategies(escenario, waveId) {
    return await _post('/api/routes/compare', {
        escenario,
        wave_id: waveId,
    });
}


/**
 * Corre la simulación de todas las waves en simultáneo para todas las combinaciones
 * posibles de estrategias y algoritmos (Cercanía con BFS, Cercanía con A*, Orden con BFS, Orden con A*).
 *
 * @param {Object} escenario  Resultado de Scenario.toJSON().
 * @returns {Promise<Object>} Objeto { tipo: 'todas_waves', total_waves, combinaciones: [ ... ] }.
 */
async function apiCompareAllCombinations(escenario) {
    return await _post('/api/routes/compare', {
        escenario,
        todas_combinaciones: true,
    });
}


// ---------------------------------------------------------------------------
// Simulacion completa (la hace el backend; el frontend solo la dibuja)
// ---------------------------------------------------------------------------

/**
 * Le pide al servidor que simule todas las waves con todos los pickers.
 *
 * @param {Object} escenario   Resultado de Scenario.toJSON().
 * @param {string} estrategia  "orden" o "cercania".
 * @param {string} buscador    "bfs" o "astar".
 * @returns {Promise<Object>}  { frames, metricas, rutas, error }.
 *     Cada frame: { tick, pickers: [{id, x, y, estado, wave, carga_kg, paso}],
 *                   zonas: {zona_id: kg}, eventos: [...] }.
 */
async function apiSimulate(escenario, estrategia, buscador) {
    return await _post('/api/simulacion', {
        escenario,
        estrategia: estrategia,
        buscador:   buscador,
    });
}
