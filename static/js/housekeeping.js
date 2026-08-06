(() => {
    const network = document.getElementById("network");
    const navToggle = document.getElementById("nav-toggle");
    const navPanel = document.getElementById("nav-panel");
    const accountMenu = document.getElementById("account-menu");

    function setNavOpen(open, { moveFocus = false } = {}) {
        navPanel?.classList.toggle("is-open", open);
        navToggle?.setAttribute("aria-expanded", String(open));
        if (navToggle) navToggle.textContent = open ? "✕ Đóng menu" : "☰ Menu";
        if (!open) accountMenu?.removeAttribute("open");
        if (moveFocus) {
            const target = open
                ? navPanel?.querySelector('[aria-current="page"]') || navPanel?.querySelector("a, button")
                : navToggle;
            requestAnimationFrame(() => target?.focus({ preventScroll:true }));
        }
    }

    navToggle?.addEventListener("click", () => {
        setNavOpen(!navPanel?.classList.contains("is-open"), { moveFocus:true });
    });
    navPanel?.addEventListener("keydown", (event) => {
        if (event.key !== "Escape") return;
        if (accountMenu?.open) {
            event.preventDefault();
            accountMenu.removeAttribute("open");
            accountMenu.querySelector("summary")?.focus();
        } else if (navPanel.classList.contains("is-open")) {
            event.preventDefault();
            setNavOpen(false, { moveFocus:true });
        }
    });
    document.addEventListener("click", (event) => {
        if (accountMenu?.open && !accountMenu.contains(event.target)) accountMenu.removeAttribute("open");
    });
    document.querySelectorAll("form[data-confirm]").forEach((form) => {
        form.addEventListener("submit", (event) => {
            if (!confirm(form.dataset.confirm)) event.preventDefault();
        });
    });

    function showNetwork() {
        if (!network) return;
        network.textContent = navigator.onLine ? "● Trực tuyến" : "○ Ngoại tuyến — dùng ứng dụng hiện trường";
        network.style.color = navigator.onLine ? "#16794d" : "#b42318";
    }
    addEventListener("online", showNetwork);
    addEventListener("offline", showNetwork);
    showNetwork();

    const autoRefreshRoot = document.querySelector("[data-auto-refresh-seconds]");
    if (autoRefreshRoot) {
        let hasUnsavedFormInput = false;
        document.addEventListener("input", (event) => {
            if (event.target.closest("form")) hasUnsavedFormInput = true;
        });
        const seconds = Number(autoRefreshRoot.dataset.autoRefreshSeconds || 30);
        setInterval(() => {
            const editing = document.querySelector("input:focus, select:focus, textarea:focus");
            if (navigator.onLine && document.visibilityState === "visible" && !editing && !hasUnsavedFormInput) {
                location.reload();
            }
        }, seconds * 1000);
    }
})();

