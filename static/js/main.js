document.addEventListener('DOMContentLoaded', function() {
    const searchForm = document.getElementById('searchForm');
    const loadDataBtn = document.getElementById('loadData');
    const loading = document.getElementById('loading');
    const resultsStats = document.getElementById('resultsStats');
    const resultsBody = document.getElementById('resultsBody');

    // Set initial language from localStorage or default to Chinese
    window.currentLang = localStorage.getItem('preferred_language') || 'zh';
    document.getElementById('languageSelect').value = window.currentLang;
    updatePageLanguage(window.currentLang);

    function showLoading() {
        loading.style.display = 'flex';
    }

    function hideLoading() {
        loading.style.display = 'none';
    }

    function showToast(message, isError = false) {
        Toastify({
            text: message,
            duration: 3000,
            gravity: "top",
            position: "right",
            backgroundColor: isError ? "#ff0000" : "#4CAF50",
        }).showToast();
    }

    function displayResults(data) {
        resultsBody.innerHTML = '';
        resultsStats.textContent = window.translations[window.currentLang]['results_count'].replace('{}', data.count);

        data.results.forEach(book => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${book.file_id || ''}</td>
                <td>${book.title || ''}</td>
                <td>${book.author || ''}</td>
                <td>${book.publisher || ''}</td>
                <td>${book.language || ''}</td>
                <td>${book.year || ''}</td>
                <td>${book.format || ''}</td>
            `;
            resultsBody.appendChild(row);
        });
    }

    function updatePageLanguage(lang) {
        document.querySelectorAll('[data-translate]').forEach(element => {
            const key = element.getAttribute('data-translate');
            if (element.tagName === 'INPUT') {
                element.placeholder = window.translations[lang][key];
            } else {
                element.textContent = window.translations[lang][key];
            }
        });
        document.documentElement.lang = lang;
    }

    window.changeLanguage = function(lang) {
        window.currentLang = lang;
        localStorage.setItem('preferred_language', lang);
        updatePageLanguage(lang);
    };

    searchForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        showLoading();

        const formData = new FormData(searchForm);
        const searchParams = {};
        for (let [key, value] of formData.entries()) {
            if (value) {
                searchParams[key] = value;
            }
        }

        try {
            const response = await fetch('/api/search', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(searchParams)
            });

            const data = await response.json();
            
            if (data.status === 'error') {
                showToast(data.message, true);
            } else {
                displayResults(data);
                showToast(window.translations[window.currentLang]['search_completed']);
            }
        } catch (error) {
            console.error('Search error:', error);
            showToast(`${window.translations[window.currentLang]['error']}: ${error.message}`, true);
        } finally {
            hideLoading();
        }
    });

    loadDataBtn.addEventListener('click', async function() {
        showLoading();
        try {
            const response = await fetch('/api/load', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    directory: '.',
                    force_reload: true
                })
            });

            const data = await response.json();
            showToast(
                data.status === 'error' 
                    ? data.message 
                    : window.translations[window.currentLang]['data_loaded'],
                data.status === 'error'
            );
        } catch (error) {
            showToast(`${window.translations[window.currentLang]['error']}: ${error.message}`, true);
            console.error('Load error:', error);
        } finally {
            hideLoading();
        }
    });
});
