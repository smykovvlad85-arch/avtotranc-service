const menu = document.querySelector(".mobile-menu");
const toggle = menu.querySelector("summary");

document.addEventListener("click", (event) => {
  if (menu.open && (!menu.contains(event.target) || event.target.closest("nav a"))) {
    menu.open = false;
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && menu.open) {
    menu.open = false;
    toggle.focus();
  }
});

window.addEventListener("hashchange", () => { menu.open = false; });
