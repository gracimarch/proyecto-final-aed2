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
