/* ================================================================
   SIM.JS
   Conecta los controles del panel derecho (Simulacion, Metricas,
   Productos recogidos) con el servidor Flask a traves de api.js.

   Responsabilidades de este modulo:
     - Boton "Generar waves":  llama a apiGenerateWaves y puebla la
       lista de waves y el selector desplegable.
     - Boton "Play":           pide el recorrido a apiPlanRoute y
       arranca la animacion de los pickers en el canvas.
     - Boton "Pause":          pausa la animacion en curso.
     - Boton "Step":           avanza la animacion un solo paso.
     - Boton "Restart":        vuelve la animacion al inicio.
     - Boton "Comparar":       llama a apiCompareStrategies y muestra
       la tabla de comparacion.
     - Actualiza las tarjetas de metricas y la lista de recogidos.

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

/** Resultado de plan_route: { path, paradas, ...metricas }. */
let _routeResult = null;

/** Indice del paso actual dentro de _routeResult.path (para la animacion). */
let _animStep = 0;

/** ID del setTimeout del loop de animacion, o null si esta pausado. */
let _animTimer = null;


// ---------------------------------------------------------------------------
// Referencias a elementos DOM del panel derecho
// ---------------------------------------------------------------------------

function _dom(id) { return document.getElementById(id); }


// ---------------------------------------------------------------------------
// Velocidades en ms/paso segun el valor del slider (1 a 5)
// ---------------------------------------------------------------------------

const SPEED_MS = { 1: 500, 2: 250, 3: 120, 4: 60, 5: 20 };

function _stepDelayMs() {
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
// Helpers: leer el escenario activo y el picker seleccionado en la wave
// ---------------------------------------------------------------------------

function _getScenario() {
    // _scenario es la variable global definida en ui.js.
    return typeof _scenario !== 'undefined' ? _scenario : null;
}

function _getSelectedWaveId() {
    return _dom('select-wave')?.value || null;
}

function _getStrategyValue() {
    // El select de estrategia tiene valores "order" y "nearest" en el HTML,
    // que corresponden a "orden" y "cercania" en el backend.
    const val = _dom('select-strategy')?.value || 'order';
    return val === 'order' ? 'orden' : 'cercania';
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
        _renderWavesList();
        _renderWaveSelector();
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
        const pickerTexto = w.picker_id ? w.picker_id : '—';
        return `
        <div class="wave-item" data-wave-id="${w.wave_id}" style="cursor:pointer">
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

    // Permitir hacer click en una card de wave para seleccionarla en el panel derecho.
    list.querySelectorAll('.wave-item').forEach(card => {
        card.addEventListener('click', () => {
            const wid = card.dataset.waveId;
            const sel = _dom('select-wave');
            if (sel) {
                sel.value = wid;
                showToast(`Wave ${wid} seleccionada.`, 'info');
            }
        });
    });
}

/** Rellena el <select> de waves del panel derecho (#select-wave). */
function _renderWaveSelector() {
    const sel = _dom('select-wave');
    if (!sel) return;

    sel.innerHTML = '<option value="">— Selecciona una wave —</option>';
    for (const w of _waves) {
        const opt = document.createElement('option');
        opt.value       = w.wave_id;
        opt.textContent = `${w.wave_id}  (prio ${w.prioridad} · ${w.unidades} uds)`;
        sel.appendChild(opt);
    }

    // Si solo hay una wave, la seleccionamos automaticamente.
    if (_waves.length === 1) {
        sel.value = _waves[0].wave_id;
    }
}


// ---------------------------------------------------------------------------
// Animacion: avanzar un paso
// ---------------------------------------------------------------------------

/** Posiciona al picker del canvas en la celda del path indicada por el indice. */
function _applyStep(stepIndex) {
    if (!_routeResult) return;

    const path = _routeResult.path;
    if (stepIndex < 0 || stepIndex >= path.length) return;

    const celda = path[stepIndex];

    // Buscar la wave activa para saber que picker mover.
    const waveId = _getSelectedWaveId();
    const waveInfo = _waves.find(w => w.wave_id === waveId);
    if (!waveInfo) return;

    const sc = _getScenario();
    if (!sc) return;

    // Mover el picker en el escenario JS (el renderer lo leerá en el proximo frame).
    const picker = sc.pickers.find(p => p.id === waveInfo.picker_id);
    if (picker) {
        _saveInitialPickerPosition(picker);
        picker.x = celda[0];
        picker.y = celda[1];
    }

    // Resaltar productos recogidos cuando el picker pasa por una parada.
    _checkPickups(stepIndex);
}

/**
 * Detecta si el paso actual coincide con alguna parada del recorrido
 * y actualiza la lista de productos recogidos (#collected-list).
 */
function _checkPickups(stepIndex) {
    if (!_routeResult) return;

    const path    = _routeResult.path;
    const paradas = _routeResult.paradas;
    const celda   = path[stepIndex];

    for (const parada of paradas) {
        // parada.celda es [x, y]
        if (parada.celda[0] === celda[0] && parada.celda[1] === celda[1]) {
            _addCollectedProducts(parada.productos);
        }
    }
}

/** Agrega una fila por cada producto recogido a la lista #collected-list. */
function _addCollectedProducts(productIds) {
    const list = _dom('collected-list');
    if (!list) return;

    // Quitar el mensaje de "Ninguno todavia" si lo hay.
    const empty = list.querySelector('.empty-msg');
    if (empty) empty.remove();

    for (const pid of productIds) {
        // Evitar duplicados.
        if (list.querySelector(`[data-pid="${pid}"]`)) continue;

        const item = document.createElement('div');
        item.className    = 'collected-item';
        item.dataset.pid  = pid;
        item.textContent  = pid;
        list.appendChild(item);
    }
}


// ---------------------------------------------------------------------------
// Controles de reproduccion: play, pause, step, restart
// ---------------------------------------------------------------------------

function simPlay() {
    if (!_routeResult) {
        showToast('Primero planificá el recorrido con Play.', 'warning');
        return;
    }
    if (_animTimer !== null) return;    // ya esta corriendo

    _scheduleNextStep();
}

function simPause() {
    if (_animTimer !== null) {
        clearTimeout(_animTimer);
        _animTimer = null;
    }
}

function simStep() {
    // Un solo paso manual: cancela el loop si estaba corriendo.
    simPause();
    if (!_routeResult) return;
    if (_animStep >= _routeResult.path.length) return;

    _applyStep(_animStep);
    _animStep = _animStep + 1;
}

function simRestart() {
    simPause();
    _restorePickerPositions();
    _animStep    = 0;
    _routeResult = null;
    _clearMetrics();
    _clearCollected();
    showToast('Simulación reiniciada.', 'info');
}

function _scheduleNextStep() {
    _animTimer = setTimeout(() => {
        if (!_routeResult || _animStep >= _routeResult.path.length) {
            _animTimer = null;
            showToast('Recorrido completado.', 'success');
            return;
        }
        _applyStep(_animStep);
        _animStep = _animStep + 1;
        _scheduleNextStep();
    }, _stepDelayMs());
}


// ---------------------------------------------------------------------------
// Planificar recorrido (disparado desde el boton Play)
// ---------------------------------------------------------------------------

/**
 * Pide el recorrido al servidor y arranca la animacion.
 * Si estaba pausado a mitad de camino, simplemente continua.
 */
async function simPlanAndPlay() {
    const sc = _getScenario();
    if (!sc) { showToast('Cargá un escenario primero.', 'warning'); return; }

    const waveId = _getSelectedWaveId();
    if (!waveId) { showToast('Seleccioná una wave.', 'warning'); return; }

    // Si ya habia un recorrido calculado y estaba pausado a mitad de camino, continuar
    if (_routeResult && _animStep < _routeResult.path.length && _animTimer === null) {
        simPlay();
        return;
    }

    // Parar la animacion actual y restaurar posicion antes de pedir la nueva ruta.
    simPause();
    _restorePickerPositions();
    _animStep    = 0;
    _routeResult = null;
    _clearMetrics();
    _clearCollected();

    const estrategia = _getStrategyValue();

    const btn = _dom('btn-play');
    if (btn) btn.disabled = true;

    try {
        _routeResult = await apiPlanRoute(sc.toJSON(), waveId, estrategia, 'bfs');
        _renderMetrics(_routeResult);
        showToast('Recorrido calculado. Animando...', 'info');
        simPlay();
    } catch (err) {
        showToast(err.error || 'Error al calcular el recorrido.', 'error');
    } finally {
        if (btn) btn.disabled = false;
    }
}


// ---------------------------------------------------------------------------
// Comparar estrategias
// ---------------------------------------------------------------------------

async function simCompare() {
    const sc = _getScenario();
    if (!sc) { showToast('Carga un escenario primero.', 'warning'); return; }

    const waveId = _getSelectedWaveId();
    if (!waveId) { showToast('Seleccioná una wave.', 'warning'); return; }

    const btn = _dom('btn-compare');
    if (btn) btn.disabled = true;

    try {
        const comparacion = await apiCompareStrategies(sc.toJSON(), waveId, 'bfs');
        _renderComparison(comparacion);
        showToast('Comparacion lista.', 'success');
    } catch (err) {
        showToast(err.error || 'Error al comparar estrategias.', 'error');
    } finally {
        if (btn) btn.disabled = false;
    }
}


// ---------------------------------------------------------------------------
// Render de metricas y comparacion
// ---------------------------------------------------------------------------

function _renderMetrics(resultado) {
    const set = (id, val) => { const el = _dom(id); if (el) el.textContent = val; };
    set('metric-distance', resultado.distancia_total + ' celdas');
    set('metric-nodes',    resultado.nodos_visitados);
    set('metric-edges',    resultado.aristas_recorridas);
    set('metric-time',     resultado.tiempo_ms.toFixed(2) + ' ms');
}

function _clearMetrics() {
    ['metric-distance', 'metric-nodes', 'metric-edges', 'metric-time'].forEach(id => {
        const el = _dom(id);
        if (el) el.textContent = '—';
    });
}

function _clearCollected() {
    const list = _dom('collected-list');
    if (list) list.innerHTML = '<p class="empty-msg">Ninguno todavía.</p>';
}

function _renderComparison(comparacion) {
    const container = _dom('compare-result');
    if (!container) return;

    // Construir una tabla simple con las dos estrategias.
    const filas = Object.entries(comparacion).map(([estrategia, r]) => `
        <tr>
            <td>${estrategia}</td>
            <td>${r.distancia_total}</td>
            <td>${r.nodos_visitados}</td>
            <td>${r.tiempo_ms.toFixed(2)} ms</td>
        </tr>`).join('');

    container.innerHTML = `
        <table class="compare-table">
            <thead>
                <tr>
                    <th>Estrategia</th>
                    <th>Distancia</th>
                    <th>Nodos vis.</th>
                    <th>Tiempo</th>
                </tr>
            </thead>
            <tbody>${filas}</tbody>
        </table>`;
}


// ---------------------------------------------------------------------------
// Inicializacion: conectar botones con funciones
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
    const btnGenerateWave = _dom('btn-generate-wave');
    if (btnGenerateWave) btnGenerateWave.addEventListener('click', simGenerateWaves);

    const btnPlay    = _dom('btn-play');
    const btnPause   = _dom('btn-pause');
    const btnStep    = _dom('btn-step');
    const btnRestart = _dom('btn-restart');
    const btnCompare = _dom('btn-compare');

    if (btnPlay)    btnPlay.addEventListener('click',    simPlanAndPlay);
    if (btnPause)   btnPause.addEventListener('click',   simPause);
    if (btnStep)    btnStep.addEventListener('click',    simStep);
    if (btnRestart) btnRestart.addEventListener('click', simRestart);
    if (btnCompare) btnCompare.addEventListener('click', simCompare);

    const rangeSpeed = _dom('range-speed');
    const speedLabel = _dom('speed-label');
    if (rangeSpeed && speedLabel) {
        rangeSpeed.addEventListener('input', (e) => {
            speedLabel.textContent = `${e.target.value}×`;
        });
    }
});
