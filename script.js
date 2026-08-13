// Status button functionality
document.getElementById('statusButton').addEventListener('click', () => {
    const statusMessage = document.getElementById('statusMessage');
    statusMessage.textContent = 'Status: Active';
});

// Counter functionality
let counter = 0;

document.getElementById('incrementButton').addEventListener('click', () => {
    counter++;
    document.getElementById('counter').textContent = counter;
});

document.getElementById('resetButton').addEventListener('click', () => {
    counter = 0;
    document.getElementById('counter').textContent = counter;
});