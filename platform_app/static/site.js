(function () {
  const key = "coachingos-theme";
  const logoKeyPrefix = "coachingos-tenant-logo-";
  const presentationKey = "coachingos-presentation-mode";
  const sidebarKey = "coachingos-sidebar-collapsed";
  const densityKey = "coachingos-compact-density";
  const tourKey = "coachingos-tour-complete-v1";
  const body = document.body;
  const tenantSlug = body.getAttribute("data-tenant-slug") || "";
  const toggle = document.querySelector("[data-theme-toggle]");
  const icon = toggle ? toggle.querySelector("i") : null;
  const presentationToggle = document.querySelector("[data-presentation-toggle]");
  const sidebarToggle = document.querySelector("[data-sidebar-toggle]");
  const densityToggle = document.querySelector("[data-density-toggle]");
  const logoOpen = document.querySelector("[data-logo-open]");
  const logoBackdrop = document.querySelector("[data-logo-backdrop]");
  const logoModal = document.querySelector("[data-logo-modal]");
  const logoForm = document.querySelector("[data-logo-form]");
  const logoCancel = document.querySelector("[data-logo-cancel]");
  const logoClear = document.querySelector("[data-logo-clear]");
  const logoImg = document.querySelector("[data-tenant-logo]");
  const tourStartBtn = document.querySelector("[data-tour-start]");
  const tourBackdrop = document.querySelector("[data-tour-backdrop]");
  const tourCard = document.querySelector("[data-tour-card]");
  const tourTitle = document.querySelector("[data-tour-title]");
  const tourBody = document.querySelector("[data-tour-body]");
  const tourNext = document.querySelector("[data-tour-next]");
  const tourSkip = document.querySelector("[data-tour-skip]");
  const counterEls = document.querySelectorAll("[data-count-to]");

  function applyTheme(theme) {
    const mode = theme === "light" ? "light" : "dark";
    body.classList.toggle("theme-light", mode === "light");
    if (icon) {
      icon.className = mode === "light" ? "bi bi-sun-fill" : "bi bi-moon-stars-fill";
    }
    if (toggle) {
      toggle.setAttribute("aria-label", mode === "light" ? "Switch to dark theme" : "Switch to light theme");
      toggle.setAttribute("title", mode === "light" ? "Light theme" : "Dark theme");
    }
  }

  const saved = localStorage.getItem(key);
  if (saved) {
    applyTheme(saved);
  } else {
    applyTheme("dark");
  }

  if (toggle) {
    toggle.addEventListener("click", function () {
      const next = body.classList.contains("theme-light") ? "dark" : "light";
      localStorage.setItem(key, next);
      applyTheme(next);
    });
  }

  function setPresentationMode(enabled) {
    body.classList.toggle("presentation-mode", Boolean(enabled));
    if (presentationToggle) {
      presentationToggle.setAttribute("title", enabled ? "Exit presentation mode" : "Enter presentation mode");
      presentationToggle.setAttribute("aria-label", enabled ? "Exit presentation mode" : "Enter presentation mode");
    }
    localStorage.setItem(presentationKey, enabled ? "1" : "0");
  }

  function setSidebarCollapsed(enabled) {
    body.classList.toggle("sidebar-collapsed", Boolean(enabled));
    if (sidebarToggle) {
      sidebarToggle.setAttribute("title", enabled ? "Expand sidebar" : "Collapse sidebar");
      sidebarToggle.setAttribute("aria-label", enabled ? "Expand sidebar" : "Collapse sidebar");
      const sidebarIcon = sidebarToggle.querySelector("i");
      if (sidebarIcon) {
        sidebarIcon.className = enabled ? "bi bi-layout-sidebar" : "bi bi-layout-sidebar-inset";
      }
    }
    localStorage.setItem(sidebarKey, enabled ? "1" : "0");
  }

  function setCompactDensity(enabled) {
    body.classList.toggle("compact-density", Boolean(enabled));
    if (densityToggle) {
      densityToggle.setAttribute("title", enabled ? "Disable compact tables" : "Enable compact tables");
      densityToggle.setAttribute("aria-label", enabled ? "Disable compact tables" : "Enable compact tables");
      const densityIcon = densityToggle.querySelector("i");
      if (densityIcon) {
        densityIcon.className = enabled ? "bi bi-table" : "bi bi-tablet";
      }
    }
    localStorage.setItem(densityKey, enabled ? "1" : "0");
  }

  if (presentationToggle) {
    presentationToggle.addEventListener("click", function () {
      setPresentationMode(!body.classList.contains("presentation-mode"));
    });
  }

  if (sidebarToggle) {
    sidebarToggle.addEventListener("click", function () {
      setSidebarCollapsed(!body.classList.contains("sidebar-collapsed"));
    });
  }
  if (densityToggle) {
    densityToggle.addEventListener("click", function () {
      setCompactDensity(!body.classList.contains("compact-density"));
    });
  }

  function hashHue(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i += 1) {
      hash = (hash << 5) - hash + str.charCodeAt(i);
      hash |= 0;
    }
    return Math.abs(hash) % 360;
  }

  function applyTenantBranding() {
    const slug = tenantSlug;
    if (!slug) return;
    const hue = hashHue(slug);
    const accent = `hsl(${hue} 88% 64%)`;
    const accentTwo = `hsl(${(hue + 35) % 360} 82% 62%)`;
    body.style.setProperty("--accent", accent);
    body.style.setProperty("--accent-2", accentTwo);
  }

  function logoStorageKey() {
    return `${logoKeyPrefix}${tenantSlug}`;
  }

  function applyTenantLogo() {
    if (!tenantSlug || !logoImg) return;
    const value = localStorage.getItem(logoStorageKey());
    if (value) {
      logoImg.src = value;
      logoImg.hidden = false;
    } else {
      logoImg.hidden = true;
      logoImg.removeAttribute("src");
    }
  }

  function openLogoModal() {
    if (!logoModal || !logoBackdrop || !logoForm) return;
    const field = logoForm.elements.logo_url;
    if (field) field.value = localStorage.getItem(logoStorageKey()) || "";
    logoBackdrop.hidden = false;
    logoModal.hidden = false;
  }

  function closeLogoModal() {
    if (logoModal) logoModal.hidden = true;
    if (logoBackdrop) logoBackdrop.hidden = true;
  }

  if (logoOpen) logoOpen.addEventListener("click", openLogoModal);
  if (logoCancel) logoCancel.addEventListener("click", closeLogoModal);
  if (logoBackdrop) logoBackdrop.addEventListener("click", closeLogoModal);
  if (logoClear) {
    logoClear.addEventListener("click", function () {
      if (!tenantSlug) return;
      localStorage.removeItem(logoStorageKey());
      applyTenantLogo();
      closeLogoModal();
    });
  }
  if (logoForm) {
    logoForm.addEventListener("submit", function (event) {
      event.preventDefault();
      if (!tenantSlug) return;
      const field = logoForm.elements.logo_url;
      const value = field ? String(field.value || "").trim() : "";
      if (value) {
        localStorage.setItem(logoStorageKey(), value);
      } else {
        localStorage.removeItem(logoStorageKey());
      }
      applyTenantLogo();
      closeLogoModal();
    });
  }

  function animateCount(el) {
    const target = Number(el.getAttribute("data-count-to"));
    if (Number.isNaN(target)) return;
    const decimals = Number(el.getAttribute("data-count-decimals") || 0);
    const suffix = el.getAttribute("data-count-suffix") || "";
    const duration = 850;
    const startTime = performance.now();
    const startVal = 0;
    function tick(now) {
      const t = Math.min(1, (now - startTime) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      const current = startVal + (target - startVal) * eased;
      el.textContent = `${current.toFixed(decimals)}${suffix}`;
      if (t < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  function initCounters() {
    counterEls.forEach((el) => animateCount(el));
  }

  function initKpiRings() {
    const rings = document.querySelectorAll("[data-kpi-pct]");
    rings.forEach((ring) => {
      const pct = Number(ring.getAttribute("data-kpi-pct"));
      if (!Number.isNaN(pct)) {
        const safePct = Math.max(0, Math.min(100, pct));
        ring.style.setProperty("--pct", String(safePct));
      }
    });
  }

  const tourSteps = [
    {
      selector: "#tour-sidebar",
      title: "Navigation Command Rail",
      body: "Access coaching operations, governance, integrations, and billing from this persistent sidebar.",
    },
    {
      selector: "#tour-topbar",
      title: "Executive Context Header",
      body: "Switch themes, review workspace scope, and launch high-priority actions from the topbar.",
    },
    {
      selector: "#tour-content",
      title: "Operational Work Surface",
      body: "This area adapts by role to show KPIs, queues, and workflows for enterprise execution.",
    },
  ];
  let tourIndex = 0;
  let activeHighlight = null;

  function clearHighlight() {
    if (activeHighlight) activeHighlight.classList.remove("tour-highlight");
    activeHighlight = null;
  }

  function showTourStep() {
    if (!tourCard || !tourBackdrop || !tourTitle || !tourBody || !tourNext) return;
    const step = tourSteps[tourIndex];
    if (!step) return;
    clearHighlight();
    const target = document.querySelector(step.selector);
    if (target) {
      target.classList.add("tour-highlight");
      activeHighlight = target;
    }
    tourTitle.textContent = step.title;
    tourBody.textContent = step.body;
    tourNext.textContent = tourIndex === tourSteps.length - 1 ? "Finish" : "Next";
    tourBackdrop.hidden = false;
    tourCard.hidden = false;
  }

  function closeTour(markComplete) {
    if (tourBackdrop) tourBackdrop.hidden = true;
    if (tourCard) tourCard.hidden = true;
    clearHighlight();
    if (markComplete) localStorage.setItem(tourKey, "1");
  }

  function nextTourStep() {
    if (tourIndex >= tourSteps.length - 1) {
      closeTour(true);
      return;
    }
    tourIndex += 1;
    showTourStep();
  }

  if (tourStartBtn) {
    tourStartBtn.addEventListener("click", function () {
      tourIndex = 0;
      showTourStep();
    });
  }
  if (tourNext) tourNext.addEventListener("click", nextTourStep);
  if (tourSkip) {
    tourSkip.addEventListener("click", function () {
      closeTour(true);
    });
  }
  if (tourBackdrop) {
    tourBackdrop.addEventListener("click", function () {
      closeTour(false);
    });
  }

  if (!localStorage.getItem(tourKey) && tenantSlug) {
    setTimeout(function () {
      tourIndex = 0;
      showTourStep();
    }, 450);
  }

  if (localStorage.getItem(presentationKey) === "1") {
    setPresentationMode(true);
  }
  if (localStorage.getItem(sidebarKey) === "1") {
    setSidebarCollapsed(true);
  } else {
    setSidebarCollapsed(false);
  }
  if (localStorage.getItem(densityKey) === "1") {
    setCompactDensity(true);
  } else {
    setCompactDensity(false);
  }
  applyTenantBranding();
  applyTenantLogo();
  initCounters();
  initKpiRings();
})();

