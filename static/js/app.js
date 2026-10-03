/* ================================================================
   THEME TOGGLE
================================================================ */
const THEME_KEY = "wh-theme";
const btnToggleTheme = document.getElementById("btn-toggle-theme");

function applyTheme(theme) {
    if (theme === "light") {
        document.documentElement.setAttribute("data-theme", "light");
        btnToggleTheme.textContent = "☾";
        btnToggleTheme.title = "Cambiar a tema oscuro";
    } else {
        document.documentElement.removeAttribute("data-theme");
        btnToggleTheme.textContent = "☀";
        btnToggleTheme.title = "Cambiar a tema claro";
    }
    localStorage.setItem(THEME_KEY, theme);
}

// Restaurar preferencia guardada al cargar la página
applyTheme(localStorage.getItem(THEME_KEY) || "dark");

btnToggleTheme.addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme");
    applyTheme(current === "light" ? "dark" : "light");
});