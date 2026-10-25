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
    inputProdWeight:() => document.getElementById('input-prod-weight'),
    inputProdZ:     () => document.getElementById('input-prod-z'),
    labelProdCell:  () => document.getElementById('label-prod-cell'),
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

    // Picker controls
    btnPickerAdd:    () => document.getElementById('btn-picker-add'),
    btnPickerRemove: () => document.getElementById('btn-picker-remove'),
    pickersCount:    () => document.getElementById('pickers-count'),
    pickersList:     () => document.getElementById('pickers-list'),
    inputPickerCap:  () => document.getElementById('input-picker-capacity'),

    // Toast
    toast: () => document.getElementById('editor-toast'),

    // Wizard
    wizardSteps:     () => document.querySelectorAll('.wizard-step'),
    wizardStepInds:  () => document.querySelectorAll('.wizard-step-ind'),
    wizardPrevBtn:   () => document.getElementById('btn-wizard-prev'),
    wizardNextBtn:   () => document.getElementById('btn-wizard-next'),
    wizardFinishBtn: () => document.getElementById('btn-wizard-finish'),
    wizardStepNum:   () => document.getElementById('wizard-step-num'),
    wizardStepTitle: () => document.getElementById('wizard-step-title'),
    wizardValidMsg:  () => document.getElementById('wizard-valid-msg'),

    // Tool selects
    doorTipoSelect:    () => document.getElementById('door-tipo-select'),
    aisleSentidoSelect:() => document.getElementById('aisle-sentido-select'),
};

// ── Estado global de la UI ────────────────────────────────────────

let _renderer = null;
let _editor   = null;
let _scenario = null;
let _productTargetRack  = null;
let _productTargetCell  = null;
let _wizardStep         = 0;
let _wizardScenario     = null;

/** Escenario activo: durante el wizard es _wizardScenario; despues es _scenario */
function _activeScenario() { return _wizardScenario || _scenario; }

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

    // Modal nuevo escenario / wizard
    DOM.btnNew().addEventListener('click', () => openModalNew());
    DOM.btnCancelWH().addEventListener('click', () => closeModalNew());
    DOM.btnCreateWH().addEventListener('click', () => createScenario());
    DOM.modalNew().addEventListener('click', e => {
        if (e.target === DOM.modalNew()) closeModalNew();
    });
    // Wizard navigation
    const wizPrev = DOM.wizardPrevBtn();
    const wizNext = DOM.wizardNextBtn();
    const wizFin  = DOM.wizardFinishBtn();
    if (wizPrev) wizPrev.addEventListener('click', () => _onWizardPrev());
    if (wizNext) wizNext.addEventListener('click', () => _onWizardNext());
    if (wizFin)  wizFin.addEventListener('click',  () => _onWizardFinish());

    // Selects de herramientas
    const doorEl = DOM.doorTipoSelect();
    if (doorEl) doorEl.addEventListener('change', () => { if (_editor) _editor._doorTipo = doorEl.value; });
    const aisleEl = DOM.aisleSentidoSelect();
    if (aisleEl) aisleEl.addEventListener('change', () => { if (_editor) _editor._aisleSentido = aisleEl.value; });

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

    // Picker controls
    DOM.btnPickerAdd().addEventListener('click', () => {
        const sc = _activeScenario();
        if (!sc) return;
        const cap = parseFloat(DOM.inputPickerCap().value) || 100;
        const picker = sc.addPicker(cap);
        if (picker) {
            _updateSidebarInfo();
            _updatePickersList();
            showToast(`${picker.name} agregado`, 'info');
        } else {
            showToast('No se pudo agregar el picker.', 'warning');
        }
    });

    DOM.btnPickerRemove().addEventListener('click', () => {
        const sc = _activeScenario();
        if (!sc || sc.pickers.length === 0) return;
        const last = sc.pickers[sc.pickers.length - 1];
        sc.removePicker(last.id);
        if (_renderer.selectedElement?.element?.id === last.id) {
            _renderer.selectedElement = null;
            _hideSelection();
        }
        _updateSidebarInfo();
        _updatePickersList();
        showToast(`${last.name} eliminado`, 'warning');
    });

    // Toggle colapsable de la lista de pickers
    const _pickerListToggle = document.getElementById('btn-pickers-list-toggle');
    if (_pickerListToggle) {
        _pickerListToggle.addEventListener('click', () => {
            const list    = document.getElementById('pickers-list');
            const chevron = _pickerListToggle.querySelector('.pickers-chevron');
            const isOpen  = _pickerListToggle.getAttribute('aria-expanded') === 'true';
            _pickerListToggle.setAttribute('aria-expanded', String(!isOpen));
            list?.classList.toggle('pickers-list--collapsed', isOpen);
            chevron?.classList.toggle('open', !isOpen);
        });
    }

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

// ── Modal: Nuevo Escenario (Wizard) ──────────────────────────────

const WIZARD_STEPS = [
    { title: 'Dimensiones' },
    { title: 'Puertas' },
    { title: 'Zonas de Despacho' },
    { title: 'Racks' },
    { title: 'Pasillos' },
];

function openModalNew() {
    _wizardStep = 0;
    _wizardScenario = null;
    updateGridPreview();
    _showWizardStep(0);
    DOM.modalNew().classList.add('open');
    DOM.inputWHName().focus();
}

function closeModalNew() {
    // Si el wizard tiene un escenario en construcción (pasos 1-4), pedir confirmación
    if (_wizardStep >= 1 && _wizardScenario) {
        _showConfirmModal(
            '¿Cancelar creación?',
            'Se descartarán todos los cambios del escenario en progreso.',
            'Sí, cancelar',
            () => _doCloseModalNew()
        );
        return;
    }
    _doCloseModalNew();
}

function _doCloseModalNew() {
    DOM.modalNew().classList.remove('open');
    _wizardFloatHide();
    _wizardStep = 0;
    if (_wizardScenario) {
        _wizardScenario = null;
        if (!_scenario) {
            const placeholder = DOM.canvasPlaceholder();
            const canvas = DOM.canvas();
            if (placeholder) placeholder.style.display = '';
            if (canvas) canvas.style.display = 'none';
            _editor?.setScenario(null);
        } else {
            _editor?.setScenario(_scenario);
        }
    } else {
        _wizardScenario = null;
    }
}

/**
 * Muestra un modal de confirmación custom (no usa confirm() nativo).
 * @param {string} title       - Título del modal
 * @param {string} message     - Mensaje descriptivo
 * @param {string} confirmText - Texto del botón de confirmar
 * @param {Function} onConfirm - Callback al confirmar
 */
function _showConfirmModal(title, message, confirmText, onConfirm) {
    // Reusar o crear overlay
    let overlay = document.getElementById('confirm-modal-overlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'confirm-modal-overlay';
        overlay.style.cssText = [
            'position:fixed', 'inset:0', 'z-index:9999',
            'display:flex', 'align-items:center', 'justify-content:center',
            'background:rgba(0,0,0,0.55)', 'backdrop-filter:blur(4px)'
        ].join(';');
        document.body.appendChild(overlay);
    }
    overlay.innerHTML = `
        <div style="
            background:var(--color-surface,#1c1f2e);
            border:1px solid rgba(255,255,255,0.08);
            border-radius:14px;
            padding:28px 32px;
            max-width:380px;
            width:90%;
            box-shadow:0 24px 48px rgba(0,0,0,0.5);
            font-family:'JetBrains Mono',monospace;
        ">
            <h3 style="margin:0 0 10px;font-size:1rem;color:var(--color-text,#e2e8f0)">${title}</h3>
            <p  style="margin:0 0 24px;font-size:.82rem;color:var(--color-text-muted,#94a3b8);line-height:1.5">${message}</p>
            <div style="display:flex;gap:10px;justify-content:flex-end">
                <button id="confirm-modal-cancel" class="btn btn--ghost btn--sm">Volver</button>
                <button id="confirm-modal-ok"     class="btn btn--danger btn--sm">${confirmText}</button>
            </div>
        </div>`;
    overlay.style.display = 'flex';

    const close = () => { overlay.style.display = 'none'; };
    overlay.querySelector('#confirm-modal-cancel').onclick = close;
    overlay.querySelector('#confirm-modal-ok').onclick = () => { close(); onConfirm(); };
    // Click fuera del cuadro también cierra
    overlay.onclick = (e) => { if (e.target === overlay) close(); };
}

function _showWizardStep(step) {
    _wizardStep = step;

    if (step === 0) {
        // Paso 0: mostrar modal normal, ocultar panel flotante
        _wizardFloatHide();
        DOM.modalNew().classList.add('open');
    } else {
        // Pasos 1-4: cerrar modal y usar panel flotante no-bloqueante
        DOM.modalNew().classList.remove('open');
        _wizardFloatShow(step);
    }

    // Actualizar indicadores dentro del modal (para cuando está visible)
    DOM.wizardSteps().forEach((el, i) => el.classList.toggle('active', i === step));
    DOM.wizardStepInds().forEach((el, i) => {
        el.classList.toggle('active', i === step);
        el.classList.toggle('done', i < step);
    });
    const numEl   = DOM.wizardStepNum();
    const titleEl = DOM.wizardStepTitle();
    if (numEl)   numEl.textContent   = (step + 1) + '/5';
    if (titleEl) titleEl.textContent = WIZARD_STEPS[step].title;

    const prevBtn   = DOM.wizardPrevBtn();
    const nextBtn   = DOM.wizardNextBtn();
    const finishBtn = DOM.wizardFinishBtn();
    if (prevBtn)   prevBtn.disabled = (step === 0);
    if (nextBtn)   nextBtn.style.display   = step < 4 ? '' : 'none';
    if (finishBtn) finishBtn.style.display = step === 4 ? '' : 'none';

    _updateWizardValidMsg();

    if (step >= 1 && _wizardScenario) {
        const toolMap = { 1: 'door', 2: 'dispatch', 3: 'rack', 4: 'aisle' };
        if (toolMap[step]) _setActiveTool(toolMap[step]);
    }
}

// ─── Panel flotante del wizard (pasos 1-4) ────────────────────────

const WIZARD_HINTS = {
    1: { icon: 'garage_door', color: '#a78bfa', text: 'Haz click en el <strong>borde</strong> del warehouse para colocar puertas. Necesitas ≥ 1.', tip: 'Cambia el tipo (IN/OUT/IO) en la barra superior.' },
    2: { icon: 'home_storage',  color: '#4fc97f', text: 'Arrastra en el canvas para colocar una <strong>Zona de Despacho</strong>. Necesitas ≥ 1.', tip: 'Cada puerta debe tener exactamente una zona de despacho frente a ella.' },
    3: { icon: 'shelves',    color: '#4f9cf9', text: 'Haz click o arrastra para colocar <strong>Racks</strong>. Necesitas ≥ 1.', tip: 'Exactamente una dimensión debe ser igual a 2 (ancho o alto).' },
    4: { icon: 'route',      color: '#fbbf24', text: 'Opcional: arrastra para definir <strong>Pasillos</strong> con dirección.', tip: 'Si omitís, todas las celdas transitables serán AMBOS.' },
};

let _wizardFloatEl = null;

function _wizardFloatShow(step) {
    const hint = WIZARD_HINTS[step];
    if (!hint) return;

    if (!_wizardFloatEl) {
        _wizardFloatEl = document.createElement('div');
        _wizardFloatEl.id = 'wizard-float';
        _wizardFloatEl.innerHTML = `
            <div class="wf-header">
                <div class="wf-steps" id="wf-step-dots"></div>
                <span class="wf-title" id="wf-title"></span>
                <button class="btn btn--ghost wf-cancel" id="wf-cancel" title="Cancelar wizard">&#x2715;</button>
            </div>
            <div class="wf-body">
                <span class="wf-icon" id="wf-icon"></span>
                <div class="wf-text" id="wf-text"></div>
            </div>
            <div class="wf-tip" id="wf-tip"></div>
            <div class="wf-valid" id="wf-valid"></div>
            <div class="wf-nav">
                <button class="btn btn--ghost btn--sm" id="wf-prev">&#x2190; Anterior</button>
                <button class="btn btn--primary btn--sm" id="wf-next">Siguiente &#x2192;</button>
                <button class="btn btn--primary btn--sm" id="wf-finish" style="display:none">&#x2713; Crear escenario</button>
            </div>`;
        document.body.appendChild(_wizardFloatEl);

        document.getElementById('wf-cancel').addEventListener('click', () => closeModalNew());
        document.getElementById('wf-prev').addEventListener('click', () => _onWizardPrev());
        document.getElementById('wf-next').addEventListener('click', () => _onWizardNext());
        document.getElementById('wf-finish').addEventListener('click', () => _onWizardFinish());
    }

    // Dots
    const dots = document.getElementById('wf-step-dots');
    dots.innerHTML = WIZARD_STEPS.map((s, i) =>
        `<span class="wf-dot ${i < step ? 'done' : i === step ? 'active' : ''}">${i+1}</span>`
    ).join('<span class="wf-dot-line"></span>');

    document.getElementById('wf-title').textContent  = WIZARD_STEPS[step].title;
    document.getElementById('wf-icon').innerHTML     = `<span class="icon icon--20 icon--filled" style="color:${hint.color}">${hint.icon}</span>`;
    document.getElementById('wf-text').innerHTML     = hint.text;
    document.getElementById('wf-tip').textContent    = hint.tip;

    // Nav
    document.getElementById('wf-prev').disabled    = (step <= 1);
    document.getElementById('wf-next').style.display   = step < 4 ? '' : 'none';
    document.getElementById('wf-finish').style.display = step === 4 ? '' : 'none';

    _wizardFloatEl.style.display = 'flex';
    _wizardFloatValidMsg();
}

function _wizardFloatHide() {
    if (_wizardFloatEl) _wizardFloatEl.style.display = 'none';
}

function _wizardFloatValidMsg() {
    const el = document.getElementById('wf-valid');
    if (!el || !_wizardScenario) { if (el) { el.textContent = ''; el.style.display = 'none'; } return; }
    // Solo mostrar en el último paso del float (Pasillos, step 4)
    if (_wizardStep < 4) { el.textContent = ''; el.style.display = 'none'; return; }
    const missing = _wizardScenario.getMissingRequirements(false);
    if (missing.length === 0) {
        el.textContent = ''; el.style.display = 'none';
    } else {
        el.innerHTML = '<span style="color:#f97316">&#x26A0;</span> Falta: ' + missing.join(', ');
        el.style.display = '';
    }
}

function _updateWizardValidMsg() {
    const msg = DOM.wizardValidMsg();
    if (!msg || !_wizardScenario) { if (msg) { msg.textContent = ''; msg.style.display = 'none'; } return; }
    // Solo mostrar en el último paso del modal (no tiene sentido en pasos intermedios)
    if (_wizardStep < 4) { msg.textContent = ''; msg.style.display = 'none'; _wizardFloatValidMsg(); return; }
    const missing = _wizardScenario.getMissingRequirements(false);
    if (missing.length === 0) {
        msg.textContent = ''; msg.style.display = 'none';
    } else {
        msg.textContent = 'Falta: ' + missing.join(', ') + '.';
        msg.style.display = '';
    }
    _wizardFloatValidMsg();
}

function _onWizardNext() {
    if (_wizardStep === 0) {
        const name   = DOM.inputWHName().value.trim() || 'Escenario 1';
        const width  = parseInt(DOM.inputWHWidth().value)  || 20;
        const height = parseInt(DOM.inputWHHeight().value) || 15;
        _wizardScenario = new Scenario({ name, width, height });
        _editor.setScenario(_wizardScenario);
        DOM.canvasPlaceholder().style.display = 'none';
        DOM.canvas().style.display = 'block';
    }
    // Validar requisito mínimo del paso actual antes de avanzar
    if (_wizardStep === 1 && _wizardScenario && _wizardScenario.doors.length === 0) {
        showToast('Colocá al menos 1 puerta antes de continuar.', 'warning');
        return;
    }
    if (_wizardStep === 2 && _wizardScenario) {
        const s = _wizardScenario;
        if (s.dispatchZones.length === 0) {
            showToast('Colocá al menos 1 zona de despacho antes de continuar.', 'warning');
            return;
        }
        // Cada puerta debe tener su zona de despacho
        const doorsWithoutZone = s.doors.filter(d => !s.dispatchZones.some(z => z.puertaId === d.id));
        if (doorsWithoutZone.length > 0) {
            showToast('Falta zona de despacho para: ' + doorsWithoutZone.map(d => d.id).join(', ') + '.', 'warning');
            return;
        }
    }
    if (_wizardStep === 3 && _wizardScenario && _wizardScenario.racks.length === 0) {
        showToast('Colocá al menos 1 rack antes de continuar.', 'warning');
        return;
    }
    if (_wizardStep < 4) _showWizardStep(_wizardStep + 1);
}

function _onWizardPrev() {
    if (_wizardStep > 0) _showWizardStep(_wizardStep - 1);
}

function _onWizardFinish() {
    if (!_wizardScenario) return;
    const s = _wizardScenario;
    const missing = s.getMissingRequirements(false); // pickers se agregan a continuación
    if (missing.length > 0) {
        _updateWizardValidMsg();
        _wizardFloatValidMsg();
        showToast('Faltan: ' + missing.join(', ') + '.', 'warning');
        return;
    }
    const picker = s.addPicker(100);
    if (!picker) showToast('Advertencia: no se pudo ubicar un picker automaticamente.', 'warning');

    _scenario = s;
    _wizardScenario = null;
    _editor.setScenario(_scenario);
    _wizardFloatHide();
    closeModalNew();
    _updateSidebarInfo();
    _updatePickersList();
    _updateCanvasStatus();
    _setActiveTool('select');
    showToast('Escenario "' + s.name + '" creado (' + s.width + 'x' + s.height + ')', 'success');
}

function updateGridPreview() {
    const w  = parseInt(DOM.inputWHWidth().value)  || 20;
    const h  = parseInt(DOM.inputWHHeight().value) || 15;
    const pg = DOM.previewGrid();
    DOM.labelWHWidth().textContent  = w;
    DOM.labelWHHeight().textContent = h;

    // Ajustar al contenedor (ancho disponible ~360px, alto ~130px)
    const container = pg.parentElement;
    const availW = (container?.clientWidth  || 360) - 8;
    const availH = 130;
    const cellPx = Math.max(2, Math.min(12, Math.floor(Math.min(availW / w, availH / h))));

    pg.style.width   = (w * cellPx) + 'px';
    pg.style.height  = (h * cellPx) + 'px';
    pg.style.setProperty('--preview-cell-px', cellPx + 'px');
    pg.innerHTML = ''; // sin divs individuales
}

function createScenario() {
    // createScenario ahora delega al wizard; se llama desde btn-create-wh (oculto)
    _onWizardFinish();
}

// ── Modal: Agregar Producto ───────────────────────────────────────

function openModalProduct(rack, targetCell = null) {
    _productTargetRack = rack;
    _productTargetCell = targetCell;

    DOM.modalProdTitle().textContent = `Agregar producto → ${rack.id}`;
    DOM.inputProdName().value  = '';
    DOM.inputProdSKU().value   = '';
    DOM.inputProdQty().value   = '1';
    DOM.inputProdWeight().value = '1.0';

    if (targetCell) {
        // Mostrar celda y calcular el siguiente nivel Z libre
        DOM.labelProdCell().textContent = `Celda: (${targetCell.x}, ${targetCell.y})`;
        const existingInCell = rack.products.filter(p => p.x === targetCell.x && p.y === targetCell.y);
        DOM.inputProdZ().value = existingInCell.length + 1;
    } else {
        // Fallback: primera celda del rack
        DOM.labelProdCell().textContent = `Celda: (${rack.x}, ${rack.y})`;
        const existingInCell = rack.products.filter(p => p.x === rack.x && p.y === rack.y);
        DOM.inputProdZ().value = existingInCell.length + 1;
    }

    DOM.modalProduct().classList.add('open');
    DOM.inputProdName().focus();
}

function closeModalProduct() {
    _productTargetRack = null;
    _productTargetCell = null;
    DOM.modalProduct().classList.remove('open');
}

function submitProduct() {
    if (!_productTargetRack) return;

    const name   = DOM.inputProdName().value.trim();
    const sku    = DOM.inputProdSKU().value.trim();
    const qty    = parseInt(DOM.inputProdQty().value)  || 1;
    const weight = parseFloat(DOM.inputProdWeight().value);
    const zVal   = parseInt(DOM.inputProdZ().value)    || 1;

    if (!name) {
        DOM.inputProdName().classList.add('input--error');
        DOM.inputProdName().focus();
        return;
    }
    if (isNaN(weight) || weight <= 0) {
        DOM.inputProdWeight().classList.add('input--error');
        DOM.inputProdWeight().focus();
        return;
    }
    if (zVal < 1) {
        DOM.inputProdZ().classList.add('input--error');
        DOM.inputProdZ().focus();
        return;
    }
    DOM.inputProdName().classList.remove('input--error');
    DOM.inputProdWeight().classList.remove('input--error');
    DOM.inputProdZ().classList.remove('input--error');

    const targetX = _productTargetCell ? _productTargetCell.x : _productTargetRack.x;
    const targetY = _productTargetCell ? _productTargetCell.y : _productTargetRack.y;

    const product = _activeScenario().addProduct(_productTargetRack.id, {
        name,
        sku: sku || name.toUpperCase().replace(/\s/g, '_'),
        quantity: qty,
        pesoKg: weight,
        x: targetX,
        y: targetY,
        z: zVal,
    });

    if (!product) { showToast('Error al agregar el producto.', 'error'); return; }

    // addProduct devuelve {error} si el slot Z está ocupado
    if (product.error) {
        DOM.inputProdZ().classList.add('input--error');
        DOM.inputProdZ().focus();
        showToast(product.error, 'warning');
        return;
    }

    const rack = _productTargetRack;
    _showSelectionRack(rack);
    closeModalProduct();
    _updateSidebarInfo();
    showToast(`Producto "${name}" (${weight} kg) agregado en (${targetX}, ${targetY}) Z:${zVal}`, 'success');
}

// ── Editor events ─────────────────────────────────────────────────

function _onEditorEvent(event, data) {
    switch (event) {
        case 'add-rack':
            _updateSidebarInfo();
            showToast(`Rack ${data.id} colocado`, 'info');
            _showSelectionRack(data);
            if (_wizardScenario) _updateWizardValidMsg();
            break;

        case 'remove-rack':
            _updateSidebarInfo();
            showToast(`Rack ${data.id} eliminado`, 'warning');
            _hideSelection();
            if (_wizardScenario) _updateWizardValidMsg();
            break;

        case 'move-rack':
            _updateSidebarInfo();
            showToast(`Rack ${data.id} movido`, 'info');
            _showSelectionRack(data);
            break;

        case 'add-door':
            _updateSidebarInfo();
            showToast(`Puerta ${data.id} colocada (${data.tipo})`, 'info');
            _showSelectionDoor(data);
            if (_wizardScenario) _updateWizardValidMsg();
            break;

        case 'remove-door':
            _updateSidebarInfo();
            showToast(`Puerta ${data.id} eliminada`, 'warning');
            _hideSelection();
            if (_wizardScenario) _updateWizardValidMsg();
            break;

        case 'select-door':
            _showSelectionDoor(data);
            break;

        case 'add-dispatch':
            _updateSidebarInfo();
            showToast(`Zona de despacho ${data.id} colocada`, 'info');
            _showSelectionDispatch(data);
            if (_wizardScenario) _updateWizardValidMsg();
            break;

        case 'remove-dispatch':
            _updateSidebarInfo();
            showToast(`Zona de despacho ${data.id} eliminada`, 'warning');
            _hideSelection();
            if (_wizardScenario) _updateWizardValidMsg();
            break;

        case 'select-dispatch':
            _showSelectionDispatch(data);
            break;

        case 'add-aisle':
            _updateSidebarInfo();
            showToast(`Pasillo ${data.id} definido (${data.sentido})`, 'info');
            _showSelectionAisle(data);
            break;

        case 'remove-aisle':
            _updateSidebarInfo();
            _hideSelection();
            break;

        case 'select-aisle':
            _showSelectionAisle(data);
            break;

        case 'remove-picker':
            _updateSidebarInfo();
            _updatePickersList();
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

        case 'open-product-form': {
            // data puede ser {rack, cell} (clic en canvas) o directamente un rack (botón lateral)
            const isRichData = data && data.rack;
            openModalProduct(isRichData ? data.rack : data, isRichData ? data.cell : null);
            break;
        }

        case 'error':
            showToast(data, 'error');
            break;

        case 'accessibility-warning':
            showToast(data, 'warning');
            break;

        case 'hint':
            showToast(data, 'info');
            break;

        case 'move-rack':
            _updateSidebarInfo();
            showToast(`Rack ${data.id} movido`, 'info');
            break;

        case 'move-picker':
            _updateSidebarInfo();
            _updatePickersList();
            showToast(`${data.name} movido a (${data.x},${data.y})`, 'info');
            break;

        case 'move-dispatch':
            _updateSidebarInfo();
            showToast(`Zona ${data.id} movida`, 'info');
            break;

        case 'move-door':
            _updateSidebarInfo();
            showToast(`Puerta ${data.id} movida a (${data.x},${data.y})`, 'info');
            break;
    }
}

// ── Panel de selección ────────────────────────────────────────────

function _showSelectionRack(rack, highlightCell = null) {
    const panel = DOM.selectionPanel();
    const body  = DOM.selectionBody();

    // Ordenar productos por celda y luego por Z
    const sorted = [...rack.products].sort((a, b) =>
        a.x !== b.x ? a.x - b.x : a.y !== b.y ? a.y - b.y : a.z - b.z
    );

    const chips = sorted.map(p => {
        const isActive = highlightCell && p.x === highlightCell.x && p.y === highlightCell.y;
        return `
        <div class="prod-chip${isActive ? ' prod-chip--active' : ''}" data-px="${p.x}" data-py="${p.y}">
            <span class="prod-chip__zbadge" title="Nivel Z">Z${p.z}</span>
            <div class="prod-chip__body">
                <span class="prod-chip__name">${p.name}</span>
                <span class="prod-chip__meta">${p.sku} &middot; ${p.pesoKg}&thinsp;kg &middot; &times;${p.quantity}</span>
            </div>
            <span class="prod-chip__cell" title="Celda">(${p.x},${p.y})</span>
            <button class="prod-chip__del" data-pid="${p.id}" title="Eliminar" aria-label="Eliminar ${p.name}">
                <span class="icon icon--sm" aria-hidden="true">close</span>
            </button>
        </div>`;
    }).join('');

    const emptyMsg = rack.products.length === 0
        ? '<p class="empty-msg" style="margin:4px 0 0">Sin productos.</p>'
        : '';

    body.innerHTML = `
        <div class="sel-header">
            <span class="sel-icon" aria-hidden="true"><span class="icon icon--18 icon--filled">shelves</span></span>
            <span class="sel-title">${rack.id}</span>
        </div>
        <div class="sel-row"><span class="sel-label">Posición</span><span class="sel-value">(${rack.x}, ${rack.y})</span></div>
        <div class="sel-row"><span class="sel-label">Tamaño</span><span class="sel-value">${rack.width}×${rack.height} celdas</span></div>
        <div class="sel-row"><span class="sel-label">Productos</span><span class="sel-value">${rack.products.length}</span></div>
        <div class="sel-products">${chips}${emptyMsg}</div>
        <div class="sel-actions">
            <button class="btn btn--sm btn--ghost" id="sel-add-product-btn">
                <span class="icon icon--sm" aria-hidden="true">add</span> Producto
            </button>
            <button class="btn btn--sm btn--ghost" id="sel-rotate-rack-btn" title="Rotar rack">
                <span class="icon icon--sm" aria-hidden="true">rotate_right</span> Rotar
            </button>
            <button class="btn btn--sm btn--danger" id="sel-del-rack-btn">
                <span class="icon icon--sm" aria-hidden="true">delete</span> Eliminar rack
            </button>
        </div>
    `;

    body.querySelector('#sel-add-product-btn')?.addEventListener('click', () => openModalProduct(rack));
    body.querySelector('#sel-rotate-rack-btn')?.addEventListener('click', () => {
        const ok = _activeScenario().rotateRack(rack.id);
        if (ok) {
            _showSelectionRack(rack);
            showToast(`Rack ${rack.id} rotado`, 'info');
        } else {
            showToast('No se puede rotar: area ocupada o restriccion de dimension.', 'warning');
        }
    });
    body.querySelector('#sel-del-rack-btn')?.addEventListener('click', () => {
        _activeScenario().removeRack(rack.id);
        _renderer.selectedElement = null;
        _updateSidebarInfo();
        _hideSelection();
        showToast(`Rack ${rack.id} eliminado`, 'warning');
    });

    body.querySelectorAll('.prod-chip__del').forEach(btn => {
        btn.addEventListener('click', () => {
            const pid = btn.dataset.pid;
            _activeScenario().removeProduct(pid);
            _updateSidebarInfo();
            _showSelectionRack(rack);
            showToast('Producto eliminado', 'warning');
        });
    });

    // Hover sobre chips → resaltar celda en el canvas
    body.querySelectorAll('.prod-chip').forEach(chip => {
        const cx = parseInt(chip.dataset.px);
        const cy = parseInt(chip.dataset.py);
        chip.addEventListener('mouseenter', () => {
            if (_renderer) _renderer.hoverCell = { x: cx, y: cy };
        });
        chip.addEventListener('mouseleave', () => {
            if (_renderer) _renderer.hoverCell = null;
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
        <div class="sel-row">
            <span class="sel-label">Color</span>
            <span class="sel-value">
                <span class="sel-color-dot" style="background:${picker.color}" aria-hidden="true"></span>${picker.color}
            </span>
        </div>
        <div class="sel-row" style="align-items:center;gap:8px">
            <span class="sel-label">Capacidad (kg)</span>
            <input class="form-input form-input--num" type="number" id="sel-picker-cap"
                   min="1" max="9999" value="${picker.capacidadKg}"
                   style="width:72px;padding:3px 6px;font-size:.8rem">
            <button class="btn btn--sm btn--ghost" id="sel-picker-cap-btn" title="Aplicar">
                <span class="icon icon--sm" aria-hidden="true">check</span>
            </button>
        </div>
        <div class="sel-actions">
            <button class="btn btn--sm btn--danger" id="sel-del-picker-btn">
                <span class="icon icon--sm" aria-hidden="true">delete</span> Eliminar picker
            </button>
        </div>
    `;

    body.querySelector('#sel-picker-cap-btn')?.addEventListener('click', () => {
        const val = parseFloat(body.querySelector('#sel-picker-cap').value);
        if (!val || val < 1) { showToast('Capacidad inválida (mínimo 1 kg).', 'warning'); return; }
        picker.capacidadKg = val;
        _updateSidebarInfo();
        showToast(`${picker.name}: capacidad actualizada a ${val} kg`, 'info');
    });

    // Aplicar también con Enter en el input
    body.querySelector('#sel-picker-cap')?.addEventListener('keydown', e => {
        if (e.key === 'Enter') body.querySelector('#sel-picker-cap-btn').click();
    });

    body.querySelector('#sel-del-picker-btn')?.addEventListener('click', () => {
        _activeScenario().removePicker(picker.id);
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

function _showSelectionDoor(door) {
    const panel = DOM.selectionPanel();
    const body  = DOM.selectionBody();
    const doorColors = { INBOUND: '#22c55e', OUTBOUND: '#f97316', AMBOS: '#a78bfa' };
    const c = doorColors[door.tipo] || '#a78bfa';
    body.innerHTML = `
        <div class="sel-header">
            <span class="sel-icon" aria-hidden="true" style="color:${c}"><span class="icon icon--18 icon--filled">garage_door</span></span>
            <span class="sel-title">${door.id}</span>
        </div>
        <div class="sel-row"><span class="sel-label">Posición</span><span class="sel-value">(${door.x}, ${door.y})</span></div>
        <div class="sel-row">
            <span class="sel-label">Tipo</span>
            <select class="sel-value" id="sel-door-tipo" style="color:${c}">
                <option value="AMBOS"   ${door.tipo==='AMBOS'   ?'selected':''}>IO (ambas)</option>
                <option value="INBOUND" ${door.tipo==='INBOUND' ?'selected':''}>IN (entrada)</option>
                <option value="OUTBOUND"${door.tipo==='OUTBOUND'?'selected':''}>OUT (salida)</option>
            </select>
        </div>
        <div class="sel-actions">
            <button class="btn btn--sm btn--danger" id="sel-del-door-btn">
                <span class="icon icon--sm" aria-hidden="true">delete</span> Eliminar puerta
            </button>
        </div>
    `;
    body.querySelector('#sel-door-tipo')?.addEventListener('change', e => {
        door.tipo = e.target.value;
    });
    body.querySelector('#sel-del-door-btn')?.addEventListener('click', () => {
        _activeScenario().removeDoor(door.id);
        _renderer.selectedElement = null;
        _updateSidebarInfo();
        _hideSelection();
        showToast(`Puerta ${door.id} eliminada`, 'warning');
    });
    panel.classList.add('open');
}

function _showSelectionDispatch(dz) {
    const panel = DOM.selectionPanel();
    const body  = DOM.selectionBody();
    const doors = _activeScenario()?.doors || [];
    const doorOpts = doors.map(d =>
        `<option value="${d.id}" ${dz.puertaId === d.id ? 'selected' : ''}>${d.id} (${d.tipo})</option>`
    ).join('');
    body.innerHTML = `
        <div class="sel-header">
            <span class="sel-icon" aria-hidden="true"><span class="icon icon--18 icon--filled">package_2</span></span>
            <span class="sel-title">${dz.id}</span>
        </div>
        <div class="sel-row"><span class="sel-label">Posición</span><span class="sel-value">(${dz.x}, ${dz.y})</span></div>
        <div class="sel-row"><span class="sel-label">Tamaño</span><span class="sel-value">${dz.width}×${dz.height} celdas</span></div>
        <div class="sel-row">
            <span class="sel-label">Puerta</span>
            <select class="sel-value" id="sel-dz-door">
                <option value="">— Sin asignar —</option>
                ${doorOpts}
            </select>
        </div>
        <div class="sel-actions">
            <button class="btn btn--sm btn--danger" id="sel-del-dz-btn">
                <span class="icon icon--sm" aria-hidden="true">delete</span> Eliminar zona
            </button>
        </div>
    `;
    body.querySelector('#sel-dz-door')?.addEventListener('change', e => {
        const newId = e.target.value || null;
        const sc = _activeScenario();
        // Verificar unicidad: una puerta no puede estar asignada a más de una zona
        if (newId && sc && sc.dispatchZones.some(z => z.id !== dz.id && z.puertaId === newId)) {
            showToast('Esa puerta ya está asignada a otra zona de despacho.', 'error');
            e.target.value = dz.puertaId || ''; // revertir el selector
            return;
        }
        dz.puertaId = newId;
    });
    body.querySelector('#sel-del-dz-btn')?.addEventListener('click', () => {
        _activeScenario().removeDispatchZone(dz.id);
        _renderer.selectedElement = null;
        _updateSidebarInfo();
        _hideSelection();
        showToast(`Zona ${dz.id} eliminada`, 'warning');
    });
    panel.classList.add('open');
}

function _showSelectionAisle(aisle) {
    const panel = DOM.selectionPanel();
    const body  = DOM.selectionBody();
    body.innerHTML = `
        <div class="sel-header">
            <span class="sel-icon" aria-hidden="true"><span class="icon icon--18 icon--filled">route</span></span>
            <span class="sel-title">${aisle.id}</span>
        </div>
        <div class="sel-row"><span class="sel-label">Posición</span><span class="sel-value">(${aisle.x}, ${aisle.y})</span></div>
        <div class="sel-row"><span class="sel-label">Tamaño</span><span class="sel-value">${aisle.width}×${aisle.height} celdas</span></div>
        <div class="sel-row">
            <span class="sel-label">Sentido</span>
            <select class="sel-value" id="sel-aisle-sentido">
                <option value="AMBOS" ${aisle.sentido==='AMBOS'?'selected':''}>↕ AMBOS</option>
                <option value="N"     ${aisle.sentido==='N'    ?'selected':''}>↑ Norte</option>
                <option value="S"     ${aisle.sentido==='S'    ?'selected':''}>↓ Sur</option>
                <option value="E"     ${aisle.sentido==='E'    ?'selected':''}>→ Este</option>
                <option value="O"     ${aisle.sentido==='O'    ?'selected':''}>← Oeste</option>
            </select>
        </div>
        <div class="sel-actions">
            <button class="btn btn--sm btn--danger" id="sel-del-aisle-btn">
                <span class="icon icon--sm" aria-hidden="true">delete</span> Eliminar pasillo
            </button>
        </div>
    `;
    body.querySelector('#sel-aisle-sentido')?.addEventListener('change', e => {
        aisle.sentido = e.target.value;
    });
    body.querySelector('#sel-del-aisle-btn')?.addEventListener('click', () => {
        _activeScenario().removeAisle(aisle.id);
        _renderer.selectedElement = null;
        _updateSidebarInfo();
        _hideSelection();
        showToast(`Pasillo ${aisle.id} eliminado`, 'warning');
    });
    panel.classList.add('open');
}

// ── Sidebar info ──────────────────────────────────────────────────

function _updateSidebarInfo() {
    const sc = _activeScenario();
    if (!sc) return;
    const st = sc.stats();
    DOM.whId().textContent       = sc.name;
    DOM.whSize().textContent     = st.size;
    DOM.whPickers().textContent  = st.pickers;
    DOM.whRacks().textContent    = st.racks;
    DOM.whProducts().textContent = st.products;

    DOM.btnPickerAdd().disabled    = false;
    DOM.btnPickerRemove().disabled = sc.pickers.length === 0;
    DOM.pickersCount()?.textContent != null && (DOM.pickersCount().textContent = sc.pickers.length);
    _updatePickersList();
}

/**
 * Renderiza la lista compacta de pickers dentro del panel de pickers.
 */
function _updatePickersList() {
    const sc = _activeScenario();
    if (!sc) return;
    const list = DOM.pickersList();
    if (sc.pickers.length === 0) {
        list.innerHTML = '<div class="pickers-list-scroll"><p class="empty-msg">Sin pickers asignados.</p></div>';
        return;
    }
    const chips = sc.pickers.map(pk => `
        <div class="picker-chip">
            <span class="picker-chip__dot" style="background:${pk.color}"></span>
            <span class="picker-chip__name">${pk.name}</span>
            <span class="picker-chip__meta">(${pk.x},${pk.y})·${pk.capacidadKg}kg</span>
        </div>
    `).join('');
    list.innerHTML = `<div class="pickers-list-scroll">${chips}</div>`;
}

function _updateCanvasStatus() {
    const sc = _activeScenario();
    if (!sc) {
        DOM.canvasStatus().textContent = 'Sin escenario cargado';
        return;
    }
    DOM.canvasStatus().textContent = `${sc.name}  ·  ${sc.width}×${sc.height}`;
    DOM.btnPickerAdd().disabled    = false;
    DOM.btnPickerRemove().disabled = sc.pickers.length === 0;
    DOM.pickersCount()?.textContent != null && (DOM.pickersCount().textContent = sc.pickers.length);
    _updatePickersList();
}

// ── Guardar / Cargar ──────────────────────────────────────────────

function saveScenario() {
    if (!_scenario) { showToast('No hay escenario para guardar.', 'warning'); return; }
    const missing = _scenario.getMissingRequirements(true);
    if (missing.length > 0) {
        showToast('Faltan: ' + missing.join(', ') + '.', 'warning');
        return;
    }
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

    const toolMap = { 's': 'select', 'r': 'rack', 'p': 'product', 'e': 'erase', 'd': 'door', 'z': 'dispatch', 'a': 'aisle', 'm': 'move-rack' };
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
        const sel = _renderer?.selectedElement;
        const sc  = _activeScenario();
        if (!sel || !sc) return;
        const id = sel.element.id;
        if      (sel.type === 'rack')     { sc.removeRack(id); }
        else if (sel.type === 'picker')   { sc.removePicker(id); _updatePickersList(); }
        else if (sel.type === 'door')     { sc.removeDoor(id); }
        else if (sel.type === 'dispatch') { sc.removeDispatchZone(id); }
        else if (sel.type === 'aisle')    { sc.removeAisle(id); }
        _renderer.selectedElement = null;
        _hideSelection();
        _updateSidebarInfo();
        if (_wizardScenario) _updateWizardValidMsg();
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

