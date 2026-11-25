(() => {
  document.querySelectorAll('[data-auto-dismiss]').forEach((element) => {
    const delay = Number(element.dataset.autoDismiss) || 3500;
    window.setTimeout(() => {
      element.classList.add('alert-leaving');
      window.setTimeout(() => element.remove(), 260);
    }, delay);
  });
})();
