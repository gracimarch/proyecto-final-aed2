/* ================================================================
   WAREHOUSE EDITOR
   Maneja la interacción del usuario con el canvas:
   colocar/remover racks, productos y pickers.
   Delega el dibujado al WarehouseRenderer.
================================================================ */

class WarehouseEditor {

    /**
     * @param {HTMLCanvasElement} canvas
     * @param {WarehouseRenderer} renderer
     * @param {function(string, any=)} onEvent  — callback de eventos al UI
     */
    constructor(canvas, renderer, onEvent) {
        this.canvas   = canvas;
        this.renderer = renderer;
        this.scenario = null;
        this.onEvent  = onEvent || (() => {});

        this.mode = 'select';  // 'select' | 'rack' | 'product' | 'erase' | 'door' | 'dispatch' | 'aisle' | 'move-rack'

        // Estado del drag de rack (colocar nuevo)
        this._rackDragStart  = null;
        this._isDragging     = false;

        // Estado drag zona de despacho
        this._dzDragStart    = null;

        // Estado drag pasillo
        this._aisleDragStart = null;

        // Mover rack existente
        this._movingRack     = null;  // { rack, offsetX, offsetY } — kept for compat
        this._movingElement  = null;  // { type, element, offsetX, offsetY } — elemento que se está arrastrando

        // Config herramientas
        this._doorTipo       = 'AMBOS';
        this._aisleSentido   = 'AMBOS';

        // Estado del pan
        this._isPanning  = false;
        this._panStart   = null;
        this._panOrigin  = null;

        // Render bajo demanda: el renderer avisa cuando su estado cambia
        // (hover, pan, selección, rutas, tema…).
        if (this.renderer) this.renderer.onDirty = () => this.requestRender();

        // Loop de render
        this._animFrame = null;
        this.isDirty   = true;   // fuerza el primer dibujo
        this._startLoop();

        this._bindEvents();
    }

    // ── Scenario ─────────────────────────────────────────────────

    setScenario(scenario) {
        this.scenario              = scenario;
        this.renderer.scenario     = scenario;
        this.renderer.selectedElement = null;
        this.renderer.setScenario(scenario);
        this.renderer.hoverCell    = null;
        this.renderer.cursorRect   = null;
    }

    // ── Modo de herramienta ───────────────────────────────────────

    setMode(mode) {
        this.mode             = mode;
        this.renderer.mode    = mode;
        this.renderer.doorTipo = this._doorTipo;
        this.renderer.cursorRect = null;
        this._rackDragStart   = null;
        this._dzDragStart     = null;
        this._aisleDragStart  = null;
        this._movingRack      = null;
        this._movingElement   = null;
        this._isDragging      = false;

        const cursors = {
            select:     'default',
            rack:       'crosshair',
            product:    'cell',
            erase:      'not-allowed',
            door:       'crosshair',
            dispatch:   'crosshair',
            aisle:      'crosshair',
            'move-rack':'grab',
        };
        this.canvas.style.cursor = cursors[mode] || 'default';
    }

    // ── Render loop ───────────────────────────────────────────────

    /** Marca el canvas como sucio: se redibuja en el próximo frame. */
    requestRender() {
        this.isDirty = true;
    }

    _startLoop() {
        const loop = () => {
            // Agendar antes de dibujar: si render() lanza una excepción,
            // el loop no debe morir y dejar el canvas congelado.
            this._animFrame = requestAnimationFrame(loop);
            // Render bajo demanda: sin cambios no se toca el canvas
            // (CPU ≈ 0% en reposo y con la simulación pausada).
            if (!this.isDirty) return;
            this.isDirty = false;
            try {
                this.renderer.render();
                this._renderErrorLogged = false;
            } catch (err) {
                if (!this._renderErrorLogged) {
                    this._renderErrorLogged = true;
                    console.error('[WarehouseEditor] Error al renderizar:', err);
                }
            }
        };
        this._animFrame = requestAnimationFrame(loop);
    }

    stopLoop() {
        if (this._animFrame) cancelAnimationFrame(this._animFrame);
    }

    // ── Eventos del canvas ────────────────────────────────────────

    _bindEvents() {
        const c = this.canvas;
        c.addEventListener('mousedown',  e => this._onMouseDown(e));
        c.addEventListener('mousemove',  e => this._onMouseMove(e));
        c.addEventListener('mouseup',    e => this._onMouseUp(e));
        c.addEventListener('mouseleave', e => this._onMouseLeave(e));
        c.addEventListener('wheel',      e => this._onWheel(e), { passive: false });
        c.addEventListener('contextmenu', e => e.preventDefault());
    }

    _screenPos(e) {
        const r = this.canvas.getBoundingClientRect();
        return { x: e.clientX - r.left, y: e.clientY - r.top };
    }

    _cellAt(e) {
        const sp = this._screenPos(e);
        return this.renderer.screenToCell(sp.x, sp.y);
    }

    // ── Mouse down ────────────────────────────────────────────────

    _onMouseDown(e) {
        const sp   = this._screenPos(e);
        const cell = this._cellAt(e);

        // Clic derecho o botón medio → pan
        if (e.button === 1 || e.button === 2) {
            this._isPanning = true;
            this._panStart  = sp;
            this._panOrigin = { x: this.renderer.panX, y: this.renderer.panY };
            this.canvas.style.cursor = 'grabbing';
            return;
        }

        if (e.button !== 0 || !this.scenario) return;

        // Bloquear herramientas de edicion mientras la simulacion esta activa.
        // El modo 'select' queda libre para poder inspeccionar elementos.
        if (typeof simIsEditingLocked === 'function' && simIsEditingLocked()) {
            if (this.mode !== 'select') return;
        }

        switch (this.mode) {
            case 'select':    this._onSelectDown(cell, e);   break;
            case 'rack':      this._onRackDown(cell);         break;
            case 'product':   this._onProductDown(cell);      break;
            case 'erase':     this._onEraseDown(cell);        break;
            case 'door':      this._onDoorDown(cell);         break;
            case 'dispatch':  this._onDispatchDown(cell);     break;
            case 'aisle':     this._onAisleDown(cell);        break;
            case 'move-rack': this._onMoveRackDown(cell);     break;
        }
        this.requestRender();
    }

    // ── Mouse move ────────────────────────────────────────────────

    _onMouseMove(e) {
        const sp   = this._screenPos(e);
        const cell = this._cellAt(e);

        if (this._isPanning) {
            const dx = sp.x - this._panStart.x;
            const dy = sp.y - this._panStart.y;
            this.renderer.panX = this._panOrigin.x + dx;
            this.renderer.panY = this._panOrigin.y + dy;
            return;
        }

        if (!this.scenario) return;

        // Hover cell
        this.renderer.hoverCell = this.scenario.isInBounds(cell.x, cell.y) ? cell : null;

        // Preview de rack durante drag
        if (this.mode === 'rack' && this._rackDragStart) {
            this._isDragging = true;
            const x = Math.min(this._rackDragStart.x, cell.x);
            const y = Math.min(this._rackDragStart.y, cell.y);
            const w = Math.abs(cell.x - this._rackDragStart.x) + 1;
            const h = Math.abs(cell.y - this._rackDragStart.y) + 1;
            this.renderer.cursorRect = { x, y, w, h };
        }

        // Preview de dispatch zone durante drag
        if (this.mode === 'dispatch' && this._dzDragStart) {
            this._isDragging = true;
            const x = Math.min(this._dzDragStart.x, cell.x);
            const y = Math.min(this._dzDragStart.y, cell.y);
            const w = Math.abs(cell.x - this._dzDragStart.x) + 1;
            const h = Math.abs(cell.y - this._dzDragStart.y) + 1;
            this.renderer.cursorRect = { x, y, w, h };
        }

        // Preview de pasillo durante drag
        if (this.mode === 'aisle' && this._aisleDragStart) {
            this._isDragging = true;
            const x = Math.min(this._aisleDragStart.x, cell.x);
            const y = Math.min(this._aisleDragStart.y, cell.y);
            const w = Math.abs(cell.x - this._aisleDragStart.x) + 1;
            const h = Math.abs(cell.y - this._aisleDragStart.y) + 1;
            this.renderer.cursorRect = { x, y, w, h };
        }

        // Preview puerta (1 celda)
        if (this.mode === 'door' && this.scenario && this.scenario.isInBounds(cell.x, cell.y)) {
            this.renderer.cursorRect = { x: cell.x, y: cell.y, w: 1, h: 1 };
        }

        // Preview celda en modo producto
        if (this.mode === 'product') {
            const rackUnder = this.scenario.getRackAt(cell.x, cell.y);
            this.renderer.cursorRect = rackUnder ? { x: cell.x, y: cell.y, w: 1, h: 1 } : null;
        }

        // Mover elemento: preview en vivo
        if (this.mode === 'move-rack' && this._movingElement) {
            this._isDragging = true;
            const { type, element, offsetX, offsetY } = this._movingElement;
            if (type === 'rack') {
                const nx = cell.x - offsetX;
                const ny = cell.y - offsetY;
                this.renderer.cursorRect = { x: nx, y: ny, w: element.width, h: element.height };
            } else if (type === 'dispatch') {
                const nx = cell.x - offsetX;
                const ny = cell.y - offsetY;
                this.renderer.cursorRect = { x: nx, y: ny, w: element.width, h: element.height };
            } else {
                // door o picker: 1×1, el cursor indica la celda destino
                this.renderer.cursorRect = { x: cell.x, y: cell.y, w: 1, h: 1 };
            }
        }
    }

    // ── Mouse up ──────────────────────────────────────────────────

    _onMouseUp(e) {
        if (this._isPanning) {
            this._isPanning = false;
            this.setMode(this.mode);  // restaura cursor
            return;
        }

        if (e.button !== 0 || !this.scenario) return;

        if (this.mode === 'rack' && this._rackDragStart) {
            if (!this._isDragging) {
                const c = this._rackDragStart;
                this.renderer.cursorRect = { x: c.x, y: c.y, w: 1, h: 2 };
            }
            this._commitRack();
        }

        if (this.mode === 'dispatch' && this._dzDragStart) {
            if (!this._isDragging) {
                const c = this._dzDragStart;
                this.renderer.cursorRect = { x: c.x, y: c.y, w: 3, h: 2 };
            }
            this._commitDispatch();
        }

        if (this.mode === 'aisle' && this._aisleDragStart) {
            if (!this._isDragging) {
                const c = this._aisleDragStart;
                this.renderer.cursorRect = { x: c.x, y: c.y, w: 1, h: 1 };
            }
            this._commitAisle();
        }

        if (this.mode === 'move-rack' && this._movingElement) {
            this._commitMove(this._cellAt(e));
        }

        this._rackDragStart  = null;
        this._dzDragStart    = null;
        this._aisleDragStart = null;
        this._movingRack     = null;
        this._movingElement  = null;
        this._isDragging     = false;
        this.renderer.cursorRect = null;
        // Los commits de arriba ya invalidaron la capa si cambiaron geometría.
        this.requestRender();
    }

    // ── Mouse leave ───────────────────────────────────────────────

    _onMouseLeave() {
        this.renderer.hoverCell  = null;
        this.renderer.cursorRect = null;
        this._isPanning          = false;
        this._rackDragStart      = null;
        this._dzDragStart        = null;
        this._aisleDragStart     = null;
        this._movingRack         = null;
        this._movingElement      = null;
        this._isDragging         = false;
        this.requestRender();
    }

    // ── Wheel (zoom) ──────────────────────────────────────────────

    _onWheel(e) {
        e.preventDefault();
        if (!this.scenario) return;
        const sp     = this._screenPos(e);
        const factor = e.deltaY < 0 ? 1.12 : 0.9;
        this.renderer.zoomBy(factor, sp.x, sp.y);
    }

    // ── Handlers por modo ────────────────────────────────────────

    _onSelectDown(cell) {
        if (!this.scenario.isInBounds(cell.x, cell.y)) {
            this._deselect();
            return;
        }

        const picker = this.scenario.getPickerAt(cell.x, cell.y);
        if (picker) {
            this.renderer.selectedElement = { type: 'picker', element: picker };
            this.onEvent('select-picker', picker);
            return;
        }

        const rack = this.scenario.getRackAt(cell.x, cell.y);
        if (rack) {
            this.renderer.selectedElement = { type: 'rack', element: rack };
            this.onEvent('select-rack', rack);
            return;
        }

        const door = this.scenario.getDoorAt(cell.x, cell.y);
        if (door) {
            this.renderer.selectedElement = { type: 'door', element: door };
            this.onEvent('select-door', door);
            return;
        }

        const dz = this.scenario.getDispatchZoneAt(cell.x, cell.y);
        if (dz) {
            this.renderer.selectedElement = { type: 'dispatch', element: dz };
            this.onEvent('select-dispatch', dz);
            return;
        }

        const aisle = this.scenario.getAisleAt(cell.x, cell.y);
        if (aisle) {
            this.renderer.selectedElement = { type: 'aisle', element: aisle };
            this.onEvent('select-aisle', aisle);
            return;
        }

        this._deselect();
    }

    _deselect() {
        this.renderer.selectedElement = null;
        this.onEvent('deselect');
    }

    _onRackDown(cell) {
        if (!this.scenario.isInBounds(cell.x, cell.y)) return;
        this._rackDragStart = cell;
        this._isDragging    = false;
        this.renderer.cursorRect = { x: cell.x, y: cell.y, w: 1, h: 1 };
    }

    _commitRack() {
        const rect = this.renderer.cursorRect;
        if (!rect) return;

        const rack = this.scenario.addRack(rect.x, rect.y, rect.w, rect.h);
        if (rack) {
            this.renderer.selectedElement = { type: 'rack', element: rack };
            this.onEvent('add-rack', rack);
        } else {
            this.onEvent('error', 'No se pudo colocar el rack. Verificá que: no esté ocupado, tenga distancia ≥ 1 con otros racks, y que todas sus celdas queden accesibles para los pickers (sin celdas bloqueadas por paredes, puertas o zonas de despacho en todos sus costados).');
        }
    }

    _onProductDown(cell) {
        if (!this.scenario.isInBounds(cell.x, cell.y)) return;
        const rack = this.scenario.getRackAt(cell.x, cell.y);
        if (rack) {
            this.onEvent('open-product-form', { rack, cell });
        } else {
            this.onEvent('hint', 'Hacé click en un rack para agregarle un producto.');
        }
    }

    _onEraseDown(cell) {
        if (!this.scenario.isInBounds(cell.x, cell.y)) return;

        const picker = this.scenario.getPickerAt(cell.x, cell.y);
        if (picker) {
            if (this.renderer.selectedElement?.element?.id === picker.id) this._deselect();
            this.scenario.removePicker(picker.id);
            this.onEvent('remove-picker', picker);
            return;
        }

        const rack = this.scenario.getRackAt(cell.x, cell.y);
        if (rack) {
            if (this.renderer.selectedElement?.element?.id === rack.id) this._deselect();
            this.scenario.removeRack(rack.id);
            this.onEvent('remove-rack', rack);
            return;
        }

        const dz = this.scenario.getDispatchZoneAt(cell.x, cell.y);
        if (dz) {
            if (this.renderer.selectedElement?.element?.id === dz.id) this._deselect();
            this.scenario.removeDispatchZone(dz.id);
            this.onEvent('remove-dispatch', dz);
            return;
        }

        const door = this.scenario.getDoorAt(cell.x, cell.y);
        if (door) {
            if (this.renderer.selectedElement?.element?.id === door.id) this._deselect();
            this.scenario.removeDoor(door.id);
            this.onEvent('remove-door', door);
            return;
        }

        const aisle = this.scenario.getAisleAt(cell.x, cell.y);
        if (aisle) {
            if (this.renderer.selectedElement?.element?.id === aisle.id) this._deselect();
            this.scenario.removeAisle(aisle.id);
            this.onEvent('remove-aisle', aisle);
            return;
        }
    }

    // ── Nuevos handlers ───────────────────────────────────────────

    _onDoorDown(cell) {
        if (!this.scenario.isInBounds(cell.x, cell.y)) return;
        const door = this.scenario.addDoor(cell.x, cell.y, this._doorTipo || 'AMBOS');
        if (door) {
            this.renderer.selectedElement = { type: 'door', element: door };
            this.onEvent('add-door', door);
        } else {
            this.onEvent('error', 'Las puertas solo se pueden colocar en el borde del warehouse, o ya existe una puerta ahí.');
        }
    }

    _onDispatchDown(cell) {
        if (!this.scenario.isInBounds(cell.x, cell.y)) return;
        this._dzDragStart = cell;
        this._isDragging  = false;
        this.renderer.cursorRect = { x: cell.x, y: cell.y, w: 3, h: 2 };
    }

    _commitDispatch() {
        const rect = this.renderer.cursorRect;
        if (!rect) return;
        const result = this.scenario.addDispatchZone(rect.x, rect.y, rect.w, rect.h);
        if (result && !result.error) {
            this.renderer.selectedElement = { type: 'dispatch', element: result };
            this.onEvent('add-dispatch', result);
        } else if (result && result.error === 'no-door') {
            this.onEvent('error', 'La zona de despacho debe ser adyacente a una puerta.');
        } else if (result && result.error === 'door-taken') {
            this.onEvent('error', 'La puerta adyacente ya está asignada a otra zona de despacho.');
        } else if (result && result.error === 'multiple-doors') {
            this.onEvent('error', 'La zona no puede ser adyacente a más de una puerta. Reubicala.');
        } else {
            this.onEvent('error', 'No se pudo colocar la zona (area ocupada o fuera de limites).');
        }
    }

    _onAisleDown(cell) {
        if (!this.scenario.isInBounds(cell.x, cell.y)) return;
        this._aisleDragStart = cell;
        this._isDragging     = false;
        this.renderer.cursorRect = { x: cell.x, y: cell.y, w: 1, h: 1 };
    }

    _commitAisle() {
        const rect = this.renderer.cursorRect;
        if (!rect) return;

        // Inferir sentido desde la dirección dominante del drag
        let sentido = 'AMBOS';
        if (this._aisleDragStart && (rect.w > 1 || rect.h > 1)) {
            const start = this._aisleDragStart;
            // rect.x = min(start.x, end.x), así que end.x es el extremo opuesto a start.x
            const endX = start.x === rect.x ? rect.x + rect.w - 1 : rect.x;
            const endY = start.y === rect.y ? rect.y + rect.h - 1 : rect.y;
            const dx = endX - start.x;
            const dy = endY - start.y;
            if (Math.abs(dx) > Math.abs(dy)) {
                sentido = dx > 0 ? 'E' : 'O';
            } else if (Math.abs(dy) > Math.abs(dx)) {
                sentido = dy > 0 ? 'N' : 'S';
            }
            // Si dx == dy (cuadrado o click simple) queda 'AMBOS'
        }

        const aisle = this.scenario.addAisle(rect.x, rect.y, rect.w, rect.h, sentido);
        if (aisle) {
            this.renderer.selectedElement = { type: 'aisle', element: aisle };
            this.onEvent('add-aisle', aisle);
        }
    }

    _onMoveRackDown(cell) {
        if (!this.scenario.isInBounds(cell.x, cell.y)) return;

        const picker = this.scenario.getPickerAt(cell.x, cell.y);
        if (picker) {
            this._movingElement = { type: 'picker', element: picker, offsetX: 0, offsetY: 0 };
            this.canvas.style.cursor = 'grabbing';
            this.renderer.cursorRect = { x: picker.x, y: picker.y, w: 1, h: 1 };
            return;
        }

        const rack = this.scenario.getRackAt(cell.x, cell.y);
        if (rack) {
            const ox = cell.x - rack.x, oy = cell.y - rack.y;
            this._movingRack    = { rack, offsetX: ox, offsetY: oy };  // compat
            this._movingElement = { type: 'rack', element: rack, offsetX: ox, offsetY: oy };
            this.canvas.style.cursor = 'grabbing';
            this.renderer.cursorRect = { x: rack.x, y: rack.y, w: rack.width, h: rack.height };
            return;
        }

        this.onEvent('hint', 'Hacé click en un rack o picker para moverlo.');
    }

    _commitMove(cell) {
        if (!this._movingElement) return;
        const { type, element, offsetX, offsetY } = this._movingElement;

        if (type === 'rack') {
            const nx = cell.x - offsetX;
            const ny = cell.y - offsetY;
            const moved = this.scenario.moveRack(element.id, nx, ny);
            if (moved) {
                this.renderer.selectedElement = { type: 'rack', element };
                this.onEvent('move-rack', element);
            } else {
                this.onEvent('error', 'No se pudo mover el rack. Verificá que: la posición esté libre, haya distancia ≥ 1 con otros racks, y que todas sus celdas queden accesibles para los pickers (sin celdas bloqueadas por paredes, puertas o zonas de despacho).');
            }
        } else if (type === 'picker') {
            const moved = this.scenario.movePicker(element.id, cell.x, cell.y);
            if (moved) {
                this.renderer.selectedElement = { type: 'picker', element };
                this.onEvent('move-picker', element);
            } else {
                this.onEvent('error', 'No se pudo mover el picker (celda ocupada o fuera de límites).');
            }
        }
    }

    // Kept for backwards compat
    _commitMoveRack(cell) { this._commitMove(cell); }
}
