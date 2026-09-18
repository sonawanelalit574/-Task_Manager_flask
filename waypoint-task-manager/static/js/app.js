(() => {
  const token = document.querySelector('meta[name="csrf-token"]')?.getAttribute("content");
  const board = document.querySelector("[data-board]");
  if (!board) return;

  let dragged = null;

  board.querySelectorAll(".task-card").forEach((card) => {
    card.addEventListener("dragstart", () => {
      dragged = card;
      card.classList.add("dragging");
    });
    card.addEventListener("dragend", () => {
      card.classList.remove("dragging");
      dragged = null;
      board.querySelectorAll(".column").forEach((col) => col.classList.remove("over"));
    });
  });

  board.querySelectorAll("[data-drop]").forEach((list) => {
    const column = list.closest(".column");
    list.addEventListener("dragover", (event) => {
      event.preventDefault();
      column.classList.add("over");
    });
    list.addEventListener("dragleave", () => column.classList.remove("over"));
    list.addEventListener("drop", async (event) => {
      event.preventDefault();
      column.classList.remove("over");
      if (!dragged) return;
      list.appendChild(dragged);
      const taskId = dragged.dataset.taskId;
      const status = column.dataset.status;
      const position = [...list.children].indexOf(dragged);
      await fetch(`/tasks/${taskId}/move`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": token || "",
        },
        body: JSON.stringify({ status, position }),
      });
    });
  });
})();
