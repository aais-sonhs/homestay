(() => {
    const shell = document.getElementById("app-shell");
    const sidebar = document.getElementById("sidebar");
    const network = document.getElementById("network");
    const networkDot = document.querySelector(".status-dot");
    const navToggle = document.getElementById("nav-toggle");
    const navPanel = document.getElementById("nav-panel");
    const mobileBackdrop = document.getElementById("mobile-backdrop");
    const accountMenu = document.getElementById("account-menu");
    const mobileBreakpoint = matchMedia("(max-width: 900px)");

    function setNavOpen(open, { moveFocus = false } = {}) {
        navPanel?.classList.toggle("is-open", open);
        shell?.classList.toggle("mobile-nav-open", open);
        document.body.classList.toggle("menu-open", open);
        navToggle?.setAttribute("aria-expanded", String(open));
        if (!open) accountMenu?.removeAttribute("open");
        if (moveFocus) {
            const target = open
                ? navPanel?.querySelector('[aria-current="page"]') || navPanel?.querySelector("a, button")
                : navToggle;
            requestAnimationFrame(() => target?.focus({ preventScroll:true }));
        }
    }

    function restoreSidebarState() {
        if (!shell || mobileBreakpoint.matches) return;
        try {
            shell.classList.toggle("sidebar-collapsed", localStorage.getItem("bliss-sidebar-collapsed") === "1");
        } catch (_) {
            shell.classList.remove("sidebar-collapsed");
        }
    }

    navToggle?.addEventListener("click", () => {
        if (mobileBreakpoint.matches) {
            setNavOpen(!navPanel.classList.contains("is-open"), { moveFocus:true });
            return;
        }
        shell?.classList.toggle("sidebar-collapsed");
        try {
            localStorage.setItem("bliss-sidebar-collapsed", shell?.classList.contains("sidebar-collapsed") ? "1" : "0");
        } catch (_) {}
    });

    mobileBackdrop?.addEventListener("click", () => setNavOpen(false, { moveFocus:true }));
    navPanel?.querySelectorAll("a").forEach((link) => link.addEventListener("click", () => {
        if (mobileBreakpoint.matches) setNavOpen(false);
    }));
    navPanel?.addEventListener("keydown", (event) => {
        if (event.key !== "Escape") return;
        if (accountMenu?.open) {
            accountMenu.removeAttribute("open");
        } else if (navPanel.classList.contains("is-open")) {
            event.preventDefault();
            setNavOpen(false, { moveFocus:true });
        }
    });
    mobileBreakpoint.addEventListener?.("change", () => {
        setNavOpen(false);
        restoreSidebarState();
    });
    restoreSidebarState();

    document.addEventListener("click", (event) => {
        if (accountMenu?.open && !accountMenu.contains(event.target)) accountMenu.removeAttribute("open");
    });
    document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape") return;
        if (accountMenu?.open) {
            accountMenu.removeAttribute("open");
            accountMenu.querySelector("summary")?.focus();
        } else if (shell?.classList.contains("mobile-nav-open")) {
            setNavOpen(false, { moveFocus:true });
        }
    });

    document.querySelectorAll("form[data-confirm]").forEach((form) => {
        form.addEventListener("submit", (event) => {
            if (!confirm(form.dataset.confirm)) event.preventDefault();
        });
    });

    function showNetwork() {
        if (!network) return;
        const online = navigator.onLine;
        network.textContent = online ? "Hệ thống trực tuyến" : "Ngoại tuyến — dùng ứng dụng hiện trường";
        network.style.color = online ? "#047857" : "#b91c1c";
        if (networkDot) {
            networkDot.style.background = online ? "#10b981" : "#ef4444";
            networkDot.style.boxShadow = online
                ? "0 0 0 4px rgba(16,185,129,.1)"
                : "0 0 0 4px rgba(239,68,68,.1)";
        }
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
