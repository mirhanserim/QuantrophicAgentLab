document.addEventListener('DOMContentLoaded', () => {
    const statusButton = document.getElementById('statusButton');
    const statusMessage = document.getElementById('statusMessage');
    const counter = document.getElementById('counter');
    const incrementButton = document.getElementById('incrementButton');
    const resetButton = document.getElementById('resetButton');
    const activeFile = document.querySelector('.active-file');

    document.querySelectorAll('.file-item').forEach(item => {
        item.addEventListener('click', () => {
            document.querySelectorAll('.file-item').forEach(i => {
                i.classList.remove('selected');
            });

            item.classList.add('selected');

            const fileName = item.getAttribute('data-file');

            if (statusMessage) {
                statusMessage.textContent = 'Selected: ' + fileName;
            }

            if (activeFile && fileName !== 'project') {
                activeFile.textContent = fileName;
            }
        });
    });

    const tabs = document.querySelectorAll('.tab-button');

    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            tabs.forEach(t => {
                t.classList.remove('selected');
            });

            tab.classList.add('selected');

            const fileName = tab.getAttribute('data-file');

            if (activeFile) {
                activeFile.textContent = fileName;
            }
        });
    });

    if (statusButton && statusMessage) {
        statusButton.addEventListener('click', () => {
            statusMessage.textContent =
                statusMessage.textContent === 'Status: Ready'
                    ? 'Status: Active'
                    : 'Status: Ready';
        });
    }

    if (incrementButton && counter) {
        incrementButton.addEventListener('click', () => {
            const value = Number(counter.textContent) || 0;
            counter.textContent = String(value + 1);
        });
    }

    if (resetButton && counter) {
        resetButton.addEventListener('click', () => {
            counter.textContent = '0';
        });
    }
});
