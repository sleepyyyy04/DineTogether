(function () {
  function initRestaurantFilters() {
    const list = document.querySelector(".restaurant-list");
    if (!list) return;

    const sortBy = document.getElementById("sort-by");
    if (!sortBy) return;
    const items = Array.from(list.querySelectorAll(".restaurant"));
    const originalOrder = items.slice();

    function apply() {
      const sort = sortBy.value || "recommended";

      let ordered = originalOrder;
      if (sort !== "recommended") {
        ordered = items.slice().sort((a, b) => {
          if (sort === "rating") {
            return (Number(b.dataset.rating) || 0) - (Number(a.dataset.rating) || 0);
          }
          if (sort === "distance") {
            return (Number(a.dataset.distance) || 0) - (Number(b.dataset.distance) || 0);
          }
          if (sort === "name") {
            return (a.dataset.name || "").localeCompare(b.dataset.name || "");
          }
          return 0;
        });
      }
      ordered.forEach((li) => list.appendChild(li));
    }

    sortBy.addEventListener("change", apply);
  }

  function initCuisineDropdowns() {
    const dropdowns = Array.from(document.querySelectorAll(".dropdown-checklist"));
    if (!dropdowns.length) return;

    dropdowns.forEach((details) => {
      const summary = details.querySelector("summary");
      if (!summary) return;
      const placeholder = summary.dataset.placeholder || summary.textContent.trim();
      const checkboxes = Array.from(details.querySelectorAll('input[type="checkbox"]'));

      function updateSummary() {
        const selected = checkboxes
          .filter((cb) => cb.checked)
          .map((cb) => {
            const span = cb.nextElementSibling;
            return span ? span.textContent.trim() : cb.value;
          });

        if (!selected.length) {
          summary.textContent = placeholder;
        } else if (selected.length <= 3) {
          summary.textContent = selected.join(", ");
        } else {
          summary.textContent = `${selected.slice(0, 3).join(", ")} +${selected.length - 3} more`;
        }
      }

      checkboxes.forEach((cb) => cb.addEventListener("change", updateSummary));
      updateSummary();
    });

    document.addEventListener("click", (event) => {
      dropdowns.forEach((details) => {
        if (details.open && !details.contains(event.target)) {
          details.removeAttribute("open");
        }
      });
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    initRestaurantFilters();
    initCuisineDropdowns();
  });
})();
