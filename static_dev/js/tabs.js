document.addEventListener('alpine:init', () => {
    Alpine.data('profileTabs', () => ({
        activeTab: 'account',

        init() {
            const path = window.location.pathname.split('/').filter(segment => segment).pop();
            const validTabs = ['account', 'orders', 'wishlist', 'returns'];

            if (!path || path === 'profile') {
                this.activeTab = 'account';
            } else {
                this.activeTab = validTabs.includes(path) ? path : 'account';
            }

            this.updateBreadcrumb();
            this.checkOrderHighlight();

            window.addEventListener('popstate', () => {
                const path = window.location.pathname.split('/').filter(segment => segment).pop();
                if (!path || path === 'profile') {
                    this.activeTab = 'account';
                } else {
                    this.activeTab = validTabs.includes(path) ? path : 'account';
                }
                this.updateBreadcrumb();
                this.checkOrderHighlight();
            });
        },

        switchTab(tabId) {
            this.activeTab = tabId;
            this.updateBreadcrumb();
            const url = tabId === 'account' ? '/profile/' : `/profile/${tabId}/`;
            history.pushState({}, '', url);
        },

        updateBreadcrumb() {
            const breadcrumbLast = document.getElementById('breadcrumb-last');
            const tabTitles = {
                'account': 'Данные аккаунта',
                'orders': 'Мои заказы',
                'wishlist': 'Лист ожидания',
                'returns': 'Мои возвраты'
            };
            if (breadcrumbLast) {
                breadcrumbLast.textContent = tabTitles[this.activeTab] || 'Данные аккаунта';
            }
        },

        checkOrderHighlight() {
            const urlParams = new URLSearchParams(window.location.search);
            const orderId = urlParams.get('order_id');
            if (orderId && this.activeTab === 'returns') {
                setTimeout(() => {
                    const returnRequest = document.querySelector(`[data-order-id="${orderId}"]`);
                    if (returnRequest) {
                        returnRequest.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    }
                }, 100);
            }
        },

        isActive(tabId) {
            return this.activeTab === tabId;
        }
    }));
});