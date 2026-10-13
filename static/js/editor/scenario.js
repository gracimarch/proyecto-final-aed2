/* ================================================================
   SCENARIO MODEL
   Clases de datos para representar el warehouse en memoria.
   No depende de ninguna librería externa.
================================================================ */

// ── Utilidades ───────────────────────────────────────────────────

function _genId(prefix = '') {
    return prefix + Math.random().toString(36).substr(2, 8).toUpperCase();
}

const PICKER_COLORS = [
    '#FF6B6B', '#4ECDC4', '#FFE66D', '#A8E6CF',
    '#FF8B94', '#7C83FD', '#96E6A1', '#F7B267',
    '#B388FF', '#80CBC4'
];

// ── Rack ─────────────────────────────────────────────────────────

class Rack {
    constructor({ id = null, x, y, width = 1, height = 2 } = {}) {
        this.id       = id || _genId('R');
        this.x        = x;        // columna (celda)
        this.y        = y;        // fila (celda)
        this.width    = width;    // en celdas
        this.height   = height;   // en celdas
        this.products = [];       // Product[]
    }

    /** Devuelve true si la celda (cx, cy) está dentro de este rack. */
    containsCell(cx, cy) {
        return cx >= this.x && cx < this.x + this.width &&
               cy >= this.y && cy < this.y + this.height;
    }

    toJSON() {
        return {
            id: this.id, x: this.x, y: this.y,
            width: this.width, height: this.height,
            products: this.products.map(p => p.toJSON())
        };
    }

    static fromJSON(data) {
        const rack = new Rack(data);
        rack.products = (data.products || []).map(p => Product.fromJSON(p));
        return rack;
    }
}

// ── Product ───────────────────────────────────────────────────────

class Product {
    constructor({ id = null, name, sku, quantity = 1, rackId } = {}) {
        this.id       = id || _genId('P');
        this.name     = name || 'Producto';
        this.sku      = sku  || this.id;
        this.quantity = quantity;
        this.rackId   = rackId;
    }

    toJSON() {
        return { id: this.id, name: this.name, sku: this.sku, quantity: this.quantity, rackId: this.rackId };
    }

    static fromJSON(data) { return new Product(data); }
}

// ── Picker ────────────────────────────────────────────────────────

class Picker {
    constructor({ id = null, x, y, name = null, color = null } = {}) {
        this.id    = id || _genId('PK');
        this.x     = x;
        this.y     = y;
        this.name  = name  || this.id;
        this.color = color || PICKER_COLORS[0];
    }

    toJSON() {
        return { id: this.id, x: this.x, y: this.y, name: this.name, color: this.color };
    }

    static fromJSON(data) { return new Picker(data); }
}

// ── Scenario ──────────────────────────────────────────────────────

class Scenario {
    constructor({ id = null, name = 'Nuevo Escenario', width = 20, height = 15 } = {}) {
        this.id      = id || _genId('SC');
        this.name    = name;
        this.width   = width;    // columnas
        this.height  = height;   // filas
        this.racks   = [];       // Rack[]
        this.pickers = [];       // Picker[]

        // Zona de despacho: esquina inferior-izquierda, 3×2 celdas
        this.dispatchZone = { x: 0, y: height - 3, w: 3, h: 2 };

        this._nextPickerColorIdx = 0;
        this._nextPickerNum      = 1;
    }

    // ── Racks ────────────────────────────────────────────────────

    addRack(x, y, width, height) {
        // Normalizar para que siempre x,y sea top-left
        const nx = Math.max(0, Math.min(x, this.width  - width));
        const ny = Math.max(0, Math.min(y, this.height - height));

        if (!this.isInBounds(nx, ny) || !this.isInBounds(nx + width - 1, ny + height - 1)) return null;
        if (this._isAreaOccupied(nx, ny, width, height)) return null;

        const rack = new Rack({ x: nx, y: ny, width, height });
        this.racks.push(rack);
        return rack;
    }

    removeRack(id) {
        const idx = this.racks.findIndex(r => r.id === id);
        if (idx === -1) return false;
        this.racks.splice(idx, 1);
        return true;
    }

    getRackById(id) {
        return this.racks.find(r => r.id === id) || null;
    }

    getRackAt(cx, cy) {
        return this.racks.find(r => r.containsCell(cx, cy)) || null;
    }

    // ── Products ─────────────────────────────────────────────────

    addProduct(rackId, { name, sku, quantity }) {
        const rack = this.getRackById(rackId);
        if (!rack) return null;
        const product = new Product({ name, sku, quantity, rackId });
        rack.products.push(product);
        return product;
    }

    removeProduct(productId) {
        for (const rack of this.racks) {
            const idx = rack.products.findIndex(p => p.id === productId);
            if (idx !== -1) { rack.products.splice(idx, 1); return true; }
        }
        return false;
    }

    getAllProducts() {
        return this.racks.flatMap(r => r.products);
    }

    // ── Pickers ───────────────────────────────────────────────────

    addPicker(x, y) {
        if (!this.isInBounds(x, y))         return null;
        if (this.getRackAt(x, y))           return null;  // no puede estar sobre un rack
        if (this.getPickerAt(x, y))         return null;  // ya hay uno
        if (this._isInDispatchZone(x, y))   return null;

        const color  = PICKER_COLORS[this._nextPickerColorIdx % PICKER_COLORS.length];
        const picker = new Picker({ x, y, color, name: `Picker ${this._nextPickerNum}` });
        this._nextPickerColorIdx++;
        this._nextPickerNum++;
        this.pickers.push(picker);
        return picker;
    }

    removePicker(id) {
        const idx = this.pickers.findIndex(p => p.id === id);
        if (idx === -1) return false;
        this.pickers.splice(idx, 1);
        return true;
    }

    getPickerAt(cx, cy) {
        return this.pickers.find(p => p.x === cx && p.y === cy) || null;
    }

    // ── Utilidades ────────────────────────────────────────────────

    isInBounds(cx, cy) {
        return cx >= 0 && cx < this.width && cy >= 0 && cy < this.height;
    }

    _isInDispatchZone(cx, cy) {
        const dz = this.dispatchZone;
        return cx >= dz.x && cx < dz.x + dz.w && cy >= dz.y && cy < dz.y + dz.h;
    }

    _isAreaOccupied(x, y, w, h) {
        for (let cy = y; cy < y + h; cy++) {
            for (let cx = x; cx < x + w; cx++) {
                if (this.getRackAt(cx, cy))       return true;
                if (this._isInDispatchZone(cx, cy)) return true;
            }
        }
        return false;
    }

    // ── Stats ─────────────────────────────────────────────────────

    stats() {
        return {
            racks:    this.racks.length,
            products: this.getAllProducts().length,
            pickers:  this.pickers.length,
            size:     `${this.width} × ${this.height}`
        };
    }

    // ── Serialización ─────────────────────────────────────────────

    toJSON() {
        return {
            id:           this.id,
            name:         this.name,
            width:        this.width,
            height:       this.height,
            racks:        this.racks.map(r => r.toJSON()),
            pickers:      this.pickers.map(p => p.toJSON()),
            dispatchZone: { ...this.dispatchZone },
            _nextPickerColorIdx: this._nextPickerColorIdx,
            _nextPickerNum:      this._nextPickerNum
        };
    }

    static fromJSON(data) {
        const s = new Scenario({
            id: data.id, name: data.name,
            width: data.width, height: data.height
        });
        s.dispatchZone         = data.dispatchZone;
        s.racks                = (data.racks   || []).map(r => Rack.fromJSON(r));
        s.pickers              = (data.pickers || []).map(p => Picker.fromJSON(p));
        s._nextPickerColorIdx  = data._nextPickerColorIdx ?? s.pickers.length;
        s._nextPickerNum       = data._nextPickerNum      ?? s.pickers.length + 1;
        return s;
    }
}
