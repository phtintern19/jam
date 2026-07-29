
// --- THEME MANAGEMENT ---
function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    updateThemeIcon(newTheme);
}

function updateThemeIcon(theme) {
    const icons = document.querySelectorAll('.theme-icon');
    icons.forEach(icon => {
        if (theme === 'light') {
            icon.classList.remove('fa-moon');
            icon.classList.add('fa-sun');
        } else {
            icon.classList.remove('fa-sun');
            icon.classList.add('fa-moon');
        }
    });
}

document.addEventListener('DOMContentLoaded', () => {
    const savedTheme = localStorage.getItem('theme') || 'dark';
    document.documentElement.setAttribute('data-theme', savedTheme);
    updateThemeIcon(savedTheme);
});
// ------------------------

// Bidding Page JavaScript

let currentUser = null;
let currentBid = 500000;
let timerSeconds = 30;
let timerInterval = null;

// Initialize bidding page on load
document.addEventListener('DOMContentLoaded', function() {
    // Check if user is authenticated via localStorage
    const userStr = localStorage.getItem('user');
    if (!userStr) {
        console.log('No user found in localStorage, redirecting to login');
        window.location.href = '/';
        return;
    }

    currentUser = JSON.parse(userStr);
    console.log('Current user:', currentUser);

    // Initialize timer
    startTimer();

    // Load initial data
    loadBiddingData();

    // Set up bid input validation
    setupBidInput();
});

// Start countdown timer
function startTimer() {
    timerInterval = setInterval(() => {
        timerSeconds--;
        
        if (timerSeconds <= 0) {
            timerSeconds = 30; // Reset timer
            // Simulate new bid coming in
            simulateIncomingBid();
        }
        
        updateTimerDisplay();
    }, 1000);
}

// Update timer display
function updateTimerDisplay() {
    const minutes = Math.floor(timerSeconds / 60);
    const seconds = timerSeconds % 60;
    const display = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
    document.getElementById('timer').textContent = display;
    
    // Change color when timer is low
    const timerElement = document.getElementById('timer');
    if (timerSeconds <= 10) {
        timerElement.style.color = '#ff0000';
        timerElement.style.textShadow = '0 0 10px #ff0000, 0 0 20px #ff0000';
    } else {
        timerElement.style.color = '#ff00ff';
        timerElement.style.textShadow = '0 0 10px #ff00ff, 0 0 20px #ff00ff, 0 0 40px #ff00ff';
    }
}

// Load bidding data
function loadBiddingData() {
    // Simulate loading data from API
    document.getElementById('currentBid').textContent = formatCurrency(currentBid);
    document.getElementById('remainingBudget').textContent = formatCurrency(7500000);
    document.getElementById('playersBought').textContent = '5';
    document.getElementById('totalSpent').textContent = formatCurrency(2500000);
    document.getElementById('slotsLeft').textContent = '10';
}

// Setup bid input validation
function setupBidInput() {
    const bidInput = document.getElementById('bidAmount');
    const minBid = currentBid + 10000;
    
    bidInput.min = minBid;
    bidInput.placeholder = `Minimum: ${formatCurrency(minBid)}`;
}

// Place bid
function placeBid() {
    const bidInput = document.getElementById('bidAmount');
    const bidAmount = parseInt(bidInput.value);
    
    if (!bidAmount || bidAmount <= currentBid) {
        alert('Please enter a valid bid amount higher than the current bid');
        return;
    }
    
    // Update current bid
    currentBid = bidAmount;
    document.getElementById('currentBid').textContent = formatCurrency(currentBid);
    document.getElementById('currentBidder').textContent = currentUser.username || 'Your Team';
    
    // Add to bid history
    addBidToHistory(currentUser.username || 'Your Team', currentBid);
    
    // Reset timer
    timerSeconds = 30;
    
    // Clear input
    bidInput.value = '';
    
    // Update minimum bid
    setupBidInput();
    
    // Show success message
    showNotification('Bid placed successfully!', 'success');
}

// Quick bid
function quickBid(amount) {
    const newBid = currentBid + amount;
    document.getElementById('bidAmount').value = newBid;
    placeBid();
}

// Add bid to history
function addBidToHistory(team, amount) {
    const historyList = document.getElementById('bidHistory');
    const historyItem = document.createElement('div');
    historyItem.className = 'history-item';
    historyItem.innerHTML = `
        <div class="history-team neon-text">${team}</div>
        <div class="history-amount neon-text">${formatCurrency(amount)}</div>
        <div class="history-time">Just now</div>
    `;
    
    // Insert at the top
    historyList.insertBefore(historyItem, historyList.firstChild);
    
    // Keep only last 10 items
    while (historyList.children.length > 10) {
        historyList.removeChild(historyList.lastChild);
    }
}

// Simulate incoming bid
function simulateIncomingBid() {
    const teams = ['Team Alpha', 'Team Beta', 'Team Gamma', 'Team Delta', 'Team Omega'];
    const randomTeam = teams[Math.floor(Math.random() * teams.length)];
    const increment = [10000, 50000, 100000][Math.floor(Math.random() * 3)];
    const newBid = currentBid + increment;
    
    currentBid = newBid;
    document.getElementById('currentBid').textContent = formatCurrency(currentBid);
    document.getElementById('currentBidder').textContent = randomTeam;
    
    addBidToHistory(randomTeam, currentBid);
    setupBidInput();
    
    showNotification(`${randomTeam} placed a bid of ${formatCurrency(currentBid)}`, 'info');
}

// Format currency
function formatCurrency(amount) {
    return '$' + amount.toLocaleString();
}

// Show notification
function showNotification(message, type) {
    // Create notification element
    const notification = document.createElement('div');
    notification.style.cssText = `
        position: fixed;
        top: 100px;
        right: 20px;
        padding: 1rem 2rem;
        border-radius: 10px;
        color: #000000;
        font-weight: bold;
        z-index: 9999;
        animation: slideIn 0.3s ease-out;
        ${type === 'success' ? 'background: #00ff00; box-shadow: 0 0 20px #00ff00;' : 'background: #00ffff; box-shadow: 0 0 20px #00ffff;'}
    `;
    notification.textContent = message;
    
    document.body.appendChild(notification);
    
    // Remove after 3 seconds
    setTimeout(() => {
        notification.style.opacity = '0';
        setTimeout(() => {
            document.body.removeChild(notification);
        }, 300);
    }, 3000);
}

// Logout function
async function logout() {
    if (confirm('Are you sure you want to logout?')) {
        try {
            await fetch('/api/logout', { method: 'POST' });
        } catch (error) {
            console.error('Error logging out:', error);
        }

        // Clear all session storage
        sessionStorage.clear();
        
        // Clear all local storage
        localStorage.removeItem('user');
        localStorage.removeItem('session_token');
        localStorage.removeItem('userType');
        localStorage.removeItem('username');
        localStorage.removeItem('teamName');

        // Stop timer
        if (timerInterval) {
            clearInterval(timerInterval);
        }

        // Redirect to home page
        window.location.replace('/');
    }
}

// Cleanup on page unload
window.addEventListener('beforeunload', function() {
    if (timerInterval) {
        clearInterval(timerInterval);
    }
});
