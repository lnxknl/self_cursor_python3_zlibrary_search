document.addEventListener('DOMContentLoaded', function() {
    console.log('JavaScript loaded successfully');
    const searchForm = document.getElementById('searchForm');
    const loadDataBtn = document.getElementById('loadData');
    const loading = document.getElementById('loading');
    const resultsStats = document.getElementById('resultsStats');
    const resultsBody = document.getElementById('resultsBody');
    const languageSelect = document.getElementById('languageSelect');

    // Initialize translations
    if (!window.translations) {
        console.error('Translations not loaded!');
        window.translations = {
            'zh': {
                'results_count': '找到 {} 条结果',
                'search_completed': '搜索完成！',
                'data_loaded': '数据加载完成！',
                'error': '错误'
            },
            'en': {
                'results_count': 'Found {} results',
                'search_completed': 'Search completed!',
                'data_loaded': 'Data loaded successfully!',
                'error': 'Error'
            }
        };
    }

    // Set initial language
    window.currentLang = localStorage.getItem('preferred_language') || 'zh';
    if (languageSelect) {
        languageSelect.value = window.currentLang;
    }

    function showLoading() {
        if (loading) loading.style.display = 'flex';
    }

    function hideLoading() {
        if (loading) loading.style.display = 'none';
    }

    function showToast(message, isError = false) {
        console.log('Showing toast:', message);
        Toastify({
            text: message,
            duration: 3000,
            gravity: "top",
            position: "right",
            backgroundColor: isError ? "#ff0000" : "#4CAF50",
        }).showToast();
    }

    function displayResults(data) {
        console.log('Displaying results:', data);
        if (!resultsBody) return;
        
        resultsBody.innerHTML = '';
        if (resultsStats) {
            const countMessage = window.translations[window.currentLang]['results_count'].replace('{}', data.count);
            resultsStats.textContent = countMessage;
        }

        if (data.results && Array.isArray(data.results)) {
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
    }

    if (searchForm) {
        searchForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            console.log('Form submitted');
            showLoading();

            const formData = new FormData(searchForm);
            const searchParams = {};
            for (let [key, value] of formData.entries()) {
                if (value) {
                    searchParams[key] = value;
                }
            }

            console.log('Search params:', searchParams);

            try {
                const response = await fetch('/api/search', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(searchParams)
                });

                const data = await response.json();
                console.log('Search response:', data);
                
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
    } else {
        console.error('Search form not found!');
    }

    if (loadDataBtn) {
        loadDataBtn.addEventListener('click', async function() {
            console.log('Load data clicked');
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
                console.error('Load error:', error);
                showToast(`${window.translations[window.currentLang]['error']}: ${error.message}`, true);
            } finally {
                hideLoading();
            }
        });
    } else {
        console.error('Load data button not found!');
    }

    const initialLang = document.documentElement.lang || 'zh';
    if (window.translations && window.translations[initialLang]) {
        updatePageLanguage(window.translations[initialLang]);
    }
});

function updatePageLanguage(translations) {
    console.log('Updating page language with translations:', translations);
    
    // Update all elements with data-translate attribute
    document.querySelectorAll('[data-translate]').forEach(element => {
        const key = element.getAttribute('data-translate');
        if (translations[key]) {
            if (element.tagName === 'INPUT') {
                element.placeholder = translations[key];
            } else {
                element.textContent = translations[key];
            }
        }
    });

    // Update table headers
    const headerMapping = {
        'file_id': translations.file_id,
        'book_title': translations.book_title,
        'author': translations.author,
        'publisher': translations.publisher,
        'language': translations.language,
        'year': translations.year,
        'format': translations.format
    };

    document.querySelectorAll('#resultsTable th').forEach(th => {
        const key = th.getAttribute('data-translate');
        if (key && headerMapping[key]) {
            th.textContent = headerMapping[key];
        }
    });

    // Update form labels
    document.querySelectorAll('label.form-label').forEach(label => {
        const key = label.getAttribute('data-translate');
        if (key && translations[key]) {
            label.textContent = translations[key];
        }
    });

    // Update buttons
    document.querySelectorAll('button').forEach(button => {
        const key = button.getAttribute('data-translate');
        if (key && translations[key]) {
            button.textContent = translations[key];
        }
    });
}

// Update the language change function
window.changeLanguage = async function(lang) {
    console.log('Changing language to:', lang);
    try {
        const response = await fetch(`/change-language/${lang}`);
        const data = await response.json();
        
        if (data.status === 'success') {
            window.currentLang = lang;
            localStorage.setItem('preferred_language', lang);
            window.translations[lang] = data.translations;
            updatePageLanguage(data.translations);
            
            // Update URL without reloading the page
            const url = new URL(window.location);
            url.searchParams.set('lang', lang);
            window.history.pushState({}, '', url);
            
            // Update the language selector
            document.getElementById('languageSelect').value = lang;
        } else {
            console.error('Failed to change language:', data.message);
        }
    } catch (error) {
        console.error('Error changing language:', error);
    }
}; 
