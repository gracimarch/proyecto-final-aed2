/* ================================================================
   SCENARIO MODEL - Clases de datos para el warehouse
================================================================ */

function _genId(prefix) {
    prefix = prefix || '';
    return prefix + Math.random().toString(36).substr(2, 8).toUpperCase();
}

const PICKER_COLORS = [
    '#FF6B6B', '#4ECDC4', '#FFE66D', '#A8E6CF',
    '#FF8B94', '#7C83FD', '#96E6A1', '#F7B267',
    '#B388FF', '#80CBC4'
];

class Rack {
    constructor({ id = null, x, y, width = 2, height = 4 } = {}) {
        this.id = id || _genId('R');
        this.x = x; this.y = y;
        this.width = width; this.height = height;
        this.products = [];
    }
    containsCell(cx, cy) {
        return cx >= this.x && cx < this.x + this.width && cy >= this.y && cy < this.y + this.height;
    }
    toJSON() {
        return { id: this.id, ubicacion: { x: this.x, y: this.y }, ancho: this.width, alto: this.height };
    }
    static fromJSON(data) {
        const ub = data.ubicacion || {};
        return new Rack({ id: data.id, x: ub.x != null ? ub.x : data.x, y: ub.y != null ? ub.y : data.y,
            width: data.ancho != null ? data.ancho : (data.width != null ? data.width : 2),
            height: data.alto != null ? data.alto : (data.height != null ? data.height : 4) });
    }
}

class Product {
    constructor({ id = null, name = 'Producto', sku = null, rackId, x = 0, y = 0, z = 1, quantity = 1, pesoKg = 1.0 } = {}) {
        this.id = id || _genId('P');
        this.name = name; this.sku = sku || this.id; this.rackId = rackId;
        this.x = x; this.y = y; this.z = z; this.quantity = quantity; this.pesoKg = pesoKg;
    }
    toJSON() {
        return { id: this.id, nombre: this.name, rack_id: this.rackId,
            ubicacion: { x: this.x, y: this.y, z: this.z }, cantidad_disponible: this.quantity, peso_kg: this.pesoKg };
    }
    static fromJSON(data) {
        const ub = data.ubicacion || {};
        return new Product({ id: data.id,
            name: data.nombre != null ? data.nombre : (data.name != null ? data.name : 'Producto'),
            sku: data.sku != null ? data.sku : data.id,
            rackId: data.rack_id != null ? data.rack_id : data.rackId,
            x: ub.x != null ? ub.x : (data.x != null ? data.x : 0),
            y: ub.y != null ? ub.y : (data.y != null ? data.y : 0),
            z: ub.z != null ? ub.z : (data.z != null ? data.z : 1),
            quantity: data.cantidad_disponible != null ? data.cantidad_disponible : (data.quantity != null ? data.quantity : 1),
            pesoKg: data.peso_kg != null ? data.peso_kg : (data.pesoKg != null ? data.pesoKg : 1.0) });
    }
}

class Picker {
    constructor({ id = null, x, y, name = null, color = null, capacidadKg = 100 } = {}) {
        this.id = id || _genId('PK');
        this.x = x; this.y = y; this.name = name || this.id;
        this.color = color || PICKER_COLORS[0]; this.capacidadKg = capacidadKg;
    }
    toJSON() {
        return { id: this.id, posicion_inicial: { x: this.x, y: this.y }, capacidad_carga_kg: this.capacidadKg };
    }
    static fromJSON(data) {
        const pos = data.posicion_inicial || {};
        return new Picker({ id: data.id,
            x: pos.x != null ? pos.x : data.x, y: pos.y != null ? pos.y : data.y,
            name: data.name != null ? data.name : data.id, color: data.color || null,
            capacidadKg: data.capacidad_carga_kg != null ? data.capacidad_carga_kg : (data.capacidadKg != null ? data.capacidadKg : 100) });
    }
}

class Door {
    constructor({ id = null, x, y, tipo = 'AMBOS' } = {}) {
        this.id = id || _genId('D'); this.x = x; this.y = y; this.tipo = tipo;
    }
    toJSON() { return { id: this.id, tipo: this.tipo, ubicacion: { x: this.x, y: this.y } }; }
    static fromJSON(data) {
        const ub = data.ubicacion || {};
        return new Door({ id: data.id, x: ub.x != null ? ub.x : data.x, y: ub.y != null ? ub.y : data.y, tipo: data.tipo || 'AMBOS' });
    }
}

class Aisle {
    constructor({ id = null, x, y, width = 1, height = 1, sentido = 'AMBOS' } = {}) {
        this.id = id || _genId('A'); this.x = x; this.y = y;
        this.width = width; this.height = height; this.sentido = sentido;
    }
    containsCell(cx, cy) {
        return cx >= this.x && cx < this.x + this.width && cy >= this.y && cy < this.y + this.height;
    }
    toJSON() { return { id: this.id, ubicacion: { x: this.x, y: this.y }, ancho: this.width, alto: this.height, sentido: this.sentido }; }
    static fromJSON(data) {
        const ub = data.ubicacion || {};
        return new Aisle({ id: data.id, x: ub.x != null ? ub.x : data.x, y: ub.y != null ? ub.y : data.y,
            width: data.ancho != null ? data.ancho : (data.width != null ? data.width : 1),
            height: data.alto != null ? data.alto : (data.height != null ? data.height : 1),
            sentido: data.sentido || 'AMBOS' });
    }
}

class DispatchZone {
    constructor({ id = null, puertaId = null, x, y, width = 3, height = 2, pesoMaxKg = 500 } = {}) {
        this.id = id || _genId('Z'); this.puertaId = puertaId;
        this.x = x; this.y = y; this.width = width; this.height = height; this.pesoMaxKg = pesoMaxKg;
    }
    containsCell(cx, cy) {
        return cx >= this.x && cx < this.x + this.width && cy >= this.y && cy < this.y + this.height;
    }
    toJSON() { return { id: this.id, puerta_id: this.puertaId, ubicacion: { x: this.x, y: this.y }, ancho: this.width, alto: this.height, peso_max_kg: this.pesoMaxKg }; }
    static fromJSON(data) {
        const ub = data.ubicacion || {};
        return new DispatchZone({ id: data.id, puertaId: data.puerta_id != null ? data.puerta_id : data.puertaId,
            x: ub.x != null ? ub.x : data.x, y: ub.y != null ? ub.y : data.y,
            width: data.ancho != null ? data.ancho : (data.width != null ? data.width : 3),
            height: data.alto != null ? data.alto : (data.height != null ? data.height : 2),
            pesoMaxKg: data.peso_max_kg != null ? data.peso_max_kg : (data.pesoMaxKg != null ? data.pesoMaxKg : 500) });
    }
}

class OrderItem {
    constructor({ productoId, cantidad = 1 } = {}) { this.productoId = productoId; this.cantidad = cantidad; }
    toJSON() { return { producto_id: this.productoId, cantidad: this.cantidad }; }
    static fromJSON(data) { return new OrderItem({ productoId: data.producto_id != null ? data.producto_id : data.productoId, cantidad: data.cantidad != null ? data.cantidad : 1 }); }
}

class Order {
    constructor({ id = null, prioridad = 3, estado = 'PENDIENTE', items = [] } = {}) {
        this.id = id || _genId('O'); this.prioridad = prioridad; this.estado = estado; this.items = items;
    }
    toJSON() { return { id: this.id, prioridad: this.prioridad, estado: this.estado, items: this.items.map(i => i.toJSON()) }; }
    static fromJSON(data) {
        return new Order({ id: data.id, prioridad: data.prioridad != null ? data.prioridad : 3,
            estado: data.estado || 'PENDIENTE', items: (data.items || []).map(i => OrderItem.fromJSON(i)) });
    }
}

class Scenario {
    constructor({ id = null, name = 'Nuevo Escenario', width = 20, height = 15 } = {}) {
        this.id = id || _genId('SC'); this.name = name; this.width = width; this.height = height;
        this.racks = []; this.pickers = []; this.doors = []; this.aisles = []; this.dispatchZones = []; this.orders = [];
        this.waveMaxPedidos = 5; this.waveMaxProductos = 20;
        // SIN zona de despacho por defecto - se coloca manualmente
        this._nextPickerColorIdx = 0; this._nextPickerNum = 1;
    }

    // ── Racks ────────────────────────────────────────────────────────
    addRack(x, y, width, height) {
        // Restriccion: min(width,height) <= 2
        if (Math.min(width, height) > 2) {
            if (width <= height) width = 2; else height = 2;
        }
        const nx = Math.max(0, Math.min(x, this.width - width));
        const ny = Math.max(0, Math.min(y, this.height - height));
        if (!this.isInBounds(nx, ny) || !this.isInBounds(nx + width - 1, ny + height - 1)) return null;
        if (this._isAreaOccupied(nx, ny, width, height)) return null;
        const rack = new Rack({ x: nx, y: ny, width, height });
        this.racks.push(rack);
        return rack;
    }

    moveRack(rackId, nx, ny) {
        const rack = this.getRackById(rackId);
        if (!rack) return false;
        nx = Math.max(0, Math.min(nx, this.width - rack.width));
        ny = Math.max(0, Math.min(ny, this.height - rack.height));
        if (!this.isInBounds(nx, ny) || !this.isInBounds(nx + rack.width - 1, ny + rack.height - 1)) return false;
        if (this._isAreaOccupiedExcluding(nx, ny, rack.width, rack.height, rackId)) return false;
        const dx = nx - rack.x; const dy = ny - rack.y;
        rack.x = nx; rack.y = ny;
        for (const p of rack.products) { p.x += dx; p.y += dy; }
        return true;
    }

    rotateRack(rackId) {
        const rack = this.getRackById(rackId);
        if (!rack) return false;
        const newW = rack.height;
        const newH = rack.width;
        if (Math.min(newW, newH) > 2) return false;
        const nx = Math.max(0, Math.min(rack.x, this.width  - newW));
        const ny = Math.max(0, Math.min(rack.y, this.height - newH));
        if (this._isAreaOccupiedExcluding(nx, ny, newW, newH, rackId)) return false;
        rack.width = newW; rack.height = newH; rack.x = nx; rack.y = ny;
        return true;
    }

    removeRack(id) { const i = this.racks.findIndex(r => r.id === id); if (i === -1) return false; this.racks.splice(i, 1); return true; }
    getRackById(id) { return this.racks.find(r => r.id === id) || null; }
    getRackAt(cx, cy) { return this.racks.find(r => r.containsCell(cx, cy)) || null; }

    // ── Products ─────────────────────────────────────────────────────
    addProduct(rackId, { name, sku, quantity, cantidad, pesoKg = 1.0 } = {}) {
        const rack = this.getRackById(rackId); if (!rack) return null;
        const qty = cantidad != null ? cantidad : (quantity != null ? quantity : 1);
        const pz = rack.products.filter(p => p.x === rack.x && p.y === rack.y).length + 1;
        const product = new Product({ name, sku, rackId, x: rack.x, y: rack.y, z: pz, quantity: qty, pesoKg });
        rack.products.push(product); return product;
    }
    removeProduct(productId) { for (const r of this.racks) { const i = r.products.findIndex(p => p.id === productId); if (i !== -1) { r.products.splice(i, 1); return true; } } return false; }
    getAllProducts() { return this.racks.flatMap(r => r.products); }

    // ── Doors ────────────────────────────────────────────────────────
    addDoor(x, y, tipo = 'AMBOS') {
        if (!(x === 0 || x === this.width - 1 || y === 0 || y === this.height - 1)) return null;
        if (this.doors.find(d => d.x === x && d.y === y)) return null;
        const door = new Door({ x, y, tipo }); this.doors.push(door); return door;
    }
    removeDoor(id) { const i = this.doors.findIndex(d => d.id === id); if (i === -1) return false; this.doors.splice(i, 1); return true; }
    getDoorAt(cx, cy) { return this.doors.find(d => d.x === cx && d.y === cy) || null; }

    // ── DispatchZones ─────────────────────────────────────────────────
    addDispatchZone(x, y, width = 3, height = 2, pesoMaxKg = 500, puertaId = null) {
        const nx = Math.max(0, Math.min(x, this.width - width));
        const ny = Math.max(0, Math.min(y, this.height - height));
        if (!this.isInBounds(nx, ny) || !this.isInBounds(nx + width - 1, ny + height - 1)) return null;
        if (this._isAreaOccupied(nx, ny, width, height)) return null;
        // Requiere que al menos una celda de la zona sea adyacente a una puerta
        if (!this._isAdjacentToDoor(nx, ny, width, height)) return { error: 'no-door' };
        // Auto-asignar puerta si hay exactamente una adyacente
        const adjDoor = this._findAdjacentDoor(nx, ny, width, height);
        if (!puertaId && adjDoor) puertaId = adjDoor.id;
        const zone = new DispatchZone({ x: nx, y: ny, width, height, pesoMaxKg, puertaId });
        this.dispatchZones.push(zone); return zone;
    }
    _isAdjacentToDoor(x, y, w, h) {
        const deltas = [[0,1],[0,-1],[1,0],[-1,0]];
        for (let cx = x; cx < x + w; cx++) {
            for (let cy = y; cy < y + h; cy++) {
                for (const [dx, dy] of deltas) {
                    if (this.getDoorAt(cx + dx, cy + dy)) return true;
                }
            }
        }
        return false;
    }
    _findAdjacentDoor(x, y, w, h) {
        const deltas = [[0,1],[0,-1],[1,0],[-1,0]];
        for (let cx = x; cx < x + w; cx++) {
            for (let cy = y; cy < y + h; cy++) {
                for (const [dx, dy] of deltas) {
                    const d = this.getDoorAt(cx + dx, cy + dy);
                    if (d) return d;
                }
            }
        }
        return null;
    }
    removeDispatchZone(id) { const i = this.dispatchZones.findIndex(z => z.id === id); if (i === -1) return false; this.dispatchZones.splice(i, 1); return true; }
    getDispatchZoneAt(cx, cy) { return this.dispatchZones.find(z => z.containsCell(cx, cy)) || null; }

    // ── Aisles ────────────────────────────────────────────────────────
    addAisle(x, y, width, height, sentido = 'AMBOS') {
        // Prevenir solapamiento con pasillos existentes
        for (let cx = x; cx < x + width; cx++) {
            for (let cy = y; cy < y + height; cy++) {
                if (this.getAisleAt(cx, cy)) return null;
            }
        }
        const aisle = new Aisle({ x, y, width, height, sentido });
        this.aisles.push(aisle); return aisle;
    }
    removeAisle(id) { const i = this.aisles.findIndex(a => a.id === id); if (i === -1) return false; this.aisles.splice(i, 1); return true; }
    getAisleAt(cx, cy) { return this.aisles.find(a => a.containsCell(cx, cy)) || null; }

    // ── Pickers ───────────────────────────────────────────────────────
    addPicker(capacidadKg = 100) {
        const pos = this._findPickerSpawnPosition(); if (!pos) return null;
        const color = PICKER_COLORS[this._nextPickerColorIdx % PICKER_COLORS.length];
        const picker = new Picker({ x: pos.x, y: pos.y, color, name: 'Picker ' + this._nextPickerNum, capacidadKg });
        this._nextPickerColorIdx++; this._nextPickerNum++; this.pickers.push(picker); return picker;
    }

    _findPickerSpawnPosition() {
        const deltas = [[0, 1], [0, -1], [1, 0], [-1, 0]];
        for (const dz of this.dispatchZones) {
            const seen = new Set();
            for (let cx = dz.x; cx < dz.x + dz.width; cx++) {
                for (let cy = dz.y; cy < dz.y + dz.height; cy++) {
                    for (const [dx, dy] of deltas) {
                        const nx = cx + dx; const ny = cy + dy;
                        if (!this.isInBounds(nx, ny)) continue;
                        const key = nx + ',' + ny;
                        if (seen.has(key)) continue; seen.add(key);
                        if (this.dispatchZones.some(z => z.containsCell(nx, ny))) continue;
                        if (this.getRackAt(nx, ny)) continue;
                        if (this.getDoorAt(nx, ny)) continue;
                        if (this.getPickerAt(nx, ny)) continue;
                        return { x: nx, y: ny };
                    }
                }
            }
        }
        return null;
    }

    removePicker(id) {
        const i = this.pickers.findIndex(p => p.id === id); if (i === -1) return false;
        this.pickers.splice(i, 1); this._renumberPickers(); return true;
    }
    _renumberPickers() {
        this.pickers.forEach((pk, i) => { pk.name = 'Picker ' + (i + 1); });
        this._nextPickerNum = this.pickers.length + 1;
    }
    getPickerAt(cx, cy) { return this.pickers.find(p => p.x === cx && p.y === cy) || null; }

    // ── Utils ─────────────────────────────────────────────────────────
    isInBounds(cx, cy) { return cx >= 0 && cx < this.width && cy >= 0 && cy < this.height; }
    _isInDispatchZone(cx, cy) { return this.dispatchZones.some(dz => dz.containsCell(cx, cy)); }
    _isAreaOccupied(x, y, w, h) {
        for (let cy = y; cy < y + h; cy++) for (let cx = x; cx < x + w; cx++) {
            if (this.getRackAt(cx, cy)) return true;
            if (this._isInDispatchZone(cx, cy)) return true;
            if (this.getDoorAt(cx, cy)) return true;
        }
        return false;
    }
    _isAreaOccupiedExcluding(x, y, w, h, excludeRackId) {
        for (let cy = y; cy < y + h; cy++) for (let cx = x; cx < x + w; cx++) {
            const rack = this.getRackAt(cx, cy);
            if (rack && rack.id !== excludeRackId) return true;
            if (this._isInDispatchZone(cx, cy)) return true;
            if (this.getDoorAt(cx, cy)) return true;
        }
        return false;
    }
    stats() { return { racks: this.racks.length, products: this.getAllProducts().length, pickers: this.pickers.length, doors: this.doors.length, dispatchZones: this.dispatchZones.length, size: this.width + ' x ' + this.height }; }
    isValidForSave() { return this.doors.length >= 1 && this.dispatchZones.length >= 1 && this.racks.length >= 1; }

    // ── Serialization ─────────────────────────────────────────────────
    toJSON() {
        const productos = this.racks.flatMap(r => r.products.map(p => p.toJSON()));
        return { warehouse: { dimensiones: { ancho_x: this.width, largo_y: this.height }, puertas: this.doors.map(d => d.toJSON()), zonas_despacho: this.dispatchZones.map(z => z.toJSON()), racks: this.racks.map(r => r.toJSON()), pasillos: this.aisles.map(a => a.toJSON()) }, pickers: this.pickers.map(p => p.toJSON()), productos, pedidos: this.orders.map(o => o.toJSON()), configuracion: { wave_max_pedidos: this.waveMaxPedidos, wave_max_productos: this.waveMaxProductos }, _editor: { id: this.id, name: this.name, _nextPickerColorIdx: this._nextPickerColorIdx, _nextPickerNum: this._nextPickerNum, pickerColors: this.pickers.map(p => ({ id: p.id, color: p.color, name: p.name })) } };
    }

    static fromJSON(data) {
        const wh = data.warehouse || {}; const dim = wh.dimensiones || {}; const config = data.configuracion || {}; const meta = data._editor || {};
        const s = new Scenario({ id: meta.id || null, name: meta.name || 'Escenario cargado', width: dim.ancho_x != null ? dim.ancho_x : (data.width != null ? data.width : 20), height: dim.largo_y != null ? dim.largo_y : (data.height != null ? data.height : 15) });
        s.dispatchZones = [];
        s.doors = (wh.puertas || []).map(d => Door.fromJSON(d));
        s.dispatchZones = (wh.zonas_despacho || []).map(z => DispatchZone.fromJSON(z));
        s.racks = (wh.racks || []).map(r => Rack.fromJSON(r));
        s.aisles = (wh.pasillos || []).map(a => Aisle.fromJSON(a));
        s.pickers = (data.pickers || []).map(p => Picker.fromJSON(p));
        s.orders = (data.pedidos || []).map(o => Order.fromJSON(o));
        s.waveMaxPedidos = config.wave_max_pedidos != null ? config.wave_max_pedidos : 5;
        s.waveMaxProductos = config.wave_max_productos != null ? config.wave_max_productos : 20;
        const pickerColors = meta.pickerColors || [];
        for (const pc of pickerColors) { const pk = s.pickers.find(p => p.id === pc.id); if (pk) { pk.color = pc.color; pk.name = pc.name; } }
        s.pickers.forEach((pk, i) => { if (!pk.color) pk.color = PICKER_COLORS[i % PICKER_COLORS.length]; });
        const rackMap = Object.fromEntries(s.racks.map(r => [r.id, r]));
        for (const pData of (data.productos || [])) { const product = Product.fromJSON(pData); const rack = rackMap[product.rackId]; if (rack) rack.products.push(product); }
        s._nextPickerColorIdx = meta._nextPickerColorIdx != null ? meta._nextPickerColorIdx : s.pickers.length;
        s._nextPickerNum = meta._nextPickerNum != null ? meta._nextPickerNum : s.pickers.length + 1;
        return s;
    }
}
