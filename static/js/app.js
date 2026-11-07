/* ================================================================
   APP.JS
   Lógica global de la aplicación:
   - Theme toggle (oscuro / claro)
   - Speed label del slider
   - Botón del placeholder (atajo a "Nuevo escenario")
   El editor del warehouse se inicializa en editor/ui.js
================================================================ */

// ── Theme toggle ──────────────────────────────────────────────────

const THEME_KEY = "wh-theme";
const btnToggleTheme = document.getElementById("btn-toggle-theme");

function applyTheme(theme) {
    const iconEl = btnToggleTheme.querySelector('.icon');
    if (theme === "light") {
        document.documentElement.setAttribute("data-theme", "light");
        if (iconEl) iconEl.textContent = "dark_mode";
        btnToggleTheme.title = "Cambiar a tema oscuro";
        btnToggleTheme.setAttribute('aria-label', 'Cambiar a tema oscuro');
    } else {
        document.documentElement.removeAttribute("data-theme");
        if (iconEl) iconEl.textContent = "light_mode";
        btnToggleTheme.title = "Cambiar a tema claro";
        btnToggleTheme.setAttribute('aria-label', 'Cambiar a tema claro');
    }
    localStorage.setItem(THEME_KEY, theme);
}

// Restaurar preferencia guardada al cargar la página
applyTheme(localStorage.getItem(THEME_KEY) || "dark");

btnToggleTheme.addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme");
    applyTheme(current === "light" ? "dark" : "light");
});

// ── Speed label ───────────────────────────────────────────────────

const rangeSpeed  = document.getElementById("range-speed");
const speedLabel  = document.getElementById("speed-label");

rangeSpeed?.addEventListener("input", () => {
    speedLabel.textContent = rangeSpeed.value + "×";
});

// ── Sidebar resizable (izquierdo y derecho) ─────────────────────────
// Permite arrastrar el borde de cada sidebar para agrandarlo o achicarlo.
// El mínimo es el tamaño actual; el máximo se define en variables.css.

(function initSidebarResize() {
    const root      = document.documentElement;
    const appLayout = document.querySelector('.app-layout');
    if (!appLayout) return;

    const handles = document.querySelectorAll('.resize-handle');
    if (!handles.length) return;

    function getVar(name, fallback) {
        const v = getComputedStyle(root).getPropertyValue(name).trim();
        return v ? parseFloat(v) : parseFloat(fallback);
    }

    function clamp(value, min, max) {
        return Math.min(Math.max(value, min), max);
    }

    let activeHandle = null;   // 'left' | 'right'

    function onMouseMove(e) {
        if (!activeHandle) return;
        const rect = appLayout.getBoundingClientRect();

        if (activeHandle === 'left') {
            let w = e.clientX - rect.left;
            const min = getVar('--sidebar-w-min', 200);
            const max = getVar('--sidebar-w-max', 450);
            w = clamp(w, min, max);
            root.style.setProperty('--sidebar-w', w + 'px');
        } else if (activeHandle === 'right') {
            let w = rect.right - e.clientX;
            const min = getVar('--sidebar-r-w-min', 220);
            const max = getVar('--sidebar-r-w-max', 480);
            w = clamp(w, min, max);
            root.style.setProperty('--sidebar-r-w', w + 'px');
        }
    }

    function onMouseUp() {
        if (!activeHandle) return;
        activeHandle = null;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
        window.removeEventListener('mousemove', onMouseMove);
        window.removeEventListener('mouseup', onMouseUp);
    }

    handles.forEach(handle => {
        handle.addEventListener('mousedown', (e) => {
            e.preventDefault();
            activeHandle = handle.dataset.handle;
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
            window.addEventListener('mousemove', onMouseMove);
            window.addEventListener('mouseup', onMouseUp);
        });
    });
})();
