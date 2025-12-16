document.addEventListener('htmx:afterSwap', function(evt) {
    // Если обновился каталог, скроллим вверх
    if (evt.detail.target.id === 'catalog-content') {
        const catalogElement = document.getElementById('catalog-content');
        if (catalogElement) {
            const offset = catalogElement.offsetTop - 100;
            window.scrollTo({
                top: offset > 0 ? offset : 0,
                behavior: 'smooth'
            });
        }
    }
});

document.addEventListener('htmx:responseError', function(evt) {
    console.error('HTMX Error:', evt.detail);
});