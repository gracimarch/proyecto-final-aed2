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
        this._movingRack     = null;  // { rack, offsetX, offsetY }

        // Config herramientas
        this._doorTipo       = 'AMBOS';
        this._aisleSentido   = 'AMBOS';

        // Estado del pan
        this._isPanning  = false;
        this._panStart   = null;
        this._panOrigin  = null;

        // Loop de render
        this._animFrame = null;
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
        this.renderer.cursorRect = null;
        this._rackDragStart   = null;
        this._dzDragStart     = null;
        this._aisleDragStart  = null;
        this._movingRack      = null;
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

    _startLoop() {
        const loop = () => {
            this.renderer.render();
            this._animFrame = requestAnimationFrame(loop);
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

        // Mover rack: preview en vivo
        if (this.mode === 'move-rack' && this._movingRack) {
            this._isDragging = true;
            const { rack, offsetX, offsetY } = this._movingRack;
            const nx = cell.x - offsetX;
            const ny = cell.y - offsetY;
            this.renderer.cursorRect = { x: nx, y: ny, w: rack.width, h: rack.height };
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

        if (this.mode === 'move-rack' && this._movingRack) {
            this._commitMoveRack(this._cellAt(e));
        }

        this._rackDragStart  = null;
        this._dzDragStart    = null;
        this._aisleDragStart = null;
        this._movingRack     = null;
        this._isDragging     = false;
        this.renderer.cursorRect = null;
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
        this._isDragging         = false;
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
            this.onEvent('error', 'No se pudo colocar el rack (área ocupada o fuera de límites).');
        }
    }

    _onProductDown(cell) {
        if (!this.scenario.isInBounds(cell.x, cell.y)) return;
        const rack = this.scenario.getRackAt(cell.x, cell.y);
        if (rack) {
            this.onEvent('open-product-form', rack);
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
        const aisle = this.scenario.addAisle(rect.x, rect.y, rect.w, rect.h, this._aisleSentido || 'AMBOS');
        if (aisle) {
            this.renderer.selectedElement = { type: 'aisle', element: aisle };
            this.onEvent('add-aisle', aisle);
        }
    }

    _onMoveRackDown(cell) {
        if (!this.scenario.isInBounds(cell.x, cell.y)) return;
        const rack = this.scenario.getRackAt(cell.x, cell.y);
        if (!rack) {
            this.onEvent('hint', 'Hacé click en un rack para moverlo.');
            return;
        }
        this._movingRack = { rack, offsetX: cell.x - rack.x, offsetY: cell.y - rack.y };
        this.canvas.style.cursor = 'grabbing';
        this.renderer.cursorRect = { x: rack.x, y: rack.y, w: rack.width, h: rack.height };
    }

    _commitMoveRack(cell) {
        if (!this._movingRack) return;
        const { rack, offsetX, offsetY } = this._movingRack;
        const nx = cell.x - offsetX;
        const ny = cell.y - offsetY;
        const moved = this.scenario.moveRack(rack.id, nx, ny);
        if (moved) {
            this.renderer.selectedElement = { type: 'rack', element: rack };
            this.onEvent('move-rack', rack);
        } else {
            this.onEvent('error', 'No se pudo mover el rack (área ocupada o fuera de límites).');
        }
    }
}

