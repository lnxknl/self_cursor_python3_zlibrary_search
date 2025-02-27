// Add a flag to prevent duplicate event listeners
let isInitialized = false;

document.addEventListener('DOMContentLoaded', function() {
    // Prevent multiple initializations
    if (isInitialized) return;
    isInitialized = true;

    console.log('JavaScript initializing...'); // Debug log
    const searchForm = document.getElementById('searchForm');
    const loadDataBtn = document.getElementById('loadDataBtn');
    const clearBtn = document.getElementById('clearBtn');
    const loading = document.getElementById('loading');
    const resultsStats = document.getElementById('resultsStats');
    const resultsBody = document.getElementById('resultsBody');
    const languageSelect = document.getElementById('languageSelect');
    const resultsTable = document.getElementById('resultsTable');

    // Initialize translations
    if (!window.translations) {
        console.error('Translations not loaded!');
        window.translations = {
            'zh': {
                'results_count': '找到 {} 条结果',
                'search_completed': '搜索完成！',
                'data_loaded': '数据加载完成！',
                'error': '错误',
                'no_results': '没有找到结果'
            },
            'en': {
                'results_count': 'Found {} results',
                'search_completed': 'Search completed!',
                'data_loaded': 'Data loaded successfully!',
                'error': 'Error',
                'no_results': 'No results found'
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

    function displayResults(results, count) {
        resultsBody.innerHTML = '';
        if (results.length === 0) {
            resultsStats.textContent = window.translations.no_results;
            resultsTable.style.display = 'none';
            return;
        }

        resultsStats.textContent = window.translations.results_count.replace('{}', count);
        resultsTable.style.display = 'table';
        
        results.forEach(book => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${book.file_id || ''}</td>
                <td>${book.title || ''}</td>
                <td>${book.author || ''}</td>
                <td>${book.publisher || ''}</td>
                <td>${book.language || ''}</td>
                <td>${book.publish_year || ''}</td>
                <td>${book.format || ''}</td>
            `;
            resultsBody.appendChild(row);
        });
    }

    // 加载数据按钮点击事件
    if (loadDataBtn) {
        loadDataBtn.addEventListener('click', loadData);
    }

    // 清除按钮点击事件
    if (clearBtn) {
        clearBtn.addEventListener('click', function() {
            searchForm.reset();
            resultsBody.innerHTML = '';
            resultsStats.textContent = '';
            resultsTable.style.display = 'none';
        });
    }

    async function loadData() {
        showLoading();
        try {
            const response = await fetch('/api/load', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    force_reload: false  // 默认不强制重新加载
                })
            });

            const data = await response.json();
            if (data.status === 'success') {
                showToast(data.message);
            } else {
                showToast(data.message, true);
            }
        } catch (error) {
            console.error('Load error:', error);
            showToast(`Error: ${error.message}`, true);
        } finally {
            hideLoading();
        }
    }

    // 搜索表单提交事件
    if (searchForm) {
        searchForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            showLoading();

            try {
                const formData = new FormData(searchForm);
                const searchParams = {};
                for (let [key, value] of formData.entries()) {
                    if (value.trim()) {
                        searchParams[key] = value.trim();
                    }
                }

                const response = await fetch('/api/search', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(searchParams)
                });

                const data = await response.json();
                if (data.status === 'success') {
                    displayResults(data.data, data.count);
                } else {
                    showToast(data.message, true);
                }
            } catch (error) {
                console.error('Search error:', error);
                showToast(`Error: ${error.message}`, true);
            } finally {
                hideLoading();
            }
        });
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
