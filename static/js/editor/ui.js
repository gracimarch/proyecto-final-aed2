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
    btnNew:      () => document.getElementById('btn-new-scenario'),
    btnSave:     () => document.getElementById('btn-save-scenario'),
    btnLoad:     () => document.getElementById('btn-load-scenario'),
    btnGenerate: () => document.getElementById('btn-generate-scenario'),

    // Modal generar escenario automático
    modalGenerate:        () => document.getElementById('modal-generate-scenario'),
    inputGenName:         () => document.getElementById('input-gen-name'),
    inputGenRacks:        () => document.getElementById('input-gen-racks'),
    inputGenAisles:       () => document.getElementById('input-gen-aisles'),
    inputGenProducts:     () => document.getElementById('input-gen-products'),
    selectGenDistribution:() => document.getElementById('select-gen-distribution'),
    selectGenOrientation: () => document.getElementById('select-gen-orientation'),
    inputGenWidth:        () => document.getElementById('input-gen-width'),
    inputGenHeight:       () => document.getElementById('input-gen-height'),
    inputGenOrders:       () => document.getElementById('input-gen-orders'),
    inputGenMaxProducts:  () => document.getElementById('input-gen-max-products'),
    inputGenWaveOrders:   () => document.getElementById('input-gen-wave-orders'),
    inputGenWaveProducts: () => document.getElementById('input-gen-wave-products'),
    inputGenDoors:        () => document.getElementById('input-gen-doors'),
    inputGenPickers:      () => document.getElementById('input-gen-pickers'),
    inputGenSeed:         () => document.getElementById('input-gen-seed'),
    generateError:        () => document.getElementById('generate-error'),
    btnConfirmGenerate:   () => document.getElementById('btn-confirm-generate'),
    btnCancelGenerate:    () => document.getElementById('btn-cancel-generate'),

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
    inputProdQty:   () => document.getElementById('input-prod-qty'),
    inputProdWeight:() => document.getElementById('input-prod-weight'),
    inputProdZ:     () => document.getElementById('input-prod-z'),
    labelProdCell:  () => document.getElementById('label-prod-cell'),
    labelProdId:    () => document.getElementById('label-prod-id'),
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

    // Modal pedido
    modalOrder:         () => document.getElementById('modal-order'),
    inputOrderPriority: () => document.getElementById('input-order-priority'),
    orderItemsList:     () => document.getElementById('order-items-list'),
    selectOrderProduct: () => document.getElementById('select-order-product'),
    inputOrderItemQty:  () => document.getElementById('input-order-item-qty'),
    btnOrderAddItem:    () => document.getElementById('btn-order-add-item'),
    btnConfirmOrder:    () => document.getElementById('btn-confirm-order'),
    btnCancelOrder:     () => document.getElementById('btn-cancel-order'),
    orderNoProductsMsg: () => document.getElementById('order-no-products-msg'),
    ordersList:         () => document.getElementById('orders-list'),
};

/**
 * True si el click fue directamente sobre el fondo oscuro del modal (no
 * sobre su contenido). Evita que al arrastrar texto desde un input y soltar
 * fuera del contenido se dispare un click en el contenedor y cierre el modal.
 */
function _clickEnOverlay(e, modal) {
    if (!modal) return false;
    const overlay = modal.querySelector('.modal__overlay');
    return !!overlay && e.target === overlay;
}

// ── Estado global de la UI ────────────────────────────────────────

let _renderer = null;
let _editor   = null;
let _scenario = null;
let _productTargetRack  = null;
let _productTargetCell  = null;
let _wizardStep         = 0;
let _wizardScenario     = null;

/** Items temporales del pedido en construcción (array de {productoId, cantidad}). */
let _orderDraftItems = [];

/**
 * ID del pedido que se está editando, o null si se está creando uno nuevo.
 * Se usa para excluir ese pedido del cálculo de stock comprometido y para
 * actualizar el pedido en lugar de crear uno nuevo al confirmar.
 */
let _editingOrderId = null;

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
        if (_clickEnOverlay(e, DOM.modalNew())) closeModalNew();
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
    if (doorEl) {
        doorEl.addEventListener('change', () => {
            if (_editor) {
                _editor._doorTipo         = doorEl.value;
                _editor.renderer.doorTipo = doorEl.value;
            }
        });
    }
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
        if (_clickEnOverlay(e, DOM.modalProduct())) closeModalProduct();
    });
    DOM.btnAddProd().addEventListener('click', () => submitProduct());

    // Enter en campos de producto
    [DOM.inputProdName(), DOM.inputProdQty()].forEach(el => {
        el.addEventListener('keydown', e => { if (e.key === 'Enter') submitProduct(); });
    });

    // Picker controls
    const btnPickerAdd = DOM.btnPickerAdd();
    if (btnPickerAdd) {
        btnPickerAdd.addEventListener('click', () => {
            const sc = _activeScenario();
            if (!sc) return;
            if (typeof simIsEditingLocked === 'function' && simIsEditingLocked()) return;
            const cap = parseFloat(DOM.inputPickerCap()?.value) || 100;
            const picker = sc.addPicker(cap);
            if (picker) {
                _updateSidebarInfo();
                _setPickersListExpanded(true);
                showToast(`${picker.name} agregado`, 'info');
            } else {
                showToast('No se pudo agregar el picker.', 'warning');
            }
        });
    }

    // Botón para colapsar / expandir la lista de pickers
    const pickersToggle = document.getElementById('btn-pickers-list-toggle');
    if (pickersToggle) {
        pickersToggle.addEventListener('click', () => {
            const expanded = pickersToggle.getAttribute('aria-expanded') !== 'false';
            _setPickersListExpanded(!expanded);
        });
    }

    // Tabla de pickers: clic en una fila = seleccionar el picker en el canvas
    const pickersList = DOM.pickersList();
    if (pickersList) {
        pickersList.addEventListener('click', e => {
            const row = e.target.closest('.picker-row');
            if (row?.dataset.pickerId) _selectPickerFromPanel(row.dataset.pickerId);
        });
    }

    // Guardar / Cargar

    DOM.btnSave().addEventListener('click', saveScenario);
    DOM.btnLoad().addEventListener('click', loadScenario);

    // Generar escenario automático
    DOM.btnGenerate()?.addEventListener('click', () => openModalGenerate());
    DOM.btnCancelGenerate()?.addEventListener('click', () => closeModalGenerate());
    DOM.modalGenerate()?.addEventListener('click', e => {
        if (_clickEnOverlay(e, DOM.modalGenerate())) closeModalGenerate();
    });
    DOM.btnConfirmGenerate()?.addEventListener('click', () => submitGenerateScenario());
    DOM.inputGenName()?.addEventListener('keydown', e => {
        if (e.key === 'Enter') submitGenerateScenario();
    });

    // Pedidos
    const btnAddOrder = document.getElementById('btn-add-order');
    if (btnAddOrder) btnAddOrder.addEventListener('click', () => openModalOrder());
    DOM.btnCancelOrder().addEventListener('click', () => closeModalOrder());
    DOM.modalOrder().addEventListener('click', e => {
        if (_clickEnOverlay(e, DOM.modalOrder())) closeModalOrder();
    });
    DOM.btnOrderAddItem().addEventListener('click', () => _orderAddItemFromUI());
    DOM.btnConfirmOrder().addEventListener('click', () => submitOrder());

    // Keyboard shortcuts
    document.addEventListener('keydown', e => _onKeyDown(e));

    // Cargar escenario soltando un archivo .json en la ventana
    _initScenarioDragDrop();

    // Inicializar renderer en el canvas (sin escenario todavía)
    const canvas = DOM.canvas();
    _renderer = new WarehouseRenderer(canvas);
    _editor   = new WarehouseEditor(canvas, _renderer, _onEditorEvent);
    _installUndoHooks();   // Ctrl+Z sobre las ediciones del escenario
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

    // Limpiar el estado de simulacion del escenario anterior
    if (typeof simReset === 'function') simReset();
    _scenario = s;
    _wizardScenario = null;
    _editor.setScenario(_scenario);
    _wizardFloatHide();
    closeModalNew();
    _updateSidebarInfo();
    _updatePickersList();
    _updateCanvasStatus();
    _setActiveTool('select');
    _resetUndoHistory();
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

    // Calcular el código secuencial que tendrá el producto (PRD001, PRD002...).
    // El usuario no elige el id; se genera automáticamente.
    const nextId = _genSeqId('PRD', _activeScenario().getAllProducts(), 3);

    DOM.modalProdTitle().textContent = `Agregar producto → ${rack.id}`;
    DOM.inputProdName().value  = '';
    DOM.inputProdQty().value   = '1';
    DOM.inputProdWeight().value = '1.0';

    if (targetCell) {
        // Mostrar celda y calcular el siguiente nivel Z libre
        DOM.labelProdCell().textContent = `Celda: (${targetCell.x}, ${targetCell.y})`;
        DOM.labelProdId().textContent   = `ID: ${nextId}`;
        const existingInCell = rack.products.filter(p => p.x === targetCell.x && p.y === targetCell.y);
        DOM.inputProdZ().value = existingInCell.length + 1;
    } else {
        // Fallback: primera celda del rack
        DOM.labelProdCell().textContent = `Celda: (${rack.x}, ${rack.y})`;
        DOM.labelProdId().textContent   = `ID: ${nextId}`;
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

    // El código/id se genera automáticamente de forma secuencial (PRD001, PRD002...);
    // el usuario no elige el id. No se pasa sku: en Product el sku queda igual al id.
    const product = _activeScenario().addProduct(_productTargetRack.id, {
        name,
        sku: undefined,
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

// ── Modal: Agregar Pedido ─────────────────────────────────────────

/** Devuelve el stock disponible de un producto descontando lo ya en el draft
 *  y lo comprometido en pedidos ya confirmados (excluyendo el pedido en edición). */
function _stockDisponible(productId) {
    const sc = _activeScenario();
    if (!sc) return 0;
    const prod = sc.getAllProducts().find(p => p.id === productId);
    if (!prod) return 0;

    // Stock comprometido en pedidos ya confirmados
    // (excluir el pedido que se está editando para no descontarlo dos veces)
    const comprometido = (sc.orders || []).reduce((total, order) => {
        if (_editingOrderId && order.id === _editingOrderId) return total;
        const item = order.items.find(it => it.productoId === productId);
        return total + (item ? item.cantidad : 0);
    }, 0);

    // Stock en el draft actual
    const yaEnDraft = _orderDraftItems.filter(it => it.productoId === productId)
                                      .reduce((s, it) => s + it.cantidad, 0);

    return Math.max(0, (prod.quantity || 0) - comprometido - yaEnDraft);
}

/** Actualiza el badge de stock y el max del input de cantidad segun el producto seleccionado. */
function _updateStockBadge() {
    const productId = DOM.selectOrderProduct().value;
    const badge     = document.getElementById('order-stock-badge');
    const qtyInput  = DOM.inputOrderItemQty();
    if (!badge) return;
    if (!productId) { badge.style.display = 'none'; return; }
    const stock = _stockDisponible(productId);
    badge.textContent = `Stock: ${stock}`;
    badge.className   = 'order-stock-badge' + (stock === 0 ? ' order-stock-badge--empty' : '');
    badge.style.display = '';
    if (qtyInput) { qtyInput.max = stock > 0 ? stock : 1; }
}

/** Extrae el número de producto del id (PRD001 → 1) para poder ordenar. */
function _numProducto(product) {
    const id = String(product.id || '');
    const m = /(\d+)\s*$/.exec(id);
    if (m) return parseInt(m[1], 10);
    const m2 = /(\d+)/.exec(id);
    return m2 ? parseInt(m2[1], 10) : Number.MAX_SAFE_INTEGER;
}

/** Devuelve una copia de los productos ordenada por número de producto. */
function _productosOrdenadosPorNumero(products) {
    return [...products].sort((a, b) => {
        const na = _numProducto(a);
        const nb = _numProducto(b);
        if (na !== nb) return na - nb;
        return String(a.id || '').localeCompare(String(b.id || ''));
    });
}

/** Habilita/deshabilita el botón de agregar según el producto seleccionado. */
function _syncOrderAddButton() {
    const sel = DOM.selectOrderProduct();
    const btn = document.getElementById('btn-order-add-item');
    if (!sel || !btn) return;
    const opt = sel.options[sel.selectedIndex];
    btn.disabled = !opt || opt.disabled;
}

/**
 * Repuebla el select de productos para agregar al pedido, ordenado por
 * número de producto y deshabilitando los que no tienen stock libre.
 * Conserva la selección actual si sigue siendo válida.
 */
function _refreshOrderProductOptions() {
    const sc = _activeScenario();
    const sel = DOM.selectOrderProduct();
    if (!sc || !sel) return;

    const allProducts = _productosOrdenadosPorNumero(sc.getAllProducts());
    const noMsg = DOM.orderNoProductsMsg();
    const addSection = document.querySelector('.order-add-product-section');
    const prev = sel.value;

    sel.innerHTML = '';

    if (allProducts.length === 0) {
        if (noMsg) noMsg.style.display = '';
        if (addSection) addSection.style.opacity = '.5';
        _updateStockBadge();
        _syncOrderAddButton();
        return;
    }

    if (noMsg) noMsg.style.display = 'none';
    if (addSection) addSection.style.opacity = '1';

    for (const p of allProducts) {
        const stockLibre = _stockDisponible(p.id);
        const opt = document.createElement('option');
        opt.value = p.id;
        opt.textContent = `${p.name} (${p.sku}) — Rack ${p.rackId} — Stock libre: ${stockLibre}`;
        if (stockLibre === 0) {
            opt.disabled = true;
            opt.textContent += ' — AGOTADO';
        }
        sel.appendChild(opt);
    }

    // Conservar la selección previa si sigue habilitada; si no, la primera válida.
    let elegida = prev ? [...sel.options].find(o => o.value === prev && !o.disabled) : null;
    if (!elegida) elegida = [...sel.options].find(o => !o.disabled);
    if (elegida) {
        sel.value = elegida.value;
    } else {
        sel.selectedIndex = -1;
    }

    _updateStockBadge();
    _syncOrderAddButton();
}


/**
 * Abre el modal de pedido.
 * @param {string|null} orderIdToEdit - ID del pedido a editar, o null para crear uno nuevo.
 */
function openModalOrder(orderIdToEdit = null) {
    const sc = _activeScenario();
    if (!sc) { showToast('Cargá un escenario primero.', 'warning'); return; }

    // Bloqueo estricto: no abrir si la simulacion esta activa o pausada
    if (typeof simIsOrderEditingLocked === 'function' && simIsOrderEditingLocked()) {
        showToast('No se pueden editar pedidos mientras la simulación está activa.', 'warning');
        return;
    }

    // Determinar modo: editar o nuevo
    _editingOrderId = orderIdToEdit || null;
    const existingOrder = orderIdToEdit
        ? (sc.orders || []).find(o => o.id === orderIdToEdit)
        : null;

    // Titulo y texto del boton segun el modo
    const modalTitleEl = document.getElementById('modal-order-title');
    const confirmBtn   = DOM.btnConfirmOrder();
    if (modalTitleEl) {
        modalTitleEl.textContent = existingOrder
            ? `Editar Pedido ${existingOrder.id}`
            : 'Nuevo Pedido';
    }
    if (confirmBtn) {
        confirmBtn.textContent = existingOrder ? 'Guardar cambios' : 'Confirmar pedido';
    }

    // Cargar draft: items del pedido existente o vacio
    if (existingOrder) {
        _orderDraftItems = existingOrder.items.map(it => ({
            productoId: it.productoId,
            cantidad:   it.cantidad,
        }));
        DOM.inputOrderPriority().value = String(existingOrder.prioridad || 3);
    } else {
        _orderDraftItems = [];
        DOM.inputOrderPriority().value = '3';
    }

    // Renderizar items del draft
    _renderOrderDraftItems();

    // Poblar select de productos (ordenado por número, sin stock deshabilitado)
    _refreshOrderProductOptions();

    DOM.inputOrderItemQty().value = '1';

    // Conectar eventos internos del modal
    DOM.selectOrderProduct().onchange = () => {
        _updateStockBadge();
        _syncOrderAddButton();
        DOM.inputOrderItemQty().value = '1';
    };

    _updateStockBadge();
    DOM.modalOrder().classList.add('open');
    DOM.inputOrderPriority().focus();
}

function closeModalOrder() {
    DOM.modalOrder().classList.remove('open');
    _orderDraftItems = [];
    _editingOrderId  = null;   // salir del modo edicion
    // Limpiar eventos internos
    const p = DOM.inputOrderPriority(); if (p) p.oninput = null;
    const s = DOM.selectOrderProduct(); if (s) s.onchange = null;
    // Restaurar titulo y boton a modo 'nuevo'
    const modalTitleEl = document.getElementById('modal-order-title');
    if (modalTitleEl) modalTitleEl.textContent = 'Nuevo Pedido';
    const confirmBtn = DOM.btnConfirmOrder();
    if (confirmBtn) confirmBtn.textContent = 'Confirmar pedido';
}

/** Agrega un item al draft con validacion de stock. */
function _orderAddItemFromUI() {
    const productId = DOM.selectOrderProduct().value;
    if (!productId) { showToast('Seleccioná un producto.', 'warning'); return; }

    const qty = parseInt(DOM.inputOrderItemQty().value) || 1;
    if (qty < 1) { showToast('La cantidad debe ser al menos 1.', 'warning'); return; }

    // Validar stock disponible
    const stock = _stockDisponible(productId);
    if (qty > stock) {
        const sc = _activeScenario();
        const prod = sc ? sc.getAllProducts().find(p => p.id === productId) : null;
        const nombre = prod ? prod.name : productId;
        showToast(`Stock insuficiente para "${nombre}": disponible ${stock}, pedido ${qty}.`, 'warning');
        DOM.inputOrderItemQty().classList.add('input--error');
        setTimeout(() => DOM.inputOrderItemQty().classList.remove('input--error'), 1500);
        return;
    }

    // Si el producto ya está en el draft, sumar cantidad
    const existing = _orderDraftItems.find(it => it.productoId === productId);
    if (existing) {
        existing.cantidad += qty;
    } else {
        _orderDraftItems.push({ productoId: productId, cantidad: qty });
    }

    _renderOrderDraftItems();
    DOM.inputOrderItemQty().value = '1';
    _refreshOrderProductOptions();   // actualizar stock restante y opciones
}

/** Renderiza la lista de items del draft en el modal. */
function _renderOrderDraftItems() {
    const container = DOM.orderItemsList();
    const countEl   = document.getElementById('order-items-count');
    if (!container) return;

    if (_orderDraftItems.length === 0) {
        container.innerHTML = '<p class="empty-msg">Sin productos agregados todavía.</p>';
        if (countEl) { countEl.textContent = ''; }
        return;
    }

    const sc = _activeScenario();
    const allProducts = sc ? sc.getAllProducts() : [];

    if (countEl) countEl.textContent = `(${_orderDraftItems.length})`;

    const rows = _orderDraftItems.map((it, idx) => {
        const prod   = allProducts.find(p => p.id === it.productoId);
        const nombre = prod ? prod.name : it.productoId;
        const sku    = prod ? prod.sku  : '';
        const stock  = prod ? prod.quantity : '?';
        const libre  = _stockDisponible(it.productoId);
        const puedeSumar  = libre > 0;
        const puedeRestar = it.cantidad > 1;
        return `
        <div class="order-item-row" data-order-item-idx="${idx}">
            <div class="order-item-info">
                <span class="order-item-name">${nombre}</span>
                <span class="order-item-meta">${sku} · Stock total: ${stock} · Libre: ${libre}</span>
            </div>
            <div class="order-item-controls">
                <button class="btn btn--icon btn--xs order-item-dec" data-order-item-idx="${idx}"
                    title="Restar una unidad" ${puedeRestar ? '' : 'disabled'}>
                    <span class="icon icon--sm" aria-hidden="true">remove</span>
                </button>
                <span class="order-item-qty">×${it.cantidad}</span>
                <button class="btn btn--icon btn--xs order-item-inc" data-order-item-idx="${idx}"
                    title="Sumar una unidad" ${puedeSumar ? '' : 'disabled'}>
                    <span class="icon icon--sm" aria-hidden="true">add</span>
                </button>
                <button class="btn btn--icon btn--xs btn--danger order-item-remove" data-order-item-idx="${idx}" title="Quitar">
                    <span class="icon icon--sm" aria-hidden="true">close</span>
                </button>
            </div>
        </div>`;
    }).join('');

    container.innerHTML = rows;

    // Sumar / restar una unidad de un producto ya agregado al pedido.
    container.querySelectorAll('.order-item-inc').forEach(btn => {
        btn.addEventListener('click', () => {
            const i = parseInt(btn.dataset.orderItemIdx);
            const item = _orderDraftItems[i];
            if (!item) return;
            if (_stockDisponible(item.productoId) <= 0) {
                showToast('No hay stock libre de este producto.', 'warning');
                return;
            }
            item.cantidad += 1;
            _renderOrderDraftItems();
            _refreshOrderProductOptions();
        });
    });

    container.querySelectorAll('.order-item-dec').forEach(btn => {
        btn.addEventListener('click', () => {
            const i = parseInt(btn.dataset.orderItemIdx);
            const item = _orderDraftItems[i];
            if (!item || item.cantidad <= 1) return;
            item.cantidad -= 1;
            _renderOrderDraftItems();
            _refreshOrderProductOptions();
        });
    });

    container.querySelectorAll('.order-item-remove').forEach(btn => {
        btn.addEventListener('click', () => {
            const i = parseInt(btn.dataset.orderItemIdx);
            _orderDraftItems.splice(i, 1);
            _renderOrderDraftItems();
            _refreshOrderProductOptions();
        });
    });
}

/** Confirma la creacion/edicion del pedido. */
function submitOrder() {
    const sc = _activeScenario();
    if (!sc) return;

    if (_orderDraftItems.length === 0) {
        showToast('Agregá al menos un producto al pedido.', 'warning');
        return;
    }

    const priority = parseInt(DOM.inputOrderPriority().value) || 3;

    if (_editingOrderId) {
        // Modo edicion: actualizar el pedido existente
        const existing = (sc.orders || []).find(o => o.id === _editingOrderId);
        if (existing) {
            _withUndo(() => {
                existing.prioridad = priority;
                existing.items = _orderDraftItems.map(
                    it => new OrderItem({ productoId: it.productoId, cantidad: it.cantidad })
                );
            });
            renderOrdersList();
            closeModalOrder();
            showToast(`Pedido ${existing.id} actualizado con ${existing.items.length} item(s).`, 'success');
        } else {
            showToast('No se encontró el pedido a editar.', 'error');
        }
        return;
    }

    // Modo creacion: agregar un pedido nuevo
    // Se pasa el array existente para generar ORDR01, ORDR02...
    const items = _orderDraftItems.map(it => new OrderItem({ productoId: it.productoId, cantidad: it.cantidad }));
    const order = new Order({ prioridad: priority, estado: 'PENDIENTE', items, _existingOrders: sc.orders });
    _withUndo(() => sc.orders.push(order));

    renderOrdersList();
    closeModalOrder();
    showToast(`Pedido ${order.id} creado con ${items.length} item(s).`, 'success');
}

/** Renderiza la lista de pedidos en el sidebar izquierdo (#orders-list). */
function renderOrdersList() {
    const sc = _activeScenario();
    const container = DOM.ordersList();
    if (!container) return;

    const orders = sc ? sc.orders : [];

    if (orders.length === 0) {
        container.innerHTML = '<p class="empty-msg">Sin pedidos cargados.</p>';
        return;
    }

    const allProducts = sc ? sc.getAllProducts() : [];

    const esc = (s) => String(s).replace(/[&<>"']/g, c => (
        { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));

    const cards = orders.map(order => {
        // Estado del pedido (via sim.js si la simulación está activa)
        const _orderStatusStyle = {
            'PENDIENTE':  { color: '#94a3b8', label: 'Pendiente' },
            'EN_WAVE':    { color: '#60a5fa', label: 'En wave' },
            'EN_PROCESO': { color: '#fbbf24', label: 'En proceso' },
            'COMPLETADO': { color: '#22c55e', label: 'Completado' },
        };
        const orderStatus = (typeof simGetOrderStatus === 'function')
            ? simGetOrderStatus(order.id)
            : 'PENDIENTE';
        const stStyle = _orderStatusStyle[orderStatus] || _orderStatusStyle['PENDIENTE'];

        // Items en una sola línea: cantidad | nombre | id/SKU
        const itemsText = order.items.map(it => {
            const p = allProducts.find(pr => pr.id === it.productoId);
            const nombre = p ? p.name : it.productoId;
            const codigo = p ? (p.sku || it.productoId) : it.productoId;
            return `<div class="order-line">`
                 + `<span class="order-line__qty">×${it.cantidad}</span>`
                 + `<span class="order-line__name" title="${esc(nombre)}">${esc(nombre)}</span>`
                 + `<span class="order-line__sku" title="${esc(codigo)}">${esc(codigo)}</span>`
                 + `</div>`;
        }).join('');

        const priorityColors = { 1: '#22c55e', 2: '#4fc97f', 3: '#fbbf24', 4: '#f97316', 5: '#ef4444' };
        const pc = priorityColors[order.prioridad] || '#94a3b8';

        return `
        <div class="wave-item" style="cursor:default">
            <div class="order-head">
                <span class="wave-item__id" style="font-size:.78rem">${esc(order.id)}</span>
                <div class="order-actions">
                    <button class="btn btn--icon btn--xs" data-edit-order="${esc(order.id)}" title="Editar pedido">
                        <span class="icon icon--sm" aria-hidden="true">edit</span>
                    </button>
                    <button class="btn btn--icon btn--xs btn--danger" data-delete-order="${esc(order.id)}" title="Eliminar pedido">
                        <span class="icon icon--sm" aria-hidden="true">delete</span>
                    </button>
                </div>
            </div>
            <div class="order-badges">
                <span class="wave-item__badge" style="color:${pc};border-color:${pc}">P${order.prioridad}</span>
                <span class="wave-item__badge"
                      style="color:${stStyle.color};border-color:${stStyle.color};opacity:.9;font-size:.62rem">
                    ${esc(stStyle.label)}
                </span>
            </div>
            <div class="wave-item__meta" style="flex-direction:column;align-items:flex-start;gap:2px">
                ${itemsText || '<span style="font-size:.72rem;color:var(--color-text-muted,#94a3b8)">Sin items</span>'}
            </div>
        </div>`;
    }).join('');

    container.innerHTML = cards;

    const isLocked = typeof simIsOrderEditingLocked === 'function'
        ? simIsOrderEditingLocked()
        : (typeof simIsEditingLocked === 'function' && simIsEditingLocked());

    // Bloquear btn-add-order si la simulacion esta activa
    const btnAddOrder = document.getElementById('btn-add-order');
    if (btnAddOrder) {
        btnAddOrder.disabled = isLocked;
        btnAddOrder.title    = isLocked ? 'No disponible mientras hay una simulacion activa' : '';
    }

    const MSG_LOCKED = 'No disponible mientras hay una simulacion activa';

    // Botones de editar pedido
    container.querySelectorAll('[data-edit-order]').forEach(btn => {
        if (isLocked) {
            btn.disabled = true;
            btn.title    = MSG_LOCKED;
            return;
        }
        btn.addEventListener('click', () => {
            openModalOrder(btn.dataset.editOrder);
        });
    });

    // Botones de eliminar pedido
    container.querySelectorAll('[data-delete-order]').forEach(btn => {
        if (isLocked) {
            btn.disabled = true;
            btn.title    = MSG_LOCKED;
            return;
        }
        btn.addEventListener('click', () => {
            const oid = btn.dataset.deleteOrder;
            const idx = sc.orders.findIndex(o => o.id === oid);
            if (idx !== -1) {
                _withUndo(() => sc.orders.splice(idx, 1));
                renderOrdersList();
                showToast('Pedido eliminado.', 'warning');
            }
        });
    });
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
            <div class="prod-chip__body">
                <span class="prod-chip__name">${p.name}</span>
                <span class="prod-chip__meta">${p.sku} &middot; ${p.pesoKg}&thinsp;kg &middot; <span class="prod-chip__stock" data-stock-pid="${p.id}">&times;${typeof simGetRemainingStock === 'function' ? simGetRemainingStock(p) : p.quantity}</span></span>
            </div>
            <span class="prod-chip__cell" title="Coordenadas (x, y, z)">(${p.x},${p.y},${p.z})</span>
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
        <div class="sel-products" tabindex="0">${chips}${emptyMsg}</div>
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

    _applySelectionLock(body);
    panel.classList.add('open');
}

/**
 * Actualiza el stock de los productos del rack seleccionado sin reconstruir
 * el panel. Se llama en cada frame de la simulación.
 */
function simRefreshSelectedRackStock() {
    const panel = DOM.selectionPanel();
    if (!panel || !panel.classList.contains('open')) return;

    const selected = _renderer?.selectedElement;
    if (!selected || selected.type !== 'rack') return;

    const rack = selected.element;
    panel.querySelectorAll('.prod-chip__stock[data-stock-pid]').forEach(el => {
        const prod = rack.products.find(p => p.id === el.dataset.stockPid);
        if (!prod) return;
        const stock = (typeof simGetRemainingStock === 'function')
            ? simGetRemainingStock(prod)
            : prod.quantity;
        const text = `×${stock}`;
        if (el.textContent !== text) el.textContent = text;
    });
}

function _showSelectionPicker(picker) {
    const panel = DOM.selectionPanel();
    const body  = DOM.selectionBody();

    body.innerHTML = `
        <div class="sel-header">
            <span class="sel-icon" style="color:${picker.color}" aria-hidden="true"><span class="icon icon--18 icon--filled">person</span></span>
            <span class="sel-title">${picker.name}</span>
        </div>
        <div class="sel-row"><span class="sel-label">Posición</span><span class="sel-value">(${picker.x}, ${picker.y})</span></div>
        <div class="sel-row"><span class="sel-label">ID</span><span class="sel-value">${picker.id}</span></div>

        <div class="sel-row">
            <span class="sel-label">Capacidad (kg)</span>
            <div style="display:flex;align-items:center;gap:4px">
                <input class="form-input form-input--num" type="number" id="sel-picker-cap"
                       min="1" max="9999" value="${picker.capacidadKg}"
                       style="width:72px;height:28px;box-sizing:border-box;padding:3px 6px;font-size:.8rem">
                <button class="btn btn--sm btn--ghost" id="sel-picker-cap-btn" title="Aplicar">
                    <span class="icon icon--sm" aria-hidden="true">check</span>
                </button>
            </div>
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
        _withUndo(() => { picker.capacidadKg = val; });
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

    _applySelectionLock(body);
    panel.classList.add('open');
}

function _hideSelection() {
    DOM.selectionPanel().classList.remove('open');
}

/**
 * Deshabilita todos los botones e inputs de edicion del panel de seleccion
 * mientras la simulacion esta activa, para evitar modificaciones inconsistentes.
 * Se llama al final de cada _showSelection* antes de abrir el panel.
 */
function _applySelectionLock(body) {
    if (typeof simIsEditingLocked !== 'function' || !simIsEditingLocked()) return;
    if (!body) return;
    const msg = 'No disponible mientras hay una simulacion activa';
    body.querySelectorAll('button').forEach(btn => {
        btn.disabled = true;
        btn.title    = msg;
    });
    body.querySelectorAll('select, input').forEach(el => {
        el.disabled = true;
    });
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
        _renderer?.invalidateStaticLayer();
    });
    body.querySelector('#sel-del-door-btn')?.addEventListener('click', () => {
        _activeScenario().removeDoor(door.id);
        _renderer.selectedElement = null;
        _updateSidebarInfo();
        _hideSelection();
        showToast(`Puerta ${door.id} eliminada`, 'warning');
    });
    _applySelectionLock(body);
    panel.classList.add('open');
}

function _showSelectionDispatch(dz) {
    const panel = DOM.selectionPanel();
    const body  = DOM.selectionBody();
    const sc    = _activeScenario();
    const allDoors = sc?.doors || [];

    // Solo puertas físicamente adyacentes a esta zona
    const adjDoors = allDoors.filter(d =>
        sc._isAdjacentToSpecificDoor(dz.x, dz.y, dz.width, dz.height, d.id)
    );

    let doorOpts;
    if (adjDoors.length === 0) {
        doorOpts = `<option value="" disabled>— Sin puertas adyacentes —</option>`;
    } else {
        doorOpts = adjDoors.map(d =>
            `<option value="${d.id}" ${dz.puertaId === d.id ? 'selected' : ''}>${d.id} (${d.tipo})</option>`
        ).join('');
    }

    body.innerHTML = `
        <div class="sel-header">
            <span class="sel-icon" style="color:#4fc97f" aria-hidden="true"><span class="icon icon--18 icon--filled">home_storage</span></span>
            <span class="sel-title">${dz.id}</span>
        </div>
        <div class="sel-row"><span class="sel-label">Posición</span><span class="sel-value">(${dz.x}, ${dz.y})</span></div>
        <div class="sel-row"><span class="sel-label">Tamaño</span><span class="sel-value">${dz.width}×${dz.height} celdas</span></div>
        <div class="sel-row">
            <span class="sel-label">Puerta</span>
            <select class="sel-value" id="sel-dz-door" ${adjDoors.length === 0 ? 'disabled' : ''}>
                <option value="">— Sin asignar —</option>
                ${doorOpts}
            </select>
        </div>
        <div class="sel-row">
            <span class="sel-label">Peso Máx. (kg)</span>
            <div style="display:flex;align-items:center;gap:4px">
                <input class="form-input form-input--num" type="number" id="sel-dz-weight"
                       min="1" max="99999" value="${dz.pesoMaxKg || 500}"
                       style="width:72px;height:28px;box-sizing:border-box;padding:3px 6px;font-size:.8rem">
                <button class="btn btn--sm btn--ghost" id="sel-dz-weight-btn" title="Aplicar">
                    <span class="icon icon--sm" aria-hidden="true">check</span>
                </button>
            </div>
        </div>
        <div class="sel-actions">
            <button class="btn btn--sm btn--danger" id="sel-del-dz-btn">
                <span class="icon icon--sm" aria-hidden="true">delete</span> Eliminar zona
            </button>
        </div>
    `;
    body.querySelector('#sel-dz-door')?.addEventListener('change', e => {
        const newId = e.target.value || null;
        const sc2 = _activeScenario();
        // Verificar que la puerta sea adyacente a esta zona
        if (newId && sc2 && !sc2._isAdjacentToSpecificDoor(dz.x, dz.y, dz.width, dz.height, newId)) {
            showToast('Esa puerta no es adyacente a la zona de despacho.', 'error');
            e.target.value = dz.puertaId || '';
            return;
        }
        // Verificar unicidad: una puerta no puede estar asignada a más de una zona
        if (newId && sc2 && sc2.dispatchZones.some(z => z.id !== dz.id && z.puertaId === newId)) {
            showToast('Esa puerta ya está asignada a otra zona de despacho.', 'error');
            e.target.value = dz.puertaId || '';
            return;
        }
        _withUndo(() => { dz.puertaId = newId; });
        _renderer?.invalidateStaticLayer();
        _updateSidebarInfo();
        if (_wizardScenario) _updateWizardValidMsg();
    });

    body.querySelector('#sel-dz-weight-btn')?.addEventListener('click', () => {
        const val = parseFloat(body.querySelector('#sel-dz-weight').value);
        if (!val || val < 1) { showToast('Peso máximo inválido (mínimo 1 kg).', 'warning'); return; }
        _withUndo(() => { dz.pesoMaxKg = val; });
        _renderer?.invalidateStaticLayer();
        _updateSidebarInfo();
        showToast(`Zona ${dz.id}: peso máximo actualizado a ${val} kg`, 'info');
    });

    // Aplicar también con Enter en el input
    body.querySelector('#sel-dz-weight')?.addEventListener('keydown', e => {
        if (e.key === 'Enter') body.querySelector('#sel-dz-weight-btn').click();
    });

    body.querySelector('#sel-del-dz-btn')?.addEventListener('click', () => {
        _activeScenario().removeDispatchZone(dz.id);
        _renderer.selectedElement = null;
        _updateSidebarInfo();
        _hideSelection();
        showToast(`Zona ${dz.id} eliminada`, 'warning');
    });
    _applySelectionLock(body);
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
        _renderer?.invalidateStaticLayer();
    });
    body.querySelector('#sel-del-aisle-btn')?.addEventListener('click', () => {
        _activeScenario().removeAisle(aisle.id);
        _renderer.selectedElement = null;
        _updateSidebarInfo();
        _hideSelection();
        showToast(`Pasillo ${aisle.id} eliminado`, 'warning');
    });
    _applySelectionLock(body);
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

    const locked = typeof simIsEditingLocked === 'function' && simIsEditingLocked();
    const addBtn = DOM.btnPickerAdd();
    if (addBtn) addBtn.disabled = locked;
    _updatePickersList();
}

/**
 * Escapa un valor para insertarlo con seguridad en HTML o en un atributo.
 */
function _escPickerHtml(value) {
    return String(value).replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
}

/**
 * Colapsa o expande la lista de pickers desde el header del panel.
 */
function _setPickersListExpanded(expanded) {
    const toggle = document.getElementById('btn-pickers-list-toggle');
    const list = DOM.pickersList();
    if (!toggle || !list) return;

    toggle.setAttribute('aria-expanded', String(expanded));
    list.classList.toggle('pickers-table--collapsed', !expanded);
    toggle.querySelector('.pickers-toggle__chevron')?.classList.toggle('open', expanded);
    toggle.title = expanded ? 'Ocultar lista de pickers' : 'Mostrar lista de pickers';
}

/**
 * Renderiza la lista de pickers del panel. Cada fila muestra color,
 * nombre, posición y capacidad, y permite seleccionar el picker en el
 * canvas para editarlo desde el panel de Selección.
 */
function _updatePickersList() {
    const sc = _activeScenario();
    if (!sc) return;
    const list = DOM.pickersList();
    if (!list) return;

    const selected = _renderer?.selectedElement;
    const selectedId = selected?.type === 'picker' ? selected.element?.id : null;

    if (sc.pickers.length === 0) {
        list.innerHTML = '<p class="empty-msg">Sin pickers asignados.</p>';
        return;
    }

    list.innerHTML = sc.pickers.map(pk => {
        const isSel = pk.id === selectedId;
        const idEsc = _escPickerHtml(pk.id);
        const nameEsc = _escPickerHtml(pk.name);
        return `
        <div class="picker-row${isSel ? ' picker-row--selected' : ''}"
             data-picker-id="${idEsc}"
             title="${nameEsc} · clic para seleccionar">
            <span class="picker-row__dot" style="background:${pk.color}"></span>
            <span class="picker-row__id">
                <span class="picker-row__name">${nameEsc}</span>
                <span class="picker-row__pos">(${pk.x},${pk.y})</span>
            </span>
            <span class="picker-row__cap">${Number(pk.capacidadKg)}<span class="picker-row__unit"> kg</span></span>
        </div>`;
    }).join('');
}

/**
 * Selecciona un picker desde el panel: lo marca en el canvas y abre el
 * panel de selección, donde ya se puede ajustar la capacidad o eliminarlo.
 */
function _selectPickerFromPanel(pickerId) {
    const sc = _activeScenario();
    if (!sc) return;
    const picker = sc.pickers.find(p => p.id === pickerId);
    if (!picker) return;
    if (_renderer) _renderer.selectedElement = { type: 'picker', element: picker };
    _showSelectionPicker(picker);
    _updatePickersList();
}

function _updateCanvasStatus() {
    const sc = _activeScenario();
    if (!sc) {
        DOM.canvasStatus().textContent = 'Sin escenario cargado';
        return;
    }
    DOM.canvasStatus().textContent = `${sc.name}  ·  ${sc.width}×${sc.height}`;
    const locked = typeof simIsEditingLocked === 'function' && simIsEditingLocked();
    const addBtn = DOM.btnPickerAdd();
    if (addBtn) addBtn.disabled = locked;
    _updatePickersList();
}

// ── Guardar / Cargar ──────────────────────────────────────────────
//
// Persistencia (§17): el escenario se guarda como un archivo .json que
// queda en la computadora del usuario. Si hay waves o una simulación,
// sim.js le agrega la sección "estado" (opciones elegidas y frame actual)
// para poder retomarla al cargar el archivo.
//
// Al cargar, el archivo se valida dos veces:
//   1. En el front (_checkScenarioShape): un control rápido de la forma
//      del JSON, solo para avisar enseguida si el archivo no sirve.
//   2. En el back (apiValidateScenario): el que decide. Arma el Warehouse
//      con todas las validaciones del modelo. Si dice que no, no se carga.

const ESTADO_OPCIONES = {
    estrategia_wave: ['por_pedido', 'por_cercania', 'solo_cercania'],
    estrategia: ['orden', 'cercania'],
    buscador: ['bfs', 'astar'],
};

function saveScenario() {
    if (!_scenario) { showToast('No hay escenario para guardar.', 'warning'); return; }
    const missing = _scenario.getMissingRequirements(true);
    if (missing.length > 0) {
        showToast('Faltan: ' + missing.join(', ') + '.', 'warning');
        return;
    }
    // sim.js agrega el estado de la simulación (si hay) y guarda los pickers
    // en su posición inicial, no donde quedaron parados en el frame actual.
    const data = (typeof simScenarioForSave === 'function')
        ? simScenarioForSave(_scenario)
        : _scenario.toJSON();
    const json = JSON.stringify(data, null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = `${_scenario.name.replace(/\s+/g, '_')}.json`;
    a.click();
    URL.revokeObjectURL(url);

    if (data.estado && data.estado.frame != null) {
        showToast(`Escenario guardado con la simulación en el tick ${data.estado.tick}.`, 'success');
    } else if (data.estado) {
        showToast('Escenario guardado con las waves generadas.', 'success');
    } else {
        showToast('Escenario guardado.', 'success');
    }
}

/**
 * Control rápido (front) de la forma del archivo antes de mandarlo al back.
 * No reemplaza la validación del back: solo evita viajes inútiles y da un
 * mensaje claro si el archivo no es un escenario.
 * Devuelve la lista de problemas encontrados (vacía si está bien).
 */
function _checkScenarioShape(data) {
    if (data === null || typeof data !== 'object' || Array.isArray(data)) {
        return ['el archivo no contiene un escenario'];
    }
    const errores = [];
    const wh = data.warehouse;
    if (!wh || typeof wh !== 'object' || Array.isArray(wh)) {
        errores.push("falta la sección 'warehouse'");
    } else {
        const dim = wh.dimensiones || {};
        const esPositivo = v => typeof v === 'number' && v > 0;
        if (!esPositivo(dim.ancho_x) || !esPositivo(dim.largo_y)) {
            errores.push('las dimensiones del warehouse no son válidas');
        }
        for (const clave of ['puertas', 'zonas_despacho', 'racks', 'pasillos']) {
            if (wh[clave] !== undefined && !Array.isArray(wh[clave])) {
                errores.push(`'warehouse.${clave}' tiene que ser una lista`);
            }
        }
    }
    for (const clave of ['pickers', 'productos', 'pedidos']) {
        if (data[clave] !== undefined && !Array.isArray(data[clave])) {
            errores.push(`'${clave}' tiene que ser una lista`);
        }
    }
    const estado = data.estado;
    if (estado !== undefined && estado !== null) {
        if (typeof estado !== 'object' || Array.isArray(estado)) {
            errores.push("la sección 'estado' no es válida");
        } else {
            for (const [clave, validas] of Object.entries(ESTADO_OPCIONES)) {
                if (estado[clave] != null && !validas.includes(estado[clave])) {
                    errores.push(`'estado.${clave}' tiene un valor desconocido`);
                }
            }
            if (estado.frame != null && (!Number.isInteger(estado.frame) || estado.frame < 0)) {
                errores.push("'estado.frame' tiene que ser un entero mayor o igual a 0");
            }
        }
    }
    return errores;
}

/** Muestra en el editor un escenario que el back ya validó. */
function _showLoadedScenario(data) {
    // Limpiar el estado de simulacion del escenario anterior
    if (typeof simReset === 'function') simReset();
    _scenario = Scenario.fromJSON(data);
    _editor.setScenario(_scenario);
    DOM.canvasPlaceholder().style.display = 'none';
    DOM.canvas().style.display            = 'block';
    _updateSidebarInfo();
    _updateCanvasStatus();
    _hideSelection();
    renderOrdersList();
    _resetUndoHistory();
}

async function _loadScenarioFromText(texto) {
    // 0. Que sea JSON
    let data;
    try {
        data = JSON.parse(texto);
    } catch (err) {
        showToast('El archivo no es un JSON válido.', 'error');
        return;
    }

    // 1. Validación rápida en el front
    const problemas = _checkScenarioShape(data);
    if (problemas.length > 0) {
        showToast('No se puede cargar: ' + problemas.join('; ') + '.', 'error', 7000);
        return;
    }

    // 2. Validación del back (la que decide)
    let resultado;
    try {
        resultado = await apiValidateScenario(data);
    } catch (err) {
        showToast(err.error || 'No se pudo validar el escenario en el servidor.', 'error', 7000);
        return;
    }
    if (!resultado.valido) {
        showToast('El escenario no es válido: ' + resultado.errores.join(' '), 'error', 9000);
        console.warn('Errores del escenario:', resultado.errores);
        return;
    }

    // 3. Mostrarlo
    try {
        _showLoadedScenario(data);
    } catch (err) {
        showToast('Error al mostrar el escenario.', 'error');
        console.error(err);
        return;
    }
    if (resultado.avisos.length > 0) {
        showToast(`Escenario "${_scenario.name}" cargado. Aviso: ` + resultado.avisos.join(' '), 'warning', 7000);
        console.warn('Avisos del escenario:', resultado.avisos);
    } else {
        showToast(`Escenario "${_scenario.name}" cargado.`, 'success');
    }

    // 4. Si el archivo trae una simulación guardada, retomarla
    if (data.estado && typeof simRestoreState === 'function') {
        await simRestoreState(data.estado);
    }
}

function loadScenario() {
    const input = document.createElement('input');
    input.type  = 'file';
    input.accept = '.json,application/json';
    input.addEventListener('change', e => {
        const file = e.target.files[0];
        if (!file) return;
        _loadScenarioFile(file);
    });
    input.click();
}

/** Lee un archivo .json y lo manda al cargador de escenarios. */
function _loadScenarioFile(file) {
    if (!file) return;
    if (!/\.json$/i.test(file.name)) {
        showToast('El archivo tiene que ser .json.', 'warning');
        return;
    }
    const reader = new FileReader();
    reader.onload  = ev => _loadScenarioFromText(ev.target.result);
    reader.onerror = () => showToast('No se pudo leer el archivo.', 'error');
    reader.readAsText(file);
}

// ── Cargar escenario arrastrando un archivo ──────────────────────

/** Profundidad de dragenter/dragleave: evita parpadeos al pasar por hijos. */
let _dragDepth = 0;

function _dragHasFiles(e) {
    const dt = e.dataTransfer;
    if (!dt) return false;
    if (dt.types) return Array.from(dt.types).includes('Files');
    return !!(dt.files && dt.files.length > 0);
}

function _scenarioDropAllowed() {
    return !(typeof simIsEditingLocked === 'function' && simIsEditingLocked());
}

function _getScenarioDropOverlay() {
    let overlay = document.getElementById('scenario-drop-overlay');
    if (overlay) return overlay;

    overlay = document.createElement('div');
    overlay.id = 'scenario-drop-overlay';
    overlay.className = 'scenario-drop-overlay';
    overlay.setAttribute('aria-hidden', 'true');
    overlay.innerHTML =
        '<div class="scenario-drop-overlay__box">' +
            '<span class="icon icon--lg icon--filled" aria-hidden="true">upload</span>' +
            '<span class="scenario-drop-overlay__title">Soltá el archivo para cargar el escenario</span>' +
            '<span class="scenario-drop-overlay__hint">Archivo .json</span>' +
        '</div>';
    document.body.appendChild(overlay);
    return overlay;
}

function _setScenarioDropOverlay(visible) {
    const overlay = _getScenarioDropOverlay();
    overlay.classList.toggle('scenario-drop-overlay--visible', visible);
    overlay.setAttribute('aria-hidden', visible ? 'false' : 'true');
}

function _initScenarioDragDrop() {
    window.addEventListener('dragenter', e => {
        if (!_dragHasFiles(e)) return;
        e.preventDefault();
        _dragDepth++;
        if (_scenarioDropAllowed()) _setScenarioDropOverlay(true);
    });

    window.addEventListener('dragover', e => {
        if (!_dragHasFiles(e)) return;
        e.preventDefault();   // sin esto el navegador no permite soltar
        e.dataTransfer.dropEffect = _scenarioDropAllowed() ? 'copy' : 'none';
    });

    window.addEventListener('dragleave', () => {
        _dragDepth = Math.max(0, _dragDepth - 1);
        if (_dragDepth === 0) _setScenarioDropOverlay(false);
    });

    window.addEventListener('drop', e => {
        if (!_dragHasFiles(e)) return;
        e.preventDefault();
        _dragDepth = 0;
        _setScenarioDropOverlay(false);

        if (!_scenarioDropAllowed()) {
            showToast('No se puede cargar un escenario mientras la simulación está activa.', 'warning');
            return;
        }
        const file = e.dataTransfer.files && e.dataTransfer.files[0];
        _loadScenarioFile(file);
    });
}

// ── Generar escenario automático ─────────────────────────────────

function openModalGenerate() {
    // Si el wizard de creación manual está abierto, se descarta para no
    // mezclar dos escenarios en construcción.
    if (DOM.modalNew()?.classList.contains('open') || _wizardScenario) {
        _doCloseModalNew();
    }
    _setGenerateError('');
    DOM.modalGenerate().classList.add('open');
    DOM.inputGenName().focus();
    DOM.inputGenName().select();
}

function closeModalGenerate() {
    DOM.modalGenerate().classList.remove('open');
    _setGenerateError('');
}

function _setGenerateError(message) {
    const el = DOM.generateError();
    if (!el) return;
    if (!message) {
        el.textContent = '';
        el.style.display = 'none';
        return;
    }
    el.textContent = message;
    el.style.display = '';
}

function _enteroDeInput(el, nombre, minimo, maximo) {
    const valor = parseInt(el.value, 10);
    if (isNaN(valor)) {
        throw new Error(`"${nombre}" debe ser un número entero.`);
    }
    if (valor < minimo || valor > maximo) {
        throw new Error(`"${nombre}" debe estar entre ${minimo} y ${maximo}.`);
    }
    return valor;
}

function _enteroOpcionalDeInput(el, nombre, minimo, maximo) {
    const texto = (el.value || '').trim();
    if (texto === '') return null;
    return _enteroDeInput(el, nombre, minimo, maximo);
}

function _leerParametrosGeneracion() {
    const semillaTexto = DOM.inputGenSeed().value.trim();
    return {
        nombre: DOM.inputGenName().value.trim() || 'Escenario generado',
        cantidad_racks: _enteroDeInput(DOM.inputGenRacks(), 'Cantidad de racks', 1, 200),
        cantidad_pasillos: _enteroDeInput(DOM.inputGenAisles(), 'Cantidad de pasillos', 1, 60),
        cantidad_productos: _enteroDeInput(DOM.inputGenProducts(), 'Cantidad de productos', 1, 1000),
        distribucion_productos: DOM.selectGenDistribution().value,
        orientacion_racks: DOM.selectGenOrientation().value,
        ancho_x: _enteroOpcionalDeInput(DOM.inputGenWidth(), 'Ancho del warehouse', 1, 500),
        largo_y: _enteroOpcionalDeInput(DOM.inputGenHeight(), 'Alto del warehouse', 1, 500),
        cantidad_pedidos: _enteroDeInput(DOM.inputGenOrders(), 'Cantidad de pedidos', 1, 1000),
        max_productos_por_pedido: _enteroDeInput(DOM.inputGenMaxProducts(), 'Máx. productos por pedido', 1, 50),
        wave_max_pedidos: _enteroDeInput(DOM.inputGenWaveOrders(), 'Capacidad wave (pedidos)', 1, 100),
        wave_max_productos: _enteroDeInput(DOM.inputGenWaveProducts(), 'Capacidad wave (unidades)', 1, 5000),
        cantidad_puertas: _enteroDeInput(DOM.inputGenDoors(), 'Puertas', 1, 4),
        cantidad_pickers: _enteroDeInput(DOM.inputGenPickers(), 'Pickers', 1, 20),
        semilla: semillaTexto === '' ? null : _enteroDeInput(DOM.inputGenSeed(), 'Semilla', 0, 2147483647),
    };
}

async function submitGenerateScenario() {
    const btn = DOM.btnConfirmGenerate();
    if (!btn || btn.disabled) return;

    _setGenerateError('');
    let parametros;
    try {
        parametros = _leerParametrosGeneracion();
    } catch (err) {
        _setGenerateError(err.message);
        return;
    }

    const htmlOriginal = btn.innerHTML;
    btn.disabled = true;
    btn.textContent = 'Generando…';

    try {
        const resultado = await apiGenerateScenario(parametros);
        _aplicarEscenarioGenerado(resultado);
    } catch (err) {
        _setGenerateError(err?.error || 'No se pudo generar el escenario.');
    } finally {
        btn.disabled = false;
        btn.innerHTML = htmlOriginal;
    }
}

function _aplicarEscenarioGenerado(resultado) {
    if (!resultado || !resultado.scenario) {
        _setGenerateError('El servidor no devolvió un escenario válido.');
        return;
    }

    // Limpiar la simulación del escenario anterior antes de reemplazarlo.
    if (typeof simReset === 'function') simReset();

    _scenario = Scenario.fromJSON(resultado.scenario);
    _wizardScenario = null;
    _editor.setScenario(_scenario);

    DOM.canvasPlaceholder().style.display = 'none';
    DOM.canvas().style.display = 'block';

    _updateSidebarInfo();
    _updatePickersList();
    _updateCanvasStatus();
    _hideSelection();
    renderOrdersList();
    _setActiveTool('select');
    _resetUndoHistory();

    closeModalGenerate();

    const meta = resultado.meta || {};
    const validacion = meta.validacion || {};
    const partes = [
        `${meta.racks ?? _scenario.racks.length} racks`,
        `${meta.pasillos ?? 0} pasillos`,
        `${meta.productos ?? _scenario.getAllProducts().length} productos`,
        `${meta.pedidos ?? _scenario.orders.length} pedidos`,
    ];
    const orientacionLabel = {
        vertical: 'racks verticales',
        horizontal: 'racks horizontales',
        aleatorio: 'racks mixtos',
    }[meta.orientacion_racks];
    if (orientacionLabel) {
        partes.push(orientacionLabel);
    }
    const resumen = partes.join(' · ');
    const validado = validacion.ok ? ' · validado ✓' : '';
    const semilla = meta.semilla != null ? ` · semilla ${meta.semilla}` : '';
    showToast(`Escenario "${_scenario.name}" generado: ${resumen}${validado}${semilla}`, 'success');
}

// ── Deshacer / rehacer ediciones (Ctrl+Z) ─────────────────────────
//
// Cada entrada del historial es un snapshot JSON del escenario tomado
// ANTES de una edición. Se enganchan los métodos que mutan el escenario
// (Scenario.prototype) más los pocos lugares que lo modifican a mano
// (pedidos, capacidad de picker, zona de despacho). No se registra nada
// mientras la simulación está activa ni durante el wizard.

const UNDO_MAX = 50;
let _undoStack = [];
let _redoStack = [];

/** Serializa el escenario activo, o null si no se puede. */
function _undoSnapshot(sc) {
    try {
        return JSON.stringify((sc || _scenario).toJSON());
    } catch (err) {
        return null;
    }
}

/**
 * Guarda un estado previo en el historial. Solo si cambió respecto del
 * estado posterior (evita pasos vacíos por operaciones que fallan).
 */
function _recordUndoSnapshot(before, after) {
    if (!before || !after || before === after) return;
    if (typeof simIsEditingLocked === 'function' && simIsEditingLocked()) return;
    if (_wizardScenario || !_scenario) return;
    // Si ya está arriba, no duplicar (p. ej. Enter + click en un mismo botón).
    if (_undoStack[_undoStack.length - 1] === before) { _redoStack = []; return; }
    _undoStack.push(before);
    if (_undoStack.length > UNDO_MAX) _undoStack.shift();
    _redoStack = [];
}

/** Toma un snapshot del escenario actual antes de una mutación directa. */
function _withUndo(fn) {
    const active = !(_wizardScenario || !_scenario) &&
        !(typeof simIsEditingLocked === 'function' && simIsEditingLocked());
    if (!active) return fn();
    const before = _undoSnapshot(_scenario);
    const result = fn();
    _recordUndoSnapshot(before, _undoSnapshot(_scenario));
    return result;
}

/** Limpia el historial (escenario nuevo, cargado o generado). */
function _resetUndoHistory() {
    _undoStack = [];
    _redoStack = [];
}

/** Aplica un snapshot reconstruyendo el escenario y toda la UI asociada. */
function _applyUndoSnapshot(snapshot) {
    const data = JSON.parse(snapshot);

    // La simulación vieja apunta a objetos que van a quedar obsoletos.
    if (typeof simReset === 'function') simReset();

    _scenario = Scenario.fromJSON(data);
    _editor.setScenario(_scenario);

    DOM.canvasPlaceholder().style.display = 'none';
    DOM.canvas().style.display = 'block';

    closeModalProduct();
    closeModalOrder();
    _hideSelection();
    if (_editor && typeof _editor._hideTooltip === 'function') _editor._hideTooltip();
    _updateSidebarInfo();
    _updatePickersList();
    _updateCanvasStatus();
    renderOrdersList();
}

function _undo() {
    if (_wizardScenario || _undoStack.length === 0) return false;
    if (typeof simIsEditingLocked === 'function' && simIsEditingLocked()) return false;
    const current = _undoSnapshot(_scenario);
    const previous = _undoStack.pop();
    if (!previous) return false;
    _redoStack.push(current);
    _applyUndoSnapshot(previous);
    return true;
}

function _redo() {
    if (_wizardScenario || _redoStack.length === 0) return false;
    if (typeof simIsEditingLocked === 'function' && simIsEditingLocked()) return false;
    const current = _undoSnapshot(_scenario);
    const next = _redoStack.pop();
    if (!next) return false;
    _undoStack.push(current);
    _applyUndoSnapshot(next);
    return true;
}

/**
 * Envuelve los métodos de Scenario que modifican el escenario para
 * registrar automáticamente el estado previo. Es un solo punto de
 * enganche: no hay que acordarse de llamar a _withUndo en cada uno.
 */
let _undoHooksInstalled = false;
function _installUndoHooks() {
    if (_undoHooksInstalled || typeof Scenario === 'undefined') return;
    _undoHooksInstalled = true;

    const mutators = [
        'addRack', 'moveRack', 'rotateRack', 'removeRack',
        'addProduct', 'removeProduct',
        'addDoor', 'removeDoor', 'moveDoor',
        'addDispatchZone', 'moveDispatchZone', 'removeDispatchZone',
        'addAisle', 'removeAisle',
        'addPicker', 'removePicker', 'movePicker',
    ];

    for (const name of mutators) {
        const original = Scenario.prototype[name];
        if (typeof original !== 'function') continue;
        Scenario.prototype[name] = function (...args) {
            const before = (this === _scenario) ? _undoSnapshot(this) : null;
            const result = original.apply(this, args);
            if (before !== null && this === _scenario) {
                _recordUndoSnapshot(before, _undoSnapshot(this));
            }
            return result;
        };
    }
}

// ── Keyboard shortcuts ────────────────────────────────────────────

function _onKeyDown(e) {
    // No activar si el foco está en un input/textarea
    if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) return;

    // Ctrl+Z / Ctrl+Shift+Z (o Ctrl+Y): deshacer / rehacer ediciones
    if ((e.ctrlKey || e.metaKey) && !e.altKey) {
        const key = (e.key || '').toLowerCase();
        const isZ = key === 'z' || e.code === 'KeyZ';
        const isY = key === 'y' || e.code === 'KeyY';
        if (isZ) {
            e.preventDefault();
            const ok = e.shiftKey ? _redo() : _undo();
            if (ok) showToast(e.shiftKey ? 'Rehacer' : 'Deshacer', 'info', 1200);
            return;
        }
        if (isY) {
            e.preventDefault();
            if (_redo()) showToast('Rehacer', 'info', 1200);
            return;
        }
    }

    // Bloquear atajos de edicion mientras la simulacion esta activa
    if (typeof simIsEditingLocked === 'function' && simIsEditingLocked()) {
        // Solo se permiten Escape y la tecla S (seleccionar)
        const editToolKeys = ['r', 'p', 'e', 'd', 'z', 'a', 'm'];
        if (editToolKeys.includes(e.key)) return;
        if (e.key === 'Delete' || e.key === 'Backspace') return;
    }

    const toolMap = { 's': 'select', 'r': 'rack', 'p': 'product', 'e': 'erase', 'd': 'door', 'z': 'dispatch', 'a': 'aisle', 'm': 'move-rack' };
    if (toolMap[e.key]) {
        _setActiveTool(toolMap[e.key]);
        return;
    }

    if (e.key === 'Escape') {
        closeModalNew();
        closeModalGenerate();
        closeModalProduct();
        closeModalOrder();
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

function showToast(msg, type = 'info', duracionMs = 3000) {
    const t = DOM.toast();
    t.textContent  = msg;
    t.className    = `editor-toast editor-toast--${type} editor-toast--show`;
    clearTimeout(_toastTimeout);
    _toastTimeout = setTimeout(() => t.classList.remove('editor-toast--show'), duracionMs);
}

// ── Arrancar cuando el DOM está listo ─────────────────────────────

document.addEventListener('DOMContentLoaded', initEditorUI);


