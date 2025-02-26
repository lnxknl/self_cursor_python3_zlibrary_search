document.addEventListener('DOMContentLoaded', function() {
    const searchForm = document.getElementById('searchForm');
    const loadDataBtn = document.getElementById('loadData');
    const loading = document.getElementById('loading');
    const resultsStats = document.getElementById('resultsStats');
    const resultsBody = document.getElementById('resultsBody');

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
    resultsStats.textContent = `Found ${data.count} results`;

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

// ... rest of the existing code ...
//    function displayResults(data) {
//        resultsBody.innerHTML = '';
//        resultsStats.textContent = `Found ${data.count} results`;
//
//        data.results.forEach(book => {
//            const row = document.createElement('tr');
//            row.innerHTML = `
//                <td>${book['文件编号'] || ''}</td>
//                <td>${book['书名'] || ''}</td>
//                <td>${book['作者'] || ''}</td>
//                <td>${book['出版社'] || ''}</td>
//                <td>${book['语种'] || ''}</td>
//                <td>${book['出版年份'] || ''}</td>
//                <td>${book['文件格式'] || ''}</td>
//            `;
//            resultsBody.appendChild(row);
//        });
//    }

// ... existing code ...

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
        console.log('Sending search request with params:', searchParams);  // Debug log
        const response = await fetch('/api/search', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(searchParams)
        });

        const data = await response.json();
        console.log('Received response:', data);  // Debug log
        
        if (data.status === 'error') {
            showToast(data.message, true);
        } else {
            displayResults(data);
        }
    } catch (error) {
        console.error('Detailed search error:', error);  // More detailed error log
        showToast(`Search error: ${error.message}`, true);
    } finally {
        hideLoading();
    }
});
//    searchForm.addEventListener('submit', async function(e) {
//        e.preventDefault();
//        showLoading();
//
//        const formData = new FormData(searchForm);
//        const searchParams = {};
//        for (let [key, value] of formData.entries()) {
//            if (value) {
//                searchParams[key] = value;
//            }
//        }
//
//        try {
//            const response = await fetch('/api/search', {
//                method: 'POST',
//                headers: {
//                    'Content-Type': 'application/json',
//                },
//                body: JSON.stringify(searchParams)
//            });
//
//            const data = await response.json();
//            
//            if (data.status === 'error') {
//                showToast(data.message, true);
//            } else {
//                displayResults(data);
//            }
//        } catch (error) {
//            showToast('Error performing search', true);
//            console.error('Search error:', error);
//        } finally {
//            hideLoading();
//        }
//    });

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
            showToast(data.message, data.status === 'error');
        } catch (error) {
            showToast('Error loading data', true);
            console.error('Load error:', error);
        } finally {
            hideLoading();
        }
    });
});
