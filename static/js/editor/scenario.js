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
        // Restriccion: exactamente uno de los lados debe ser igual a 2
        if (width !== 2 && height !== 2) {
            if (width <= height) width = 2; else height = 2;
        }
        const nx = Math.max(0, Math.min(x, this.width - width));
        const ny = Math.max(0, Math.min(y, this.height - height));
        if (!this.isInBounds(nx, ny) || !this.isInBounds(nx + width - 1, ny + height - 1)) return null;
        if (this._isAreaOccupied(nx, ny, width, height)) return null;
        if (this._isRackAdjacentToOtherRack(nx, ny, width, height, null)) return null;
        // Verificar accesibilidad: ninguna cara del rack puede quedar contra la pared
        const tempRack = { x: nx, y: ny, width, height };
        if (!this.isRackFullyAccessible(tempRack)) return null;
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
        if (this._isRackAdjacentToOtherRack(nx, ny, rack.width, rack.height, rackId)) return false;
        // Verificar accesibilidad en la nueva posición
        if (!this.isRackFullyAccessible({ x: nx, y: ny, width: rack.width, height: rack.height })) return false;
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
        if (newW !== 2 && newH !== 2) return false;
        const nx = Math.max(0, Math.min(rack.x, this.width  - newW));
        const ny = Math.max(0, Math.min(rack.y, this.height - newH));
        if (!this.isInBounds(nx, ny) || !this.isInBounds(nx + newW - 1, ny + newH - 1)) return false;
        if (this._isAreaOccupiedExcluding(nx, ny, newW, newH, rackId)) return false;
        if (this._isRackAdjacentToOtherRack(nx, ny, newW, newH, rackId)) return false;
        // Verificar accesibilidad tras la rotación
        if (!this.isRackFullyAccessible({ x: nx, y: ny, width: newW, height: newH })) return false;
        rack.width = newW; rack.height = newH; rack.x = nx; rack.y = ny;
        return true;
    }

    removeRack(id) { const i = this.racks.findIndex(r => r.id === id); if (i === -1) return false; this.racks.splice(i, 1); return true; }
    getRackById(id) { return this.racks.find(r => r.id === id) || null; }
    getRackAt(cx, cy) { return this.racks.find(r => r.containsCell(cx, cy)) || null; }
    /**
     * Verifica que cada celda del rack tenga al menos un vecino que esté
     * dentro del warehouse Y fuera del rack.
     * Detecta celdas "encerradas" sin rechazar casos válidos como un rack 2×1
     * en una esquina (accesible desde arriba/abajo).
     * No verifica otros racks porque ya se garantiza distancia ≥ 1 entre racks.
     */
    isRackFullyAccessible(rack) {
        const deltas = [[1,0],[-1,0],[0,1],[0,-1]];
        for (let cy = rack.y; cy < rack.y + rack.height; cy++) {
            for (let cx = rack.x; cx < rack.x + rack.width; cx++) {
                let hasAccess = false;
                for (const [dx, dy] of deltas) {
                    const nx = cx + dx, ny = cy + dy;
                    if (nx < 0 || nx >= this.width || ny < 0 || ny >= this.height) continue;
                    if (nx >= rack.x && nx < rack.x + rack.width &&
                        ny >= rack.y && ny < rack.y + rack.height) continue;
                    hasAccess = true;
                    break;
                }
                if (!hasAccess) return false;
            }
        }
        return true;
    }


    // ── Products ─────────────────────────────────────────────────────
    addProduct(rackId, { name, sku, quantity, cantidad, pesoKg, x, y, z } = {}) {
        const rack = this.getRackById(rackId); if (!rack) return null;
        const qty = cantidad != null ? cantidad : (quantity != null ? quantity : 1);
        const weight = (pesoKg != null && !isNaN(parseFloat(pesoKg))) ? parseFloat(pesoKg) : 1.0;

        // Determinar celda destino: usar (x, y) si pertenece al rack, sino esquina inferior-izquierda
        let targetX = rack.x;
        let targetY = rack.y;
        if (x != null && y != null && rack.containsCell(x, y)) {
            targetX = x;
            targetY = y;
        }

        // Nivel Z: usar el provisto (si válido) o calcular el siguiente libre en la celda
        const cellProducts = rack.products.filter(p => p.x === targetX && p.y === targetY);
        const targetZ = (z != null && Number.isInteger(+z) && +z >= 1) ? +z : cellProducts.length + 1;

        // Validar que el slot (x, y, z) no esté ya ocupado
        const slotOccupied = rack.products.some(p => p.x === targetX && p.y === targetY && p.z === targetZ);
        if (slotOccupied) {
            return { error: `La posición (${targetX}, ${targetY}) Z:${targetZ} ya está ocupada. Elegí un nivel Z diferente.` };
        }

        const product = new Product({ name, sku, rackId, x: targetX, y: targetY, z: targetZ, quantity: qty, pesoKg: weight });
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
    removeDoor(id) {
        const i = this.doors.findIndex(d => d.id === id);
        if (i === -1) return false;
        this.doors.splice(i, 1);
        for (const dz of this.dispatchZones) { if (dz.puertaId === id) dz.puertaId = null; }
        return true;
    }
    moveDoor(id, nx, ny) {
        const door = this.doors.find(d => d.id === id);
        if (!door) return false;
        // Debe permanecer en el borde
        if (!(nx === 0 || nx === this.width - 1 || ny === 0 || ny === this.height - 1)) return false;
        // No puede estar donde ya hay otra puerta
        if (this.doors.some(d => d.id !== id && d.x === nx && d.y === ny)) return false;
        door.x = nx; door.y = ny;
        // Detectar zonas que quedan despegadas de la puerta
        const orphanedZones = [];
        for (const dz of this.dispatchZones) {
            if (dz.puertaId !== id) continue;
            if (!this._isAdjacentToSpecificDoor(dz.x, dz.y, dz.width, dz.height, id)) {
                dz.puertaId = null;
                orphanedZones.push(dz);
            }
        }
        return { moved: true, orphanedZones };
    }
    getDoorAt(cx, cy) { return this.doors.find(d => d.x === cx && d.y === cy) || null; }

    // ── DispatchZones ─────────────────────────────────────────────────
    addDispatchZone(x, y, width = 3, height = 2, pesoMaxKg = 500, puertaId = null) {
        const nx = Math.max(0, Math.min(x, this.width - width));
        const ny = Math.max(0, Math.min(y, this.height - height));
        if (!this.isInBounds(nx, ny) || !this.isInBounds(nx + width - 1, ny + height - 1)) return null;
        if (this._isAreaOccupied(nx, ny, width, height)) return null;
        // Verificar que la zona sea adyacente a exactamente UNA puerta
        const adjCount = this._countAdjacentDoors(nx, ny, width, height);
        if (adjCount === 0) return { error: 'no-door' };
        if (adjCount > 1)   return { error: 'multiple-doors' };
        // Auto-asignar puerta
        const adjDoor = this._findAdjacentDoor(nx, ny, width, height);
        if (!puertaId && adjDoor) puertaId = adjDoor.id;
        // Verificar unicidad de puerta: una puerta no puede tener más de una zona
        if (puertaId && this.dispatchZones.some(z => z.puertaId === puertaId)) {
            return { error: 'door-taken' };
        }
        const zone = new DispatchZone({ x: nx, y: ny, width, height, pesoMaxKg, puertaId });
        this.dispatchZones.push(zone); return zone;
    }
    /** Cuenta cuántas puertas distintas son adyacentes al área (x,y,w,h). */
    _countAdjacentDoors(x, y, w, h) {
        const doorIds = new Set();
        const deltas = [[0,1],[0,-1],[1,0],[-1,0]];
        for (let cx = x; cx < x + w; cx++) {
            for (let cy = y; cy < y + h; cy++) {
                for (const [dx, dy] of deltas) {
                    const d = this.getDoorAt(cx + dx, cy + dy);
                    if (d) doorIds.add(d.id);
                }
            }
        }
        return doorIds.size;
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
    moveDispatchZone(id, nx, ny) {
        const dz = this.dispatchZones.find(z => z.id === id);
        if (!dz) return false;
        nx = Math.max(0, Math.min(nx, this.width  - dz.width));
        ny = Math.max(0, Math.min(ny, this.height - dz.height));
        if (!this.isInBounds(nx, ny) || !this.isInBounds(nx + dz.width - 1, ny + dz.height - 1)) return false;
        // El área destino no debe estar ocupada (excluyendo la zona misma)
        for (let cy = ny; cy < ny + dz.height; cy++) {
            for (let cx = nx; cx < nx + dz.width; cx++) {
                if (this.getRackAt(cx, cy)) return false;
                const existingDz = this.getDispatchZoneAt(cx, cy);
                if (existingDz && existingDz.id !== id) return false;
                if (this.getDoorAt(cx, cy)) return false;
                if (this.getAisleAt(cx, cy)) return false;
            }
        }
        // Debe quedar adyacente a exactamente la puerta asignada (si tiene)
        if (dz.puertaId) {
            const adjCount = this._countAdjacentDoorsExcept(nx, ny, dz.width, dz.height, dz.puertaId);
            const stillAdjToOwn = this._isAdjacentToSpecificDoor(nx, ny, dz.width, dz.height, dz.puertaId);
            if (!stillAdjToOwn) return false; // se alejó de su puerta
            if (adjCount > 0) return false;   // ahora también toca otra puerta
        }
        dz.x = nx; dz.y = ny;
        return true;
    }
    _isAdjacentToSpecificDoor(x, y, w, h, doorId) {
        const deltas = [[0,1],[0,-1],[1,0],[-1,0]];
        for (let cx = x; cx < x + w; cx++)
            for (let cy = y; cy < y + h; cy++)
                for (const [dx, dy] of deltas) {
                    const d = this.getDoorAt(cx + dx, cy + dy);
                    if (d && d.id === doorId) return true;
                }
        return false;
    }
    _countAdjacentDoorsExcept(x, y, w, h, exceptId) {
        const ids = new Set();
        const deltas = [[0,1],[0,-1],[1,0],[-1,0]];
        for (let cx = x; cx < x + w; cx++)
            for (let cy = y; cy < y + h; cy++)
                for (const [dx, dy] of deltas) {
                    const d = this.getDoorAt(cx + dx, cy + dy);
                    if (d && d.id !== exceptId) ids.add(d.id);
                }
        return ids.size;
    }
    removeDispatchZone(id) { const i = this.dispatchZones.findIndex(z => z.id === id); if (i === -1) return false; this.dispatchZones.splice(i, 1); return true; }
    getDispatchZoneAt(cx, cy) { return this.dispatchZones.find(z => z.containsCell(cx, cy)) || null; }

    // ── Aisles ────────────────────────────────────────────────────────
    addAisle(x, y, width, height, sentido = 'AMBOS') {
        // Clamp a los límites del warehouse
        const nx = Math.max(0, Math.min(x, this.width - width));
        const ny = Math.max(0, Math.min(y, this.height - height));
        if (!this.isInBounds(nx, ny) || !this.isInBounds(nx + width - 1, ny + height - 1)) return null;
        // Prevenir solapamiento con pasillos, racks, zonas de despacho y puertas
        for (let cx = nx; cx < nx + width; cx++) {
            for (let cy = ny; cy < ny + height; cy++) {
                if (this.getAisleAt(cx, cy)) return null;
                if (this.getRackAt(cx, cy)) return null;
                if (this._isInDispatchZone(cx, cy)) return null;
                if (this.getDoorAt(cx, cy)) return null;
            }
        }
        const aisle = new Aisle({ x: nx, y: ny, width, height, sentido });
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
        // Buscar cualquier celda libre: no rack, no zona de despacho, no puerta, no picker
        for (let y = 0; y < this.height; y++) {
            for (let x = 0; x < this.width; x++) {
                if (this.getRackAt(x, y)) continue;
                if (this._isInDispatchZone(x, y)) continue;
                if (this.getDoorAt(x, y)) continue;
                if (this.getPickerAt(x, y)) continue;
                return { x, y };
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
    movePicker(id, nx, ny) {
        const picker = this.pickers.find(p => p.id === id);
        if (!picker) return false;
        if (!this.isInBounds(nx, ny)) return false;
        if (this.getRackAt(nx, ny)) return false;
        if (this._isInDispatchZone(nx, ny)) return false;
        if (this.getDoorAt(nx, ny)) return false;
        if (this.pickers.some(p => p.id !== id && p.x === nx && p.y === ny)) return false;
        picker.x = nx; picker.y = ny;
        return true;
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
            if (this.getAisleAt(cx, cy)) return true;
            if (this.getPickerAt(cx, cy)) return true;
        }
        return false;
    }
    _isAreaOccupiedExcluding(x, y, w, h, excludeRackId) {
        for (let cy = y; cy < y + h; cy++) for (let cx = x; cx < x + w; cx++) {
            const rack = this.getRackAt(cx, cy);
            if (rack && rack.id !== excludeRackId) return true;
            if (this._isInDispatchZone(cx, cy)) return true;
            if (this.getDoorAt(cx, cy)) return true;
            if (this.getAisleAt(cx, cy)) return true;
            if (this.getPickerAt(cx, cy)) return true;
        }
        return false;
    }
    _isRackAdjacentToOtherRack(x, y, w, h, excludeId) {
        // Devuelve true si alguna celda inmediatamente adyacente al rectángulo (x,y,w,h)
        // pertenece a otro rack (distancia mínima = 1 entre racks).
        for (let cy = y - 1; cy <= y + h; cy++) {
            for (let cx = x - 1; cx <= x + w; cx++) {
                // Saltar las celdas propias del rectángulo
                if (cx >= x && cx < x + w && cy >= y && cy < y + h) continue;
                if (!this.isInBounds(cx, cy)) continue;
                const r = this.getRackAt(cx, cy);
                if (r && r.id !== excludeId) return true;
            }
        }
        return false;
    }
    stats() { return { racks: this.racks.length, products: this.getAllProducts().length, pickers: this.pickers.length, doors: this.doors.length, dispatchZones: this.dispatchZones.length, size: this.width + ' x ' + this.height }; }
    /** Devuelve un array de strings describiendo qué requisitos faltan.
     *  Si includePickers=false omite la verificación de pickers (útil durante el wizard
     *  antes de agregar el picker automático). */
    getMissingRequirements(includePickers = true) {
        const missing = [];
        if (this.doors.length === 0)         missing.push('al menos 1 puerta');
        if (this.dispatchZones.length === 0) missing.push('al menos 1 zona de despacho');
        if (this.racks.length === 0)         missing.push('al menos 1 rack');
        if (includePickers && this.pickers.length === 0) missing.push('al menos 1 picker');
        // Cada puerta debe tener exactamente una zona de despacho
        for (const door of this.doors) {
            if (!this.dispatchZones.some(z => z.puertaId === door.id))
                missing.push(`zona de despacho frente a puerta "${door.id}"`);
        }
        // Cada zona debe tener una puerta válida asignada
        for (const zone of this.dispatchZones) {
            if (!zone.puertaId || !this.doors.some(d => d.id === zone.puertaId))
                missing.push(`puerta asignada a zona "${zone.id}"`);
        }
        return missing;
    }
    isValidForSave() { return this.getMissingRequirements(true).length === 0; }

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
