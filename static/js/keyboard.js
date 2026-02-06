(function() {
    let selectedIndex = -1;
    let cards = [];

    function updateCards() {
        cards = Array.from(document.querySelectorAll('.news-card'));
    }

    function selectCard(index) {
        cards.forEach(c => c.classList.remove('selected'));

        if (index >= 0 && index < cards.length) {
            selectedIndex = index;
            cards[selectedIndex].classList.add('selected');
            cards[selectedIndex].scrollIntoView({ behavior: 'smooth', block: 'center' });
            cards[selectedIndex].focus();
        }
    }

    function getSelectedCard() {
        if (selectedIndex >= 0 && selectedIndex < cards.length) {
            return cards[selectedIndex];
        }
        return null;
    }

    document.addEventListener('keydown', function(e) {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
            return;
        }

        updateCards();

        switch(e.key.toLowerCase()) {
            case 'j':
                e.preventDefault();
                if (selectedIndex < cards.length - 1) {
                    selectCard(selectedIndex + 1);
                } else if (selectedIndex === -1 && cards.length > 0) {
                    selectCard(0);
                }
                break;

            case 'k':
                e.preventDefault();
                if (selectedIndex > 0) {
                    selectCard(selectedIndex - 1);
                } else if (selectedIndex === -1 && cards.length > 0) {
                    selectCard(cards.length - 1);
                }
                break;

            case 's':
                e.preventDefault();
                const card = getSelectedCard();
                if (card) {
                    const saveBtn = card.querySelector('.save-btn');
                    if (saveBtn) saveBtn.click();
                }
                break;

            case 'o':
                e.preventDefault();
                const openCard = getSelectedCard();
                if (openCard) {
                    const url = openCard.dataset.url;
                    if (url) window.open(url, '_blank');
                }
                break;

            case 'r':
                e.preventDefault();
                const scanBtn = document.querySelector('[hx-post="/scan-news"]');
                if (scanBtn) scanBtn.click();
                break;

            case '1': case '2': case '3': case '4': case '5':
            case '6': case '7': case '8': case '9':
                const filterChips = document.querySelectorAll('.filter-group:last-child .filter-chip');
                const chipIndex = parseInt(e.key);
                if (filterChips[chipIndex]) {
                    filterChips[chipIndex].click();
                }
                break;
        }
    });

    document.addEventListener('htmx:afterSwap', function() {
        updateCards();
        selectedIndex = -1;
    });

    updateCards();
})();
