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