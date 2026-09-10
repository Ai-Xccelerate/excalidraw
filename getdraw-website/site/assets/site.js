const menuButton = document.querySelector("[data-menu-button]");
const menu = document.querySelector("[data-menu]");

if (menuButton && menu) {
  menuButton.addEventListener("click", () => {
    const isOpen = menuButton.getAttribute("aria-expanded") === "true";
    menuButton.setAttribute("aria-expanded", String(!isOpen));
    menu.toggleAttribute("data-open", !isOpen);
  });

  menu.addEventListener("click", (event) => {
    if (event.target.closest("a")) {
      menuButton.setAttribute("aria-expanded", "false");
      menu.removeAttribute("data-open");
    }
  });
}

const revealObserver = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.setAttribute("data-visible", "");
        revealObserver.unobserve(entry.target);
      }
    });
  },
  { rootMargin: "0px 0px -8%", threshold: 0.08 },
);

document.querySelectorAll("[data-reveal]").forEach((element) => {
  revealObserver.observe(element);
});

document.querySelectorAll("[data-faq-button]").forEach((button) => {
  button.addEventListener("click", () => {
    const item = button.closest(".faq-item");
    const open = item.hasAttribute("data-open");
    document.querySelectorAll(".faq-item[data-open]").forEach((current) => {
      current.removeAttribute("data-open");
      current
        .querySelector("[data-faq-button]")
        ?.setAttribute("aria-expanded", "false");
    });
    if (!open) {
      item.setAttribute("data-open", "");
      button.setAttribute("aria-expanded", "true");
    }
  });
});

const year = document.querySelector("[data-year]");
if (year) {
  year.textContent = String(new Date().getFullYear());
}
