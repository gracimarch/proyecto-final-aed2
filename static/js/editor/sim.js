/* ================================================================
   SIM.JS
   Conecta los controles del panel derecho (Simulacion, Metricas,
   Productos recogidos) con el servidor Flask a traves de api.js.

   Responsabilidades de este modulo:
     - Boton "Generar waves":  llama a apiGenerateWaves y puebla la
       lista de waves del sidebar izquierdo.
     - Boton "Play":           pide las rutas de TODAS las waves
       asignadas y arranca la animacion concurrente de todos los
       pickers en el canvas.
     - Boton "Pause":          pausa la animacion en curso.
     - Boton "Step":           avanza la animacion un solo tick.
     - Boton "Restart":        vuelve la animacion al inicio.
     - Boton "Comparar":       llama a apiCompareStrategies y muestra
       la tabla de comparacion (requiere wave seleccionada con click).
     - Actualiza el panel de flota, las tarjetas de metricas y la
       lista de recogidos.

   SIMULACION CONCURRENTE MULTI-PICKER:
     - En cada "tick" de animacion, todos los pickers activos avanzan
       un paso simultaneamente.
     - Deteccion y resolucion integral de conflictos (§ 3.6 de las consignas):
         * Conflictos de vertice: dos pickers intentan entrar a la misma celda.
         * Conflictos de cruce frontal (swap): se resuelve mediante desvio
           lateral (sidestep) a una celda libre de pasillo, o detencion preventiva.
         * Conflictos con agentes detenidos o en espera.
     - Asignacion dinamica: a medida que un picker completa su wave
       y regresa a despacho, se le asigna automaticamente la siguiente
       wave pendiente de la cola compatible con su capacidad de carga.

   Variables que se leen de otros modulos (globales):
     _scenario   : el escenario activo (definido en ui.js).
     WarehouseRenderer : clase del canvas (definida en renderer.js).
   Funciones que se usan de otros modulos:
     showToast(msg, type)  : notificaciones (definida en ui.js).
     apiGenerateWaves, apiPlanRoute, apiCompareStrategies  (api.js).
================================================================ */


// ---------------------------------------------------------------------------
// Estado de la simulacion
// ---------------------------------------------------------------------------

/** Waves devueltas por el servidor en el ultimo generate. */
let _waves = [];

/** Copia de las waves generadas para poder reiniciar al estado original con Restart. */
let _initialWavesSnapshot = [];

/**
 * Lista de agentes activos en la simulacion.
 * Cada agente es un objeto:
 *   { pickerId, waveId, pickerPriority, path, step, waitTick, pickingCooldown, routeResult }
 *
 * - path             : [[x,y], ...] camino completo calculado por el backend.
 * - step             : indice del proximo paso a aplicar.
 * - waitTick         : si es true, el agente espera este tick por colision (no avanza).
 * - pickingCooldown  : ticks restantes de pausa individual por recogida de producto.
 *                      Mientras sea > 0 el agente permanece en su celda actual sin
 *                      avanzar, permitiendo que los demas pickers sigan moviendose.
 * - routeResult      : objeto completo devuelto por el backend (con metricas).
 * - pickerPriority   : prioridad de la wave actual (mayor = cede menos el paso).
 */
let _agents = [];

/** Historial de todas las rutas planificadas para calcular metricas de la flota. */
let _allPlannedRoutes = [];

/** ID del setTimeout del loop de animacion, o null si esta pausado. */
let _animTimer = null;

/**
 * Wave seleccionada con click en la lista para la funcion "Comparar".
 * En la simulacion concurrente NO restringe cuales waves se animan.
 */
let _selectedWaveId = null;

/**
 * Indica si el usuario cambio manualmente el modo de enfoque durante
 * la simulacion activa. Evita que simPlanAndPlay lo sobreescriba.
 */
let _focusModeUserSet = false;


// ---------------------------------------------------------------------------
// Referencias a elementos DOM del panel derecho
// ---------------------------------------------------------------------------

function _dom(id) { return document.getElementById(id); }


// ---------------------------------------------------------------------------
// Velocidades en ms/tick segun el valor del slider (1 a 5)
// ---------------------------------------------------------------------------

const SPEED_MS = { 1: 500, 2: 250, 3: 120, 4: 60, 5: 20 };

function _tickDelayMs() {
    const val = parseInt(_dom('range-speed')?.value || '1');
    return SPEED_MS[val] || 200;
}


// Mapa de posiciones iniciales de pickers: pickerId -> { x, y }
const _initialPickerPositions = new Map();

function _saveInitialPickerPosition(picker) {
    if (!_initialPickerPositions.has(picker.id)) {
        _initialPickerPositions.set(picker.id, { x: picker.x, y: picker.y });
    }
}

function _restorePickerPositions() {
    const sc = _getScenario();
    if (!sc) return;
    for (const [id, pos] of _initialPickerPositions) {
        const picker = sc.pickers.find(p => p.id === id);
        if (picker) {
            picker.x = pos.x;
            picker.y = pos.y;
        }
    }
}


// ---------------------------------------------------------------------------
// Helpers: leer el escenario activo y parametros de ruteo
// ---------------------------------------------------------------------------

function _getScenario() {
    return typeof _scenario !== 'undefined' ? _scenario : null;
}

function _getStrategyValue() {
    const val = _dom('select-strategy')?.value || 'order';
    return val === 'order' ? 'orden' : 'cercania';
}

function _getBuscadorValue() {
    return _dom('select-buscador')?.value || 'bfs';
}


// ---------------------------------------------------------------------------
// Generar waves
// ---------------------------------------------------------------------------

async function simGenerateWaves() {
    const sc = _getScenario();
    if (!sc) { showToast('Cargá un escenario primero.', 'warning'); return; }

    if (!sc.orders || sc.orders.length === 0) {
        showToast('El escenario no tiene pedidos para procesar.', 'warning');
        return;
    }

    const btn = _dom('btn-generate-wave');
    if (btn) btn.disabled = true;

    try {
        _waves = await apiGenerateWaves(sc.toJSON());
        _initialWavesSnapshot = JSON.parse(JSON.stringify(_waves));
        _renderWavesList();
        _renderFleetStatus();
        showToast(`${_waves.length} wave(s) generada(s).`, 'success');
    } catch (err) {
        showToast(err.error || 'Error al generar waves.', 'error');
    } finally {
        if (btn) btn.disabled = false;
    }
}

/** Rellena la lista de waves en el sidebar izquierdo (#waves-list). */
function _renderWavesList() {
    const list = _dom('waves-list');
    if (!list) return;

    if (_waves.length === 0) {
        list.innerHTML = '<p class="empty-msg">Sin waves generadas.</p>';
        return;
    }

    const items = _waves.map(w => {
        const pickerTexto = w.picker_id ? w.picker_id : '— en espera —';
        const isSelected  = w.wave_id === _selectedWaveId;
        return `
        <div class="wave-item ${isSelected ? 'wave-item--selected' : ''}"
             data-wave-id="${w.wave_id}" style="cursor:pointer">
            <div class="wave-item__header">
                <span class="wave-item__id">${w.wave_id}</span>
                <span class="wave-item__badge">${w.status}</span>
            </div>
            <div class="wave-item__meta">
                <span>Prioridad ${w.prioridad}</span>
                <span>${w.unidades} uds · ${w.peso_kg} kg</span>
            </div>
            <div class="wave-item__meta">
                <span>Picker: ${pickerTexto}</span>
                <span>${w.pedidos.join(', ')}</span>
            </div>
        </div>`;
    }).join('');

    list.innerHTML = items;

    // Click en una card de wave: la selecciona para "Comparar".
    list.querySelectorAll('.wave-item').forEach(card => {
        card.addEventListener('click', () => {
            _selectedWaveId = card.dataset.waveId;
            _renderWavesList();   // re-renderiza para destacar visualmente la wave
            showToast(`Wave ${_selectedWaveId} seleccionada para comparar.`, 'info');
        });
    });
}


// ---------------------------------------------------------------------------
// Panel de flota (estado en vivo de todos los pickers)
// ---------------------------------------------------------------------------

function _renderFleetStatus() {
    const container = _dom('fleet-status');
    if (!container) return;

    const rows = _agents.length > 0 ? _buildRowsFromAgents() : _buildRowsFromWaves();

    if (rows.length === 0) {
        container.innerHTML = '<p class="empty-msg">Sin pickers asignados.</p>';
        return;
    }

    container.innerHTML = rows.join('');
}

function _buildRowsFromWaves() {
    return _waves
        .filter(w => w.picker_id)
        .map(w => {
            const sc = _getScenario();
            const picker = sc ? sc.pickers.find(p => p.id === w.picker_id) : null;
            const color  = picker ? picker.color : '#888';
            return `
            <div class="fleet-row">
                <span class="fleet-row__dot" style="background:${color}"></span>
                <span class="fleet-row__picker">${w.picker_id}</span>
                <span class="fleet-row__wave">${w.wave_id}</span>
                <span class="fleet-row__status">${w.status}</span>
            </div>`;
        });
}

function _buildRowsFromAgents() {
    const sc = _getScenario();
    return _agents.map(ag => {
        const picker = sc ? sc.pickers.find(p => p.id === ag.pickerId) : null;
        const color  = picker ? picker.color : '#888';
        const total  = ag.path.length;
        const pct    = total > 0 ? Math.round((ag.step / total) * 100) : 0;

        let label = 'EN_CAMINO';
        if (ag.step >= total) {
            label = 'COMPLETA';
        } else if (ag.pickingCooldown > 0) {
            label = 'RECOGIENDO';
        } else if (ag.waitTick) {
            label = 'ESPERANDO';
        }

        return `
        <div class="fleet-row">
            <span class="fleet-row__dot" style="background:${color}"></span>
            <span class="fleet-row__picker">${ag.pickerId}</span>
            <span class="fleet-row__wave">${ag.waveId}</span>
            <span class="fleet-row__status">${label} ${pct}%</span>
        </div>`;
    });
}


// ---------------------------------------------------------------------------
// Planificacion y construccion de agentes
// ---------------------------------------------------------------------------

async function _buildAgent(wave, sc) {
    const estrategia = _getStrategyValue();
    const buscador   = _getBuscadorValue();

    try {
        const routeResult = await apiPlanRoute(sc.toJSON(), wave.wave_id, estrategia, buscador);

        const picker = sc.pickers.find(p => p.id === wave.picker_id);
        if (picker) {
            _saveInitialPickerPosition(picker);
        }

        return {
            pickerId:        wave.picker_id,
            waveId:          wave.wave_id,
            pickerPriority:  wave.prioridad,
            path:            routeResult.path,
            step:            0,
            waitTick:        false,
            pickingCooldown: 0,
            routeResult,
        };
    } catch (err) {
        showToast(`Error en ruta de ${wave.wave_id}: ${err.error || err}`, 'error');
        return null;
    }
}

async function simPlanAndPlay() {
    const sc = _getScenario();
    if (!sc) { showToast('Cargá un escenario primero.', 'warning'); return; }

    // Si hay agentes activos y la animacion estaba pausada → reanudar.
    if (_agents.length > 0 && _animTimer === null) {
        _scheduleNextTick();
        _updatePlayPauseBtn(true);
        return;
    }

    const wavesAsignadas = _waves.filter(w => w.picker_id);
    if (wavesAsignadas.length === 0) {
        showToast('Generá waves primero (se necesita al menos un picker asignado).', 'warning');
        return;
    }

    simPause();
    _restorePickerPositions();
    _agents           = [];
    _allPlannedRoutes = [];
    _clearCollected();
    _clearMetrics();
    _clearRoutesFromRenderer();

    const btn = _dom('btn-play-pause');
    if (btn) btn.disabled = true;

    showToast('Calculando recorridos de la flota...', 'info');

    const promesas = wavesAsignadas.map(w => _buildAgent(w, sc));
    const resultados = await Promise.all(promesas);

    _agents = resultados.filter(ag => ag !== null);

    if (_agents.length === 0) {
        showToast('No se pudo calcular ninguna ruta.', 'error');
        if (btn) btn.disabled = false;
        return;
    }

    _allPlannedRoutes = _agents.map(ag => ag.routeResult);
    _updateFleetMetrics();
    _pushRoutesToRenderer();

    for (const ag of _agents) {
        const waveInfo = _waves.find(w => w.wave_id === ag.waveId);
        if (waveInfo) waveInfo.status = 'EN_PROCESO';
    }
    _renderWavesList();
    _renderFleetStatus();

    if (!_focusModeUserSet) {
        _setFocusMode(true);
    }

    showToast(`Animando ${_agents.length} picker(s) concurrentemente...`, 'success');
    _updatePlayPauseBtn(true);
    if (btn) btn.disabled = false;
    _scheduleNextTick();
}


// ---------------------------------------------------------------------------
// Deteccion y resolucion integral de colisiones (§ 3.6 de las consignas)
// ---------------------------------------------------------------------------

/**
 * Verifica si una celda (x, y) es pasillo transitable según el escenario.
 */
function _isWalkableCell(x, y, sc) {
    if (!sc.isInBounds(x, y)) return false;
    if (sc.getRackAt(x, y)) return false;
    if (sc.doors && sc.doors.some(d => d.x === x && d.y === y)) return false;
    if (sc.dispatchZones && sc.dispatchZones.some(z => x >= z.x && x < z.x + z.width && y >= z.y && y < z.y + z.height)) return false;
    return true;
}

/**
 * Verifica si el sentido del pasillo permite el movimiento de (fromX, fromY) a (toX, toY).
 */
function _isDirectionAllowed(fromX, fromY, toX, toY, sc) {
    const aisle = sc.getAisleAt(toX, toY) || sc.getAisleAt(fromX, fromY);
    if (!aisle || aisle.sentido === 'AMBOS') return true;

    const dx = toX - fromX;
    const dy = toY - fromY;

    if (aisle.sentido === 'N' && dy < 0) return false;
    if (aisle.sentido === 'S' && dy > 0) return false;
    if (aisle.sentido === 'E' && dx < 0) return false;
    if (aisle.sentido === 'O' && dx > 0) return false;

    return true;
}

/**
 * Busca una celda adyacente libre de pasillo para esquivar un choque frontal.
 */
function _findSidestep(picker, forbiddenCells, sc) {
    const px = picker.x;
    const py = picker.y;
    const candidates = [
        [px, py + 1],
        [px, py - 1],
        [px + 1, py],
        [px - 1, py],
    ];

    for (const [cx, cy] of candidates) {
        const key = `${cx},${cy}`;
        if (forbiddenCells.has(key)) continue;
        if (!_isWalkableCell(cx, cy, sc)) continue;
        if (!_isDirectionAllowed(px, py, cx, cy, sc)) continue;
        return [cx, cy];
    }
    return null;
}

/** Devuelve true si agA debe ceder el paso a agB. */
function _debeEsperar(agA, agB) {
    if (agA.pickerPriority !== agB.pickerPriority) {
        return agA.pickerPriority < agB.pickerPriority;
    }
    return agA.pickerId > agB.pickerId;
}

/**
 * Resuelve todos los conflictos entre los agentes antes de ejecutar el tick:
 *   1. Cruces frontales (head-on swap): se resuelven mediante evasión lateral (sidestep)
 *      o frenando ambos agentes antes de que compartan celda.
 *   2. Conflictos de vértice: dos pickers intentando pisar la misma celda al mismo tiempo.
 *   3. Choques contra agentes detenidos o en espera.
 */
function _resolveCollisions() {
    const sc = _getScenario();
    if (!sc) return;

    for (const ag of _agents) {
        ag.waitTick = false;
    }

    const currPos = _agents.map(ag => {
        const p = sc.pickers.find(pk => pk.id === ag.pickerId);
        return p ? [p.x, p.y] : null;
    });

    const targetPos = _agents.map(ag => {
        if (ag.step >= ag.path.length) return null;
        // Un agente en cooldown de recogida no se mueve: es un obstaculo
        // estatico para los demas. No tiene celda destino este tick.
        if (ag.pickingCooldown > 0) return null;
        return ag.path[ag.step];
    });

    // ── 1. Cruces frontales (Head-on / Swap) ─────────────────────────
    for (let i = 0; i < _agents.length; i++) {
        if (!targetPos[i] || !currPos[i]) continue;

        for (let j = i + 1; j < _agents.length; j++) {
            if (!targetPos[j] || !currPos[j]) continue;

            const ci = currPos[i], ti = targetPos[i];
            const cj = currPos[j], tj = targetPos[j];

            const esCruceFrontal = (ti[0] === cj[0] && ti[1] === cj[1]) &&
                                   (tj[0] === ci[0] && tj[1] === ci[1]);

            if (esCruceFrontal) {
                const cedeI = _debeEsperar(_agents[i], _agents[j]);
                const cedeIdx = cedeI ? i : j;

                const cedePicker = sc.pickers.find(pk => pk.id === _agents[cedeIdx].pickerId);
                const cedeAg     = _agents[cedeIdx];

                // Celdas prohibidas para esquivar
                const forbidden = new Set();
                for (let k = 0; k < _agents.length; k++) {
                    if (currPos[k]) forbidden.add(`${currPos[k][0]},${currPos[k][1]}`);
                    if (targetPos[k] && k !== cedeIdx) forbidden.add(`${targetPos[k][0]},${targetPos[k][1]}`);
                }

                const sidestep = cedePicker ? _findSidestep(cedePicker, forbidden, sc) : null;

                if (sidestep) {
                    // El agente que cede da un paso lateral hacia sidestep y luego retoma su ruta
                    cedeAg.path.splice(cedeAg.step, 0, sidestep, [currPos[cedeIdx][0], currPos[cedeIdx][1]]);
                    targetPos[cedeIdx] = sidestep;
                } else {
                    // Si no hay celda lateral libre en este tick, ambos se detienen
                    _agents[i].waitTick = true;
                    _agents[j].waitTick = true;
                }
            }
        }
    }

    // ── 2. Conflictos de vértice (ambos quieren la misma celda destino) ─
    for (let i = 0; i < _agents.length; i++) {
        if (!targetPos[i] || _agents[i].waitTick) continue;

        for (let j = i + 1; j < _agents.length; j++) {
            if (!targetPos[j] || _agents[j].waitTick) continue;

            if (targetPos[i][0] === targetPos[j][0] && targetPos[i][1] === targetPos[j][1]) {
                const cedeI = _debeEsperar(_agents[i], _agents[j]);
                if (cedeI) {
                    _agents[i].waitTick = true;
                } else {
                    _agents[j].waitTick = true;
                }
            }
        }
    }

    // ── 3. Prohibir entrar a una celda ocupada por un picker que NO se mueve ──
    let cambio = true;
    while (cambio) {
        cambio = false;
        for (let i = 0; i < _agents.length; i++) {
            if (!targetPos[i] || _agents[i].waitTick) continue;

            for (let j = 0; j < _agents.length; j++) {
                if (i === j || !currPos[j]) continue;

                const jQuedaEnCelda = _agents[j].waitTick
                    || _agents[j].pickingCooldown > 0
                    || _agents[j].step >= _agents[j].path.length;

                if (jQuedaEnCelda && targetPos[i][0] === currPos[j][0] && targetPos[i][1] === currPos[j][1]) {
                    _agents[i].waitTick = true;
                    cambio = true;
                }
            }
        }
    }
}


// ---------------------------------------------------------------------------
// Asignacion dinamica de waves a pickers liberados
// ---------------------------------------------------------------------------

/**
 * Cuando un picker completa su wave en la zona de despacho, busca en
 * la cola la siguiente wave pendiente compatible con su capacidad de carga
 * y planifica su recorrido de inmediato.
 */
async function _tryAssignNextWave(ag, sc) {
    if (!sc) return false;
    const picker = sc.pickers.find(p => p.id === ag.pickerId);
    if (!picker) return false;

    // Capacidad del picker en JS: la propiedad es capacidadKg
    const pickerCap = picker.capacidadKg != null ? picker.capacidadKg : (picker.capacidad_carga_kg || 100);

    // Buscar una wave pendiente sin picker asignado que soporte el peso
    const nextWave = _waves.find(w => {
        const sinPicker = !w.picker_id || w.picker_id === '';
        const pendiente = w.status === 'ABIERTA';
        const entraPeso = w.peso_kg <= pickerCap;
        return sinPicker && pendiente && entraPeso;
    });

    if (!nextWave) return false;

    nextWave.picker_id = ag.pickerId;
    nextWave.status    = 'EN_PROCESO';

    const estrategia = _getStrategyValue();
    const buscador   = _getBuscadorValue();

    try {
        const routeResult = await apiPlanRoute(sc.toJSON(), nextWave.wave_id, estrategia, buscador);
        _allPlannedRoutes.push(routeResult);
        _updateFleetMetrics();

        // Reconfigurar agente para su nuevo recorrido
        ag.waveId          = nextWave.wave_id;
        ag.pickerPriority  = nextWave.prioridad;
        ag.path            = routeResult.path;
        ag.step            = 0;
        ag.waitTick        = false;
        ag.pickingCooldown = 0;
        ag.routeResult     = routeResult;

        _renderWavesList();
        _renderFleetStatus();
        _pushRoutesToRenderer();
        showToast(`Picker ${ag.pickerId} liberado: asignado a wave ${nextWave.wave_id}`, 'info');
        return true;
    } catch (err) {
        console.error('Error al planificar ruta para siguiente wave:', err);
        return false;
    }
}

/**
 * Revisa que waves terminaron su camino, las marca como COMPLETA
 * y reasigna los pickers liberados a waves pendientes.
 */
async function _checkCompletedWaves() {
    const sc = _getScenario();
    for (const ag of _agents) {
        if (ag.step >= ag.path.length) {
            const waveInfo = _waves.find(w => w.wave_id === ag.waveId);
            if (waveInfo && waveInfo.status !== 'COMPLETA') {
                waveInfo.status = 'COMPLETA';
                _renderWavesList();

                // El picker quedo libre: intentar asignarle otra wave
                await _tryAssignNextWave(ag, sc);
            }
        }
    }
}

function _allAgentsDone() {
    const agentesFinalizados = _agents.every(ag => ag.step >= ag.path.length);
    const sinWavesEnEspera   = !_waves.some(w => (!w.picker_id || w.picker_id === '') && w.status === 'ABIERTA');
    return agentesFinalizados && sinWavesEnEspera;
}


// ---------------------------------------------------------------------------
// Loop de animacion concurrente (avanzar un tick)
// ---------------------------------------------------------------------------

async function _applyTick() {
    const sc = _getScenario();
    if (!sc) return;

    // Resolucion de colisiones: los agentes en cooldown actuan como
    // obstaculos estaticos (gestionado en _resolveCollisions Regla 3).
    _resolveCollisions();

    for (const ag of _agents) {
        if (ag.step >= ag.path.length) continue;

        // Espera individual de recogida: el picker ya esta en la celda
        // correcta (se movio el tick anterior). Solo esperamos aqui sin
        // cambiar picker.x/y ni step, para que los demas sigan moviendose.
        if (ag.pickingCooldown > 0) {
            ag.pickingCooldown -= 1;
            const pickerC = sc.pickers.find(p => p.id === ag.pickerId);
            if (pickerC) pickerC.isWalking = false;
            continue;
        }

        // Frenado por colision este tick: no avanzar.
        if (ag.waitTick) {
            const pickerW = sc.pickers.find(p => p.id === ag.pickerId);
            if (pickerW) pickerW.isWalking = false;
            continue;
        }

        // Avanzar: mover el picker a la siguiente celda del camino.
        const celda  = ag.path[ag.step];
        const picker = sc.pickers.find(p => p.id === ag.pickerId);
        if (picker) {
            picker.x         = celda[0];
            picker.y         = celda[1];
            picker.isWalking = true;
        }

        // Si la celda recien pisada es una parada de recogida, activar
        // cooldown individual. step se incrementa igual: al terminar el
        // cooldown el agente continuara desde la celda siguiente.
        if (_checkPickups(ag, ag.step)) {
            ag.pickingCooldown = 1;
            if (picker) picker.isWalking = false;
        }

        ag.step += 1;
    }

    // Gestionar waves completadas y liberacion de pickers
    await _checkCompletedWaves();

    // Actualizar progreso de las rutas en el canvas
    _syncRoutesWithRenderer();

    // Actualizar panel de flota
    _renderFleetStatus();
}

function _checkPickups(agent, stepIndex) {
    const paradas = agent.routeResult.paradas;
    const celda   = agent.path[stepIndex];
    let hit = false;

    for (const parada of paradas) {
        if (parada.celda[0] === celda[0] && parada.celda[1] === celda[1]) {
            _addCollectedProducts(parada.productos, agent.waveId);
            hit = true;
        }
    }
    return hit;
}

function _scheduleNextTick() {
    _animTimer = setTimeout(async () => {
        if (_allAgentsDone()) {
            _animTimer = null;
            _onSimulationComplete();
            return;
        }

        await _applyTick();
        _animTimer = null;

        if (_allAgentsDone()) {
            _onSimulationComplete();
            return;
        }

        // El reloj global avanza siempre al mismo ritmo; cada picker
        // gestiona su propia pausa de recogida mediante pickingCooldown.
        _scheduleNextTick();
    }, _tickDelayMs());
}

function _onSimulationComplete() {
    _clearRoutesFromRenderer();
    _updatePlayPauseBtn(false);
    _focusModeUserSet = false;
    _setFocusMode(false);
    _renderWavesList();
    _renderFleetStatus();
    showToast('¡Simulación completada! Todas las waves preparadas ✓', 'success');
}


// ---------------------------------------------------------------------------
// Render del canvas: trazado multi-agente
// ---------------------------------------------------------------------------

function _pushRoutesToRenderer() {
    if (typeof _renderer === 'undefined' || !_renderer) return;
    const sc = _getScenario();

    _renderer.agentRoutes = _agents.map(ag => {
        const picker = sc ? sc.pickers.find(p => p.id === ag.pickerId) : null;
        return {
            path:    ag.path,
            paradas: ag.routeResult.paradas,
            step:    ag.step,
            color:   picker ? picker.color : '#fbbf24',
        };
    });
}

function _syncRoutesWithRenderer() {
    if (typeof _renderer === 'undefined' || !_renderer) return;
    if (!_renderer.agentRoutes) return;

    for (let i = 0; i < _agents.length; i++) {
        if (_renderer.agentRoutes[i]) {
            _renderer.agentRoutes[i].step = _agents[i].step;
        }
    }
}

function _clearRoutesFromRenderer() {
    if (typeof _renderer === 'undefined' || !_renderer) return;
    _renderer.agentRoutes = [];
    _renderer.routePath   = null;
    _renderer.routeStops  = [];
    _renderer.routeStep   = 0;
}


// ---------------------------------------------------------------------------
// Controles de reproduccion: play, pause, step, restart
// ---------------------------------------------------------------------------

function simPlay() {
    if (_agents.length === 0) {
        showToast('Primero planificá las rutas con Play.', 'warning');
        return;
    }
    if (_animTimer !== null) return;
    _updatePlayPauseBtn(true);
    _scheduleNextTick();
}

function simPause() {
    if (_animTimer !== null) {
        clearTimeout(_animTimer);
        _animTimer = null;
    }
    _updatePlayPauseBtn(false);
}

function _updatePlayPauseBtn(isPlaying) {
    const btn = _dom('btn-play-pause');
    if (!btn) return;
    const icon = btn.querySelector('.icon');
    if (icon) icon.textContent = isPlaying ? 'pause' : 'play_arrow';
    btn.title = isPlaying ? 'Pausar' : 'Iniciar / Continuar';
    btn.setAttribute('aria-label', isPlaying ? 'Pausar simulación' : 'Iniciar simulación');
}

async function simStep() {
    simPause();
    if (_agents.length === 0) return;
    if (_allAgentsDone()) return;

    await _applyTick();
}

function simRestart() {
    simPause();
    _restorePickerPositions();
    _agents           = [];
    _allPlannedRoutes = [];
    _focusModeUserSet = false;
    _clearMetrics();
    _clearCollected();
    _clearRoutesFromRenderer();

    // Restaurar estado inicial de waves si existe snapshot
    if (_initialWavesSnapshot && _initialWavesSnapshot.length > 0) {
        _waves = JSON.parse(JSON.stringify(_initialWavesSnapshot));
    } else {
        for (const w of _waves) {
            w.status = 'ABIERTA';
        }
    }
    _renderWavesList();
    _renderFleetStatus();
    _updatePlayPauseBtn(false);
    _setFocusMode(false);
    showToast('Simulación reiniciada.', 'info');
}


// ---------------------------------------------------------------------------
// Comparar estrategias (requiere seleccionar una wave con click)
// ---------------------------------------------------------------------------

async function simCompare() {
    const sc = _getScenario();
    if (!sc) { showToast('Cargá un escenario primero.', 'warning'); return; }

    if (!_selectedWaveId) {
        showToast('Hacé click en una wave de la lista para seleccionarla y comparar.', 'warning');
        return;
    }

    const btn = _dom('btn-compare');
    if (btn) btn.disabled = true;

    try {
        const comparacion = await apiCompareStrategies(sc.toJSON(), _selectedWaveId, _getBuscadorValue());
        _renderComparison(comparacion);
        showToast(`Comparación lista para ${_selectedWaveId}.`, 'success');
    } catch (err) {
        showToast(err.error || 'Error al comparar estrategias.', 'error');
    } finally {
        if (btn) btn.disabled = false;
    }
}


// ---------------------------------------------------------------------------
// Metricas de la flota y comparacion
// ---------------------------------------------------------------------------

function _updateFleetMetrics() {
    let dist = 0, edges = 0, expanded = 0, time = 0;
    const visitedNodes = new Set();

    for (const r of _allPlannedRoutes) {
        dist     += r.distancia_total;
        edges    += r.aristas_recorridas;
        expanded += r.nodos_expandidos;
        time     += r.tiempo_ms;
        for (const [x, y] of r.path) {
            visitedNodes.add(`${x},${y}`);
        }
    }

    _renderMetrics({
        distancia_total:    dist,
        nodos_visitados:    visitedNodes.size,
        aristas_recorridas: edges,
        nodos_expandidos:   expanded,
        tiempo_ms:          time,
    });
}

function _renderMetrics(resultado) {
    const set = (id, val) => { const el = _dom(id); if (el) el.textContent = val; };
    set('metric-distance', resultado.distancia_total + ' celdas');
    set('metric-nodes',    resultado.nodos_visitados);
    set('metric-edges',    resultado.aristas_recorridas);
    set('metric-expanded', resultado.nodos_expandidos);
    set('metric-time',     resultado.tiempo_ms.toFixed(2) + ' ms');
}

function _clearMetrics() {
    ['metric-distance', 'metric-nodes', 'metric-edges', 'metric-expanded', 'metric-time'].forEach(id => {
        const el = _dom(id);
        if (el) el.textContent = '—';
    });
}

function _clearCollected() {
    const list = _dom('collected-list');
    if (list) list.innerHTML = '<p class="empty-msg">Ninguno todavía.</p>';
}

function _addCollectedProducts(productIds, waveId) {
    const list = _dom('collected-list');
    if (!list) return;

    const empty = list.querySelector('.empty-msg');
    if (empty) empty.remove();

    for (const pid of productIds) {
        const key = `${waveId}::${pid}`;
        if (list.querySelector(`[data-key="${key}"]`)) continue;

        const item = document.createElement('div');
        item.className   = 'collected-item';
        item.dataset.key = key;
        item.textContent = `[${waveId}] ${pid}`;
        list.appendChild(item);
    }
}

function _renderComparison(comparacion) {
    const container = _dom('compare-result');
    if (!container) return;

    const filas = Object.entries(comparacion).map(([estrategia, r]) => `
        <tr>
            <td>${estrategia}</td>
            <td>${r.distancia_total}</td>
            <td>${r.nodos_visitados}</td>
            <td>${r.nodos_expandidos}</td>
            <td>${r.tiempo_ms.toFixed(2)} ms</td>
        </tr>`).join('');

    container.innerHTML = `
        <table class="compare-table">
            <thead>
                <tr>
                    <th>Estrategia</th>
                    <th>Distancia</th>
                    <th>Nodos vis.</th>
                    <th>Nodos exp.</th>
                    <th>Tiempo</th>
                </tr>
            </thead>
            <tbody>${filas}</tbody>
        </table>`;
}


// ---------------------------------------------------------------------------
// Reset completo de simulacion
// ---------------------------------------------------------------------------

function simReset() {
    simPause();

    _restorePickerPositions();
    _initialPickerPositions.clear();

    _waves                = [];
    _initialWavesSnapshot = [];
    _agents               = [];
    _allPlannedRoutes     = [];
    _selectedWaveId       = null;
    _focusModeUserSet     = false;

    const wavesList = _dom('waves-list');
    if (wavesList) wavesList.innerHTML = '<p class="empty-msg">Sin waves generadas.</p>';

    _clearMetrics();
    _clearCollected();

    const compareResult = _dom('compare-result');
    if (compareResult) compareResult.innerHTML = '';

    _clearRoutesFromRenderer();
    _renderFleetStatus();
    _updatePlayPauseBtn(false);
    _setFocusMode(false);
}


// ---------------------------------------------------------------------------
// Modo de enfoque del recorrido
// ---------------------------------------------------------------------------

function _setFocusMode(active) {
    if (typeof _renderer !== 'undefined' && _renderer) {
        _renderer.focusMode = active;
    }
    const btn = _dom('btn-focus-mode');
    if (btn) {
        btn.setAttribute('aria-pressed', String(active));
        btn.classList.toggle('active', active);
    }
}

function simToggleFocusMode() {
    const current = (typeof _renderer !== 'undefined' && _renderer) ? _renderer.focusMode : false;
    if (_agents.length > 0) {
        _focusModeUserSet = true;
    }
    _setFocusMode(!current);
}


// ---------------------------------------------------------------------------
// Inicializacion
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
    const btnGenerateWave = _dom('btn-generate-wave');
    if (btnGenerateWave) btnGenerateWave.addEventListener('click', simGenerateWaves);

    const btnPlayPause = _dom('btn-play-pause');
    const btnStep      = _dom('btn-step');
    const btnRestart   = _dom('btn-restart');
    const btnCompare   = _dom('btn-compare');

    if (btnPlayPause) btnPlayPause.addEventListener('click', () => {
        if (_animTimer !== null) {
            simPause();
        } else {
            simPlanAndPlay();
        }
    });
    if (btnStep)    btnStep.addEventListener('click',    simStep);
    if (btnRestart) btnRestart.addEventListener('click', simRestart);
    if (btnCompare) btnCompare.addEventListener('click', simCompare);

    const btnFocusMode = _dom('btn-focus-mode');
    if (btnFocusMode) btnFocusMode.addEventListener('click', simToggleFocusMode);

    const rangeSpeed = _dom('range-speed');
    const speedLabel = _dom('speed-label');
    if (rangeSpeed && speedLabel) {
        rangeSpeed.addEventListener('input', (e) => {
            speedLabel.textContent = `${e.target.value}×`;
        });
    }
});
