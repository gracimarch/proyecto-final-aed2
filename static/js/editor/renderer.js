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

    /** Celda → píxel pantalla (esquina superior-izquierda de la celda) */
    cellToScreen(cx, cy) {
        return {
            x: cx * CELL * this.zoom + this.panX,
            y: cy * CELL * this.zoom + this.panY
        };
    }

    /** Píxel pantalla → celda */
    screenToCell(sx, sy) {
        return {
            x: Math.floor((sx - this.panX) / (CELL * this.zoom)),
            y: Math.floor((sy - this.panY) / (CELL * this.zoom))
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
        this._drawRacks();
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

        // Hover cell
        if (this.hoverCell && s.isInBounds(this.hoverCell.x, this.hoverCell.y)) {
            const hx = this.hoverCell.x * CELL;
            const hy = this.hoverCell.y * CELL;
            ctx.fillStyle = 'rgba(79, 156, 249, 0.12)';
            ctx.fillRect(hx + 1, hy + 1, CELL - 2, CELL - 2);

            // Coordenadas de celda
            ctx.fillStyle   = 'rgba(79, 156, 249, 0.6)';
            ctx.font        = `${Math.max(7, 7)}px "JetBrains Mono", monospace`;
            ctx.textAlign   = 'left';
            ctx.textBaseline = 'top';
            ctx.fillText(`${this.hoverCell.x},${this.hoverCell.y}`, hx + 2, hy + 2);
        }
    }

    // ── Zona de despacho ──────────────────────────────────────────

    _drawDispatchZone() {
        const ctx = this.ctx;
        const dz  = this.scenario.dispatchZone;
        const x   = dz.x * CELL;
        const y   = dz.y * CELL;
        const w   = dz.w * CELL;
        const h   = dz.h * CELL;

        // Relleno
        ctx.fillStyle = 'rgba(79, 201, 127, 0.12)';
        ctx.fillRect(x, y, w, h);

        // Borde punteado
        ctx.strokeStyle = 'rgba(79, 201, 127, 0.75)';
        ctx.lineWidth   = 1.5;
        ctx.setLineDash([5, 4]);
        ctx.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1);
        ctx.setLineDash([]);

        // Etiqueta
        ctx.fillStyle    = 'rgba(79, 201, 127, 0.85)';
        ctx.font         = `bold 9px "JetBrains Mono", monospace`;
        ctx.textAlign    = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('DESPACHO', x + w / 2, y + h / 2);
    }

    // ── Racks ─────────────────────────────────────────────────────

    _drawRacks() {
        for (const rack of this.scenario.racks) {
            this._drawRack(rack);
        }
    }

    _drawRack(rack) {
        const ctx = this.ctx;
        const rx  = rack.x * CELL + 2;
        const ry  = rack.y * CELL + 2;
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
        ctx.roundRect(rx, ry, rw, rh, r);
        ctx.stroke();

        // ID del rack (esquina superior)
        ctx.fillStyle    = isSelected ? 'rgba(200, 204, 255, 0.85)' : 'rgba(130, 150, 220, 0.6)';
        ctx.font         = `8px "JetBrains Mono", monospace`;
        ctx.textAlign    = 'center';
        ctx.textBaseline = 'top';
        ctx.fillText(rack.id, rx + rw / 2, ry + 3);

        // Productos
        if (rack.products.length > 0) {
            this._drawProductsOnRack(rack, rx, ry, rw, rh);
        }
    }

    _drawProductsOnRack(rack, rx, ry, rw, rh) {
        const ctx = this.ctx;

        const maxSpriteSize = Math.min(rw - 10, rh - 18, CELL * 0.65);
        const sp   = maxSpriteSize;
        const sx   = rx + (rw - sp) / 2;
        const sy   = ry + (rh - sp) / 2 + 3;

        if (this.productSprite.complete && this.productSprite.naturalWidth > 0) {
            // Renderizar sprite pixel art con escalado nítido
            ctx.save();
            ctx.imageSmoothingEnabled = false;
            ctx.drawImage(this.productSprite, sx, sy, sp, sp);
            ctx.restore();
        } else {
            // Fallback: caja dibujada
            ctx.fillStyle   = '#78350f';
            ctx.strokeStyle = '#451a03';
            ctx.lineWidth   = 1.5;
            ctx.beginPath();
            ctx.roundRect(sx, sy, sp, sp, 2);
            ctx.fill();
            ctx.stroke();
            // Cruz (tapa de caja)
            ctx.strokeStyle = 'rgba(0,0,0,0.3)';
            ctx.lineWidth   = 1;
            ctx.beginPath();
            ctx.moveTo(sx, sy); ctx.lineTo(sx + sp, sy + sp);
            ctx.moveTo(sx + sp, sy); ctx.lineTo(sx, sy + sp);
            ctx.stroke();
        }

        // Badge con cantidad de productos
        const count   = rack.products.length;
        const badgeR  = 7;
        const bx      = rx + rw - badgeR - 2;
        const by      = ry + badgeR + 2;

        ctx.fillStyle = '#4f9cf9';
        ctx.beginPath();
        ctx.arc(bx, by, badgeR, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle    = '#fff';
        ctx.font         = `bold 8px "JetBrains Mono", monospace`;
        ctx.textAlign    = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(count, bx, by);
    }

    // ── Pickers ───────────────────────────────────────────────────

    _drawPickers() {
        for (const picker of this.scenario.pickers) {
            this._drawPicker(picker);
        }
    }

    _drawPicker(picker) {
        const ctx = this.ctx;
        const cx  = picker.x * CELL + CELL / 2;
        const cy  = picker.y * CELL + CELL / 2;

        const isSelected = this.selectedElement?.type === 'picker' &&
                           this.selectedElement.element.id === picker.id;

        const FW = WarehouseRenderer.FRAME_W;  // 32
        const FH = WarehouseRenderer.FRAME_H;  // 24

        // Escalar por altura exacta de la celda: spriteH = CELL → sin overflow vertical
        // scale = CELL/FH = 36/24 = 1.5  →  spriteW=48, spriteH=36
        const scale = CELL / FH;
        const spriteW = FW * scale;   // 48px (levemente más ancho que la celda, centrado)
        const spriteH = FH * scale;   // 36px (exactamente la altura de la celda)

        // Posición: centrado horizontalmente, alineado al borde superior de la celda
        const drawX = cx - spriteW / 2;
        const drawY = picker.y * CELL;   // empieza en el borde superior → sin overflow abajo

        // Buscar la variante de sprite que corresponde al color del picker
        const variant = this._getPickerVariant(picker.color);
        const sprites = this._pickerSprites[variant];
        const idleImg = sprites?.idle;

        if (idleImg && idleImg.complete && idleImg.naturalWidth > 0) {
            // Dirección: por ahora usamos row 0 (mirando hacia abajo), frame 0
            const srcX = 0;   // columna 0
            const srcY = 0;   // fila 0 (DIR_DOWN)

            ctx.save();
            ctx.imageSmoothingEnabled = false;  // escalado nítido pixel art

            if (isSelected) {
                ctx.shadowColor = picker.color;
                ctx.shadowBlur  = 14;
            }

            ctx.drawImage(
                idleImg,
                srcX, srcY, FW, FH,   // source: un frame del spritesheet
                drawX, drawY, spriteW, spriteH  // destino: centrado en celda
            );

            ctx.restore();

        } else {
            // Fallback: figura geométrica
            ctx.save();
            if (isSelected) {
                ctx.shadowColor = picker.color;
                ctx.shadowBlur  = 14;
            }

            // Cuerpo
            ctx.fillStyle = picker.color;
            ctx.beginPath();
            ctx.ellipse(cx, cy + CELL * 0.1, CELL * 0.18, CELL * 0.22, 0, 0, Math.PI * 2);
            ctx.fill();

            // Cabeza
            ctx.fillStyle = '#fcd34d';
            ctx.beginPath();
            ctx.arc(cx, cy - CELL * 0.18, CELL * 0.14, 0, Math.PI * 2);
            ctx.fill();

            // Casco
            ctx.fillStyle = picker.color;
            ctx.beginPath();
            ctx.arc(cx, cy - CELL * 0.22, CELL * 0.13, Math.PI, 0, false);
            ctx.fill();

            ctx.restore();
        }

        // Anillo de selección
        if (isSelected) {
            ctx.strokeStyle  = picker.color;
            ctx.lineWidth    = 1.5;
            ctx.setLineDash([4, 3]);
            ctx.strokeRect(
                picker.x * CELL + 2, picker.y * CELL + 2,
                CELL - 4, CELL - 4
            );
            ctx.setLineDash([]);
        }

        // Nombre debajo
        ctx.fillStyle    = picker.color;
        ctx.font         = `bold 7px "JetBrains Mono", monospace`;
        ctx.textAlign    = 'center';
        ctx.textBaseline = 'bottom';
        ctx.fillText(picker.name, cx, picker.y * CELL + CELL - 2);
    }

    // ── Cursor preview (modo rack) ────────────────────────────────

    _drawCursorPreview() {
        if (!this.cursorRect || this.mode !== 'rack') return;
        const ctx = this.ctx;
        const { x, y, w, h } = this.cursorRect;
        const px = x * CELL;
        const py = y * CELL;
        const pw = w * CELL;
        const ph = h * CELL;

        ctx.fillStyle   = 'rgba(79, 156, 249, 0.2)';
        ctx.fillRect(px, py, pw, ph);

        ctx.strokeStyle = '#4f9cf9';
        ctx.lineWidth   = 1.5;
        ctx.setLineDash([4, 3]);
        ctx.strokeRect(px + 0.5, py + 0.5, pw - 1, ph - 1);
        ctx.setLineDash([]);

        // Dimensiones del rack
        ctx.fillStyle    = '#4f9cf9';
        ctx.font         = `bold 9px "JetBrains Mono", monospace`;
        ctx.textAlign    = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(`${w}×${h}`, px + pw / 2, py + ph / 2);
    }

    // ── Cleanup ───────────────────────────────────────────────────

    destroy() {
        this._ro.disconnect();
    }
}
