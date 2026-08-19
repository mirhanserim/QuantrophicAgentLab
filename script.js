document.addEventListener('DOMContentLoaded', () => {
    const statusButton = document.getElementById('statusButton');
    document.querySelectorAll('.file-item').forEach(item => {
        item.addEventListener('click', () => {
            document.querySelectorAll('.file-item').forEach(i => i.classList.remove('selected'));
            item.classList.add('selected');
            statusButton.textContent = 'Selected: ' + item.textContent;
        });
    });
});
// Code editor functionality
const tabs = document.querySelectorAll('.tab-button');
const contentArea = document.querySelector('.content');

tabs.forEach(tab => {
    tab.addEventListener('click', () => {
        tabs.forEach(t => t.classList.remove('selected'));
        tab.classList.add('selected');
        contentArea.focus();
    });
});
