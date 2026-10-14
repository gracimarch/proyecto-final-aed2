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

        this.mode = 'select';  // 'select' | 'rack' | 'product' | 'erase'

        // Estado del drag de rack
        this._rackDragStart = null;
        this._isDragging    = false;

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
        this.mode            = mode;
        this.renderer.mode   = mode;
        this.renderer.cursorRect = null;
        this._rackDragStart  = null;
        this._isDragging     = false;

        const cursors = {
            select:  'default',
            rack:    'crosshair',
            product: 'cell',
            erase:   'not-allowed'
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
            case 'select':  this._onSelectDown(cell, e);  break;
            case 'rack':    this._onRackDown(cell);        break;
            case 'product': this._onProductDown(cell);     break;
            case 'erase':   this._onEraseDown(cell);       break;
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
                // Click simple → rack 1×2 en la celda clickeada
                const c = this._rackDragStart;
                this.renderer.cursorRect = { x: c.x, y: c.y, w: 1, h: 2 };
            }
            this._commitRack();
        }

        this._rackDragStart = null;
        this._isDragging    = false;
        this.renderer.cursorRect = null;
    }

    // ── Mouse leave ───────────────────────────────────────────────

    _onMouseLeave() {
        this.renderer.hoverCell  = null;
        this.renderer.cursorRect = null;
        this._isPanning          = false;
        this._rackDragStart      = null;
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

        // Picker tiene prioridad (está encima)
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

        // Picker primero
        const picker = this.scenario.getPickerAt(cell.x, cell.y);
        if (picker) {
            if (this.renderer.selectedElement?.element?.id === picker.id) this._deselect();
            this.scenario.removePicker(picker.id);
            this.onEvent('remove-picker', picker);
            return;
        }

        // Luego rack
        const rack = this.scenario.getRackAt(cell.x, cell.y);
        if (rack) {
            if (this.renderer.selectedElement?.element?.id === rack.id) this._deselect();
            this.scenario.removeRack(rack.id);
            this.onEvent('remove-rack', rack);
        }
    }
}
