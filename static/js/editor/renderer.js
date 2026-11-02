/* ================================================================
   WAREHOUSE RENDERER
   Dibuja el scenario en un <canvas> usando Canvas 2D API.
   Es stateless respecto a la interacción: el Editor le setea
   las propiedades de estado (hover, selection, cursorRect…)
   y este módulo solo dibuja.
================================================================ */

const CELL = 36;   // tamaño base de celda en píxeles (world space)

// ── Paletas de colores para el canvas según tema ─────────────────
const CANVAS_THEMES = {
    dark: {
        floor:          '#12141f',
        floorLines:     'rgba(255,255,255,0.018)',
        floorBorder:    'rgba(79,156,249,0.35)',
        floorVignette:  'rgba(0,0,0,0.3)',
        grid:           'rgba(255,255,255,0.045)',
        // Racks
        rackFill:       'rgba(79,156,249,0.10)',
        rackFillSel:    'rgba(79,156,249,0.22)',
        rackBorder:     'rgba(79,156,249,0.55)',
        rackBorderSel:  'rgba(79,156,249,1.0)',
        rackCross:      'rgba(79,156,249,0.08)',
        rackCrossSel:   'rgba(79,156,249,0.18)',
        rackLines:      'rgba(79,156,249,0.12)',
        rackLinesSel:   'rgba(79,156,249,0.25)',
        rackGlow:       'rgba(79,156,249,0.5)',
        rackGlowStroke: 'rgba(79,156,249,0.8)',
        rackIdBg:       'rgba(0,0,0,0.45)',
        rackIdText:     'rgba(79,156,249,0.9)',
        rackIdTextSel:  'rgba(79,156,249,1.0)',
        // Hover cell
        hoverFill:      'rgba(79,156,249,0.12)',
        hoverFillOnRack:'rgba(79,156,249,0.25)',
        hoverCoordBg:   'rgba(0,0,0,0.55)',
        hoverCoordText: 'rgba(79,156,249,0.9)',
        hoverCoordOnRack:'#93c5fd',
        // Door ID / label
        doorIdBg:       'rgba(0,0,0,0.55)',
    },
    light: {
        floor:          '#f0f4f8',
        floorLines:     'rgba(0,0,0,0.028)',
        floorBorder:    'rgba(37,99,235,0.40)',
        floorVignette:  'rgba(0,0,0,0.04)',
        grid:           'rgba(0,0,0,0.07)',
        // Racks
        rackFill:       'rgba(37,99,235,0.08)',
        rackFillSel:    'rgba(37,99,235,0.20)',
        rackBorder:     'rgba(37,99,235,0.55)',
        rackBorderSel:  'rgba(37,99,235,1.0)',
        rackCross:      'rgba(37,99,235,0.08)',
        rackCrossSel:   'rgba(37,99,235,0.18)',
        rackLines:      'rgba(37,99,235,0.14)',
        rackLinesSel:   'rgba(37,99,235,0.28)',
        rackGlow:       'rgba(37,99,235,0.35)',
        rackGlowStroke: 'rgba(37,99,235,0.75)',
        rackIdBg:       'rgba(255,255,255,0.85)',
        rackIdText:     '#1d4ed8',
        rackIdTextSel:  '#1e3a8a',
        // Hover cell
        hoverFill:      'rgba(37,99,235,0.10)',
        hoverFillOnRack:'rgba(37,99,235,0.22)',
        hoverCoordBg:   'rgba(255,255,255,0.85)',
        hoverCoordText: '#1d4ed8',
        hoverCoordOnRack:'#1e3a8a',
        // Door ID / label
        doorIdBg:       'rgba(255,255,255,0.85)',
    },
};

/** Devuelve la paleta activa leyendo data-theme del <html>. */
function _getCanvasTheme() {
    return document.documentElement.getAttribute('data-theme') === 'light'
        ? CANVAS_THEMES.light
        : CANVAS_THEMES.dark;
}

class WarehouseRenderer {

    constructor(canvas) {
        this.canvas  = canvas;
        this.ctx     = canvas.getContext('2d');
        this.scenario = null;

        // ── Capa estática pre-renderizada (offscreen canvas) ─────────
        // Toda la geometría del warehouse (piso, grilla, pasillos, racks…)
        // se dibuja una sola vez acá y luego se blitea con un único
        // drawImage() por frame.
        this._staticCanvas = document.createElement('canvas');
        this._staticCtx    = this._staticCanvas.getContext('2d');
        this._staticDirty  = true;   // fuerza el primer render de la capa
        this._staticScale  = 1;      // píxeles de capa por unidad world
        this._staticContentW = 0;    // área realmente dibujada (px de capa)
        this._staticContentH = 0;

        // Callback de "render bajo demanda" (lo conecta WarehouseEditor).
        this.onDirty = null;

        // ── Paleta y color de fondo cacheados ────────────────────────
        // Se leen del DOM una sola vez y solo se refrescan cuando cambia
        // data-theme (MutationObserver), nunca por frame.
        this._theme     = CANVAS_THEMES.dark;
        this._themeName = 'dark';
        this._bgColor   = '#0f0f0f';
        this._refreshThemeCache();
        this._themeObserver = new MutationObserver(() => this._refreshThemeCache());
        this._themeObserver.observe(document.documentElement, {
            attributes: true,
            attributeFilter: ['data-theme'],
        });

        // Viewport
        this.zoom = 1;
        this.panX = 40;
        this.panY = 40;

        // Estado visual (lo setea WarehouseEditor)
        this.hoverCell       = null;   // { x, y } | null
        this.cursorRect      = null;   // { x, y, w, h } para preview de rack
        this.selectedElement = null;   // { type, element } | null
        this.mode            = 'select';
        this.doorTipo        = 'AMBOS'; // sincronizado por el editor al cambiar tipo de puerta

        // Estado de ruta de simulación (seteado desde sim.js).
        // Modo multi-agente: lista de rutas, una por picker activo.
        // Cada entrada es { path, paradas, step, color }.
        this.agentRoutes = [];

        // Compatibilidad con código legado que use routePath directamente.
        this.routePath  = null;
        this.routeStops = [];
        this.routeStep  = 0;

        // Modo de enfoque del recorrido (seteado desde sim.js).
        // Cuando esta activo, el relleno de los pasillos se atenua para destacar
        // el trazado amarillo y el picker. Las flechas mantienen su opacidad.
        this.focusMode  = false;
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

    // ── Estado visual con notificación de cambios ─────────────────
    // Los setters marcan el canvas como "sucio" solo cuando el valor
    // realmente cambia, habilitando el render bajo demanda.

    get hoverCell() { return this._hoverCell; }
    set hoverCell(v) {
        const a = this._hoverCell;
        if (a === v) return;
        if (a && v && a.x === v.x && a.y === v.y) return;
        this._hoverCell = v;
        this._markDirty();
    }

    get cursorRect() { return this._cursorRect; }
    set cursorRect(v) {
        const a = this._cursorRect;
        if (a === v) return;
        if (a && v && a.x === v.x && a.y === v.y && a.w === v.w && a.h === v.h) return;
        this._cursorRect = v;
        this._markDirty();
    }

    get selectedElement() { return this._selectedElement; }
    set selectedElement(v) {
        const a = this._selectedElement;
        if (a === v) return;
        const same = (a?.type === v?.type) &&
                     (a?.element?.id === v?.element?.id) &&
                     (!!a === !!v);
        this._selectedElement = v;
        if (same) return;
        // La selección pinta borde/glow sobre la geometría estática.
        this._staticDirty = true;
        this._markDirty();
    }

    get mode() { return this._mode; }
    set mode(v) {
        if (this._mode === v) return;
        this._mode = v;
        this._markDirty();
    }

    get doorTipo() { return this._doorTipo; }
    set doorTipo(v) {
        if (this._doorTipo === v) return;
        this._doorTipo = v;
        this._markDirty();
    }

    get agentRoutes() { return this._agentRoutes; }
    set agentRoutes(v) { this._agentRoutes = v; this._markDirty(); }

    get routePath() { return this._routePath; }
    set routePath(v) { this._routePath = v; this._markDirty(); }

    get routeStops() { return this._routeStops; }
    set routeStops(v) { this._routeStops = v; this._markDirty(); }

    get routeStep() { return this._routeStep; }
    set routeStep(v) { this._routeStep = v; this._markDirty(); }

    get focusMode() { return this._focusMode; }
    set focusMode(v) {
        v = !!v;
        if (this._focusMode === v) return;
        this._focusMode = v;
        // En modo enfoque los pasillos cambian relleno/flechas.
        this.invalidateStaticLayer();
    }

    get panX() { return this._panX; }
    set panX(v) {
        if (this._panX === v) return;
        this._panX = v;
        this._markDirty();
    }

    get panY() { return this._panY; }
    set panY(v) {
        if (this._panY === v) return;
        this._panY = v;
        this._markDirty();
    }

    get zoom() { return this._zoom; }
    set zoom(v) {
        if (this._zoom === v) return;
        this._zoom = v;
        // La capa estática se genera a la resolución del zoom actual.
        this.invalidateStaticLayer();
    }

    // ── Render bajo demanda ───────────────────────────────────────

    /** Marca el canvas para redibujarse en el próximo frame. */
    requestRender() { this._markDirty(); }

    _markDirty() {
        if (typeof this.onDirty === 'function') this.onDirty();
    }

    /** La geometría estática cambió: hay que regenerar la capa offscreen. */
    invalidateStaticLayer() {
        this._staticDirty = true;
        this._markDirty();
    }

    /** Relee la paleta y el color de fondo. Solo se llama al cambiar el tema. */
    _refreshThemeCache() {
        const name = document.documentElement.getAttribute('data-theme') === 'light'
            ? 'light' : 'dark';
        this._themeName = name;
        this._theme     = _getCanvasTheme();
        this._bgColor   = getComputedStyle(document.documentElement)
                              .getPropertyValue('--color-bg').trim() || '#0f0f0f';
        this.invalidateStaticLayer();
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
            if (loaded >= totalImages) {
                this._spritesReady = true;
                // Los sprites aparecieron: hay que repintar pickers (capa
                // dinámica) y productos sobre racks (capa estática).
                this.invalidateStaticLayer();
            }
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
        const w = p.clientWidth;
        const h = p.clientHeight;
        if (this.canvas.width === w && this.canvas.height === h) return;
        this.canvas.width  = w;
        this.canvas.height = h;
        // El tamaño del viewport cambió: recalcular en el próximo frame.
        this.invalidateStaticLayer();
    }

    // ── Scenario ──────────────────────────────────────────────────

    setScenario(scenario) {
        this.scenario = scenario;
        this._observeScenarioMutations(scenario);
        this._centerView();
        this.invalidateStaticLayer();
    }

    /**
     * Envuelve los métodos de mutación del escenario para invalidar la capa
     * estática y pedir un repintado automáticamente, sin importar desde qué
     * módulo (editor, ui.js, wizard) se modifique el warehouse.
     * Se ejecuta una sola vez por instancia de escenario.
     */
    _observeScenarioMutations(scenario) {
        if (!scenario || scenario.__rendererObserved) return;
        scenario.__rendererObserved = true;

        const MUTATORS = [
            'addRack', 'removeRack', 'moveRack', 'rotateRack',
            'addDoor', 'removeDoor', 'moveDoor',
            'addDispatchZone', 'removeDispatchZone',
            'addAisle', 'removeAisle',
            'addProduct', 'removeProduct',
            'addPicker', 'removePicker', 'movePicker',
        ];

        for (const name of MUTATORS) {
            const original = scenario[name];
            if (typeof original !== 'function') continue;
            scenario[name] = (...args) => {
                const result = original.apply(scenario, args);
                this.invalidateStaticLayer();
                return result;
            };
        }
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

    // ── Capa estática (offscreen) ─────────────────────────────────

    /**
     * Pre-renderiza toda la geometría estática del warehouse (piso, grilla,
     * zonas de despacho, pasillos, puertas y racks) en un canvas fuera de
     * pantalla, en coordenadas world-space y a la resolución del zoom actual.
     *
     * Solo se re-ejecuta cuando algo estructural cambia: escenario, tamaño
     * del canvas, tema, selección o zoom. Nunca en cada frame.
     */
    _renderStaticLayer() {
        const sc = this.scenario;
        const c  = this._staticCanvas;

        if (!sc) {
            if (c.width !== 1 || c.height !== 1) { c.width = 1; c.height = 1; }
            this._staticScale    = 1;
            this._staticContentW = 0;
            this._staticContentH = 0;
            this._staticDirty = false;
            return;
        }

        const worldW = sc.width  * CELL;
        const worldH = sc.height * CELL;

        // 1 px de capa por px de pantalla al zoom actual (blit 1:1 = nítido).
        // Se limita el tamaño para no exceder los límites de canvas/GPU en
        // escenarios grandes con zoom alto (en ese caso se reescala levemente).
        const targetW = worldW * this.zoom;
        const targetH = worldH * this.zoom;
        const MAX_DIM  = 8192;
        const MAX_AREA = 32 * 1024 * 1024;   // ~32 MPx
        let q = 1;
        if (targetW > MAX_DIM || targetH > MAX_DIM || targetW * targetH > MAX_AREA) {
            q = Math.min(
                MAX_DIM / targetW,
                MAX_DIM / targetH,
                Math.sqrt(MAX_AREA / (targetW * targetH)),
            );
        }

        const sw = Math.max(1, Math.ceil(targetW * q));
        const sh = Math.max(1, Math.ceil(targetH * q));

        if (c.width !== sw || c.height !== sh) {
            c.width  = sw;   // redimensionar también limpia el canvas
            c.height = sh;
        } else {
            this._staticCtx.setTransform(1, 0, 0, 1, 0, 0);
            this._staticCtx.clearRect(0, 0, sw, sh);
        }

        this._staticScale = this.zoom * q;   // px de capa por unidad world
        // Área realmente dibujada dentro del canvas (puede quedar < 1 px de
        // margen por el ceil). Se usa como source rect para un blit 1:1.
        this._staticContentW = worldW * this._staticScale;
        this._staticContentH = worldH * this._staticScale;

        // Los métodos _draw* dibujan sobre this.ctx: apuntamos al offscreen
        // durante la generación y restauramos al terminar (síncrono, sin
        // reentrancia posible).
        const mainCtx = this.ctx;
        this.ctx = this._staticCtx;
        try {
            const ctx = this._staticCtx;
            const theme = this._theme;

            ctx.save();
            ctx.setTransform(this._staticScale, 0, 0, this._staticScale, 0, 0);

            this._drawFloor(theme);
            this._drawGrid(theme);
            this._drawDispatchZone();
            this._drawAisles();
            this._drawDoors(theme);
            this._drawRacks(theme);

            ctx.restore();
        } finally {
            this.ctx = mainCtx;
        }

        this._staticDirty = false;
    }

    // ── Render principal ──────────────────────────────────────────

    render() {
        const ctx = this.ctx;
        const W   = this.canvas.width;
        const H   = this.canvas.height;

        // Paleta cacheada: no se toca getComputedStyle por frame.
        const theme = this._theme;

        // Limpiar
        ctx.clearRect(0, 0, W, H);
        this._drawAppBackground(W, H);

        if (!this.scenario) {
            this._staticDirty = false;
            return;
        }

        // Regenerar la capa estática solo si algo estructural cambió.
        if (this._staticDirty) this._renderStaticLayer();

        const z = this.zoom;

        ctx.save();
        try {
            ctx.translate(this.panX, this.panY);
            ctx.scale(z, z);

            // ── Capa estática: un único drawImage (antes ~20.000 ops) ──
            // Se copia solo el área de contenido real a su tamaño world, de
            // modo que el blit sea 1:1 y no haya reescalado subpíxel.
            if (this._staticCanvas.width > 1 && this._staticContentW > 0) {
                ctx.imageSmoothingEnabled = true;
                ctx.imageSmoothingQuality = 'high';
                ctx.drawImage(
                    this._staticCanvas,
                    0, 0,
                    this._staticContentW, this._staticContentH,
                    0, 0,
                    this.scenario.width  * CELL,
                    this.scenario.height * CELL,
                );
            }

            // ── Capa dinámica ─────────────────────────────────────
            this._drawRoutePath();            // trayecto de simulación (bajo el picker)
            this._drawHoverCell(theme);   // dibujado DESPUÉS de racks para que las coordenadas sean siempre visibles
            this._drawPickers();
            this._drawCursorPreview();
        } finally {
            ctx.restore();
        }
    }

    // ── Fondo de aplicación ───────────────────────────────────────

    _drawAppBackground(W, H) {
        const ctx = this.ctx;
        // Color cacheado: se refresca solo cuando cambia el tema.
        ctx.fillStyle = this._bgColor || '#0f0f0f';
        ctx.fillRect(0, 0, W, H);
    }

    // ── Piso del warehouse ─────────────────────────────────────────

    _drawFloor(theme) {
        const ctx = this.ctx;
        const s   = this.scenario;
        const W   = s.width  * CELL;
        const H   = s.height * CELL;

        // Base
        ctx.fillStyle = theme.floor;
        ctx.fillRect(0, 0, W, H);

        // Textura sutil: líneas diagonales
        ctx.save();
        ctx.strokeStyle = theme.floorLines;
        ctx.lineWidth   = 1;
        for (let i = -H; i < W + H; i += 18) {
            ctx.beginPath();
            ctx.moveTo(i, 0);
            ctx.lineTo(i + H, H);
            ctx.stroke();
        }
        ctx.restore();

        // Borde exterior
        ctx.strokeStyle = theme.floorBorder;
        ctx.lineWidth   = 2;
        ctx.strokeRect(0, 0, W, H);

        // Sombra interna (vignette)
        const grad = ctx.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, Math.max(W, H) * 0.7);
        grad.addColorStop(0, 'rgba(0,0,0,0)');
        grad.addColorStop(1, theme.floorVignette);
        ctx.fillStyle = grad;
        ctx.fillRect(0, 0, W, H);
    }

    // ── Grid ──────────────────────────────────────────────────────

    _drawGrid(theme) {
        const ctx = this.ctx;
        const s   = this.scenario;

        ctx.strokeStyle = theme.grid;
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

    _drawHoverCell(theme) {
        const ctx = this.ctx;
        const s   = this.scenario;
        if (!this.hoverCell || !s.isInBounds(this.hoverCell.x, this.hoverCell.y)) return;

        const hx = this.hoverCell.x * CELL;
        const hy = this._wy(this.hoverCell.y);

        const onRack = !!s.getRackAt(this.hoverCell.x, this.hoverCell.y);

        // Fondo con mayor contraste si está sobre un rack
        ctx.fillStyle = onRack ? theme.hoverFillOnRack : theme.hoverFill;
        ctx.fillRect(hx + 1, hy + 1, CELL - 2, CELL - 2);

        // Coordenadas — fondo para garantizar legibilidad sobre el color del rack
        const label = `${this.hoverCell.x},${this.hoverCell.y}`;
        ctx.font         = `7px "JetBrains Mono", monospace`;
        ctx.textAlign    = 'left';
        ctx.textBaseline = 'top';
        const tw = ctx.measureText(label).width;
        ctx.fillStyle = theme.hoverCoordBg;
        ctx.fillRect(hx + 2, hy + 2, tw + 4, 10);
        ctx.fillStyle = onRack ? theme.hoverCoordOnRack : theme.hoverCoordText;
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

        ctx.textAlign    = 'center';
        ctx.textBaseline = 'middle';

        // Calcular cuántas líneas y centrar verticalmente el bloque
        const lines = ['DESPACHO'];
        lines.push(dz.id);
        if (dz.puertaId)           lines.push(`Puerta: ${dz.puertaId}`);
        lines.push(`Máx: ${dz.pesoMaxKg || 500} kg`);

        const lineHeight = 11;
        const totalH     = (lines.length - 1) * lineHeight;
        const startY     = y + h / 2 - totalH / 2;

        lines.forEach((text, i) => {
            const cy = startY + i * lineHeight;
            if (i === 0) {
                ctx.font      = `bold 9px "JetBrains Mono", monospace`;
                ctx.fillStyle = 'rgba(79,201,127,0.9)';
            } else {
                ctx.font      = `7px "JetBrains Mono", monospace`;
                ctx.fillStyle = 'rgba(79,201,127,0.7)';
            }
            ctx.fillText(text, x + w / 2, cy);
        });

        ctx.restore();

        // El rect del clip queda en el path actual (save/restore no lo limpia).
        // Lo reiniciamos para que ningún fill/stroke posterior lo repinte.
        ctx.beginPath();
    }

    // ── Pasillos (flechas de dirección) ──────────────────────────

    _drawAisles() {
        for (const aisle of this.scenario.aisles) {
            this._drawOneAisle(aisle);
        }
    }

    _drawOneAisle(aisle) {
        const isSel = this.selectedElement?.type === 'aisle' &&
                      this.selectedElement.element.id === aisle.id;

        const ctx = this.ctx;
        const s   = this.scenario;
        const x   = aisle.x * CELL;
        const y   = (s.height - aisle.y - aisle.height) * CELL;
        const w   = aisle.width  * CELL;
        const h   = aisle.height * CELL;

        // Si está seleccionado, dibujar fondo iluminado previo
        if (isSel) {
            ctx.save();
            ctx.fillStyle = 'rgba(253, 196, 51, 0.18)';
            ctx.fillRect(x, y, w, h);
            ctx.restore();
        }

        // Celdas y flechas individuales
        for (let cx = aisle.x; cx < aisle.x + aisle.width; cx++) {
            for (let cy = aisle.y; cy < aisle.y + aisle.height; cy++) {
                this._drawAisleCell(cx, cy, aisle.sentido, isSel);
            }
        }

        // Si está seleccionado, dibujar contorno perimetral discontinuo con glow
        if (isSel) {
            ctx.save();
            ctx.shadowColor   = 'rgba(251,191,36,0.45)';
            ctx.shadowBlur    = 8;
            ctx.strokeStyle   = 'rgba(251,191,36,1.0)';
            ctx.lineWidth     = 2;
            ctx.setLineDash([5, 4]);
            ctx.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1);
            ctx.setLineDash([]);
            ctx.restore();
        }
    }

    _drawAisleCell(cx, cy, sentido, isSelected = false) {
        const ctx = this.ctx;
        const s   = this.scenario;
        const px  = cx * CELL;
        const py  = (s.height - 1 - cy) * CELL;
        const mid = CELL / 2;
        const ar  = CELL * 0.22;

        ctx.save();
        ctx.translate(px + mid, py + mid);

        // En modo enfoque no se dibuja el fondo amarillo: solo las flechas.
        // En modo normal se mantiene el relleno original.
        if (!this.focusMode) {
            ctx.fillStyle = isSelected ? 'rgba(251,191,36,0.12)' : 'rgba(251,191,36,0.07)';
            ctx.fillRect(-mid, -mid, CELL, CELL);
        }

        // En focusMode: flechas menos notorias y AMBOS sin flechas.
        // En modo normal: opacidad completa y AMBOS con 4 flechas (comportamiento original).
        const strokeColor = isSelected ? 'rgba(251,191,36,0.95)' : 'rgba(251,191,36,0.55)';
        const strokeColorBoth = isSelected ? 'rgba(251,191,36,0.65)' : 'rgba(251,191,36,0.25)';

        // En focusMode las flechas con sentido especifico se dibujan mas tenues
        const arrowAlpha = this.focusMode ? 0.30 : 1.0;

        ctx.strokeStyle = strokeColor;
        ctx.fillStyle   = strokeColor;
        ctx.lineWidth   = isSelected ? 1.6 : 1.2;

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
                // Norte logico (+y) = arriba en canvas (-py), Sur logico (-y) = abajo en canvas (+py)
                const sy = dy > 0 ? -1 : 1;
                ctx.moveTo(0, sy * len);
                ctx.lineTo(-hw, sy * (len - hh));
                ctx.lineTo( hw, sy * (len - hh));
            }
            ctx.closePath();
            ctx.fill();
        };

        if (sentido === 'N' || sentido === 'S' || sentido === 'E' || sentido === 'O') {
            // Sentido especifico: dibujar siempre, pero mas tenue en focusMode
            ctx.save();
            ctx.globalAlpha = arrowAlpha;
            if      (sentido === 'N') { drawArrow(0,  1); }
            else if (sentido === 'S') { drawArrow(0, -1); }
            else if (sentido === 'E') { drawArrow(1,  0); }
            else                     { drawArrow(-1, 0); }
            ctx.restore();
        } else if (!this.focusMode) {
            // AMBOS: solo dibujar las 4 flechas en modo normal (en focusMode desaparecen)
            ctx.strokeStyle = strokeColorBoth;
            ctx.fillStyle   = strokeColorBoth;
            drawArrow(0, 1); drawArrow(0, -1);
            drawArrow(1, 0); drawArrow(-1, 0);
        }
        ctx.restore()
    }

    // ── Puertas (muelles) ─────────────────────────────────────────

    _drawDoors(theme) {
        for (const door of this.scenario.doors) {
            this._drawDoor(door, theme);
        }
    }

    _drawDoor(door, theme) {
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
        ctx.fillStyle    = theme.doorIdBg;
        ctx.fillRect(px + CELL / 2 - idW / 2, py + 2, idW, 11);
        ctx.fillStyle    = base;
        ctx.fillText(door.id, px + CELL / 2, py + 3);
        ctx.restore();

        // Evitar que el rect del clip quede en el path para el resto del frame
        ctx.beginPath();
    }

    // ── Racks ─────────────────────────────────────────────────────

    _drawRacks(theme) {
        for (const rack of this.scenario.racks) {
            this._drawRack(rack, theme);
        }
    }

    _drawRack(rack, theme) {
        const ctx = this.ctx;
        const s   = this.scenario;

        // Coordenadas del bounding box del rack (pegado a la grilla, sin margen)
        const rx = rack.x * CELL;
        const ry = (s.height - rack.y - rack.height) * CELL;
        const rw = rack.width  * CELL;
        const rh = rack.height * CELL;

        const cols = rack.width;
        const rows = rack.height;

        const isSelected = this.selectedElement?.type === 'rack' &&
                           this.selectedElement.element.id === rack.id;

        // Colores del tema activo
        const border    = isSelected ? theme.rackBorderSel  : theme.rackBorder;
        const crossCol  = isSelected ? theme.rackCrossSel   : theme.rackCross;
        const lineCol   = isSelected ? theme.rackLinesSel   : theme.rackLines;

        // ── 1. Fondo fill (igual que dispatch y aisle) ───────────────
        ctx.fillStyle = isSelected ? theme.rackFillSel : theme.rackFill;
        ctx.fillRect(rx, ry, rw, rh);

        // ── 2. Clip para los detalles interiores ────────────────────
        ctx.save();
        ctx.beginPath();
        ctx.rect(rx, ry, rw, rh);
        ctx.clip();

        // ── 3. Contravientos en X por celda (detalle blueprint sutil) ──
        ctx.strokeStyle = crossCol;
        ctx.lineWidth   = 1;
        for (let col = 0; col < cols; col++) {
            for (let row = 0; row < rows; row++) {
                const cx = rx + col * CELL;
                const cy = ry + row * CELL;
                const cw = CELL - 4;
                const ch = CELL - 4;
                const ox = cx + 2, oy = cy + 2;
                ctx.beginPath();
                ctx.moveTo(ox,      oy);
                ctx.lineTo(ox + cw, oy + ch);
                ctx.moveTo(ox + cw, oy);
                ctx.lineTo(ox,      oy + ch);
                ctx.stroke();
            }
        }

        // ── 4. Líneas de división de celdas (grilla interna) ─────────
        ctx.strokeStyle = lineCol;
        ctx.lineWidth   = 1;
        // Verticales
        for (let col = 1; col < cols; col++) {
            const lx = rx + col * CELL;
            ctx.beginPath();
            ctx.moveTo(lx, ry);
            ctx.lineTo(lx, ry + rh);
            ctx.stroke();
        }
        // Horizontales
        for (let row = 1; row < rows; row++) {
            const ly = ry + row * CELL;
            ctx.beginPath();
            ctx.moveTo(rx, ly);
            ctx.lineTo(rx + rw, ly);
            ctx.stroke();
        }

        ctx.restore();  // fin del clip

        // ── 5. Borde exterior (igual que dispatch: sólido cuando sel., casi sólido si no) ──
        ctx.strokeStyle = border;
        ctx.lineWidth   = isSelected ? 2 : 1.5;
        ctx.strokeRect(rx, ry, rw, rh);

        // Glow cuando está seleccionado (como el aisle)
        if (isSelected) {
            ctx.save();
            ctx.shadowColor = theme.rackGlow;
            ctx.shadowBlur  = 8;
            ctx.strokeStyle = theme.rackGlowStroke;
            ctx.lineWidth   = 2;
            ctx.strokeRect(rx, ry, rw, rh);
            ctx.restore();
        }

        // ── 6. Etiqueta del ID (misma tipografía y estilo que las puertas) ──
        ctx.save();
        ctx.font         = `bold 8px "JetBrains Mono", monospace`;
        ctx.textAlign    = 'center';
        ctx.textBaseline = 'top';
        const idW = Math.ceil(ctx.measureText(rack.id).width) + 6;
        // Fondo de la etiqueta
        ctx.fillStyle = theme.rackIdBg;
        ctx.fillRect(rx + rw / 2 - idW / 2, ry + 3, idW, 11);
        // Texto
        ctx.fillStyle = isSelected ? theme.rackIdTextSel : theme.rackIdText;
        ctx.fillText(rack.id, rx + rw / 2, ry + 4);
        ctx.restore();

        // ── 7. Productos ─────────────────────────────────────────────
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

    // ── Ruta de simulación ────────────────────────────────────────

    // ── Rutas de simulación (multi-agente) ────────────────────

    /**
     * Dibuja las rutas de todos los agentes activos.
     * Cada ruta usa el color propio del picker para distinguirse.
     * Si no hay agentRoutes definidas, cae al modo mono-agente legado
     * usando routePath/routeStops/routeStep (compatibilidad).
     */
    _drawRoutePath() {
        // Modo multi-agente: iterar sobre todas las rutas de agentes.
        if (this.agentRoutes && this.agentRoutes.length > 0) {
            for (const route of this.agentRoutes) {
                this._drawSingleRoute(route.path, route.paradas, route.step, route.color);
            }
            return;
        }

        // Modo legado (mono-agente): usar routePath directamente.
        if (!this.routePath || this.routePath.length === 0) return;
        this._drawSingleRoute(this.routePath, this.routeStops, this.routeStep, '#fbbf24');
    }

    /**
     * Dibuja una ruta individual:
     * - Tramo ya recorrido: línea sólida con el color del picker.
     * - Tramo pendiente:    línea discontinua tenue del mismo color.
     * - Paradas de recogida: círculo resaltado con ese color.
     *
     * @param {Array}  path    - [[x,y], ...] camino completo.
     * @param {Array}  paradas - [{celda:[x,y], productos:[...]}, ...].
     * @param {number} step    - índice del paso actual.
     * @param {string} color   - color CSS del picker (hex o rgb).
     */
    _drawSingleRoute(path, paradas, step, color) {
        if (!path || path.length === 0) return;

        const ctx = this.ctx;
        step = Math.max(0, step);

        const cellCX = ([cx, cy]) => cx * CELL + CELL / 2;
        const cellCY = ([cx, cy]) => this._wy(cy) + CELL / 2;

        // Convertir color a rgba para poder variar la opacidad.
        // Si el color ya es rgba lo usamos directamente; si es hex lo parseamos.
        const toRgba = (hex, alpha) => {
            const r = parseInt(hex.slice(1, 3), 16);
            const g = parseInt(hex.slice(3, 5), 16);
            const b = parseInt(hex.slice(5, 7), 16);
            return `rgba(${r},${g},${b},${alpha})`;
        };
        const safeColor = color || '#fbbf24';
        const rgba = (col, alpha) => toRgba(col || safeColor, alpha);

        ctx.save();

        // ── Tramo pendiente (desde el paso actual al final) ──────
        if (step < path.length) {
            ctx.beginPath();
            ctx.setLineDash([4, 5]);
            ctx.strokeStyle = this.focusMode
                ? rgba(color, 0.55)
                : rgba(color, 0.30);
            ctx.lineWidth = 2;
            const start = Math.max(0, step - 1);
            ctx.moveTo(cellCX(path[start]), cellCY(path[start]));
            for (let i = start + 1; i < path.length; i++) {
                ctx.lineTo(cellCX(path[i]), cellCY(path[i]));
            }
            ctx.stroke();
            ctx.setLineDash([]);
        }

        // ── Tramo ya recorrido (paso 0 hasta paso actual) ────────
        if (step > 1) {
            ctx.beginPath();
            ctx.strokeStyle = this.focusMode
                ? rgba(color, 0.95)
                : rgba(color, 0.75);
            ctx.lineWidth = this.focusMode ? 3.5 : 2.5;
            ctx.moveTo(cellCX(path[0]), cellCY(path[0]));
            for (let i = 1; i < step && i < path.length; i++) {
                ctx.lineTo(cellCX(path[i]), cellCY(path[i]));
            }
            ctx.stroke();
        }

        // ── Paradas de recogida: círculo con el color del picker ─
        for (const parada of (paradas || [])) {
            const [cx, cy] = parada.celda;
            const sx = cx * CELL + CELL / 2;
            const sy = this._wy(cy) + CELL / 2;

            ctx.fillStyle = rgba(color, 0.18);
            ctx.beginPath();
            ctx.arc(sx, sy, CELL * 0.38, 0, Math.PI * 2);
            ctx.fill();

            ctx.strokeStyle = rgba(color, 0.80);
            ctx.lineWidth   = 1.5;
            ctx.beginPath();
            ctx.arc(sx, sy, CELL * 0.38, 0, Math.PI * 2);
            ctx.stroke();

            ctx.fillStyle    = rgba(color, 0.90);
            ctx.font         = `bold 9px "JetBrains Mono", monospace`;
            ctx.textAlign    = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText('✦', sx, sy);
        }

        ctx.restore();
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

        const variant  = this._getPickerVariant(picker.color);
        const sprites  = this._pickerSprites[variant];
        // Elegir sprite segun si el picker se esta moviendo (walk) o no (idle).
        const animKey  = picker.isWalking ? 'walk' : 'idle';
        const animImg  = sprites?.[animKey];
        // Fallback: si el sprite walk no cargo, usar idle.
        const idleImg  = sprites?.idle;
        const drawImg  = (animImg && animImg.complete && animImg.naturalWidth > 0)
                            ? animImg : idleImg;

        if (drawImg && drawImg.complete && drawImg.naturalWidth > 0) {
            ctx.save();
            ctx.imageSmoothingEnabled = false;
            if (isSelected) {
                ctx.shadowColor = picker.color;
                ctx.shadowBlur  = 14;
            }
            ctx.drawImage(drawImg, 0, 0, FW, FH, drawX, drawY, spriteW, spriteH);
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
            const doorColorMap = {
                AMBOS:    { stroke: '#a78bfa', fill: 'rgba(167,139,250,0.35)' },
                INBOUND:  { stroke: '#22c55e', fill: 'rgba(34,197,94,0.35)'  },
                OUTBOUND: { stroke: '#f97316', fill: 'rgba(249,115,22,0.35)' },
            };
            const dc = doorColorMap[this.doorTipo || 'AMBOS'] || doorColorMap['AMBOS'];
            ctx.fillStyle   = dc.fill;
            ctx.fillRect(px, py, CELL, CELL);
            ctx.strokeStyle = dc.stroke;
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
        if (this._themeObserver) this._themeObserver.disconnect();
        this.onDirty = null;
    }
}

