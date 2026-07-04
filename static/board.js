document.querySelectorAll('.slot-cell, #hold-tray').forEach(el => {
  new Sortable(el, {
    group: 'board',
    animation: 150,
    onEnd(evt) {
      const id = evt.item.dataset.id;
      const target = evt.to;
      const payload = target.id === 'hold-tray'
        ? { status: 'hold' }
        : { date: target.dataset.date, slot: target.dataset.slot, status: 'scheduled' };
      fetch(`/block/${id}/move`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      }).then(r => r.json()).then(() => location.reload());
    }
  });
});
