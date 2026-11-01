/* ================================================================
   SIM.JS
   Conecta los controles del panel derecho (Simulacion, Metricas,
   Productos recogidos) con el servidor Flask a traves de api.js.

   IMPORTANTE: toda la logica de la simulacion la hace el backend
   (models/simulation.py). Este archivo NO decide nada: pide la
   simulacion completa una sola vez y la reproduce frame por frame.

   Responsabilidades de este modulo:
     - Boton "Generar waves":  llama a apiGenerateWaves y puebla la
       lista de waves del sidebar izquierdo.
     - Boton "Play":           la primera vez pide la simulacion a
       apiSimulate; despues reproduce los frames uno por uno.
     - Boton "Pause":          pausa la reproduccion.
     - Boton "Step":           muestra el frame siguiente.
     - Boton "Restart":        vuelve al frame 0.
     - Boton "Comparar":       llama a apiCompareStrategies y muestra
       la tabla de comparacion (requiere wave seleccionada con click).
     - Actualiza el panel de flota, las metricas y la lista de
       recogidos con lo que dice cada frame.

   QUE ES UN FRAME (lo arma el backend, uno por tick):
     {
       tick:    3,
       pickers: [{ id, x, y, estado, wave, carga_kg, paso }, ...],
       zonas:   { ZONA_A: 12.5, ... },
       eventos: [{ tipo: "ruta" | "inicio_wave" | "recoge" | "descarga"
                         | "espera" | "desvio" | "fin_wave", picker, ... }]
     }
   Para mostrar un frame solo hay que poner cada picker en su (x, y)
   y aplicar sus eventos (cambiar el estado de una wave, agregar
   productos recogidos, guardar la ruta nueva para dibujarla).

   Variables que se leen de otros modulos (globales):
     _scenario   : el escenario activo (definido en ui.js).
     _renderer   : el canvas (definido en ui.js).
   Funciones que se usan de otros modulos:
     showToast(msg, type)  : notificaciones (definida en ui.js).
     apiGenerateWaves, apiSimulate, apiCompareStrategies  (api.js).
================================================================ */


// ---------------------------------------------------------------------------
// Estado de la reproduccion
// ---------------------------------------------------------------------------

/** Waves devueltas por el servidor en el ultimo generate. */
let _waves = [];

/** Copia de las waves generadas para poder volver al estado original con Restart. */
let _initialWavesSnapshot = [];

/** Respuesta de /api/simulacion: { frames, metricas, rutas, error }, o null. */
let _simulation = null;

/** Indice del frame que se esta mostrando (-1 = todavia ninguno). */
let _frameIndex = -1;

/**
 * Ruta que esta siguiendo cada picker, para dibujarla en el canvas.
 * pickerId -> { path: [[x,y], ...], paradas: [{celda, productos}, ...] }
 */
let _routes = {};

/** ID del setTimeout del loop de reproduccion, o null si esta pausado. */
let _animTimer = null;

/**
 * Wave seleccionada con click en la lista para la funcion "Comparar".
 * No cambia que waves se simulan (se simulan todas).
 */
let _selectedWaveId = null;

/**
 * Indica si el usuario cambio manualmente el modo de enfoque durante
 * la simulacion. Evita que la reproduccion lo sobreescriba.
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

function _saveInitialPickerPositions() {
    const sc = _getScenario();
    if (!sc) return;
    for (const picker of sc.pickers) {
        if (!_initialPickerPositions.has(picker.id)) {
            _initialPickerPositions.set(picker.id, { x: picker.x, y: picker.y });
        }
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
            picker.isWalking = false;
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
    const val = _dom('select-strategy')?.value || 'nearest';
    return val === 'order' ? 'orden' : 'cercania';
}

function _getBuscadorValue() {
    return _dom('select-buscador')?.value || 'bfs';
}

function _currentFrame() {
    if (!_simulation || _frameIndex < 0) return null;
    return _simulation.frames[_frameIndex];
}

function _isLastFrame() {
    return _simulation !== null && _frameIndex >= _simulation.frames.length - 1;
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
        _simulation = null;     // las waves cambiaron: hay que volver a simular
        _frameIndex = -1;
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
        // Soportar picker_ids (lista nueva) y picker_id (compat)
        const ids = (w.picker_ids && w.picker_ids.length > 0)
            ? w.picker_ids
            : (w.picker_id ? [w.picker_id] : []);
        const pickerTexto = ids.length > 0 ? ids.join(', ') : '\u2014 en espera \u2014';
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
                <span>${w.unidades} uds &middot; ${w.peso_kg} kg</span>
            </div>
            <div class="wave-item__meta">
                <span>Picker${ids.length > 1 ? 's' : ''}: ${pickerTexto}</span>
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
// Panel de flota (estado de cada picker en el frame actual)
// ---------------------------------------------------------------------------

function _renderFleetStatus() {
    const container = _dom('fleet-status');
    if (!container) return;

    const frame = _currentFrame();
    const rows  = frame ? _buildRowsFromFrame(frame) : _buildRowsFromWaves();

    if (rows.length === 0) {
        container.innerHTML = '<p class="empty-msg">Sin pickers asignados.</p>';
        return;
    }

    container.innerHTML = rows.join('');
}

function _pickerColor(pickerId) {
    const sc = _getScenario();
    const picker = sc ? sc.pickers.find(p => p.id === pickerId) : null;
    return picker ? picker.color : '#888';
}

function _buildRowsFromWaves() {
    // Generar una fila por picker (las waves multi-picker producen varias filas)
    const rows = [];
    for (const w of _waves) {
        const ids = (w.picker_ids && w.picker_ids.length > 0)
            ? w.picker_ids
            : (w.picker_id ? [w.picker_id] : []);
        for (const pid of ids) {
            rows.push(`
                <div class="fleet-row">
                    <span class="fleet-row__dot" style="background:${_pickerColor(pid)}"></span>
                    <span class="fleet-row__picker">${pid}</span>
                    <span class="fleet-row__wave">${w.wave_id}</span>
                    <span class="fleet-row__status">${w.status}</span>
                </div>`);
        }
    }
    return rows;
}

function _buildRowsFromFrame(frame) {
    return frame.pickers.map(p => `
        <div class="fleet-row">
            <span class="fleet-row__dot" style="background:${_pickerColor(p.id)}"></span>
            <span class="fleet-row__picker">${p.id}</span>
            <span class="fleet-row__wave">${p.wave || '—'}</span>
            <span class="fleet-row__status">${p.estado} · ${p.carga_kg} kg</span>
        </div>`);
}


// ---------------------------------------------------------------------------
// Pedir la simulacion al backend
// ---------------------------------------------------------------------------

/**
 * Pide la simulacion completa al servidor y muestra el frame 0.
 * Devuelve true si salio bien.
 */
async function _loadSimulation() {
    const sc = _getScenario();
    if (!sc) { showToast('Cargá un escenario primero.', 'warning'); return false; }

    if (_waves.length === 0) {
        showToast('Generá waves primero.', 'warning');
        return false;
    }

    const btn = _dom('btn-play-pause');
    if (btn) btn.disabled = true;
    showToast('Calculando la simulación en el servidor...', 'info');

    try {
        _restorePickerPositions();
        _saveInitialPickerPositions();
        _simulation = await apiSimulate(sc.toJSON(), _getStrategyValue(), _getBuscadorValue());
    } catch (err) {
        showToast(err.error || 'Error al calcular la simulación.', 'error');
        return false;
    } finally {
        if (btn) btn.disabled = false;
    }

    _resetPlayback();
    _renderMetrics(_simulation.metricas);
    _showFrame(0);

    if (!_focusModeUserSet) {
        _setFocusMode(true);
    }
    return true;
}


// ---------------------------------------------------------------------------
// Mostrar un frame
// ---------------------------------------------------------------------------

/** Vuelve todo a como estaba antes del frame 0 (sin borrar la simulacion). */
function _resetPlayback() {
    _frameIndex = -1;
    _routes     = {};
    _restorePickerPositions();
    _clearCollected();
    _clearRoutesFromRenderer();
    if (_initialWavesSnapshot.length > 0) {
        _waves = JSON.parse(JSON.stringify(_initialWavesSnapshot));
    }
}

/**
 * Muestra el frame `index`. Los frames se aplican en orden, porque los
 * eventos (waves que empiezan o terminan, productos recogidos) se van
 * acumulando.
 */
function _showFrame(index) {
    const sc = _getScenario();
    if (!sc || !_simulation) return;

    const frame = _simulation.frames[index];
    _frameIndex = index;

    // 1. Poner cada picker donde dice el backend. Si cambio de celda, el
    //    renderer lo dibuja con el sprite de caminar (isWalking).
    for (const p of frame.pickers) {
        const picker = sc.pickers.find(pk => pk.id === p.id);
        if (picker) {
            picker.isWalking = index > 0 && (picker.x !== p.x || picker.y !== p.y);
            picker.x = p.x;
            picker.y = p.y;
        }
    }

    // 2. Aplicar lo que paso en este tick.
    for (const evento of frame.eventos) {
        _applyEvent(evento);
    }

    // 3. Actualizar el dibujo de las rutas y los paneles.
    _pushRoutesToRenderer(frame);
    _renderWavesList();
    _renderFleetStatus();
}

function _applyEvent(evento) {
    const wave = _waves.find(w => w.wave_id === evento.wave);

    if (evento.tipo === 'ruta') {
        // Ruta nueva (al empezar una wave, al desviarse o al cambiar de zona).
        const anterior = _routes[evento.picker];
        _routes[evento.picker] = {
            path:    evento.path,
            paradas: evento.paradas || (anterior ? anterior.paradas : []),
        };
    } else if (evento.tipo === 'inicio_wave') {
        if (wave) {
            wave.status    = 'EN_PROCESO';
            wave.picker_id = evento.picker;   // compat con código legacy
            // Acumular en picker_ids para waves con varios pickers
            if (!wave.picker_ids) wave.picker_ids = [];
            if (!wave.picker_ids.includes(evento.picker)) {
                wave.picker_ids.push(evento.picker);
            }
        }
    } else if (evento.tipo === 'recoge') {
        _addCollectedProducts(evento.productos, evento.wave);
    } else if (evento.tipo === 'fin_wave') {
        if (wave) wave.status = 'COMPLETADA';
        delete _routes[evento.picker];
    }
    // "espera", "desvio" y "descarga" ya se ven en el estado de los pickers.
}


// ---------------------------------------------------------------------------
// Render del canvas: rutas de cada picker
// ---------------------------------------------------------------------------

function _pushRoutesToRenderer(frame) {
    if (typeof _renderer === 'undefined' || !_renderer) return;

    const rutas = [];
    for (const p of frame.pickers) {
        const ruta = _routes[p.id];
        if (!ruta || p.paso === null) continue;
        rutas.push({
            path:    ruta.path,
            paradas: ruta.paradas,
            step:    p.paso + 1,     // el renderer pinta como recorrido hasta step - 1
            color:   _pickerColor(p.id),
        });
    }
    _renderer.agentRoutes = rutas;
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

async function simPlanAndPlay() {
    if (!_simulation) {
        const ok = await _loadSimulation();
        if (!ok) return;
    } else if (_isLastFrame()) {
        // Ya termino: Play la vuelve a mostrar desde el principio.
        _resetPlayback();
        _showFrame(0);
    }
    simPlay();
}

function simPlay() {
    if (!_simulation) return;
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

function _scheduleNextTick() {
    _animTimer = setTimeout(() => {
        if (_isLastFrame()) {
            _animTimer = null;
            _onSimulationComplete();
            return;
        }
        _showFrame(_frameIndex + 1);
        _scheduleNextTick();
    }, _tickDelayMs());
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
    if (!_simulation) {
        await _loadSimulation();    // el primer Step muestra el frame 0
        return;
    }
    if (_isLastFrame()) return;
    _showFrame(_frameIndex + 1);
}

function simRestart() {
    simPause();
    if (_simulation) {
        _resetPlayback();
        _showFrame(0);
    } else {
        _resetPlayback();
        _renderWavesList();
        _renderFleetStatus();
    }
    _focusModeUserSet = false;
    showToast('Simulación reiniciada.', 'info');
}

function _onSimulationComplete() {
    const sc = _getScenario();
    if (sc) {
        for (const picker of sc.pickers) picker.isWalking = false;
    }
    _updatePlayPauseBtn(false);
    _focusModeUserSet = false;
    _setFocusMode(false);

    if (_simulation.error) {
        showToast(`La simulación se detuvo: ${_simulation.error}`, 'error');
        return;
    }
    const m = _simulation.metricas;
    showToast(
        `¡Simulación completada en ${m.ticks} ticks! ` +
        `(${m.esperas} esperas, ${m.desvios} desvíos)`,
        'success'
    );
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
        const comparacion = await apiCompareStrategies(sc.toJSON(), _selectedWaveId);
        _renderComparison(comparacion, { waveId: _selectedWaveId });
        showToast(`Comparación de todas las combinaciones lista para ${_selectedWaveId}.`, 'success');
    } catch (err) {
        showToast(err.error || 'Error al comparar estrategias.', 'error');
    } finally {
        if (btn) btn.disabled = false;
    }
}


/**
 * Corre todas las combinaciones posibles de estrategias y algoritmos
 * (Cercanía + BFS, Cercanía + A*, Orden + BFS, Orden + A*) simulando
 * TODAS las waves en simultáneo.
 */
async function simCompareAll() {
    const sc = _getScenario();
    if (!sc) { showToast('Cargá un escenario primero.', 'warning'); return; }

    const btn = _dom('btn-compare-all');
    if (btn) btn.disabled = true;

    try {
        showToast('Ejecutando simulación de todas las waves en simultáneo...', 'info');
        const res = await apiCompareAllCombinations(sc.toJSON());
        _renderComparison(res);
        showToast('Comparación de todas las combinaciones completada.', 'success');
    } catch (err) {
        showToast(err.error || 'Error al comparar combinaciones.', 'error');
    } finally {
        if (btn) btn.disabled = false;
    }
}


// ---------------------------------------------------------------------------
// Metricas y comparacion
// ---------------------------------------------------------------------------

function _renderMetrics(m) {
    const set = (id, val) => { const el = _dom(id); if (el) el.textContent = val; };
    set('metric-distance', m.distancia_total + ' celdas');
    set('metric-nodes',    m.nodos_visitados);
    set('metric-edges',    m.aristas_recorridas);
    set('metric-expanded', m.nodos_expandidos);
    set('metric-time',     m.tiempo_ms.toFixed(2) + ' ms');
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

function _renderComparison(datos, options = {}) {
    const container = _dom('compare-result');
    if (!container || !datos) return;

    let lista = [];
    let tituloBadge = '';

    if (datos.tipo === 'todas_waves' && Array.isArray(datos.combinaciones)) {
        lista = datos.combinaciones;
        const total = datos.total_waves !== undefined ? datos.total_waves : '';
        tituloBadge = `<div class="compare-badge">Todas las waves (${total ? total + ' ' : ''}en simultáneo)</div>`;
    } else if (datos.combinaciones && Array.isArray(datos.combinaciones)) {
        lista = datos.combinaciones;
        const waveId = datos.wave_id || options.waveId;
        if (waveId) {
            tituloBadge = `<div class="compare-badge">Wave: ${waveId}</div>`;
        }
    } else if (Array.isArray(datos)) {
        lista = datos;
    } else if (typeof datos === 'object') {
        const orderedKeys = ['cercania', 'orden'].filter(k => k in datos);
        Object.keys(datos).forEach(k => {
            if (!orderedKeys.includes(k)) orderedKeys.push(k);
        });
        lista = orderedKeys.map(k => datos[k]);
        if (options.waveId) {
            tituloBadge = `<div class="compare-badge">Wave: ${options.waveId}</div>`;
        }
    }

    const strategyLabels = {
        cercania: 'Cercanía',
        orden:    'Orden de pedidos'
    };

    const buscadorLabels = {
        bfs:   'BFS',
        astar: 'A*'
    };

    const filas = lista.map(r => {
        const estLabel = strategyLabels[r.estrategia] || r.estrategia;
        const algLabel = buscadorLabels[r.buscador] || (r.buscador ? r.buscador.toUpperCase() : '—');
        const distancia = (r.distancia_total !== undefined && r.distancia_total !== null) ? `${r.distancia_total} celdas` : '—';
        const nodosVis = (r.nodos_visitados !== undefined && r.nodos_visitados !== null) ? r.nodos_visitados : '—';
        const nodosExp = (r.nodos_expandidos !== undefined && r.nodos_expandidos !== null) ? r.nodos_expandidos : '—';
        const tiempo = (r.tiempo_ms !== undefined && r.tiempo_ms !== null) ? `${Number(r.tiempo_ms).toFixed(2)} ms` : '—';

        return `
        <tr>
            <td class="compare-cell--name"><strong>${estLabel}</strong></td>
            <td><span class="badge-algo">${algLabel}</span></td>
            <td class="text-right">${distancia}</td>
            <td class="text-right">${nodosVis}</td>
            <td class="text-right">${nodosExp}</td>
            <td class="text-right">${tiempo}</td>
        </tr>`;
    }).join('');

    container.innerHTML = `
        ${tituloBadge}
        <table class="compare-table">
            <thead>
                <tr>
                    <th>Estrategia</th>
                    <th>Algoritmo</th>
                    <th class="text-right">Distancia total</th>
                    <th class="text-right">Nodos visitados</th>
                    <th class="text-right">Nodos expandidos</th>
                    <th class="text-right">Tiempo</th>
                </tr>
            </thead>
            <tbody>${filas}</tbody>
        </table>`;
}


// ---------------------------------------------------------------------------
// Reset completo de simulacion (lo llama ui.js al cambiar de escenario)
// ---------------------------------------------------------------------------

function simReset() {
    simPause();

    _restorePickerPositions();
    _initialPickerPositions.clear();

    _waves                = [];
    _initialWavesSnapshot = [];
    _simulation           = null;
    _frameIndex           = -1;
    _routes               = {};
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
    if (_simulation) {
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
    const btnCompareAll = _dom('btn-compare-all');
    if (btnCompareAll) btnCompareAll.addEventListener('click', simCompareAll);

    const btnFocusMode = _dom('btn-focus-mode');
    if (btnFocusMode) btnFocusMode.addEventListener('click', simToggleFocusMode);

    // Si cambia la estrategia o el buscador, la simulacion guardada ya no sirve.
    const selStrategy = _dom('select-strategy');
    const selBuscador = _dom('select-buscador');
    const invalidar = () => {
        if (_simulation) {
            simRestart();
            _simulation = null;
            _clearMetrics();
        }
    };
    if (selStrategy) selStrategy.addEventListener('change', invalidar);
    if (selBuscador) selBuscador.addEventListener('change', invalidar);

    const rangeSpeed = _dom('range-speed');
    const speedLabel = _dom('speed-label');
    if (rangeSpeed && speedLabel) {
        rangeSpeed.addEventListener('input', (e) => {
            speedLabel.textContent = `${e.target.value}×`;
        });
    }
});
