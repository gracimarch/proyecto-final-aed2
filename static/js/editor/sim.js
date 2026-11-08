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
       eventos: [{ tipo: "ruta" | "inicio_wave" | "recoge" | "parada_recogida"
                         | "descarga" | "espera" | "desvio" | "fin_wave",
                  picker, ... }]
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

/**
 * Historial acumulado de celdas ya recorridas por cada picker.
 * Se construye frame a frame rastreando la posición real del picker,
 * para que el camino no se borre cuando hay desvíos por colisión
 * o descargas intermedias. pickerId -> [[x,y], ...]
 */
let _routeHistory = {};

/**
 * Última posición conocida de cada picker (para detectar cambios y
 * construir el historial acumulado sin saltos ni diagonales).
 * pickerId -> [x, y]
 */
let _lastPickerPos = {};

/**
 * Unidades ya recogidas en la simulación que se está reproduciendo:
 * productId -> cantidad. Permite mostrar el stock restante en los racks
 * sin modificar los datos del escenario (que conserva el stock original).
 */
let _consumedStock = {};

/**
 * Devuelve true si dos celdas son ortogonalmente adyacentes
 * (arriba, abajo, izquierda o derecha). Nunca diagonales.
 */
function esAdyacente(c1, c2) {
    return Math.abs(c1[0] - c2[0]) + Math.abs(c1[1] - c2[1]) === 1;
}

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

/**
 * Indica si la edicion del almacen esta bloqueada porque hay una
 * simulacion activa (corriendo o pausada). Se libera al reiniciar,
 * resetear o completar la simulacion.
 */
let _simulationLocked = false;

/** Modo de armado con el que se generaron las waves actuales (para guardarlo). */
let _wavesOnda = null;

/**
 * Opciones con las que se pidio la simulacion actual:
 * { estrategia_wave, estrategia, buscador, velocidad }, o null.
 * Se guardan en el archivo para poder retomar la simulacion (persistencia).
 */
let _simParams = null;


// ---------------------------------------------------------------------------
// Referencias a elementos DOM del panel derecho
// ---------------------------------------------------------------------------

function _dom(id) { return document.getElementById(id); }


// ---------------------------------------------------------------------------
// Velocidades en ms/tick segun el valor del slider (1 a 5)
// ---------------------------------------------------------------------------

const SPEED_MS = { 1: 500, 2: 250, 3: 120, 4: 60, 5: 20, 6: 15, 7: 12, 8: 10, 9: 8, 10: 5 };

function _tickDelayMs() {
    const val = parseInt(_dom('range-speed')?.value || '1');
    return SPEED_MS[val] || 5;
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

function _getOndaValue() {
    return _dom('select-onda')?.value || 'por_cercania';
}

function _getSpeedValue() {
    const val = parseInt(_dom('range-speed')?.value || '1');
    return val >= 1 && val <= 10 ? val : 1;
}

/**
 * Cantidad de frames que se avanzan por cada tick del timer de reproduccion.
 * Hasta 5x alcanza con bajar el delay; a partir de ahi el limite practico
 * pasa a ser el refresco/render, asi que se avanzan varios frames por tick.
 */
const FRAMES_PER_TICK = { 1: 1, 2: 1, 3: 1, 4: 1, 5: 1, 6: 2, 7: 2, 8: 3, 9: 4, 10: 5 };

function _framesPerTick() {
    return FRAMES_PER_TICK[_getSpeedValue()] || 1;
}

function _currentFrame() {
    if (!_simulation || _frameIndex < 0) return null;
    return _simulation.frames[_frameIndex];
}

function _isLastFrame() {
    return _simulation !== null && _frameIndex >= _simulation.frames.length - 1;
}

/** Pide un repintado del canvas en el próximo frame (render bajo demanda). */
function _requestCanvasRender() {
    if (typeof _editor !== 'undefined' && _editor) {
        _editor.requestRender();
    } else if (typeof _renderer !== 'undefined' && _renderer) {
        _renderer.requestRender();
    }
}


// ---------------------------------------------------------------------------
// Generar waves
// ---------------------------------------------------------------------------

async function simGenerateWaves() {
    const sc = _getScenario();
    if (!sc) { showToast('Cargá un escenario primero.', 'warning'); return false; }

    if (!sc.orders || sc.orders.length === 0) {
        showToast('El escenario no tiene pedidos para procesar.', 'warning');
        return false;
    }

    const btn = _dom('btn-generate-wave');
    if (btn) btn.disabled = true;

    const estrategiaWave = _getOndaValue();
    try {
        _waves = await apiGenerateWaves(sc.toJSON(), estrategiaWave);
        _initialWavesSnapshot = JSON.parse(JSON.stringify(_waves));
        _wavesOnda = estrategiaWave;
        _simulation = null;     // las waves cambiaron: hay que volver a simular
        _simParams = null;
        _frameIndex = -1;
        _resetConsumedStock();
        _refreshStockDisplays();
        _renderWavesList();
        simUpdateConsultarBtn();
        _renderFleetStatus();
        if (typeof renderOrdersList === 'function') renderOrdersList();
        showToast(`${_waves.length} wave(s) generada(s).`, 'success');
        return true;
    } catch (err) {
        showToast(err.error || 'Error al generar waves.', 'error');
        return false;
    } finally {
        if (btn) btn.disabled = false;
    }
}

// ── Estado del DOM de waves (actualizaciones quirúrgicas) ────────

/** Array de waves con el que se construyó #waves-list (control de identidad). */
let _wavesListSource = null;

/** Nodos mutables por wave_id: { card, badge, pickers, badgeText, pickersText }. */
let _wavesListNodes = new Map();

/** Delegación de click: se asocia una única vez al contenedor #waves-list. */
function _ensureWavesListDelegation(list) {
    if (list.dataset.wavesDelegated === '1') return;
    list.dataset.wavesDelegated = '1';
    list.addEventListener('click', (e) => {
        const card = e.target.closest('.wave-item');
        if (!card || !list.contains(card)) return;
        _selectedWaveId = card.dataset.waveId;
        _renderWavesList();   // solo actualiza la clase de selección
        showToast(`Wave ${_selectedWaveId} seleccionada para comparar.`, 'info');
        simUpdateConsultarBtn();
    });
}

/** Texto de la línea "Picker(s): ..." de una wave. */
function _wavePickerText(w) {
    const ids = (w.picker_ids && w.picker_ids.length > 0)
        ? w.picker_ids
        : (w.picker_id ? [w.picker_id] : []);
    return `Picker${ids.length > 1 ? 's' : ''}: ` +
        (ids.length > 0 ? ids.join(', ') : '\u2014 en espera \u2014');
}

/** Construye la estructura completa (solo al generar/reiniciar waves). */
function _buildWavesListDOM(list) {
    list.innerHTML = _waves.map(w => `
        <div class="wave-item ${w.wave_id === _selectedWaveId ? 'wave-item--selected' : ''}"
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
                <span class="wave-item__pickers">${_wavePickerText(w)}</span>
                <span>${w.pedidos.join(', ')}</span>
            </div>
        </div>`).join('');

    // Cachear los nodos que mutan durante la simulación.
    _wavesListNodes.clear();
    list.querySelectorAll('.wave-item').forEach(card => {
        _wavesListNodes.set(card.dataset.waveId, {
            card,
            badge: card.querySelector('.wave-item__badge'),
            pickers: card.querySelector('.wave-item__pickers'),
            badgeText: null,
            pickersText: null,
        });
    });
}

/** Actualiza solo los valores que cambiaron (status, pickers, selección). */
function _updateWavesListDOM() {
    for (const w of _waves) {
        const node = _wavesListNodes.get(w.wave_id);
        if (!node) continue;

        const isSelected = w.wave_id === _selectedWaveId;
        if (node.card.classList.contains('wave-item--selected') !== isSelected) {
            node.card.classList.toggle('wave-item--selected', isSelected);
        }

        if (node.badgeText !== w.status) {
            node.badge.textContent = w.status;
            node.badgeText = w.status;
        }

        const pickersText = _wavePickerText(w);
        if (node.pickersText !== pickersText) {
            node.pickers.textContent = pickersText;
            node.pickersText = pickersText;
        }
    }
}

/**
 * Rellena/actualiza la lista de waves del sidebar (#waves-list).
 * La estructura se construye una sola vez por set de waves; en cada tick
 * solo se tocan los nodos cuyos valores cambiaron.
 */
function _renderWavesList() {
    const list = _dom('waves-list');
    if (!list) return;

    _ensureWavesListDelegation(list);

    if (_waves.length === 0) {
        // Mostrar el mensaje vacío si todavía hay cards o si falta el texto.
        if (list.querySelector('.wave-item') || !list.querySelector('.empty-msg')) {
            list.innerHTML = '<p class="empty-msg">Sin waves generadas.</p>';
        }
        _wavesListSource = null;
        _wavesListNodes.clear();
        return;
    }

    // Reconstruir solo cuando cambia el set de waves (generar / reiniciar).
    if (_wavesListSource !== _waves || list.querySelector('.wave-item') === null) {
        _buildWavesListDOM(list);
        _wavesListSource = _waves;
    }

    _updateWavesListDOM();
}


// ---------------------------------------------------------------------------
// Panel de flota (estado de cada picker en el frame actual)
// ---------------------------------------------------------------------------

// ── Estado del DOM de flota (actualizaciones quirúrgicas) ────────

/** Firma (ids en orden) del set de filas actualmente renderizado. */
let _fleetSignature = null;

/** Nodos mutables de cada fila: { wave, status, waveText, statusText }. */
let _fleetNodes = [];

function _renderFleetStatus() {
    const container = _dom('fleet-status');
    if (!container) return;

    const frame = _currentFrame();
    const rows = frame ? _buildFleetDataFromFrame(frame) : _buildFleetDataFromWaves();

    if (rows.length === 0) {
        if (_fleetSignature !== 'empty') {
            container.innerHTML = '<p class="empty-msg">Sin pickers asignados.</p>';
            _fleetSignature = 'empty';
            _fleetNodes = [];
        }
        return;
    }

    // Solo se reconstruyen las filas cuando cambia el set/orden de pickers.
    const signature = rows.map(r => r.id).join('|');
    if (_fleetSignature !== signature) {
        container.innerHTML = rows.map(r => `
            <div class="fleet-row" data-picker-id="${r.id}">
                <span class="fleet-row__dot" style="background:${_pickerColor(r.id)}"></span>
                <span class="fleet-row__picker">${r.id}</span>
                <span class="fleet-row__wave"></span>
                <span class="fleet-row__status"></span>
            </div>`).join('');

        _fleetNodes = Array.from(container.querySelectorAll('.fleet-row')).map(row => ({
            wave: row.querySelector('.fleet-row__wave'),
            status: row.querySelector('.fleet-row__status'),
            waveText: null,
            statusText: null,
        }));
        _fleetSignature = signature;
    }

    // Actualización quirúrgica: solo el texto que cambió.
    for (let i = 0; i < rows.length; i++) {
        const node = _fleetNodes[i];
        if (!node) continue;
        const { wave, status } = rows[i];
        if (node.waveText !== wave) {
            node.wave.textContent = wave;
            node.waveText = wave;
        }
        if (node.statusText !== status) {
            node.status.textContent = status;
            node.statusText = status;
        }
    }
}

function _pickerColor(pickerId) {
    const sc = _getScenario();
    const picker = sc ? sc.pickers.find(p => p.id === pickerId) : null;
    return picker ? picker.color : '#888';
}

function _buildFleetDataFromWaves() {
    // Generar una fila por picker (las waves multi-picker producen varias filas)
    const rows = [];
    for (const w of _waves) {
        const ids = (w.picker_ids && w.picker_ids.length > 0)
            ? w.picker_ids
            : (w.picker_id ? [w.picker_id] : []);
        for (const pid of ids) {
            rows.push({ id: pid, wave: w.wave_id, status: w.status });
        }
    }
    return rows;
}

function _buildFleetDataFromFrame(frame) {
    return frame.pickers.map(p => ({
        id: p.id,
        wave: p.wave || '—',
        status: `${p.estado} · ${p.carga_kg} kg`,
    }));
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

    const params = {
        estrategia_wave: _getOndaValue(),
        estrategia: _getStrategyValue(),
        buscador: _getBuscadorValue(),
        velocidad: _getSpeedValue(),
    };
    try {
        _restorePickerPositions();
        _saveInitialPickerPositions();
        _simulation = await apiSimulate(
            sc.toJSON(),
            params.estrategia,
            params.buscador,
            params.estrategia_wave,
            1,
        );
        _simParams = params;
    } catch (err) {
        showToast(err.error || 'Error al calcular la simulación.', 'error');
        return false;
    } finally {
        if (btn) btn.disabled = false;
    }

    _resetPlayback();
    _renderMetrics(_simulation.metricas);
    _showFrame(0);
    _setEditingLock(true);      // bloquear edicion mientras la sim esta activa

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
    _routes = {};
    _routeHistory = {};
    _lastPickerPos = {};
    _restorePickerPositions();
    _clearCollected();
    _clearRoutesFromRenderer();
    _resetZoneWeights();
    _resetConsumedStock();
    if (_initialWavesSnapshot.length > 0) {
        _waves = JSON.parse(JSON.stringify(_initialWavesSnapshot));
    }
    _requestCanvasRender();   // los pickers volvieron a su posición inicial
    _refreshStockDisplays();
    if (typeof renderOrdersList === 'function') renderOrdersList();
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
    _refreshStockDisplays();
    _syncZoneWeights(frame);
    _pushRoutesToRenderer(frame);
    _renderWavesList();
    _renderFleetStatus();
    if (typeof renderOrdersList === 'function') renderOrdersList();
    _updateStepButtons();
    _requestCanvasRender();   // este tick movió pickers/sprites en el canvas
}

function _applyEvent(evento) {
    const wave = _waves.find(w => w.wave_id === evento.wave);

    if (evento.tipo === 'ruta') {
        // Ruta nueva (al empezar una wave, al desviarse o al cambiar de zona).
        const anterior = _routes[evento.picker];
        _routes[evento.picker] = {
            path: evento.path,
            paradas: evento.paradas || (anterior ? anterior.paradas : []),
        };
    } else if (evento.tipo === 'inicio_wave') {
        if (wave) {
            wave.status = 'EN_PROCESO';
            wave.picker_id = evento.picker;   // compat con código legacy
            // Acumular en picker_ids para waves con varios pickers
            if (!wave.picker_ids) wave.picker_ids = [];
            if (!wave.picker_ids.includes(evento.picker)) {
                wave.picker_ids.push(evento.picker);
            }
        }
    } else if (evento.tipo === 'recoge') {
        _applyCollectedStock(evento);
        _addCollectedProducts(evento.productos, evento.wave);
    } else if (evento.tipo === 'parada_recogida') {
        // El backend envía la lista autoritativa de paradas que todavía
        // faltan. Reemplazarla evita que una celda ya recogida siga
        // dibujándose si el camino vuelve a pasar por ella como tránsito.
        const ruta = _routes[evento.picker];
        if (ruta && Array.isArray(evento.paradas)) {
            ruta.paradas = evento.paradas;
        }
    } else if (evento.tipo === 'fin_wave') {
        if (wave) wave.status = 'COMPLETADA';
        delete _routes[evento.picker];
        // El picker terminó su trabajo: borrar su ruta, historial y última posición.
        delete _routeHistory[evento.picker];
        delete _lastPickerPos[evento.picker];
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
        const pickerId = p.id;

        // ── Rastrear posición real del picker para historial acumulado ──
        const posActual = [p.x, p.y];

        if (!_routeHistory[pickerId]) _routeHistory[pickerId] = [];
        const historial = _routeHistory[pickerId];

        if (!_lastPickerPos[pickerId]) {
            // Primera vez que vemos al picker: registrar posición inicial
            _lastPickerPos[pickerId] = [...posActual];
            // Si ya tiene ruta activa, incluir la posición actual como primer punto
            if (_routes[pickerId] && historial.length === 0) {
                historial.push([...posActual]);
            }
        } else {
            const ultimaPos = _lastPickerPos[pickerId];
            const movio = posActual[0] !== ultimaPos[0] || posActual[1] !== ultimaPos[1];
            if (movio) {
                // Agregar nueva posición al historial (solo si tiene ruta activa)
                if (_routes[pickerId]) {
                    historial.push([...posActual]);
                }
                _lastPickerPos[pickerId] = [...posActual];
            } else if (historial.length === 0 && _routes[pickerId]) {
                // Picker parado con ruta activa pero sin historial: registrar pos actual
                historial.push([...posActual]);
            }
        }

        const ruta = _routes[pickerId];
        if (!ruta) continue;

        const pasoActual = p.paso;
        if (pasoActual === null || pasoActual === undefined) continue;

        // Camino pendiente de la ruta actual (desde el siguiente paso en adelante)
        const caminoPendiente = pasoActual >= 0 ? ruta.path.slice(pasoActual + 1) : ruta.path.slice(1);

        // ── Construir path para el renderer ──────────────────────────────
        // path = historial (ya recorrido) + caminoPendiente (futuro)
        // step = historial.length  →  path[0..step-1] sólido, path[step-1..end] punteado
        //
        // Si el historial está vacío (picker sin movimiento previo), usar la posición
        // actual como punto de inicio del tramo sólido.

        let pathParaRenderer;
        let stepParaRenderer;

        if (historial.length > 0) {
            if (caminoPendiente.length > 0) {
                pathParaRenderer = [...historial, ...caminoPendiente];
            } else {
                pathParaRenderer = [...historial];
            }
            stepParaRenderer = historial.length; // todo el historial está "ya recorrido"
        } else {
            // Sin historial: mostrar la pos actual como inicio + pendiente como punteado
            if (caminoPendiente.length > 0) {
                pathParaRenderer = [[p.x, p.y], ...caminoPendiente];
            } else {
                pathParaRenderer = [[p.x, p.y]];
            }
            stepParaRenderer = 1; // solo el punto actual está "hecho"
        }

        // ── Paradas: el backend ya envía solo las que siguen pendientes ──
        // No se filtran por el camino actual: una parada puede no estar en
        // este tramo (por ejemplo, mientras se va a descargar por capacidad)
        // y aun así seguir pendiente. Filtrarlas por geometría era lo que
        // hacía reaparecer el círculo en celdas de simple tránsito.
        const paradasPendientes = ruta.paradas || [];

        rutas.push({
            path: pathParaRenderer,
            paradas: paradasPendientes,
            step: stepParaRenderer,
            color: _pickerColor(pickerId),
        });
    }
    _renderer.agentRoutes = rutas;
}
function _clearRoutesFromRenderer() {
    if (typeof _renderer === 'undefined' || !_renderer) return;
    _renderer.agentRoutes = [];
    _renderer.routePath = null;
    _renderer.routeStops = [];
    _renderer.routeStep = 0;
}


// ---------------------------------------------------------------------------
// Zonas de despacho: peso ocupado segun el frame actual
// ---------------------------------------------------------------------------

/**
 * Copia al escenario el peso ocupado de cada zona de despacho que viene en
 * el frame (`frame.zonas`, zone_id -> kg) y repinta si hubo cambios.
 * Las zonas se dibujan en la capa estatica del renderer, por eso hay que
 * invalidarla cuando cambia el valor.
 */
function _syncZoneWeights(frame) {
    const sc = _getScenario();
    if (!sc) return;

    const pesos = (frame && frame.zonas) || {};
    let changed = false;
    for (const dz of sc.dispatchZones) {
        const nuevo = Number(pesos[dz.id] ?? 0) || 0;
        if ((dz.peso_actual ?? 0) !== nuevo) {
            dz.peso_actual = nuevo;
            changed = true;
        }
    }
    if (changed && typeof _renderer !== 'undefined' && _renderer) {
        _renderer.invalidateStaticLayer();
    }
}

/** Vuelve a cero el peso ocupado de todas las zonas de despacho. */
function _resetZoneWeights() {
    const sc = _getScenario();
    if (!sc) return;

    let changed = false;
    for (const dz of sc.dispatchZones) {
        if ((dz.peso_actual ?? 0) !== 0) {
            dz.peso_actual = 0;
            changed = true;
        }
    }
    if (changed && typeof _renderer !== 'undefined' && _renderer) {
        _renderer.invalidateStaticLayer();
    }
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
        _setEditingLock(true);   // vuelve a bloquear la edicion durante el replay
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
        const framesPerTick = _framesPerTick();
        let advanced = 0;
        for (let i = 0; i < framesPerTick && !_isLastFrame(); i++) {
            _showFrame(_frameIndex + 1);
            advanced++;
        }

        if (_isLastFrame() || advanced === 0) {
            _animTimer = null;
            _onSimulationComplete();
            return;
        }
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
    _setEditingLock(true);      // sigue habiendo una simulacion activa
    _showFrame(_frameIndex + 1);
}

function simRestart() {
    simPause();
    _resetPlayback();
    _simulation = null;   // libera la planificacion calculada
    _simParams = null;
    _focusModeUserSet = false;
    _clearMetrics();
    _setFocusMode(false);
    _setEditingLock(false);     // devuelve la edicion al usuario
    simUpdateConsultarBtn();
    _renderWavesList();
    _renderFleetStatus();
    if (typeof renderOrdersList === 'function') renderOrdersList();
    showToast('Simulación reiniciada. Podés editar el escenario.', 'info');
}

function _onSimulationComplete() {
    const sc = _getScenario();
    if (sc) {
        for (const picker of sc.pickers) picker.isWalking = false;
    }
    _requestCanvasRender();   // los pickers vuelven al sprite idle
    _updatePlayPauseBtn(false);
    _focusModeUserSet = false;
    _setFocusMode(false);
    _setEditingLock(false);     // la simulacion termino: desbloquear edicion

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


/**
 * Genera las waves con los tres modos de armado ("por_pedido", "por_cercania"
 * y "solo_cercania") sobre el mismo escenario y renderiza una tabla por modo.
 */
async function simCompareWaves() {
    const sc = _getScenario();
    if (!sc) { showToast('Cargá un escenario primero.', 'warning'); return; }

    const btn = _dom('btn-compare-waves');
    if (btn) btn.disabled = true;

    try {
        showToast('Generando waves con los tres modos...', 'info');
        const datos = await apiCompareWaves(sc.toJSON());
        _renderWaveComparison(datos);
        showToast('Comparación de modos de armado de waves lista.', 'success');
    } catch (err) {
        showToast(err.error || 'Error al comparar modos de armado de waves.', 'error');
    } finally {
        if (btn) btn.disabled = false;
    }
}


// ---------------------------------------------------------------------------
// Metricas y comparacion
// ---------------------------------------------------------------------------

function _renderMetrics(m) {
    const set = (id, val) => { const el = _dom(id); if (el) el.textContent = val; };
    set('metric-ticks', m.ticks);
    set('metric-distance', m.distancia_total + ' celdas');
    set('metric-nodes', m.nodos_visitados);
    set('metric-edges', m.aristas_recorridas);
    set('metric-expanded', m.nodos_expandidos);
    set('metric-time', m.tiempo_ms.toFixed(2) + ' ms');
}

function _clearMetrics() {
    ['metric-ticks', 'metric-distance', 'metric-nodes', 'metric-edges', 'metric-expanded', 'metric-time'].forEach(id => {
        const el = _dom(id);
        if (el) el.textContent = '—';
    });
}

function _clearCollected() {
    const list = _dom('collected-list');
    if (list) list.innerHTML = '<p class="empty-msg">Ninguno todavía.</p>';
    _updateCollectedTotal();
}

/** Actualiza el contador del encabezado del panel. */
function _updateCollectedTotal() {
    const list = _dom('collected-list');
    const total = _dom('collected-total');
    if (!list || !total) return;
    total.textContent = list.querySelectorAll('.collected-item').length;
}

/**
 * Agrega productos recogidos agrupándolos en una tarjeta por wave.
 * Se llama en tiempo real a medida que avanza la simulación.
 */
function _addCollectedProducts(productIds, waveId) {
    const list = _dom('collected-list');
    if (!list || !productIds || productIds.length === 0) return;

    const empty = list.querySelector('.empty-msg');
    if (empty) empty.remove();

    // Tarjeta de la wave (se crea la primera vez que aparece).
    let card = list.querySelector('[data-collected-wave="' + waveId + '"]');
    if (!card) {
        card = document.createElement('div');
        card.className = 'collected-wave';
        card.dataset.collectedWave = waveId;

        const header = document.createElement('div');
        header.className = 'collected-wave__header';

        const title = document.createElement('span');
        title.className = 'collected-wave__title';
        title.textContent = waveId;

        const count = document.createElement('span');
        count.className = 'collected-wave__count';
        count.textContent = '0 productos';

        header.append(title, count);

        const innerList = document.createElement('div');
        innerList.className = 'collected-wave__list';

        card.append(header, innerList);
        list.appendChild(card);
    }

    const inner = card.querySelector('.collected-wave__list');
    if (!inner) return;

    const sc = _getScenario();
    const allProducts = sc ? sc.getAllProducts() : [];

    for (const pid of productIds) {
        const key = waveId + '::' + pid;
        if (list.querySelector('[data-key="' + key + '"]')) continue;

        const product = allProducts.find(pr => pr.id === pid);
        const nombre = product ? product.name : pid;

        const item = document.createElement('div');
        item.className = 'collected-item';
        item.dataset.key = key;

        const nameEl = document.createElement('span');
        nameEl.className = 'collected-item__name';
        nameEl.textContent = nombre;
        nameEl.title = nombre;

        const idEl = document.createElement('span');
        idEl.className = 'collected-item__id';
        idEl.textContent = pid;
        idEl.title = 'id del producto';

        item.append(nameEl, idEl);
        inner.appendChild(item);
    }

    // Contador de la tarjeta (productos distintos recogidos de esa wave).
    const countEl = card.querySelector('.collected-wave__count');
    if (countEl) {
        const n = inner.querySelectorAll('.collected-item').length;
        countEl.textContent = n + (n === 1 ? ' producto' : ' productos');
    }

    _updateCollectedTotal();
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
        orden: 'Orden de pedidos'
    };

    const buscadorLabels = {
        bfs: 'BFS',
        astar: 'A*'
    };

    const tieneTicks = lista.some(r => r.ticks !== undefined && r.ticks !== null);

    const filas = lista.map(r => {
        const estLabel = strategyLabels[r.estrategia] || r.estrategia;
        const algLabel = buscadorLabels[r.buscador] || (r.buscador ? r.buscador.toUpperCase() : '—');
        const distancia = (r.distancia_total !== undefined && r.distancia_total !== null) ? `${r.distancia_total} celdas` : '—';
        const nodosVis = (r.nodos_visitados !== undefined && r.nodos_visitados !== null) ? r.nodos_visitados : '—';
        const nodosExp = (r.nodos_expandidos !== undefined && r.nodos_expandidos !== null) ? r.nodos_expandidos : '—';
        const ticks = (r.ticks !== undefined && r.ticks !== null) ? r.ticks : '—';
        const tiempo = (r.tiempo_ms !== undefined && r.tiempo_ms !== null) ? `${Number(r.tiempo_ms).toFixed(2)} ms` : '—';

        return `
        <tr>
            <td class="compare-cell--name"><strong>${estLabel}</strong></td>
            <td><span class="badge-algo">${algLabel}</span></td>
            <td class="text-right">${distancia}</td>
            <td class="text-right">${nodosVis}</td>
            <td class="text-right">${nodosExp}</td>
            ${tieneTicks ? `<td class="text-right">${ticks}</td>` : ''}
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
                    ${tieneTicks ? '<th class="text-right">Ticks</th>' : ''}
                    <th class="text-right">Tiempo</th>
                </tr>
            </thead>
            <tbody>${filas}</tbody>
        </table>`;
}

/**
 * Renderiza la comparacion de modos de armado de waves (por_pedido,
 * por_cercania y solo_cercania) como una tabla por modo en #compare-waves-result.
 *
 * @param {Object} datos Respuesta de /api/waves/compare:
 *   { comparacion: [{estrategia, total_waves, total_ticks, total_unidades,
 *     total_peso_kg, distancia_estimada_total, promedio_unidades_por_wave,
 *     waves: [{wave_id, pedidos, unidades, peso_kg, distancia_estimada, picker_ids}]}],
 *     mismo_resultado }
 */
function _renderWaveComparison(datos) {
    const container = _dom('compare-waves-result');
    if (!container || !datos) return;

    const comparacion = datos.comparacion;
    if (!Array.isArray(comparacion) || comparacion.length === 0) {
        container.innerHTML = '<p class="empty-msg">No hay datos para comparar el armado de waves.</p>';
        return;
    }

    const mismoResultado = datos.mismo_resultado === true;

    const igual = mismoResultado
        ? '<span class="compare-badge--equal">Todos los modos generan el mismo armado de waves.</span>'
        : '';

    const tablas = comparacion.map(c => {
        const TITULOS = {
            por_pedido:    'Pedidos completos',
            por_cercania:  'Cercanía entre pedidos',
            solo_cercania: 'Cercanía sin prioridad',
        };
        const titulo = TITULOS[c.estrategia] || c.estrategia;
        const filas = (c.waves || []).map(w => `
            <tr>
                <td class="compare-cell--name"><strong>${w.wave_id}</strong></td>
                <td class="text-right">${(w.pedidos || []).join(', ') || '\u2014'}</td>
                <td class="text-right">${w.unidades}</td>
                <td class="text-right">${Number(w.peso_kg || 0).toFixed(2)} kg</td>
                <td class="text-right">${w.distancia_estimada !== undefined ? w.distancia_estimada : '\u2014'}</td>
                <td class="text-right">${(w.picker_ids || []).join(', ') || '\u2014'}</td>
            </tr>
        `).join('');

        const totales = [
            `${c.total_waves} wave${c.total_waves !== 1 ? 's' : ''}`,
        ];
        if (c.total_ticks !== undefined && c.total_ticks !== null) {
            totales.push(`${c.total_ticks} ticks`);
        }
        if (c.distancia_estimada_total !== undefined) {
            totales.push(`${c.distancia_estimada_total} celdas est.`);
        }

        return `
        <div class="wave-compare-table">
            <div class="wave-compare-table__header">
                <span class="wave-compare-table__titulo">${titulo}</span>
                <span class="wave-compare-table__totals">${totales.join('  \u00b7  ')}</span>
            </div>
            <div class="wave-compare-table__body">
                <table class="compare-table">
                    <thead>
                        <tr>
                            <th>Wave</th>
                            <th class="text-right">Pedidos</th>
                            <th class="text-right">Unidades</th>
                            <th class="text-right">Peso</th>
                            <th class="text-right">Dist. est.</th>
                            <th class="text-right">Picker(s)</th>
                        </tr>
                    </thead>
                    <tbody>${filas}</tbody>
                </table>
            </div>
        </div>
        `;
    }).join('');

    container.innerHTML = `
        ${igual}
        <div class="wave-compare-grid">${tablas}</div>
    `;
}

// ---------------------------------------------------------------------------
// Reset completo de simulacion (lo llama ui.js al cambiar de escenario)
// ---------------------------------------------------------------------------

/**
 * Calcula el estado visible de un pedido basado en el estado actual de _waves.
 * Devuelve: 'PENDIENTE' | 'EN_WAVE' | 'EN_PROCESO' | 'COMPLETADO'
 */
function simGetOrderStatus(orderId) {
    if (!_waves || _waves.length === 0) return 'PENDIENTE';
    const wavesDelPedido = _waves.filter(w => w.pedidos && w.pedidos.includes(orderId));
    if (wavesDelPedido.length === 0) return 'PENDIENTE';
    const todas = wavesDelPedido.length;
    const completadas = wavesDelPedido.filter(w => w.status === 'COMPLETADA').length;
    const enProceso = wavesDelPedido.filter(w => w.status === 'EN_PROCESO').length;
    if (completadas === todas) return 'COMPLETADO';
    if (enProceso > 0 || (completadas > 0 && completadas < todas)) return 'EN_PROCESO';
    return 'EN_WAVE';
}

function simReset() {
    simPause();
    _setEditingLock(false);     // garantiza que el reset siempre libera la edicion
    simUpdateConsultarBtn();

    _restorePickerPositions();
    _initialPickerPositions.clear();

    _waves = [];
    _initialWavesSnapshot = [];
    _wavesOnda = null;
    _simulation = null;
    _simParams = null;
    _simulationLocked = false;
    _frameIndex = -1;
    _routes = {};
    _selectedWaveId = null;
    _focusModeUserSet = false;

    _renderWavesList();

    _clearMetrics();
    _clearCollected();
    _resetZoneWeights();
    _resetConsumedStock();
    _refreshStockDisplays();

    const compareResult = _dom('compare-result');
    if (compareResult) compareResult.innerHTML = '';

    const compareWavesResult = _dom('compare-waves-result');
    if (compareWavesResult) compareWavesResult.innerHTML = '';

    _clearRoutesFromRenderer();
    _renderFleetStatus();
    if (typeof renderOrdersList === 'function') renderOrdersList();
    _requestCanvasRender();
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
        btn.setAttribute('aria-checked', String(active));
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
// Bloqueo de edicion durante la simulacion
// ---------------------------------------------------------------------------

/**
 * Devuelve true cuando la simulacion esta activa (corriendo o pausada).
 * Bloquea tanto las operaciones de edicion del almacen como las de pedidos.
 * Se libera al reiniciar, resetear o completar la simulacion.
 * Lo consultan editor.js y ui.js para bloquear las operaciones de edicion.
 */
function simIsEditingLocked() {
    return _simulationLocked;
}

// ---------------------------------------------------------------------------
// Stock restante de los productos
// ---------------------------------------------------------------------------

/**
 * Acumula las unidades recogidas por el evento "recoge". Usa el detalle
 * `items` (con cantidades); si no viene, cae al listado de ids y descuenta
 * una unidad por cada id (compatibilidad con eventos viejos).
 */
function _applyCollectedStock(evento) {
    if (Array.isArray(evento.items)) {
        for (const it of evento.items) {
            const pid  = it.producto_id;
            const cant = Number(it.cantidad) || 0;
            if (!pid || cant <= 0) continue;
            _consumedStock[pid] = (_consumedStock[pid] || 0) + cant;
        }
        return;
    }
    for (const pid of evento.productos || []) {
        if (!pid) continue;
        _consumedStock[pid] = (_consumedStock[pid] || 0) + 1;
    }
}

/**
 * Unidades que le quedan a un producto segun lo recogido hasta el frame
 * que se esta mostrando. No modifica el escenario: el stock original se
 * conserva para guardar/cargar y para reiniciar la simulacion.
 */
function simGetRemainingStock(product) {
    if (!product) return 0;
    const base  = Number(product.quantity) || 0;
    const usado = _consumedStock[product.id] || 0;
    return Math.max(0, base - usado);
}

function _resetConsumedStock() {
    _consumedStock = {};
}

/** Refresca los paneles abiertos que muestran stock (tooltip y panel de rack). */
function _refreshStockDisplays() {
    if (typeof _editor !== 'undefined' && _editor &&
        typeof _editor._refreshPinnedRackTooltip === 'function') {
        _editor._refreshPinnedRackTooltip();
    }
    if (typeof simRefreshSelectedRackStock === 'function') {
        simRefreshSelectedRackStock();
    }
}


// ---------------------------------------------------------------------------
// Tooltip de pickers: acceso al estado de simulacion del frame actual
// ---------------------------------------------------------------------------

/**
 * Devuelve todos los datos de simulacion del picker para el frame actual,
 * combinando la info del scenario (estática) con la del frame (dinámica).
 *
 * Si no hay simulación activa, devuelve solo los datos estáticos.
 *
 * @param {string} pickerId - ID del picker.
 * @param {object} scenarioPicker - Instancia de Picker del scenario (tiene .capacidadKg, .color, .name).
 * @returns {object} Datos enriquecidos listos para el tooltip.
 */
function simGetPickerRuntimeData(pickerId, scenarioPicker) {
    const frame = _currentFrame();

    // Datos base (siempre disponibles desde el escenario)
    const base = {
        id: pickerId,
        name: scenarioPicker?.name || pickerId,
        color: scenarioPicker?.color || '#4f9cf9',
        capacidadKg: scenarioPicker?.capacidadKg ?? 100,
        x: scenarioPicker?.x ?? 0,
        y: scenarioPicker?.y ?? 0,
        // Datos de simulación con valores por defecto (modo edición)
        estado: 'LIBRE',
        wave: null,
        carga_kg: 0,
        carga: [],
        proximo_objetivo: { tipo: 'FIN', destino: null, descripcion: 'En espera / sin wave' },
        // Ruta activa
        ruta: _routes[pickerId] || null,
    };

    if (!frame) return base;

    // Buscar el estado del picker en el frame actual
    const fp = frame.pickers.find(p => p.id === pickerId);
    if (!fp) return base;

    return {
        ...base,
        x: fp.x,
        y: fp.y,
        estado: fp.estado || 'LIBRE',
        wave: fp.wave || null,
        carga_kg: fp.carga_kg ?? 0,
        // Enriquecidos (si el backend ya los provee en el frame)
        carga: fp.carga || [],
        proximo_objetivo: fp.proximo_objetivo || base.proximo_objetivo,
    };
}

/** Habilita/deshabilita todos los controles de edicion del warehouse. */
function _setEditingLock(locked) {
    _simulationLocked = locked;

    const MSG = 'No disponible mientras hay una simulacion activa';

    // Herramientas de edicion del canvas (excepto seleccionar)
    ['tool-rack', 'tool-move-rack', 'tool-product',
        'tool-erase', 'tool-door', 'tool-dispatch', 'tool-aisle'].forEach(id => {
            const btn = _dom(id);
            if (!btn) return;
            btn.disabled = locked;
            if (locked) { btn._origTitle = btn.title; btn.title = MSG; }
            else if (btn._origTitle !== undefined) { btn.title = btn._origTitle; }
        });

    // Selectores asociados a herramientas de edicion
    ['door-tipo-select', 'aisle-sentido-select'].forEach(id => {
        const el = _dom(id);
        if (el) el.disabled = locked;
    });

    // Panel de pickers
    ['btn-picker-add'].forEach(id => {
        const btn = _dom(id);
        if (!btn) return;
        btn.disabled = locked;
        if (locked) btn.title = MSG;
    });
    const inputPickerCap = document.getElementById('input-picker-capacity');
    if (inputPickerCap) inputPickerCap.disabled = locked;

    // Panel de pedidos
    const btnAddOrder = document.getElementById('btn-add-order');
    if (btnAddOrder) {
        btnAddOrder.disabled = locked;
        if (locked) btnAddOrder.title = MSG;
    }
    // Botones de eliminar pedido: re-renderizar para aplicar disabled/enabled
    // (se llama al final de esta funcion para que _simulationLocked ya este
    // actualizado cuando renderOrdersList lo consulte con simIsEditingLocked())

    // Selectores de estrategia y algoritmo (no se pueden cambiar una vez
    // que hay una simulación activa, porque las waves ya se armaron con esos valores)
    ['select-strategy', 'select-buscador', 'select-onda'].forEach(id => {
        const el = _dom(id);
        if (!el) return;
        el.disabled = locked;
        if (locked) el.title = MSG;
        else el.title = '';
    });

    // Generacion de waves
    const btnGenWave = _dom('btn-generate-wave');
    if (btnGenWave) {
        btnGenWave.disabled = locked;
        if (locked) btnGenWave.title = MSG;
    }

    // Botones de escenario en la navbar
    ['btn-new-scenario', 'btn-load-scenario'].forEach(id => {
        const btn = document.getElementById(id);
        if (!btn) return;
        btn.disabled = locked;
        if (locked) btn.title = MSG;
    });

    _updateStepButtons();

    // Siempre re-renderizar la lista de pedidos: al bloquear aplica disabled=true
    // a los botones existentes (evita que botones previos sigan disparando),
    // y al desbloquear restaura los event listeners.
    if (typeof renderOrdersList === 'function') renderOrdersList();

    // Re-renderizar la tabla de pickers para deshabilitar/habilitar
    // los inputs de capacidad y los botones de eliminar.
    if (typeof _updatePickersList === 'function') _updatePickersList();
}

/** Sincroniza el estado de los botones de paso adelante y atras. */
function _updateStepButtons() {
    const btnBack = _dom('btn-step-back');
    const btnNext = _dom('btn-step');
    if (btnBack) btnBack.disabled = !_simulation || _frameIndex <= 0;
    if (btnNext) btnNext.disabled = !!_simulation && _isLastFrame();
}


// ---------------------------------------------------------------------------
// Paso atras
// ---------------------------------------------------------------------------

/**
 * Retrocede un frame re-aplicando todos los eventos desde el principio.
 */
function simStepBack() {
    simPause();
    if (!_simulation || _frameIndex <= 0) return;
    _setEditingLock(true);      // al retroceder vuelve a haber una simulacion activa
    _replayTo(_frameIndex - 1);
}

/**
 * Deja la reproduccion en el frame `target` re-aplicando los frames
 * 0..target desde el estado inicial (los eventos se acumulan, por eso no
 * se puede saltar directo). Lo usan el paso atras y la carga de una
 * simulacion guardada.
 * Para evitar saturar el DOM en cada paso intermedio, solo actualiza el
 * renderer y los paneles una vez, al llegar al frame destino.
 */
function _replayTo(target) {
    if (!_simulation) return;
    const sc = _getScenario();

    // Volver al estado inicial limpio
    _frameIndex = -1;
    _routes = {};
    _routeHistory = {};
    _lastPickerPos = {};
    _restorePickerPositions();
    _clearCollected();
    _clearRoutesFromRenderer();
    _resetZoneWeights();
    _resetConsumedStock();
    if (_initialWavesSnapshot.length > 0) {
        _waves = JSON.parse(JSON.stringify(_initialWavesSnapshot));
    }

    // Re-aplicar frames 0...target de forma silenciosa
    for (let i = 0; i <= target; i++) {
        const frame = _simulation.frames[i];
        _frameIndex = i;

        // Posiciones de pickers (solo en memoria, sin tocar el renderer aun)
        if (sc) {
            for (const p of frame.pickers) {
                const picker = sc.pickers.find(pk => pk.id === p.id);
                if (picker) {
                    picker.isWalking = i > 0 && (picker.x !== p.x || picker.y !== p.y);
                    picker.x = p.x;
                    picker.y = p.y;
                }
            }
        }

        // Eventos: modifica _waves, _routes y la lista de productos recogidos
        for (const evento of frame.eventos) {
            _applyEvent(evento);
        }

        // Actualizar historial de posiciones durante el replay silencioso.
        // Es necesario para que _pushRoutesToRenderer tenga el historial correcto al final.
        for (const p of frame.pickers) {
            const pickerId = p.id;
            const posActual = [p.x, p.y];

            if (!_routeHistory[pickerId]) _routeHistory[pickerId] = [];
            const historial = _routeHistory[pickerId];

            if (!_lastPickerPos[pickerId]) {
                _lastPickerPos[pickerId] = [...posActual];
                if (_routes[pickerId] && historial.length === 0) {
                    historial.push([...posActual]);
                }
            } else {
                const ultimaPos = _lastPickerPos[pickerId];
                const movio = posActual[0] !== ultimaPos[0] || posActual[1] !== ultimaPos[1];
                if (movio) {
                    if (_routes[pickerId]) {
                        historial.push([...posActual]);
                    }
                    _lastPickerPos[pickerId] = [...posActual];
                } else if (historial.length === 0 && _routes[pickerId]) {
                    historial.push([...posActual]);
                }
            }
        }
    }

    // Una sola actualizacion del renderer y los paneles al final
    if (target >= 0) {
        _syncZoneWeights(_simulation.frames[target]);
        _pushRoutesToRenderer(_simulation.frames[target]);
    }
    _refreshStockDisplays();
    _renderWavesList();
    _renderFleetStatus();
    if (typeof renderOrdersList === 'function') renderOrdersList();
    _updateStepButtons();
    _requestCanvasRender();
}


// ---------------------------------------------------------------------------
// Persistencia: guardar y retomar la simulacion
// ---------------------------------------------------------------------------
//
// No se guardan las waves, las rutas ni los frames: el back los vuelve a
// calcular. Como la generacion de waves, BFS/A* y la simulacion son
// deterministas, con el mismo escenario y las mismas opciones salen
// exactamente iguales. Por eso alcanza con guardar las opciones elegidas
// y el numero de frame que se estaba mostrando.

/**
 * Devuelve el JSON para guardar en el archivo: el escenario y, si hay
 * waves o una simulacion, la seccion "estado".
 *
 * Durante la simulacion los pickers del editor se mueven, asi que se
 * guardan en su posicion inicial (si no, al retomar arrancarian desde
 * donde quedaron y la simulacion seria otra).
 */
function simScenarioForSave(sc) {
    const data = sc.toJSON();
    if (_waves.length === 0) return data;     // no hay nada de simulacion

    if (_simulation) {
        for (const p of data.pickers) {
            const pos = _initialPickerPositions.get(p.id);
            if (pos) p.posicion_inicial = { x: pos.x, y: pos.y };
        }
    }

    const frame = _currentFrame();
    data.estado = {
        estrategia_wave: _simParams ? _simParams.estrategia_wave : _wavesOnda,
        estrategia: _simParams ? _simParams.estrategia : _getStrategyValue(),
        buscador: _simParams ? _simParams.buscador : _getBuscadorValue(),
        velocidad: _simParams ? _simParams.velocidad : _getSpeedValue(),
        frame: frame ? _frameIndex : null,
        tick: frame ? frame.tick : null,
    };
    return data;
}

/** Cambia el valor de un select sin disparar su evento 'change'. */
function _setSelectValue(id, value) {
    const el = _dom(id);
    if (el && value != null) el.value = value;
}

/**
 * Retoma lo guardado en la seccion "estado" de un archivo, despues de que
 * ui.js cargo el escenario:
 *   1. pone los selectores como estaban al guardar;
 *   2. vuelve a generar las waves (salen iguales);
 *   3. si habia una simulacion, la vuelve a pedir y salta al frame
 *      guardado, en pausa. Con Play sigue desde ahi.
 */
async function simRestoreState(estado) {
    if (!estado || !estado.estrategia_wave) return;

    _setSelectValue('select-onda', estado.estrategia_wave);
    if (estado.estrategia) {
        _setSelectValue('select-strategy', estado.estrategia === 'orden' ? 'order' : 'nearest');
    }
    _setSelectValue('select-buscador', estado.buscador);
    if (estado.velocidad) {
        _setSelectValue('range-speed', String(estado.velocidad));
        const label = _dom('speed-label');
        if (label) label.textContent = `${estado.velocidad}×`;
    }

    const wavesOk = await simGenerateWaves();
    if (!wavesOk || estado.frame == null) return;

    const simOk = await _loadSimulation();
    if (!simOk) return;

    const destino = Math.min(estado.frame, _simulation.frames.length - 1);
    _replayTo(destino);

    if (_isLastFrame()) {
        _onSimulationComplete();
    } else {
        showToast(
            `Simulación retomada en el tick ${_currentFrame().tick}. Apretá Play para continuar.`,
            'success'
        );
    }
}


// ---------------------------------------------------------------------------
// Inicializacion
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
    const btnGenerateWave = _dom('btn-generate-wave');
    if (btnGenerateWave) btnGenerateWave.addEventListener('click', simGenerateWaves);

    const btnPlayPause = _dom('btn-play-pause');
    const btnStep = _dom('btn-step');
    const btnStepBack = _dom('btn-step-back');
    const btnRestart = _dom('btn-restart');
    const btnCompare = _dom('btn-compare');

    if (btnPlayPause) btnPlayPause.addEventListener('click', () => {
        if (_animTimer !== null) {
            simPause();
        } else {
            simPlanAndPlay();
        }
    });
    if (btnStep) btnStep.addEventListener('click', simStep);
    if (btnStepBack) btnStepBack.addEventListener('click', simStepBack);
    if (btnRestart) btnRestart.addEventListener('click', simRestart);
    if (btnCompare) btnCompare.addEventListener('click', simCompare);
    const btnCompareAll = _dom('btn-compare-all');
    if (btnCompareAll) btnCompareAll.addEventListener('click', simCompareAll);
    const btnCompareWaves = _dom('btn-compare-waves');
    if (btnCompareWaves) btnCompareWaves.addEventListener('click', simCompareWaves);

    const btnFocusMode = _dom('btn-focus-mode');
    if (btnFocusMode) btnFocusMode.addEventListener('click', simToggleFocusMode);

    // Si cambia la estrategia, el buscador o el modo de armado de waves,
    // la simulacion guardada ya no sirve.
    const selStrategy = _dom('select-strategy');
    const selBuscador = _dom('select-buscador');
    const selOnda = _dom('select-onda');
    const invalidar = () => { if (_simulation) simRestart(); };
    if (selStrategy) selStrategy.addEventListener('change', invalidar);
    if (selBuscador) selBuscador.addEventListener('change', invalidar);
    if (selOnda) selOnda.addEventListener('change', invalidar);

    const rangeSpeed = _dom('range-speed');
    const speedLabel = _dom('speed-label');
    if (rangeSpeed && speedLabel) {
        rangeSpeed.addEventListener('input', (e) => {
            speedLabel.textContent = `${e.target.value}×`;
        });
    }
});
 // ================================================================
 // Detalle de wave (consultar) — modal con productos, pedidos y pickers
 // ================================================================

 /** Abre el modal de detalle de la wave seleccionada. */
 function simOpenWaveDetail() {
    try {
        if (!_selectedWaveId) {
            showToast('Seleccioná una wave de la lista antes de consultar.', 'warning');
            return;
        }
        const w = _waves.find(x => x.wave_id === _selectedWaveId);
        if (!w) {
            showToast('No se encontró la wave seleccionada.', 'error');
            return;
        }

        const sc = _getScenario();
        const orders = sc ? sc.orders : [];
        const allProducts = sc ? sc.getAllProducts() : [];

        const ids = (w.picker_ids && w.picker_ids.length > 0)
            ? w.picker_ids
            : (w.picker_id ? [w.picker_id] : []);
        const pickersText = ids.length > 0 ? ids.join(', ') : '\u2014';

        const pedidosText = (w.pedidos && w.pedidos.length > 0)
            ? w.pedidos.join(', ')
            : '\u2014';

        // Filas planas: una fila por ítem de cada pedido de la wave (sin recursividad).
        let filas = '';
        if (w.pedidos && w.pedidos.length > 0) {
            filas = w.pedidos.map(oid => {
                const order = orders.find(o => o.id === oid);
                if (!order || !order.items || order.items.length === 0) {
                    return '<tr>' +
                        '<td class="text-right"><strong>' + oid + '</strong></td>' +
                        '<td class="text-right">' + (order ? order.prioridad : '—') + '</td>' +
                        '<td colspan="4">Sin items</td>' +
                        '</tr>';
                }
                return order.items.map(it => {
                    const p = allProducts.find(pr => pr.id === it.productoId);
                    const nombre = p ? p.name : it.productoId;
                    const sku = p ? (p.sku || it.productoId) : it.productoId;
                    const peso = p ? p.pesoKg : '?';
                    return '<tr>' +
                        '<td class="text-right"><strong>' + oid + '</strong></td>' +
                        '<td class="text-right">' + order.prioridad + '</td>' +
                        '<td class="text-right">' + it.cantidad + '</td>' +
                        '<td>' + nombre + '</td>' +
                        '<td class="text-right" style="font-family:var(--font-mono,monospace)">[' + sku + ']</td>' +
                        '<td class="text-right">' + (peso ? peso.toFixed(2) : '?') + ' kg</td>' +
                        '</tr>';
                }).join('');
            }).join('');
        }

        const detalle = filas ? (
            '<div class="wave-detail__row">' +
            '<span class="wave-detail__label">Pedidos (' + w.pedidos.length + ')</span>' +
            '<span class="wave-detail__value">' + pedidosText + '</span>' +
            '</div>' +
            '<table class="wave-detail__table">' +
            '<thead><tr>' +
            '<th class="text-right">Pedido</th>' +
            '<th class="text-right">Prioridad</th>' +
            '<th class="text-right">Cant.</th>' +
            '<th>Producto</th>' +
            '<th class="text-right">SKU</th>' +
            '<th class="text-right">Peso</th>' +
            '</tr></thead>' +
            '<tbody>' + filas + '</tbody>' +
            '</table>'
        ) : (
            '<div class="wave-detail__row">' +
            '<span class="wave-detail__label">Pedidos</span>' +
            '<span class="wave-detail__value">' + pedidosText + '</span>' +
            '</div>' +
            '<p class="wave-detail__empty">Sin detalle de pedidos disponible.</p>'
        );

        const html = '<div class="wave-detail">' +
            '<div class="wave-detail__meta">' +
            '<div class="wave-detail__row">' +
            '<span class="wave-detail__label">Wave</span>' +
            '<span class="wave-detail__value">' + w.wave_id + '</span>' +
            '</div>' +
            '<div class="wave-detail__row">' +
            '<span class="wave-detail__label">Estado</span>' +
            '<span class="wave-detail__value" style="color:var(--color-primary)">' + w.status + '</span>' +
            '</div>' +
            '<div class="wave-detail__row">' +
            '<span class="wave-detail__label">Picker(s)</span>' +
            '<span class="wave-detail__value">' + pickersText + '</span>' +
            '</div>' +
            '<div class="wave-detail__row">' +
            '<span class="wave-detail__label">Prioridad</span>' +
            '<span class="wave-detail__value">' + w.prioridad + '</span>' +
            '</div>' +
            '<div class="wave-detail__row">' +
            '<span class="wave-detail__label">Unidades</span>' +
            '<span class="wave-detail__value">' + w.unidades + '</span>' +
            '</div>' +
            '<div class="wave-detail__row">' +
            '<span class="wave-detail__label">Peso</span>' +
            '<span class="wave-detail__value">' + Number(w.peso_kg || 0).toFixed(2) + ' kg</span>' +
            '</div>' +
            '</div>' +
            detalle +
            '</div>';

        const modalIdEl = document.getElementById('modal-wave-id');
        const modalBodyEl = document.getElementById('modal-wave-body');
        const modalEl = document.getElementById('modal-wave-detail');
        if (!modalIdEl || !modalBodyEl || !modalEl) {
            showToast('Error interno: elementos del modal no encontrados.', 'error');
            return;
        }
        modalIdEl.textContent = w.wave_id;
        modalBodyEl.innerHTML = html;
        modalEl.classList.add('open');
    } catch (err) {
        showToast('Error al abrir detalle de wave: ' + (err && err.message ? err.message : err), 'error');
    }
}

 /** Cierra el modal de detalle de wave. */
 function simCloseWaveDetail() {
     document.getElementById('modal-wave-detail').classList.remove('open');
 }

 // ================================================================
 // Cableado del botón "Consultar" y modal de detalle de wave
 // ================================================================

 /** Habilita/deshabilita el botón Consultar según si hay una wave seleccionada. */
 function simUpdateConsultarBtn() {
     const btn = _dom('btn-consultar-wave');
     if (!btn) return;
     btn.disabled = !_selectedWaveId;
     if (btn.disabled) {
         btn.title = 'Seleccioná una wave de la lista para consultar su detalle.';
     } else {
         btn.title = 'Ver detalle de la wave seleccionada';
     }
 }

 function _wireConsultar() {
     const btnConsultar = _dom('btn-consultar-wave');
     const btnClose = _dom('btn-close-wave-detail');
     const modal = document.getElementById('modal-wave-detail');

     if (btnConsultar) {
         btnConsultar.addEventListener('click', (e) => {
             e.preventDefault();
             e.stopPropagation();
             simOpenWaveDetail();
         });
     }
     if (btnClose) btnClose.addEventListener('click', simCloseWaveDetail);
     if (modal) {
         modal.addEventListener('click', (e) => {
             if (e.target === modal) simCloseWaveDetail();
         });
     }
 }

 // Registrar cuanto antes (DOMContentLoaded o inmediatamente si ya pasó).
 if (document.readyState === 'loading') {
     document.addEventListener('DOMContentLoaded', _wireConsultar);
 } else {
     _wireConsultar();
 }
