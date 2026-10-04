document.getElementById('btn-load').addEventListener('click', async () => {
  const r = await fetch('/api/status');
  const j = await r.json();
  document.getElementById('status').textContent = j.state + ' @ ' + j.ts;
});
