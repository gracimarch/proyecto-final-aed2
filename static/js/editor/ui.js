/* ================================================================
   EDITOR UI
   Conecta el WarehouseEditor con los elementos del DOM:
   - Modal "Nuevo Escenario"
   - Modal "Agregar Producto"
   - Toolbar de herramientas
   - Panel lateral (info del warehouse, selección)
   - Guardar / Cargar escenario
================================================================ */

// ── Referencias DOM ───────────────────────────────────────────────

const DOM = {
    // Canvas
    canvas:            () => document.getElementById('warehouse-canvas'),
    canvasPlaceholder: () => document.getElementById('canvas-placeholder'),
    canvasStatus:      () => document.getElementById('canvas-status'),

    // Navbar buttons
    btnNew:    () => document.getElementById('btn-new-scenario'),
    btnSave:   () => document.getElementById('btn-save-scenario'),
    btnLoad:   () => document.getElementById('btn-load-scenario'),

    // Zoom
    btnZoomIn:    () => document.getElementById('btn-zoom-in'),
    btnZoomOut:   () => document.getElementById('btn-zoom-out'),
    btnZoomReset: () => document.getElementById('btn-zoom-reset'),

    // Tool buttons
    toolBtns: () => document.querySelectorAll('.tool-btn'),

    // Modal nuevo escenario
    modalNew:       () => document.getElementById('modal-new-scenario'),
    inputWHName:    () => document.getElementById('input-wh-name'),
    inputWHWidth:   () => document.getElementById('input-wh-width'),
    inputWHHeight:  () => document.getElementById('input-wh-height'),
    labelWHWidth:   () => document.getElementById('label-wh-width'),
    labelWHHeight:  () => document.getElementById('label-wh-height'),
    previewGrid:    () => document.getElementById('wh-preview-grid'),
    btnCreateWH:    () => document.getElementById('btn-create-wh'),
    btnCancelWH:    () => document.getElementById('btn-cancel-wh'),

    // Modal producto
    modalProduct:   () => document.getElementById('modal-product'),
    inputProdName:  () => document.getElementById('input-prod-name'),
    inputProdSKU:   () => document.getElementById('input-prod-sku'),
    inputProdQty:   () => document.getElementById('input-prod-qty'),
    btnAddProd:     () => document.getElementById('btn-add-prod'),
    btnCancelProd:  () => document.getElementById('btn-cancel-prod'),
    modalProdTitle: () => document.getElementById('modal-prod-title'),

    // Panel info del warehouse (sidebar izquierdo)
    whId:       () => document.getElementById('wh-id'),
    whSize:     () => document.getElementById('wh-size'),
    whPickers:  () => document.getElementById('wh-pickers'),
    whRacks:    () => document.getElementById('wh-racks'),
    whProducts: () => document.getElementById('wh-products'),

    // Panel de selección
    selectionPanel: () => document.getElementById('selection-panel'),
    selectionBody:  () => document.getElementById('selection-body'),

    // Toast
    toast: () => document.getElementById('editor-toast'),
};

// ── Estado global de la UI ────────────────────────────────────────

let _renderer = null;
let _editor   = null;
let _scenario = null;
let _productTargetRack = null;  // rack al que se le agrega producto

// ── Init ──────────────────────────────────────────────────────────

function initEditorUI() {
    // Zoom
    DOM.btnZoomIn().addEventListener('click',    () => _renderer?.zoomBy(1.2, _renderer.canvas.width / 2, _renderer.canvas.height / 2));
    DOM.btnZoomOut().addEventListener('click',   () => _renderer?.zoomBy(0.85, _renderer.canvas.width / 2, _renderer.canvas.height / 2));
    DOM.btnZoomReset().addEventListener('click', () => _renderer?.zoomReset());

    // Toolbar de herramientas
    DOM.toolBtns().forEach(btn => {
        btn.addEventListener('click', () => {
            DOM.toolBtns().forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            _editor?.setMode(btn.dataset.tool);
        });
    });

    // Modal nuevo escenario
    DOM.btnNew().addEventListener('click', () => openModalNew());
    DOM.btnCancelWH().addEventListener('click', () => closeModalNew());
    DOM.btnCreateWH().addEventListener('click', () => createScenario());
    DOM.modalNew().addEventListener('click', e => {
        if (e.target === DOM.modalNew()) closeModalNew();
    });

    // Sliders de nuevo escenario
    DOM.inputWHWidth().addEventListener('input', () => {
        DOM.labelWHWidth().textContent = DOM.inputWHWidth().value;
        updateGridPreview();
    });
    DOM.inputWHHeight().addEventListener('input', () => {
        DOM.labelWHHeight().textContent = DOM.inputWHHeight().value;
        updateGridPreview();
    });

    // Modal de producto
    DOM.btnCancelProd().addEventListener('click', () => closeModalProduct());
    DOM.modalProduct().addEventListener('click', e => {
        if (e.target === DOM.modalProduct()) closeModalProduct();
    });
    DOM.btnAddProd().addEventListener('click', () => submitProduct());

    // Enter en campos de producto
    [DOM.inputProdName(), DOM.inputProdSKU(), DOM.inputProdQty()].forEach(el => {
        el.addEventListener('keydown', e => { if (e.key === 'Enter') submitProduct(); });
    });

    // Guardar / Cargar
    DOM.btnSave().addEventListener('click', saveScenario);
    DOM.btnLoad().addEventListener('click', loadScenario);

    // Keyboard shortcuts
    document.addEventListener('keydown', e => _onKeyDown(e));

    // Inicializar renderer en el canvas (sin escenario todavía)
    const canvas = DOM.canvas();
    _renderer = new WarehouseRenderer(canvas);
    _editor   = new WarehouseEditor(canvas, _renderer, _onEditorEvent);
    _renderer.render();   // dibuja fondo vacío
}

// ── Modal: Nuevo Escenario ────────────────────────────────────────

function openModalNew() {
    updateGridPreview();
    DOM.modalNew().classList.add('open');
    DOM.inputWHName().focus();
    DOM.inputWHName().select();
}

function closeModalNew() {
    DOM.modalNew().classList.remove('open');
}

function updateGridPreview() {
    const w  = parseInt(DOM.inputWHWidth().value)  || 20;
    const h  = parseInt(DOM.inputWHHeight().value) || 15;
    const pg = DOM.previewGrid();
    DOM.labelWHWidth().textContent  = w;
    DOM.labelWHHeight().textContent = h;

    // Mini-grilla visual proporcional
    const maxPx = 140;
    const cellW = Math.floor(Math.min(maxPx / w, maxPx / h, 12));
    const cellH = cellW;
    pg.style.width  = (w * cellW) + 'px';
    pg.style.height = (h * cellH) + 'px';
    pg.style.gridTemplateColumns = `repeat(${w}, ${cellW}px)`;
    pg.style.gridTemplateRows    = `repeat(${h}, ${cellH}px)`;
    pg.innerHTML = '';
    for (let i = 0; i < w * h; i++) {
        const cell = document.createElement('div');
        cell.className = 'preview-cell';
        // Zona de despacho (esquina inferior-izquierda, 3×2)
        const cx = i % w;
        const cy = Math.floor(i / w);
        if (cx < 3 && cy >= h - 3 && cy < h - 1) {
            cell.className += ' preview-cell--dispatch';
        }
        pg.appendChild(cell);
    }
}

function createScenario() {
    const name   = DOM.inputWHName().value.trim() || 'Escenario 1';
    const width  = parseInt(DOM.inputWHWidth().value)  || 20;
    const height = parseInt(DOM.inputWHHeight().value) || 15;

    _scenario = new Scenario({ name, width, height });
    _editor.setScenario(_scenario);

    closeModalNew();
    DOM.canvasPlaceholder().style.display = 'none';
    DOM.canvas().style.display            = 'block';
    _updateSidebarInfo();
    _updateCanvasStatus();
    showToast(`Escenario "${name}" creado (${width}×${height})`, 'success');
}

// ── Modal: Agregar Producto ───────────────────────────────────────

function openModalProduct(rack) {
    _productTargetRack = rack;
    DOM.modalProdTitle().textContent = `Agregar producto → ${rack.id}`;
    DOM.inputProdName().value = '';
    DOM.inputProdSKU().value  = '';
    DOM.inputProdQty().value  = '1';
    DOM.modalProduct().classList.add('open');
    DOM.inputProdName().focus();
}

function closeModalProduct() {
    _productTargetRack = null;
    DOM.modalProduct().classList.remove('open');
}

function submitProduct() {
    if (!_productTargetRack) return;

    const name = DOM.inputProdName().value.trim();
    const sku  = DOM.inputProdSKU().value.trim();
    const qty  = parseInt(DOM.inputProdQty().value) || 1;

    if (!name) {
        DOM.inputProdName().classList.add('input--error');
        DOM.inputProdName().focus();
        return;
    }
    DOM.inputProdName().classList.remove('input--error');

    const product = _scenario.addProduct(_productTargetRack.id, {
        name, sku: sku || name.toUpperCase().replace(/\s/g, '_'), quantity: qty
    });

    if (product) {
        closeModalProduct();
        _updateSidebarInfo();
        showToast(`Producto "${name}" agregado a ${_productTargetRack.id}`, 'success');
        _productTargetRack = null;
    }
}

// ── Editor events ─────────────────────────────────────────────────

function _onEditorEvent(event, data) {
    switch (event) {
        case 'add-rack':
            _updateSidebarInfo();
            showToast(`Rack ${data.id} colocado`, 'info');
            _showSelectionRack(data);
            break;

        case 'add-picker':
            _updateSidebarInfo();
            showToast(`${data.name} colocado`, 'info');
            _showSelectionPicker(data);
            break;

        case 'remove-rack':
            _updateSidebarInfo();
            showToast(`Rack ${data.id} eliminado`, 'warning');
            _hideSelection();
            break;

        case 'remove-picker':
            _updateSidebarInfo();
            showToast(`${data.name} eliminado`, 'warning');
            _hideSelection();
            break;

        case 'select-rack':
            _showSelectionRack(data);
            break;

        case 'select-picker':
            _showSelectionPicker(data);
            break;

        case 'deselect':
            _hideSelection();
            break;

        case 'open-product-form':
            openModalProduct(data);
            break;

        case 'error':
            showToast(data, 'error');
            break;

        case 'hint':
            showToast(data, 'info');
            break;
    }
}

// ── Panel de selección ────────────────────────────────────────────

function _showSelectionRack(rack) {
    const panel = DOM.selectionPanel();
    const body  = DOM.selectionBody();

    const prods = rack.products.map(p =>
        `<div class="sel-product">
            <span class="sel-prod-name">${p.name}</span>
            <span class="sel-prod-meta">${p.sku} · ×${p.quantity}</span>
            <button class="sel-prod-del" data-pid="${p.id}" title="Eliminar producto" aria-label="Eliminar ${p.name}">
                <span class="icon icon--sm" aria-hidden="true">close</span>
            </button>
         </div>`
    ).join('');

    body.innerHTML = `
        <div class="sel-header">
            <span class="sel-icon" aria-hidden="true"><span class="icon icon--18 icon--filled">shelves</span></span>
            <span class="sel-title">${rack.id}</span>
        </div>
        <div class="sel-row"><span class="sel-label">Posición</span><span class="sel-value">(${rack.x}, ${rack.y})</span></div>
        <div class="sel-row"><span class="sel-label">Tamaño</span><span class="sel-value">${rack.width}×${rack.height} celdas</span></div>
        <div class="sel-row"><span class="sel-label">Productos</span><span class="sel-value">${rack.products.length}</span></div>
        <div class="sel-products">${prods}</div>
        <div class="sel-actions">
            <button class="btn btn--sm btn--ghost" id="sel-add-product-btn">
                <span class="icon icon--sm" aria-hidden="true">add</span> Producto
            </button>
            <button class="btn btn--sm btn--danger" id="sel-del-rack-btn">
                <span class="icon icon--sm" aria-hidden="true">delete</span> Eliminar rack
            </button>
        </div>
    `;

    // Botones del panel
    body.querySelector('#sel-add-product-btn')?.addEventListener('click', () => openModalProduct(rack));
    body.querySelector('#sel-del-rack-btn')?.addEventListener('click',    () => {
        _scenario.removeRack(rack.id);
        _renderer.selectedElement = null;
        _updateSidebarInfo();
        _hideSelection();
        showToast(`Rack ${rack.id} eliminado`, 'warning');
    });

    // Eliminar producto individual
    body.querySelectorAll('.sel-prod-del').forEach(btn => {
        btn.addEventListener('click', () => {
            const pid = btn.dataset.pid;
            _scenario.removeProduct(pid);
            _updateSidebarInfo();
            _showSelectionRack(rack);  // refresh
            showToast('Producto eliminado', 'warning');
        });
    });

    panel.classList.add('open');
}

function _showSelectionPicker(picker) {
    const panel = DOM.selectionPanel();
    const body  = DOM.selectionBody();

    body.innerHTML = `
        <div class="sel-header">
            <span class="sel-icon sel-picker-dot" style="background:${picker.color}" aria-hidden="true"></span>
            <span class="sel-title">${picker.name}</span>
        </div>
        <div class="sel-row"><span class="sel-label">Posición</span><span class="sel-value">(${picker.x}, ${picker.y})</span></div>
        <div class="sel-row"><span class="sel-label">ID</span><span class="sel-value">${picker.id}</span></div>
        <div class="sel-row"><span class="sel-label">Color</span>
            <span class="sel-value">
                <span class="sel-color-dot" style="background:${picker.color}" aria-hidden="true"></span>${picker.color}
            </span>
        </div>
        <div class="sel-actions">
            <button class="btn btn--sm btn--danger" id="sel-del-picker-btn">
                <span class="icon icon--sm" aria-hidden="true">delete</span> Eliminar picker
            </button>
        </div>
    `;

    body.querySelector('#sel-del-picker-btn')?.addEventListener('click', () => {
        _scenario.removePicker(picker.id);
        _renderer.selectedElement = null;
        _updateSidebarInfo();
        _hideSelection();
        showToast(`${picker.name} eliminado`, 'warning');
    });

    panel.classList.add('open');
}

function _hideSelection() {
    DOM.selectionPanel().classList.remove('open');
}

// ── Sidebar info ──────────────────────────────────────────────────

function _updateSidebarInfo() {
    if (!_scenario) return;
    const st = _scenario.stats();
    DOM.whId().textContent       = _scenario.name;
    DOM.whSize().textContent     = st.size;
    DOM.whPickers().textContent  = st.pickers;
    DOM.whRacks().textContent    = st.racks;
    DOM.whProducts().textContent = st.products;
}

function _updateCanvasStatus() {
    if (!_scenario) {
        DOM.canvasStatus().textContent = 'Sin escenario cargado';
        return;
    }
    DOM.canvasStatus().textContent = `${_scenario.name}  ·  ${_scenario.width}×${_scenario.height}`;
}

// ── Guardar / Cargar ──────────────────────────────────────────────

function saveScenario() {
    if (!_scenario) { showToast('No hay escenario para guardar.', 'warning'); return; }
    const json = JSON.stringify(_scenario.toJSON(), null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = `${_scenario.name.replace(/\s+/g, '_')}.json`;
    a.click();
    URL.revokeObjectURL(url);
    showToast('Escenario guardado.', 'success');
}

function loadScenario() {
    const input = document.createElement('input');
    input.type  = 'file';
    input.accept = '.json';
    input.addEventListener('change', e => {
        const file = e.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = ev => {
            try {
                const data = JSON.parse(ev.target.result);
                _scenario = Scenario.fromJSON(data);
                _editor.setScenario(_scenario);
                DOM.canvasPlaceholder().style.display = 'none';
                DOM.canvas().style.display            = 'block';
                _updateSidebarInfo();
                _updateCanvasStatus();
                _hideSelection();
                showToast(`Escenario "${_scenario.name}" cargado.`, 'success');
            } catch (err) {
                showToast('Error al leer el archivo JSON.', 'error');
                console.error(err);
            }
        };
        reader.readAsText(file);
    });
    input.click();
}

// ── Keyboard shortcuts ────────────────────────────────────────────

function _onKeyDown(e) {
    // No activar si el foco está en un input/textarea
    if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) return;

    const toolMap = { 's': 'select', 'r': 'rack', 'p': 'product', 'k': 'picker', 'e': 'erase' };
    if (toolMap[e.key]) {
        _setActiveTool(toolMap[e.key]);
        return;
    }

    if (e.key === 'Escape') {
        closeModalNew();
        closeModalProduct();
        _hideSelection();
        _editor?.setMode('select');
        _setActiveTool('select');
        _renderer && (_renderer.selectedElement = null);
    }

    if (e.key === 'Delete' || e.key === 'Backspace') {
        // Eliminar elemento seleccionado
        const sel = _renderer?.selectedElement;
        if (!sel || !_scenario) return;
        if (sel.type === 'rack') {
            _scenario.removeRack(sel.element.id);
            _renderer.selectedElement = null;
            _hideSelection();
            _updateSidebarInfo();
        } else if (sel.type === 'picker') {
            _scenario.removePicker(sel.element.id);
            _renderer.selectedElement = null;
            _hideSelection();
            _updateSidebarInfo();
        }
    }
}

function _setActiveTool(tool) {
    DOM.toolBtns().forEach(b => {
        b.classList.toggle('active', b.dataset.tool === tool);
    });
    _editor?.setMode(tool);
}

// ── Toast ─────────────────────────────────────────────────────────

let _toastTimeout = null;

function showToast(msg, type = 'info') {
    const t = DOM.toast();
    t.textContent  = msg;
    t.className    = `editor-toast editor-toast--${type} editor-toast--show`;
    clearTimeout(_toastTimeout);
    _toastTimeout = setTimeout(() => t.classList.remove('editor-toast--show'), 3000);
}

// ── Arrancar cuando el DOM está listo ─────────────────────────────

document.addEventListener('DOMContentLoaded', initEditorUI);
