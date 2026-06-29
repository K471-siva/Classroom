// =========================
// SHARED REALTIME + TOASTS
// One socket per page. Templates call showToast(...) instead of
// opening their own WebSocket (which caused duplicate notifications).
// =========================

(function () {

    // Ensure a single toast container exists

    function toastStack() {

        let stack = document.getElementById("toast-stack");

        if (!stack) {
            stack = document.createElement("div");
            stack.id = "toast-stack";
            document.body.appendChild(stack);
        }

        return stack;
    }

    // Public: show a stacking, auto-dismissing toast

    window.showToast = function (message, timeout) {

        const stack = toastStack();

        const toast = document.createElement("div");
        toast.className = "toast";
        toast.textContent = message;

        // Click to dismiss early
        toast.addEventListener("click", () => dismiss(toast));

        stack.appendChild(toast);

        setTimeout(() => dismiss(toast), timeout || 5000);
    };

    function dismiss(toast) {

        if (!toast || toast.classList.contains("leaving")) {
            return;
        }

        toast.classList.add("leaving");
        setTimeout(() => toast.remove(), 350);
    }

    // =========================
    // COLLAPSIBLE SECTIONS
    // Toggle a .collapse-body by id; swaps the toggle button label.
    // =========================

    window.toggleCollapse = function (bodyId, btn) {

        const body = document.getElementById(bodyId);
        if (!body) { return; }

        const collapsed = body.classList.toggle("collapsed");

        if (btn) {
            btn.textContent = collapsed ? "+" : "−";
        }
    };

    // =========================
    // WEBSOCKET (single connection, auto-reconnect)
    // =========================

    let socket;

    function connect() {

        const proto =
            window.location.protocol === "https:" ? "wss" : "ws";

        socket = new WebSocket(
            proto + "://" + window.location.host + "/ws"
        );

        socket.onopen = () => {
            console.log("✅ WebSocket Connected");
        };

        socket.onmessage = (event) => {
            console.log("Realtime:", event.data);
            window.showToast(event.data);
        };

        socket.onclose = () => {
            console.log("❌ WebSocket closed — retrying in 3s");
            setTimeout(connect, 3000);
        };

        socket.onerror = () => {
            socket.close();
        };
    }

    connect();
})();
