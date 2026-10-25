/* ================================================================
   WAREHOUSE RENDERER
   Dibuja el scenario en un <canvas> usando Canvas 2D API.
   Es stateless respecto a la interacción: el Editor le setea
   las propiedades de estado (hover, selection, cursorRect…)
   y este módulo solo dibuja.
================================================================ */

const CELL = 36;   // tamaño base de celda en píxeles (world space)

class WarehouseRenderer {

    constructor(canvas) {
        this.canvas  = canvas;
        this.ctx     = canvas.getContext('2d');
        this.scenario = null;

        // Viewport
        this.zoom = 1;
        this.panX = 40;
        this.panY = 40;

        // Estado visual (lo setea WarehouseEditor)
        this.hoverCell       = null;   // { x, y } | null
        this.cursorRect      = null;   // { x, y, w, h } para preview de rack
        this.selectedElement = null;   // { type, element } | null
        this.mode            = 'select';

        // Sprites
        this._spritesReady = false;
        this._loadSprites();

        // Ajustar canvas cuando cambia el tamaño del contenedor
        this._ro = new ResizeObserver(() => this._fitCanvas());
        this._ro.observe(canvas.parentElement);
        this._fitCanvas();

        // Polyfill roundRect para browsers viejos
        if (!CanvasRenderingContext2D.prototype.roundRect) {
            CanvasRenderingContext2D.prototype.roundRect = function(x, y, w, h, r) {
                r = Math.min(r, Math.min(w, h) / 2);
                this.beginPath();
                this.moveTo(x + r, y);
                this.lineTo(x + w - r, y);
                this.arcTo(x + w, y, x + w, y + r, r);
                this.lineTo(x + w, y + h - r);
                this.arcTo(x + w, y + h, x + w - r, y + h, r);
                this.lineTo(x + r, y + h);
                this.arcTo(x, y + h, x, y + h - r, r);
                this.lineTo(x, y + r);
                this.arcTo(x, y, x + r, y, r);
                this.closePath();
            };
        }
    }

    // ── Sprites ──────────────────────────────────────────────────

    // Pixel-art sprite frame constants
    static FRAME_W = 32;   // ancho de cada frame del spritesheet
    static FRAME_H = 24;   // alto de cada frame del spritesheet

    // Directiones → fila del spritesheet
    static DIR_DOWN  = 0;
    static DIR_RIGHT = 1;
    static DIR_LEFT  = 2;
    static DIR_UP    = 3;

    // Variantes de color disponibles en los sprites
    static PICKER_VARIANTS = ['default', 'blue', 'red', 'green', 'yellow'];

    // Mapeo de los colores del PICKER_COLORS a la variante de sprite más adecuada
    static COLOR_TO_VARIANT = {
        '#FF6B6B': 'red',
        '#4ECDC4': 'blue',
        '#FFE66D': 'yellow',
        '#A8E6CF': 'green',
        '#FF8B94': 'red',
        '#7C83FD': 'blue',
        '#96E6A1': 'green',
        '#F7B267': 'yellow',
        '#B388FF': 'blue',
        '#80CBC4': 'green',
    };

    _loadSprites() {
        this._spritesReady = false;
        this._pickerSprites = {};   // { variant: { idle: Image, walk: Image } }
        this.productSprite  = new Image();

        // Cantidad total de imágenes que necesitamos cargar
        const variants = WarehouseRenderer.PICKER_VARIANTS;
        const animTypes = ['idle', 'walk'];
        const totalImages = variants.length * animTypes.length + 1; // +1 por el productSprite
        let loaded = 0;

        const checkReady = () => {
            loaded++;
            if (loaded >= totalImages) this._spritesReady = true;
        };

        // Cargar product sprite (box.png, 18×18 pixel art)
        this.productSprite.onload  = checkReady;
        this.productSprite.onerror = checkReady;
        this.productSprite.src     = '/static/sprites/box.png';

        // Cargar sprites de cada variante de picker
        for (const variant of variants) {
            this._pickerSprites[variant] = {};
            for (const anim of animTypes) {
                const img = new Image();
                img.onload  = checkReady;
                img.onerror = checkReady;
                img.src     = `/static/sprites/picker/${variant}/${anim}.png`;
                this._pickerSprites[variant][anim] = img;
            }
        }
    }

    /**
     * Devuelve la variante de sprite ('default', 'blue', 'red', 'green', 'yellow')
     * que mejor coincide con el color hexadecimal del picker.
     */
    _getPickerVariant(color) {
        const upper = (color || '').toUpperCase();
        return WarehouseRenderer.COLOR_TO_VARIANT[upper] || 'default';
    }

    // ── Canvas resize ─────────────────────────────────────────────

    _fitCanvas() {
        const p = this.canvas.parentElement;
        if (!p) return;
        this.canvas.width  = p.clientWidth;
        this.canvas.height = p.clientHeight;
    }

    // ── Scenario ──────────────────────────────────────────────────

    setScenario(scenario) {
        this.scenario = scenario;
        this._centerView();
    }

    _centerView() {
        if (!this.scenario) return;
        const totalW = this.scenario.width  * CELL * this.zoom;
        const totalH = this.scenario.height * CELL * this.zoom;
        this.panX = Math.max(20, (this.canvas.width  - totalW) / 2);
        this.panY = Math.max(20, (this.canvas.height - totalH) / 2);
    }

    // ── Coordenadas ───────────────────────────────────────────────

    /**
     * Celda lógica → coordenada Y en world-space.
     * El canvas nativo tiene y creciente hacia abajo, pero el sistema de
     * coordenadas del warehouse tiene y=0 en la esquina inferior-izquierda
     * (y crece hacia arriba). Esta función aplica la inversión.
     */
    _wy(cy) {
        if (!this.scenario) return 0;
        return (this.scenario.height - 1 - cy) * CELL;
    }

    /** Celda → píxel pantalla (esquina INFERIOR-izquierda de la celda en lógica, superior en pantalla) */
    cellToScreen(cx, cy) {
        if (!this.scenario) return { x: 0, y: 0 };
        return {
            x: cx               * CELL * this.zoom + this.panX,
            y: this._wy(cy)     * this.zoom        + this.panY,
        };
    }

    /** Píxel pantalla → celda lógica (con y=0 abajo) */
    screenToCell(sx, sy) {
        const h = this.scenario ? this.scenario.height : 1;
        return {
            x: Math.floor((sx - this.panX) / (CELL * this.zoom)),
            y: h - 1 - Math.floor((sy - this.panY) / (CELL * this.zoom)),
        };
    }

    // ── Zoom / Pan ────────────────────────────────────────────────

    zoomBy(factor, cx, cy) {
        const newZoom = Math.max(0.25, Math.min(4, this.zoom * factor));
        const ratio   = newZoom / this.zoom;
        this.panX = cx - ratio * (cx - this.panX);
        this.panY = cy - ratio * (cy - this.panY);
        this.zoom = newZoom;
    }

    zoomReset() {
        this.zoom = 1;
        this._centerView();
    }

    // ── Render principal ──────────────────────────────────────────

    render() {
        const ctx = this.ctx;
        const W   = this.canvas.width;
        const H   = this.canvas.height;

        // Limpiar
        ctx.clearRect(0, 0, W, H);
        this._drawAppBackground(W, H);

        if (!this.scenario) return;

        const z = this.zoom;

        ctx.save();
        ctx.translate(this.panX, this.panY);
        ctx.scale(z, z);

        this._drawFloor();
        this._drawGrid();
        this._drawDispatchZone();
        this._drawAisles();
        this._drawDoors();
        this._drawRacks();
        this._drawHoverCell();   // dibujado DESPUÉS de racks para que las coordenadas sean siempre visibles
        this._drawPickers();
        this._drawCursorPreview();

        ctx.restore();
    }

    // ── Fondo de aplicación ───────────────────────────────────────

    _drawAppBackground(W, H) {
        const ctx = this.ctx;
        const bg  = getComputedStyle(document.documentElement)
                        .getPropertyValue('--color-bg').trim() || '#0f0f0f';
        ctx.fillStyle = bg;
        ctx.fillRect(0, 0, W, H);
    }

    // ── Piso del warehouse ─────────────────────────────────────────

    _drawFloor() {
        const ctx = this.ctx;
        const s   = this.scenario;
        const W   = s.width  * CELL;
        const H   = s.height * CELL;

        // Base
        ctx.fillStyle = '#12141f';
        ctx.fillRect(0, 0, W, H);

        // Textura sutil: líneas diagonales
        ctx.save();
        ctx.strokeStyle = 'rgba(255,255,255,0.018)';
        ctx.lineWidth   = 1;
        for (let i = -H; i < W + H; i += 18) {
            ctx.beginPath();
            ctx.moveTo(i, 0);
            ctx.lineTo(i + H, H);
            ctx.stroke();
        }
        ctx.restore();

        // Borde exterior
        ctx.strokeStyle = 'rgba(79, 156, 249, 0.35)';
        ctx.lineWidth   = 2;
        ctx.strokeRect(0, 0, W, H);

        // Sombra interna (vignette)
        const grad = ctx.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, Math.max(W, H) * 0.7);
        grad.addColorStop(0,   'rgba(0,0,0,0)');
        grad.addColorStop(1,   'rgba(0,0,0,0.3)');
        ctx.fillStyle = grad;
        ctx.fillRect(0, 0, W, H);
    }

    // ── Grid ──────────────────────────────────────────────────────

    _drawGrid() {
        const ctx = this.ctx;
        const s   = this.scenario;

        ctx.strokeStyle = 'rgba(255,255,255,0.045)';
        ctx.lineWidth   = 1;

        for (let x = 0; x <= s.width; x++) {
            ctx.beginPath();
            ctx.moveTo(x * CELL, 0);
            ctx.lineTo(x * CELL, s.height * CELL);
            ctx.stroke();
        }
        for (let y = 0; y <= s.height; y++) {
            ctx.beginPath();
            ctx.moveTo(0, y * CELL);
            ctx.lineTo(s.width * CELL, y * CELL);
            ctx.stroke();
        }

        // ── El hover de celda se dibuja por separado en _drawHoverCell() ──────────────
    }

    // ── Hover de celda (sobre todos los elementos, incluso racks) ─────

    _drawHoverCell() {
        const ctx = this.ctx;
        const s   = this.scenario;
        if (!this.hoverCell || !s.isInBounds(this.hoverCell.x, this.hoverCell.y)) return;

        const hx = this.hoverCell.x * CELL;
        const hy = this._wy(this.hoverCell.y);

        const onRack = !!s.getRackAt(this.hoverCell.x, this.hoverCell.y);

        // Fondo con mayor contraste si está sobre un rack
        ctx.fillStyle = onRack ? 'rgba(79, 156, 249, 0.25)' : 'rgba(79, 156, 249, 0.12)';
        ctx.fillRect(hx + 1, hy + 1, CELL - 2, CELL - 2);

        // Coordenadas — fondo oscuro para garantizar legibilidad sobre el color del rack
        const label = `${this.hoverCell.x},${this.hoverCell.y}`;
        ctx.font         = `7px "JetBrains Mono", monospace`;
        ctx.textAlign    = 'left';
        ctx.textBaseline = 'top';
        const tw = ctx.measureText(label).width;
        ctx.fillStyle = 'rgba(0,0,0,0.55)';
        ctx.fillRect(hx + 2, hy + 2, tw + 4, 10);
        ctx.fillStyle = onRack ? '#93c5fd' : 'rgba(79, 156, 249, 0.9)';
        ctx.fillText(label, hx + 4, hy + 3);
    }

    // ── Zonas de despacho (múltiples) ────────────────────────────

    _drawDispatchZone() {
        for (const dz of this.scenario.dispatchZones) {
            this._drawOneDispatchZone(dz);
        }
    }

    _drawOneDispatchZone(dz) {
        const ctx = this.ctx;
        const s   = this.scenario;
        const x   = dz.x * CELL;
        const y   = (s.height - dz.y - dz.height) * CELL;
        const w   = dz.width  * CELL;
        const h   = dz.height * CELL;
        const isSel = this.selectedElement?.type === 'dispatch' && this.selectedElement.element.id === dz.id;

        ctx.fillStyle = isSel ? 'rgba(79,201,127,0.22)' : 'rgba(79,201,127,0.12)';
        ctx.fillRect(x, y, w, h);

        ctx.strokeStyle = isSel ? 'rgba(79,201,127,1.0)' : 'rgba(79,201,127,0.75)';
        ctx.lineWidth   = isSel ? 2 : 1.5;
        ctx.setLineDash([5, 4]);
        ctx.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1);
        ctx.setLineDash([]);

        // Etiquetas — clipeadas al área de la zona
        ctx.save();
        ctx.beginPath();
        ctx.rect(x + 2, y + 2, w - 4, h - 4);
        ctx.clip();

        ctx.fillStyle    = 'rgba(79,201,127,0.9)';
        ctx.font         = `bold 9px "JetBrains Mono", monospace`;
        ctx.textAlign    = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('DESPACHO', x + w / 2, y + h / 2);

        if (dz.puertaId) {
            ctx.font      = `7px "JetBrains Mono", monospace`;
            ctx.fillStyle = 'rgba(79,201,127,0.7)';
            ctx.fillText(dz.puertaId, x + w / 2, y + h / 2 + 12);
        }
        ctx.restore();

        // El rect del clip queda en el path actual (save/restore no lo limpia).
        // Lo reiniciamos para que ningún fill/stroke posterior lo repinte.
        ctx.beginPath();
    }

    // ── Pasillos (flechas de dirección) ──────────────────────────

    _drawAisles() {
        for (const aisle of this.scenario.aisles) {
            for (let cx = aisle.x; cx < aisle.x + aisle.width; cx++) {
                for (let cy = aisle.y; cy < aisle.y + aisle.height; cy++) {
                    this._drawAisleCell(cx, cy, aisle.sentido);
                }
            }
        }
    }

    _drawAisleCell(cx, cy, sentido) {
        const ctx = this.ctx;
        const s   = this.scenario;
        const px  = cx * CELL;
        const py  = (s.height - 1 - cy) * CELL;
        const mid = CELL / 2;
        const ar  = CELL * 0.22;

        ctx.save();
        ctx.translate(px + mid, py + mid);

        ctx.fillStyle = 'rgba(251,191,36,0.07)';
        ctx.fillRect(-mid, -mid, CELL, CELL);

        ctx.strokeStyle = 'rgba(251,191,36,0.55)';
        ctx.fillStyle   = 'rgba(251,191,36,0.55)';
        ctx.lineWidth   = 1.2;

        const drawArrow = (dx, dy) => {
            const len = ar;
            ctx.beginPath();
            ctx.moveTo(-dx * len * 0.6, -dy * len * 0.6);
            ctx.lineTo( dx * len,        dy * len);
            ctx.stroke();
            const hw = 3, hh = 4;
            ctx.beginPath();
            if (dy === 0) {
                const sx = dx > 0 ? 1 : -1;
                ctx.moveTo(sx * len, 0);
                ctx.lineTo(sx * (len - hh), -hw);
                ctx.lineTo(sx * (len - hh),  hw);
            } else {
                // Norte lógico (+y) = arriba en canvas (-py), Sur lógico (-y) = abajo en canvas (+py)
                const sy = dy > 0 ? -1 : 1;
                ctx.moveTo(0, sy * len);
                ctx.lineTo(-hw, sy * (len - hh));
                ctx.lineTo( hw, sy * (len - hh));
            }
            ctx.closePath();
            ctx.fill();
        };

        if      (sentido === 'N') { drawArrow(0,  1); }
        else if (sentido === 'S') { drawArrow(0, -1); }
        else if (sentido === 'E') { drawArrow(1,  0); }
        else if (sentido === 'O') { drawArrow(-1, 0); }
        else {
            ctx.strokeStyle = 'rgba(251,191,36,0.25)';
            ctx.fillStyle   = 'rgba(251,191,36,0.25)';
            drawArrow(0, 1); drawArrow(0, -1);
            drawArrow(1, 0); drawArrow(-1, 0);
        }
        ctx.restore();
    }

    // ── Puertas (muelles) ─────────────────────────────────────────

    _drawDoors() {
        for (const door of this.scenario.doors) {
            this._drawDoor(door);
        }
    }

    _drawDoor(door) {
        const ctx = this.ctx;
        const s   = this.scenario;
        const px  = door.x * CELL;
        const py  = (s.height - 1 - door.y) * CELL;
        const isSel = this.selectedElement?.type === 'door' && this.selectedElement.element.id === door.id;

        const colors = { INBOUND: '#22c55e', OUTBOUND: '#f97316', AMBOS: '#a78bfa' };
        const base = colors[door.tipo] || '#a78bfa';

        ctx.fillStyle = isSel ? base + '44' : base + '1a';
        ctx.fillRect(px, py, CELL, CELL);

        ctx.strokeStyle = base;
        ctx.lineWidth   = isSel ? 2.5 : 1.5;
        ctx.strokeRect(px + 1, py + 1, CELL - 2, CELL - 2);

        // Arco simbólico de puerta
        ctx.strokeStyle = base;
        ctx.lineWidth   = 1.5;
        ctx.beginPath();
        ctx.moveTo(px + 7, py + CELL - 5);
        ctx.lineTo(px + 7, py + 7);
        ctx.quadraticCurveTo(px + CELL / 2, py + 3, px + CELL - 7, py + 7);
        ctx.lineTo(px + CELL - 7, py + CELL - 5);
        ctx.stroke();

        const labelMap = { INBOUND: 'IN', OUTBOUND: 'OUT', AMBOS: 'IO' };
        ctx.save();
        // Clip al área de la celda de la puerta (solo para el tag IN/OUT)
        ctx.beginPath(); ctx.rect(px, py, CELL, CELL); ctx.clip();
        // Etiqueta de tipo — siempre visible
        ctx.fillStyle    = base;
        ctx.font         = `bold 8px "JetBrains Mono", monospace`;
        ctx.textAlign    = 'center';
        ctx.textBaseline = 'bottom';
        ctx.fillText(labelMap[door.tipo] || 'IO', px + CELL / 2, py + CELL - 2);
        ctx.restore();

        // ID de la puerta — se dibuja SIN clip: los IDs generados son más anchos
        // que la celda y antes quedaban cortados por ambos lados.
        ctx.save();
        ctx.font         = `bold 8px "JetBrains Mono", monospace`;
        ctx.textAlign    = 'center';
        ctx.textBaseline = 'top';
        const idW = Math.ceil(ctx.measureText(door.id).width) + 4;
        ctx.fillStyle    = 'rgba(0,0,0,0.55)';
        ctx.fillRect(px + CELL / 2 - idW / 2, py + 2, idW, 11);
        ctx.fillStyle    = base;
        ctx.fillText(door.id, px + CELL / 2, py + 3);
        ctx.restore();

        // Evitar que el rect del clip quede en el path para el resto del frame
        ctx.beginPath();
    }

    // ── Racks ─────────────────────────────────────────────────────

    _drawRacks() {
        for (const rack of this.scenario.racks) {
            this._drawRack(rack);
        }
    }

    _drawRack(rack) {
        const ctx = this.ctx;
        const s   = this.scenario;
        const rx  = rack.x * CELL + 2;
        // El borde superior en pantalla = celda lógica superior del rack (rack.y + rack.height - 1)
        const ry  = (s.height - rack.y - rack.height) * CELL + 2;
        const rw  = rack.width  * CELL - 4;
        const rh  = rack.height * CELL - 4;
        const r   = 4;

        const isSelected = this.selectedElement?.type === 'rack' &&
                           this.selectedElement.element.id === rack.id;

        // Sombra
        ctx.save();
        ctx.shadowColor   = 'rgba(0,0,0,0.5)';
        ctx.shadowBlur    = 10;
        ctx.shadowOffsetX = 2;
        ctx.shadowOffsetY = 2;

        // Cuerpo (gradiente vertical)
        const grad = ctx.createLinearGradient(rx, ry, rx, ry + rh);
        grad.addColorStop(0, isSelected ? '#3d4470' : '#2e3150');
        grad.addColorStop(1, isSelected ? '#272b52' : '#1c1f38');
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.roundRect(rx, ry, rw, rh, r);
        ctx.fill();

        ctx.shadowColor = 'transparent';
        ctx.shadowBlur  = 0;
        ctx.restore();

        // Líneas de estante (horizontales cada media celda)
        const shelfH = CELL * 0.5;
        ctx.strokeStyle = 'rgba(255,255,255,0.07)';
        ctx.lineWidth   = 1;
        for (let sy = ry + shelfH; sy < ry + rh - 2; sy += shelfH) {
            ctx.beginPath();
            ctx.moveTo(rx + 5, sy);
            ctx.lineTo(rx + rw - 5, sy);
            ctx.stroke();
        }

        // Borde
        ctx.strokeStyle = isSelected ? '#818cf8' : 'rgba(79, 156, 249, 0.45)';
        ctx.lineWidth   = isSelected ? 2 : 1;
        ctx.beginPath();
        ctx.roundRect(rx, ry, rw, rh, r);
        ctx.stroke();

        // ID del rack — siempre visible, clipeado al rack
        ctx.save();
        ctx.beginPath(); ctx.roundRect(rx, ry, rw, rh, r); ctx.clip();
        ctx.fillStyle    = isSelected ? 'rgba(220, 225, 255, 0.98)' : 'rgba(180, 200, 245, 0.92)';
        ctx.font         = `bold ${Math.max(7, Math.min(9, rw / 4 | 0))}px "JetBrains Mono", monospace`;
        ctx.textAlign    = 'center';
        ctx.textBaseline = 'top';
        // Fondo semi-opaco para garantizar legibilidad sobre el gradiente
        const idMetrics = ctx.measureText(rack.id);
        const idW = idMetrics.width + 6;
        ctx.fillStyle = 'rgba(0,0,0,0.3)';
        ctx.fillRect(rx + rw / 2 - idW / 2, ry + 2, idW, 12);
        ctx.fillStyle = isSelected ? 'rgba(220, 225, 255, 0.98)' : 'rgba(180, 200, 245, 0.92)';
        ctx.fillText(rack.id, rx + rw / 2, ry + 4);
        ctx.restore();

        // Productos
        if (rack.products.length > 0) {
            this._drawProductsOnRack(rack);
        }
    }

    _drawProductsOnRack(rack) {
        const ctx = this.ctx;

        // Agrupar productos por celda única (cx, cy)
        const cellMap = new Map();
        for (const p of rack.products) {
            const key = `${p.x},${p.y}`;
            if (!cellMap.has(key)) cellMap.set(key, []);
            cellMap.get(key).push(p);
        }

        const boxSize = Math.round(CELL * 0.58);   // ~21px para CELL=36

        for (const [, cellProds] of cellMap) {
            const cx  = cellProds[0].x;
            const cy  = cellProds[0].y;
            const px  = cx * CELL;
            const py  = this._wy(cy);
            const sx  = px + (CELL - boxSize) / 2;
            const sy  = py + (CELL - boxSize) / 2;

            if (this.productSprite.complete && this.productSprite.naturalWidth > 0) {
                ctx.save();
                ctx.imageSmoothingEnabled = false;
                ctx.drawImage(this.productSprite, sx, sy, boxSize, boxSize);
                ctx.restore();
            } else {
                // Fallback: caja dibujada
                ctx.fillStyle   = '#78350f';
                ctx.strokeStyle = '#451a03';
                ctx.lineWidth   = 1.5;
                ctx.beginPath();
                ctx.roundRect(sx, sy, boxSize, boxSize, 2);
                ctx.fill();
                ctx.stroke();
                ctx.strokeStyle = 'rgba(0,0,0,0.3)';
                ctx.lineWidth   = 1;
                ctx.beginPath();
                ctx.moveTo(sx, sy); ctx.lineTo(sx + boxSize, sy + boxSize);
                ctx.moveTo(sx + boxSize, sy); ctx.lineTo(sx, sy + boxSize);
                ctx.stroke();
            }

            // Badge de cantidad si hay más de 1 producto en la celda
            if (cellProds.length > 1) {
                const badgeR = 6;
                const bx     = px + CELL - badgeR - 1;
                const by     = py + badgeR + 1;
                ctx.fillStyle = '#4f9cf9';
                ctx.beginPath();
                ctx.arc(bx, by, badgeR, 0, Math.PI * 2);
                ctx.fill();
                ctx.fillStyle    = '#fff';
                ctx.font         = `bold 7px "JetBrains Mono", monospace`;
                ctx.textAlign    = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillText(cellProds.length, bx, by);
            }
        }
    }

    // ── Pickers ───────────────────────────────────────────────────

    _drawPickers() {
        for (const picker of this.scenario.pickers) {
            this._drawPicker(picker);
        }
    }

    _drawPicker(picker) {
        const ctx = this.ctx;
        const s   = this.scenario;
        // Posición de la celda en world-space (con y=0 abajo)
        const worldY = this._wy(picker.y);
        const cx     = picker.x * CELL + CELL / 2;
        const cy     = worldY + CELL / 2;

        const isSelected = this.selectedElement?.type === 'picker' &&
                           this.selectedElement.element.id === picker.id;

        const FW = WarehouseRenderer.FRAME_W;  // 32
        const FH = WarehouseRenderer.FRAME_H;  // 24

        const scale   = CELL / FH;
        const spriteW = FW * scale;
        const spriteH = FH * scale;

        const drawX = cx - spriteW / 2;
        const drawY = worldY;

        const variant = this._getPickerVariant(picker.color);
        const sprites = this._pickerSprites[variant];
        const idleImg = sprites?.idle;

        if (idleImg && idleImg.complete && idleImg.naturalWidth > 0) {
            ctx.save();
            ctx.imageSmoothingEnabled = false;
            if (isSelected) {
                ctx.shadowColor = picker.color;
                ctx.shadowBlur  = 14;
            }
            ctx.drawImage(idleImg, 0, 0, FW, FH, drawX, drawY, spriteW, spriteH);
            ctx.restore();
        } else {
            // Fallback geométrico
            ctx.save();
            if (isSelected) {
                ctx.shadowColor = picker.color;
                ctx.shadowBlur  = 14;
            }
            ctx.fillStyle = picker.color;
            ctx.beginPath();
            ctx.ellipse(cx, cy + CELL * 0.1, CELL * 0.18, CELL * 0.22, 0, 0, Math.PI * 2);
            ctx.fill();
            ctx.fillStyle = '#fcd34d';
            ctx.beginPath();
            ctx.arc(cx, cy - CELL * 0.18, CELL * 0.14, 0, Math.PI * 2);
            ctx.fill();
            ctx.fillStyle = picker.color;
            ctx.beginPath();
            ctx.arc(cx, cy - CELL * 0.22, CELL * 0.13, Math.PI, 0, false);
            ctx.fill();
            ctx.restore();
        }

        // Anillo de selección
        if (isSelected) {
            ctx.strokeStyle = picker.color;
            ctx.lineWidth   = 1.5;
            ctx.setLineDash([4, 3]);
            ctx.strokeRect(picker.x * CELL + 2, worldY + 2, CELL - 4, CELL - 4);
            ctx.setLineDash([]);
        }

        // Nombre al pie de la celda
        ctx.fillStyle    = picker.color;
        ctx.font         = `bold 7px "JetBrains Mono", monospace`;
        ctx.textAlign    = 'center';
        ctx.textBaseline = 'bottom';
        ctx.fillText(picker.name, cx, worldY + CELL - 2);
    }

    // ── Cursor preview (todos los modos) ──────────────────────────

    _drawCursorPreview() {
        if (!this.cursorRect) return;
        const ctx = this.ctx;
        const s   = this.scenario;
        const { x, y, w, h } = this.cursorRect;

        if (this.mode === 'rack' || this.mode === 'dispatch' || this.mode === 'aisle' || this.mode === 'move-rack') {
            const px = x * CELL;
            const py = (s.height - y - h) * CELL;
            const pw = w * CELL;
            const ph = h * CELL;

            let color;
            if      (this.mode === 'dispatch')   color = '79,201,127';
            else if (this.mode === 'aisle')       color = '251,191,36';
            else if (this.mode === 'move-rack')   color = '168,85,247';
            else                                  color = '79,156,249';

            ctx.fillStyle   = `rgba(${color},0.2)`;
            ctx.fillRect(px, py, pw, ph);
            ctx.strokeStyle = `rgb(${color})`;
            ctx.lineWidth   = 1.5;
            ctx.setLineDash([4, 3]);
            ctx.strokeRect(px + 0.5, py + 0.5, pw - 1, ph - 1);
            ctx.setLineDash([]);
            ctx.fillStyle    = `rgb(${color})`;
            ctx.font         = `bold 9px "JetBrains Mono", monospace`;
            ctx.textAlign    = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(`${w}x${h}`, px + pw / 2, py + ph / 2);

        } else if (this.mode === 'door') {
            const px = x * CELL;
            const py = (s.height - 1 - y) * CELL;
            ctx.fillStyle   = 'rgba(251,146,60,0.35)';
            ctx.fillRect(px, py, CELL, CELL);
            ctx.strokeStyle = '#fb923c';
            ctx.lineWidth   = 2;
            ctx.strokeRect(px + 1, py + 1, CELL - 2, CELL - 2);

        } else if (this.mode === 'product') {
            // Resaltar la celda del rack donde se colocará el producto
            const px = x * CELL;
            const py = this._wy(y);
            ctx.fillStyle   = 'rgba(251, 191, 36, 0.18)';
            ctx.fillRect(px + 1, py + 1, CELL - 2, CELL - 2);
            ctx.strokeStyle = '#fbbf24';
            ctx.lineWidth   = 1.5;
            ctx.setLineDash([4, 3]);
            ctx.strokeRect(px + 1.5, py + 1.5, CELL - 3, CELL - 3);
            ctx.setLineDash([]);
        }
    }

    // ── Cleanup ───────────────────────────────────────────────────

    destroy() {
        this._ro.disconnect();
    }
}

