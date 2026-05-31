(function () {
    function markActiveNav() {
        var path = window.location.pathname;
        document.querySelectorAll(".admin-primary-nav a, .sidebar-quick-links a").forEach(function (link) {
            var target = link.getAttribute("data-admin-path");
            if (!target) {
                target = link.getAttribute("href");
            }
            if (!target) {
                return;
            }
            if (target === "/admin/") {
                if (path === "/admin/" || path.indexOf("/admin/home/") === 0 || path.indexOf("/admin/auth/") === 0) {
                    link.classList.add("is-active");
                }
                return;
            }
            if (path.indexOf(target) === 0) {
                link.classList.add("is-active");
            }
        });
    }

    function enhanceSidebar() {
        var sidebar = document.getElementById("nav-sidebar");
        var toggle = document.getElementById("toggle-nav-sidebar");
        if (sidebar && !sidebar.hasAttribute("aria-expanded")) {
            sidebar.setAttribute("aria-expanded", window.innerWidth > 900 ? "true" : "false");
        }
        if (toggle && sidebar) {
            toggle.addEventListener("click", function () {
                var expanded = sidebar.getAttribute("aria-expanded") !== "false";
                sidebar.setAttribute("aria-expanded", expanded ? "false" : "true");
            });
        }

        var filter = document.getElementById("nav-filter");
        if (!filter) {
            return;
        }
        filter.addEventListener("input", function () {
            var query = filter.value.trim().toLowerCase();
            document.querySelectorAll(".sidebar-quick-links a, #nav-sidebar .module tr").forEach(function (item) {
                var text = item.textContent.toLowerCase();
                item.style.display = !query || text.indexOf(query) !== -1 ? "" : "none";
            });
            document.querySelectorAll(".sidebar-section-title").forEach(function (title) {
                var links = title.nextElementSibling;
                if (!links || !links.classList.contains("sidebar-quick-links")) {
                    return;
                }
                var visible = Array.prototype.some.call(links.querySelectorAll("a"), function (link) {
                    return link.style.display !== "none";
                });
                title.style.display = !query || visible ? "" : "none";
                links.style.display = !query || visible ? "" : "none";
            });
        });
    }

    function addMobileTableLabels() {
        document.querySelectorAll("table").forEach(function (table) {
            var headers = Array.prototype.map.call(table.querySelectorAll("thead th"), function (th) {
                return th.textContent.trim();
            });
            if (!headers.length) {
                return;
            }
            table.querySelectorAll("tbody tr").forEach(function (row) {
                row.querySelectorAll("td, th").forEach(function (cell, index) {
                    if (headers[index] && !cell.hasAttribute("data-label")) {
                        cell.setAttribute("data-label", headers[index]);
                    }
                });
            });
        });
    }

    function annotateAdminForms() {
        var path = window.location.pathname;
        if (path.indexOf("/admin/home/user/add/") !== -1) {
            document.body.classList.add("admin-add-user");
            var roleField = document.querySelector('[name="role"]');
            if (!roleField || roleField.value === "doctor" || window.location.search.indexOf("role=doctor") !== -1) {
                document.body.classList.add("admin-add-doctor");
            }
            if (roleField) {
                roleField.addEventListener("change", function () {
                    document.body.classList.toggle("admin-add-doctor", this.value === "doctor");
                });
            }
        }
    }

    function passwordStrengthText(value) {
        var score = 0;
        if (value.length >= 8) score += 1;
        if (/[a-z]/.test(value)) score += 1;
        if (/[A-Z]/.test(value)) score += 1;
        if (/[0-9]/.test(value)) score += 1;
        if (/[@+\-#$%&!]/.test(value)) score += 1;
        if (score < 3) return ["Weak password", "weak"];
        if (score < 5) return ["Medium strength", "medium"];
        return ["Strong password", "strong"];
    }

    function enhancePasswordFields() {
        document.querySelectorAll('input[type="password"]').forEach(function (input) {
            input.addEventListener("input", function () {
                var existing = input.parentElement.querySelector(".password-strength");
                if (existing) {
                    existing.remove();
                }
                if (!input.value) {
                    return;
                }
                var result = passwordStrengthText(input.value);
                var indicator = document.createElement("div");
                indicator.className = "password-strength " + result[1];
                indicator.textContent = result[0];
                input.parentElement.appendChild(indicator);
            });
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        markActiveNav();
        enhanceSidebar();
        addMobileTableLabels();
        annotateAdminForms();
        enhancePasswordFields();
    });
})();
