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
 * @param {string} waveId      ID de la wave a recorrer (ej. "WAVE_01").
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
 * Corre todas las estrategias sobre la misma wave y devuelve la comparacion.
 *
 * @param {Object} escenario  Resultado de Scenario.toJSON().
 * @param {string} waveId     ID de la wave.
 * @param {string} buscador   "bfs" o "astar".
 * @returns {Promise<Object>} Objeto con una clave por estrategia, cada una
 *     con su RouteResult serializado: { orden: {...}, cercania: {...} }.
 */
async function apiCompareStrategies(escenario, waveId, buscador) {
    return await _post('/api/routes/compare', {
        escenario,
        wave_id:  waveId,
        buscador: buscador,
    });
}
