(function () {
    // Храним инстанс карты, чтобы удалять его при обновлении
    window.myMapInstance = null;
    window.placemarkInstance = null;
    let searchControl = null;

    // --- КОНСТАНТЫ ---
    const SAFU_ADDRESS = 'Архангельская область, Северодвинск, улица Капитана Воронина, 6';
    const SAFU_COORDS = [64.562961, 39.803955];
    const SEVERODVINSK_CENTER = [64.5635, 39.8256];
    const SEVERODVINSK_BOUNDS = [[64.50, 39.65], [64.65, 40.00]];

    // --- ГЛАВНАЯ ФУНКЦИЯ ИНИЦИАЛИЗАЦИИ ---
    window.initMapLogic = function () {
        // 1. Ищем контейнер
        const mapContainer = document.getElementById('map');

        // Если контейнера нет (HTMX еще не загрузил форму) — выходим
        if (!mapContainer) return;

        // 2. Ждем загрузки API Яндекса
        if (typeof ymaps === 'undefined') {
            // Если API еще грузится, пробуем снова через 100мс
            setTimeout(window.initMapLogic, 100);
            return;
        }

        // 3. Если карта уже была создана, проверяем, жива ли она
        if (window.myMapInstance) {
            // Если контейнер карты исчез из DOM (HTMX перезаписал его), убиваем старый инстанс
            try {
                if (!document.body.contains(window.myMapInstance.container.getElement())) {
                    window.myMapInstance.destroy();
                    window.myMapInstance = null;
                    window.placemarkInstance = null;
                } else {
                    // Карта уже есть и она на месте — выходим, чтобы не дублировать
                    return;
                }
            } catch (e) {
                // Если ошибка доступа к контейнеру — точно убиваем
                window.myMapInstance = null;
            }
        }

        // 4. Если мы здесь — значит API готов, контейнер есть, карты нет. Создаем!
        ymaps.ready(() => {
            try {
                mapContainer.innerHTML = '';
                createMap();
            } catch (e) {
                console.error('Ошибка создания карты:', e);
            }
        });
    };

    function createMap() {
        window.myMapInstance = new ymaps.Map("map", {
            center: SEVERODVINSK_CENTER,
            zoom: 13,
            controls: ['zoomControl']
        });

        searchControl = new ymaps.control.SearchControl({
            options: {
                provider: 'yandex#search',
                noPlacemark: true,
                boundedBy: SEVERODVINSK_BOUNDS,
                strictBounds: true,
                placeholderContent: 'Введите адрес (улица, дом)',
                fitMaxWidth: true,
                noPopup: true
            }
        });

        window.myMapInstance.controls.add(searchControl);

        // Твой фикс для выпадающего списка
        searchControl.events.add('load', function (e) {
            if (e.get('count') > 0) {
                searchControl.state.set('resultsIsOpen', true);
                setTimeout(function () {
                    const listButton = document.querySelector('ymaps[class*="searchbox-list-button"]');
                    if (listButton) {
                        const clickEvent = new MouseEvent('click', {
                            bubbles: true, cancelable: true, view: window
                        });
                        listButton.dispatchEvent(clickEvent);
                    }
                }, 200);
            }
        });

        searchControl.events.add('resultselect', handleSearchResult);
        window.myMapInstance.events.add('click', handleMapClick);

        // Инициализируем слушатели формы
        initFormListeners();

        // Проверяем начальное состояние
        const buyingType = document.getElementById('id_buying_type')?.value;
        const currentAddress = document.getElementById('address')?.value;

        if (buyingType === 'self') {
            handleBuyingTypeChange();
        }
        else if (currentAddress && currentAddress.trim() !== '' && currentAddress !== SAFU_ADDRESS) {
            let searchContext = currentAddress;
            if (!currentAddress.toLowerCase().includes('северодвинск')) {
                searchContext = 'Северодвинск, ' + currentAddress;
            }
            ymaps.geocode(searchContext, { boundedBy: SEVERODVINSK_BOUNDS }).then(res => {
                const firstGeoObject = res.geoObjects.get(0);
                if (firstGeoObject) {
                    const coords = firstGeoObject.geometry.getCoordinates();
                    // Ставим метку, но не перезаписываем текст, чтобы не сбивать пользователя
                    setAddressVisuals(coords);
                }
            });
        }
    }

    // --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

    function cleanAddressString(address) {
        if (!address) return '';
        let clean = address.replace(/^Россия,\s*/, '').replace('Архангельская область, ', '');
        let parts = clean.split(',').map(part => part.trim());
        return [...new Set(parts)].join(', ');
    }

    function handleSearchResult(e) {
        const index = e.get('index');
        searchControl.getResult(index).then(res => {
            let rawAddress = res.properties.get('text') || res.properties.get('name');
            const finalAddress = cleanAddressString(rawAddress);
            const coords = res.geometry.getCoordinates();
            setAddress(finalAddress, coords);
            searchControl.clear();
        });
    }

    function handleMapClick(e) {
        // Если самовывоз — клики не работают
        const type = document.getElementById('id_buying_type')?.value;
        if (type === 'self') return;

        const coords = e.get('coords');
        ymaps.geocode(coords).then(res => {
            const firstGeoObject = res.geoObjects.get(0);
            let rawAddress = firstGeoObject ? firstGeoObject.properties.get('text') : 'Адрес не найден';
            const finalAddress = cleanAddressString(rawAddress);
            setAddress(finalAddress, coords);
        });
    }

    // Устанавливает только метку на карте (без текста в инпуте)
    function setAddressVisuals(coords) {
        if (window.placemarkInstance) {
            window.myMapInstance.geoObjects.remove(window.placemarkInstance);
        }
        window.placemarkInstance = new ymaps.Placemark(coords, {
            iconCaption: 'Адрес доставки'
        }, { preset: 'islands#blueDotIcon', hasBalloon: false });
        window.myMapInstance.geoObjects.add(window.placemarkInstance);
        window.myMapInstance.setCenter(coords, 16);
    }

    function setAddress(address, coords, zoom = 16, isSafu = false) {
        const addrInput = document.getElementById('address');
        const addrText = document.getElementById('address-text');
        const errMsg = document.getElementById('error-message');

        if (addrInput) addrInput.value = address;
        if (addrText) addrText.textContent = address;
        if (errMsg) errMsg.style.display = 'none';

        if (window.placemarkInstance) {
            window.myMapInstance.geoObjects.remove(window.placemarkInstance);
        }

        let placemarkOptions = isSafu
            ? { preset: 'islands#blueEducationIcon', iconColor: '#2563eb', hasBalloon: false }
            : { preset: 'islands#blueDotIcon', hasBalloon: false };

        window.placemarkInstance = new ymaps.Placemark(coords, {
            iconCaption: isSafu ? 'Пункт выдачи (ИСМАРТ)' : 'Адрес доставки'
        }, placemarkOptions);

        window.myMapInstance.geoObjects.add(window.placemarkInstance);

        window.myMapInstance.panTo(coords, { duration: 500 }).then(() => {
            window.myMapInstance.setZoom(zoom, { duration: 300 });
        });
    }

    function handleBuyingTypeChange() {
        const select = document.getElementById('id_buying_type');
        const mapDiv = document.getElementById('map');
        if (!select || !window.myMapInstance || !mapDiv) return;

        if (select.value === 'self') {
            setAddress(SAFU_ADDRESS, SAFU_COORDS, 16, true);
            // Важно: обновляем скрытый input для бэкенда
            const addrInput = document.getElementById('address');
            if (addrInput) addrInput.value = SAFU_ADDRESS;

            window.myMapInstance.behaviors.disable(['drag', 'scrollZoom', 'dblClickZoom', 'multiTouch']);
            if (searchControl) searchControl.options.set('visible', false);

            mapDiv.classList.add('opacity-80', 'pointer-events-none');
        } else {
            window.myMapInstance.behaviors.enable(['drag', 'scrollZoom', 'dblClickZoom', 'multiTouch']);
            if (searchControl) searchControl.options.set('visible', true);

            mapDiv.classList.remove('opacity-80', 'pointer-events-none');

            const currentVal = document.getElementById('address').value;
            if (currentVal === SAFU_ADDRESS) {
                document.getElementById('address').value = '';
                document.getElementById('address-text').textContent = 'Не выбран';
                if (window.placemarkInstance) {
                    window.myMapInstance.geoObjects.remove(window.placemarkInstance);
                    window.placemarkInstance = null;
                }
                window.myMapInstance.setCenter(SEVERODVINSK_CENTER, 13, { duration: 300 });
            }
        }
    }

    function initFormListeners() {
        // Логика типа доставки
        const buyingTypeSelect = document.getElementById('id_buying_type');
        if (buyingTypeSelect) {
            // Удаляем старый листенер, чтобы не дублировать при HTMX свопах
            buyingTypeSelect.removeEventListener('change', handleBuyingTypeChange);
            buyingTypeSelect.addEventListener('change', handleBuyingTypeChange);
        }

        // Логика даты 
        const dateInput = document.getElementById('id_order_date');
        const dateText = document.getElementById('date-text');

        function syncDateVisual() {
            if (!dateInput || !dateText) return;
            const val = dateInput.value;
            if (val) {
                const [year, month, day] = val.split('-');
                if (year && month && day) {
                    dateText.textContent = `${day}.${month}.${year}`;
                    dateText.classList.remove('text-gray-400');
                    dateText.classList.add('text-black');
                }
            } else {
                dateText.textContent = 'Выберите дату';
                dateText.classList.add('text-gray-400');
                dateText.classList.remove('text-black');
            }
        }

        if (dateInput) {
            if (!dateInput.value) {
                const d = new Date();
                d.setDate(d.getDate() + 2);
                const year = d.getFullYear();
                const month = String(d.getMonth() + 1).padStart(2, '0');
                const day = String(d.getDate()).padStart(2, '0');
                dateInput.value = `${year}-${month}-${day}`;
            }
            syncDateVisual();

            dateInput.removeEventListener('input', syncDateVisual);
            dateInput.removeEventListener('change', syncDateVisual);
            dateInput.addEventListener('input', syncDateVisual);
            dateInput.addEventListener('change', syncDateVisual);
        }

        // Логика сабмита формы (валидация самовывоза)
        const form = document.getElementById('order-form');
        if (form) {
            form.onsubmit = function (e) {
                const address = document.getElementById('address').value;
                const type = document.getElementById('id_buying_type')?.value;
                if (!address) {
                    e.preventDefault();
                    alert('Пожалуйста, выберите адрес на карте');
                    return;
                }
                if (type === 'self' && address !== SAFU_ADDRESS) {
                    // Авто-фикс, если пользователь натыкал адрес, а потом выбрал самовывоз
                    document.getElementById('address').value = SAFU_ADDRESS;
                }
            };
        }
    }

    // --- ЗАПУСК ---
    // 1. При обычной загрузке
    document.addEventListener('DOMContentLoaded', window.initMapLogic);

    // 2. При HTMX загрузке 
    if (typeof htmx !== 'undefined') {
        htmx.on('htmx:afterSwap', function (evt) {
            setTimeout(window.initMapLogic, 100);
        });
        htmx.on('htmx:historyRestore', function (evt) {
            setTimeout(window.initMapLogic, 100);
        });
    }

})();