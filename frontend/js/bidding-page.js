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

// --- BIDDING PAGE LOGIC ---
let currentUser = null;
let currentEventId = null;
let socket = null;
let currentBid = 0;
let basePrice = 0;
let remainingBudget = 0;

document.addEventListener('DOMContentLoaded', function() {
    // 1. Verify Auth
    const userStr = localStorage.getItem('user');
    if (!userStr) {
        console.log('No user found in localStorage, redirecting to login');
        window.location.href = '/';
        return;
    }

    currentUser = JSON.parse(userStr);
    console.log('Current user:', currentUser);

    // Get Event ID from URL or localStorage
    const urlParams = new URLSearchParams(window.location.search);
    currentEventId = urlParams.get('id') || localStorage.getItem('currentAuctionId');

    if (!currentEventId) {
        alert("No event ID provided");
        window.location.href = '/team-owner-dashboard.html';
        return;
    }

    // Initialize UI and Socket
    loadInitialTeamData();
    initSocket();
});

function loadInitialTeamData() {
    // In a real app, fetch the exact remaining budget and slots from the API.
    // We will initialize them to 0 and let team_status_update fill them.
    remainingBudget = 0;
    updateStatsUI(0, 0, 0, 0);
}

function initSocket() {
    socket = io({ transports: ['polling'], upgrade: false });

    socket.on('connect', () => {
        console.log('Connected to WebSocket server');
        socket.emit('join_lobby', {
            auction_id: currentEventId,
            team_id: currentUser.team_id
        });
        
        // Let admin know team is ready
        socket.emit('team_ready', {
            auction_id: currentEventId,
            team_id: currentUser.team_id
        });
    });

    socket.on('team_status_update', (data) => {
        console.log('Team status update:', data);
        // Assuming data includes budget details (you may need to enhance this backend payload if it doesn't)
        // For now, if your app provides budget via API, you'd fetch it. We will use the data object if provided.
        if (data.team_id == currentUser.team_id) {
            remainingBudget = data.remaining_budget || 0;
            updateStatsUI(remainingBudget, data.players_bought || 0, data.total_spent || 0, data.slots_left || 0);
        }
    });

    socket.on('auction_update', (data) => {
        console.log('Auction update:', data);
        if (data.status === 'RUNNING') {
            if (data.current_player) {
                document.getElementById('playerName').textContent = data.current_player.name;
                document.getElementById('playerCategory').textContent = data.current_player.role || 'Unknown';
                document.getElementById('playerRating').textContent = 'Standard';
                document.getElementById('playerCountry').textContent = 'N/A';
                
                basePrice = data.current_player.base_price || 0;
                currentBid = data.current_bid || basePrice;
                
                document.getElementById('currentBid').textContent = formatCurrency(currentBid);
                document.getElementById('currentBidder').textContent = data.current_bidder_name || 'Base Price';
                
                const imgEl = document.querySelector('.player-image .image-placeholder');
                if (data.current_player.photo && imgEl) {
                    imgEl.innerHTML = `<img src="${data.current_player.photo}" style="width:100%; height:100%; border-radius:50%; object-fit:cover;" />`;
                }
            }
            document.getElementById('timer').textContent = data.time_left || '--';
            setupBidInput();
        } else if (data.status === 'PAUSED' || data.status === 'COMPLETED') {
            document.getElementById('timer').textContent = data.status;
            document.getElementById('bidAmount').disabled = true;
        }
    });

    socket.on('bid_placed', (data) => {
        console.log('Bid placed:', data);
        currentBid = data.amount;
        document.getElementById('currentBid').textContent = formatCurrency(currentBid);
        document.getElementById('currentBidder').textContent = `Team ${data.team_id}`; // Or fetch team name
        
        document.getElementById('timer').textContent = data.time_left;
        
        addBidToHistory(`Team ${data.team_id}`, currentBid);
        setupBidInput();
        
        if (data.team_id == currentUser.team_id) {
            showNotification('Your bid is the highest!', 'success');
        } else {
            showNotification(`Team ${data.team_id} bid ${formatCurrency(currentBid)}`, 'info');
        }
    });

    socket.on('player_sold', (data) => {
        showNotification(`Player Sold to Team ${data.team_id} for ${formatCurrency(data.amount)}!`, 'success');
        if (data.team_id == currentUser.team_id) {
            remainingBudget -= data.amount;
            updateStatsUI(remainingBudget, null, null, null);
        }
    });

    socket.on('player_unsold', (data) => {
        showNotification('Player was marked UNSOLD', 'info');
    });

    socket.on('error', (err) => {
        console.error("Socket error:", err);
        showNotification(err.msg || "Error", 'error');
    });
}

function setupBidInput() {
    const bidInput = document.getElementById('bidAmount');
    if (!bidInput) return;
    const minBid = currentBid > 0 ? currentBid + 10000 : basePrice;
    
    bidInput.min = minBid;
    bidInput.value = minBid;
    bidInput.disabled = false;
}

function placeBid() {
    const bidInput = document.getElementById('bidAmount');
    const bidAmount = parseInt(bidInput.value);
    
    if (!bidAmount || bidAmount <= currentBid) {
        alert('Please enter a valid bid amount higher than the current bid');
        return;
    }
    
    if (socket && currentEventId && currentUser.team_id) {
        socket.emit('place_bid', {
            auction_id: currentEventId,
            team_id: currentUser.team_id,
            amount: bidAmount
        });
        
        bidInput.value = '';
    }
}

function quickBid(amount) {
    const newBid = currentBid + amount;
    document.getElementById('bidAmount').value = newBid;
    placeBid();
}

function updateStatsUI(remBudget, pBought, tSpent, sLeft) {
    const budgetEl = document.getElementById('remainingBudget');
    if (budgetEl && remBudget !== null) budgetEl.textContent = formatCurrency(remBudget);
    
    const boughtEl = document.getElementById('playersBought');
    if (boughtEl && pBought !== null) boughtEl.textContent = pBought;
    
    const spentEl = document.getElementById('totalSpent');
    if (spentEl && tSpent !== null) spentEl.textContent = formatCurrency(tSpent);
    
    const slotsEl = document.getElementById('slotsLeft');
    if (slotsEl && sLeft !== null) slotsEl.textContent = sLeft;
}

function addBidToHistory(team, amount) {
    const historyList = document.getElementById('bidHistory');
    if (!historyList) return;
    
    const historyItem = document.createElement('div');
    historyItem.className = 'history-item';
    historyItem.innerHTML = `
        <div class="history-team neon-text">${team}</div>
        <div class="history-amount neon-text">${formatCurrency(amount)}</div>
        <div class="history-time">Just now</div>
    `;
    
    historyList.insertBefore(historyItem, historyList.firstChild);
    while (historyList.children.length > 10) {
        historyList.removeChild(historyList.lastChild);
    }
}

function formatCurrency(amount) {
    return '₹' + amount.toLocaleString('en-IN');
}

function showNotification(message, type) {
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
        ${type === 'success' ? 'background: #00ff00; box-shadow: 0 0 20px #00ff00;' : 
          type === 'error' ? 'background: #ff0000; color: #ffffff; box-shadow: 0 0 20px #ff0000;' :
          'background: #00ffff; box-shadow: 0 0 20px #00ffff;'}
    `;
    notification.textContent = message;
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.style.opacity = '0';
        setTimeout(() => {
            document.body.removeChild(notification);
        }, 300);
    }, 3000);
}

async function logout() {
    if (confirm('Are you sure you want to logout?')) {
        try {
            await fetch('/api/logout', { method: 'POST' });
        } catch (error) {
            console.error('Error logging out:', error);
        }

        sessionStorage.clear();
        localStorage.clear();

        if (socket) {
            socket.disconnect();
        }

        window.location.replace('/');
    }
}
