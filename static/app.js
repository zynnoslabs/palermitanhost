// app.js — helpers generales de RentaIA

// Auto-cierra alertas después de 5 segundos
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.alert').forEach(el => {
    setTimeout(() => { el.style.opacity='0'; el.style.transition='opacity .4s';
      setTimeout(() => el.remove(), 400); }, 5000);
  });
});
