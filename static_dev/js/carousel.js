window.initCarousels = function(scope = document) {
    let carousels = [];
    if (scope.querySelectorAll) {
        carousels = Array.from(scope.querySelectorAll('[data-carousel]:not([data-initialized])'));
    }
    if (scope.hasAttribute && scope.hasAttribute('data-carousel') && !scope.hasAttribute('data-initialized')) {
        carousels.push(scope);
    }

    carousels.forEach(carousel => {
        carousel.setAttribute('data-initialized', 'true');
        const card = carousel.closest('.card');
        if (!card) return;

        // Получаем массив URL-адресов
        let imagesUrl = [];
        try {
            const cleanedData = carousel.dataset.images.replace(/\s+/g, ' ').trim();
            imagesUrl = JSON.parse(cleanedData).filter(url => url && url !== '');
        } catch (e) {
            console.error('Ошибка парсинга картинок', e);
            return;
        }

        const totalImages = parseInt(carousel.dataset.totalImages, 10) || 1;
        const dotsContainer = card.querySelector('[data-carousel-dots]');
        const dotElements = dotsContainer ? dotsContainer.querySelectorAll('[data-dot-index]') : [];

        // Скрываем лишние точки
        if (totalImages !== dotElements.length) {
            dotElements.forEach((dot, index) => {
                if (index >= totalImages) dot.style.display = 'none';
            });
        }

        if (totalImages <= 1) {
            if (dotElements[0]) {
                dotElements[0].classList.add('bg-black');
                dotElements[0].classList.remove('bg-black/20');
            }
            return;
        }

        let currentIndex = 0;
        let imagesLoaded = false; // Флаг: загружены ли доп. фото

        // --- Функция загрузки изображений (LAZY LOAD) ---
        function loadImages() {
            if (imagesLoaded) return;
            
            // Начинаем с 1, так как 0 (главная) уже есть
            for (let i = 1; i < imagesUrl.length; i++) {
                const img = document.createElement('img');
                img.src = imagesUrl[i];
                img.alt = 'Preview';
                // Стили: такая же позиция, но z-0 (под главной)
                img.className = 'absolute w-full h-full object-cover transition-all duration-200 z-0';
                img.setAttribute('data-carousel-image', i);
                carousel.appendChild(img);
            }
            imagesLoaded = true;
        }

        // --- Обновление карусели ---
        function updateCarousel(newIndex) {
            if (newIndex === currentIndex || newIndex < 0 || newIndex >= totalImages) return;

            // Если пытаемся показать фото, которого нет в DOM (не загрузилось), загружаем принудительно
            if (!imagesLoaded && newIndex > 0) {
                loadImages();
            }

            // Ищем картинки (теперь динамически, т.к. они могли только что появиться)
            const currentImg = carousel.querySelector(`[data-carousel-image="${currentIndex}"]`);
            const nextImg = carousel.querySelector(`[data-carousel-image="${newIndex}"]`);

            // Скрываем текущую
            if (currentImg) {
                currentImg.classList.replace('z-10', 'z-0');
                if (dotElements[currentIndex]) {
                    dotElements[currentIndex].classList.replace('bg-black', 'bg-black/20');
                }
            }

            // Показываем новую
            if (nextImg) {
                nextImg.classList.replace('z-0', 'z-10');
                if (dotElements[newIndex]) {
                    dotElements[newIndex].classList.replace('bg-black/20', 'bg-black');
                }
            }
            currentIndex = newIndex;
        }

        // --- События ---

        // 1. LAZY LOAD при наведении мыши на карточку
        // Используем mouseenter на самой карточке или карусели
        carousel.addEventListener('mouseenter', () => {
            loadImages();
        });

        // 2. Клики по точкам
        dotElements.forEach((dot, index) => {
            dot.addEventListener('click', (e) => {
                e.preventDefault();
                // Если кликнули, а мышь не наводили (тачскрин), тоже грузим
                loadImages(); 
                updateCarousel(index);
            });
        });

        // 3. Движение мыши
        let isProcessing = false;
        carousel.addEventListener('mousemove', (e) => {
            if (e.target.closest('.group\\/fire')) return;
            if (isProcessing) return;
            
            isProcessing = true;
            requestAnimationFrame(() => {
                const rect = carousel.getBoundingClientRect();
                if (rect.width === 0) { isProcessing = false; return; }

                const zoneWidth = rect.width / totalImages;
                const relativeX = e.clientX - rect.left;
                const zoneIndex = Math.floor(relativeX / zoneWidth);
                const safeIndex = Math.max(0, Math.min(zoneIndex, totalImages - 1));
                
                updateCarousel(safeIndex);
                isProcessing = false;
            });
        });

        carousel.addEventListener('mouseleave', () => updateCarousel(0));
        
        // Начальная установка активной точки
        if (dotElements[0]) {
             dotElements[0].classList.add('bg-black');
             dotElements[0].classList.remove('bg-black/20');
        }
    });
};

// --- ГАРАНТИРОВАННАЯ ИНИЦИАЛИЗАЦИЯ ---
(function() {
    function init() {
        // Запускаем для всего документа
        window.initCarousels(document);
        
        // Пытаемся подключиться к HTMX
        if (typeof htmx !== 'undefined') {
            htmx.onLoad(function(content) {
                window.initCarousels(content);
            });
        }
    }

    // Если скрипт загружен после полной загрузки страницы
    if (document.readyState === 'complete' || document.readyState === 'interactive') {
        init();
    } else {
        document.addEventListener('DOMContentLoaded', init);
    }
})();