
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

// Team Owner Dashboard
// Authentication check
document.addEventListener('DOMContentLoaded', function () {
    console.log('Team Owner dashboard loading...');

    // Check if user is authenticated via localStorage
    const userStr = localStorage.getItem('user');
    if (!userStr) {
        console.log('No user found in localStorage, redirecting to login');
        window.location.href = '/';
        return;
    }

    const user = JSON.parse(userStr);
    console.log('Current user:', user);

    // Check if user is team owner, manager, or analyst
    if (!['team_owner', 'team_manager', 'team_analyst'].includes(user.user_type)) {
        console.log('Access denied - user is not team staff');
        showModal('Access Denied', 'Please login as a team owner, manager, or analyst to access this page.');
        setTimeout(() => {
            window.location.href = '/';
        }, 2000);
        return;
    }

    // Apply role-based UI restrictions
    applyRolePermissions(user);

    // Check if auction is in preparation phase
    const currentAuctionStatus = localStorage.getItem('currentAuctionStatus');
    const auctionStarting = localStorage.getItem('auctionStarting');

    // Load bidding time preference from team owner's selection or admin's decision
    const teamBidTime = localStorage.getItem('teamBidTimePreference');
    const adminBidTime = localStorage.getItem('auctionBidTime');

    if (adminBidTime) {
        // Admin has set the final bidding time
        currentAuction.bidTimeLimit = parseInt(adminBidTime);
        console.log('Using admin-set bidding time:', adminBidTime + ' seconds');
    } else if (teamBidTime) {
        // Use team owner's preference until admin decides
        currentAuction.bidTimeLimit = parseInt(teamBidTime);
        console.log('Using team preference:', teamBidTime + ' seconds');
    }

    if (currentAuctionStatus === 'NOT_STARTED' && auctionStarting === 'true') {
        // Auction is in preparation, redirect to countdown page
        console.log('Auction in preparation, redirecting to countdown...');
        return;
    } else if (currentAuctionStatus === 'NOT_STARTED' && !auctionStarting) {
        // Auction not started yet, show waiting message
        console.log('Auction not started, showing dashboard with waiting message...');
        // Continue with normal dashboard loading but auction will show "Waiting for auction to start..."
    }

    // Load team owner data and initialize dashboard
    loadTeamOwnerData();
    loadSquad();
    initializeAuction();

    // Setup event listeners
    setupEventListeners();

    // Start auction timer if running
    startAuctionTimer();
});

// Helper: write to admin activity log in localStorage (shared with admin dashboard)
function adminLogActivity(action, details) {
    try {
        const key = 'adminActivityLogs';
        const logs = JSON.parse(localStorage.getItem(key) || '[]');
        logs.push({ timestamp: new Date().toISOString(), action, details });
        // Keep last 500 entries max
        const trimmed = logs.slice(-500);
        localStorage.setItem(key, JSON.stringify(trimmed));
    } catch (e) {
        // Swallow errors to avoid blocking functionality
        console.warn('Failed to write admin activity log:', e);
    }

    // Also send activity to backend so it is stored in the database
    try {
        fetch('/api/activity-logs', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                action_type: action,
                action_description: details || '',
                entity_type: null,
                entity_id: null,
                ip_address: null,
                user_agent: navigator.userAgent
            })
        }).catch(err => {
            console.warn('Failed to send team owner activity log to server:', err);
        });
    } catch (err) {
        console.warn('Failed to send team owner activity log to server:', err);
    }
}


// Team Owner Data Structure
// Mock data removed
// const mockTeamOwnerData = ...

// Sample team owner credentials
// Mock data removed - replaced with API calls
// const sampleTeamOwners = ...

// Set initial auction status in localStorage if not already set
if (!localStorage.getItem('currentAuctionStatus')) {
    localStorage.setItem('currentAuctionStatus', 'NOT_STARTED');
}

// Current auction state (mock data)
let currentAuction = {
    id: 1,
    status: 'NOT_STARTED', // NOT_STARTED, RUNNING, PAUSED, ENDED
    currentPlayer: null, // No current player when not started
    currentBid: 0,
    highestBidder: null,
    timeLeft: 0,
    bidders: []
};

// Load team owner data
// Load team owner data
// Global current team ID
let currentTeamId = null;

// Load team owner data
async function loadTeamOwnerData(teamId = null) {
    try {
        let url = '/api/team-owner/dashboard';
        if (teamId) {
            url += `?team_id=${teamId}`;
            currentTeamId = teamId; // Update global state
        }

        const response = await fetch(url, {
            headers: {
                'Accept': 'application/json'
            },
            credentials: 'include'
        });

        if (response.ok) {
            const data = await response.json();

            // Set current Team ID from response if not set (initial load)
            if (!currentTeamId && data.team_id) {
                currentTeamId = data.team_id;
            }

            // Populate Team Selector and Event Title
            const teamSelector = document.getElementById('teamSelector');
            const eventTitleEl = document.getElementById('currentEventTitle');
            let currentEventName = 'Unknown Event';

            if (data.my_teams && data.my_teams.length > 0) {
                // Find current team object
                const currentTeam = data.my_teams.find(t => t.team_id == currentTeamId) || data.my_teams[0];
                if (currentTeam) {
                    currentEventName = currentTeam.event_title;
                }

                if (data.my_teams.length > 1) {
                    teamSelector.style.display = 'block';
                    teamSelector.innerHTML = '<option value="">Select Event</option>';
                    data.my_teams.forEach(team => {
                        const option = document.createElement('option');
                        option.value = team.team_id;
                        option.textContent = `${team.event_title} (${team.team_name})`;
                        if (currentTeamId == team.team_id) {
                            option.selected = true;
                        }
                        teamSelector.appendChild(option);
                    });
                } else {
                    teamSelector.style.display = 'none';
                }
            }

            // Set Event Title Header
            if (eventTitleEl) eventTitleEl.textContent = currentEventName;

            // Update wallet balance
            document.getElementById('walletAmount').textContent = `₹${data.wallet_balance.toLocaleString()}`;

            // Store current team owner data
            sessionStorage.setItem('teamName', data.team_name);
            sessionStorage.setItem('walletBalance', data.wallet_balance);
            sessionStorage.setItem('squadData', JSON.stringify(data.squad));

            // Trigger squad update
            renderSquad(data.squad);

            // Handle auction status
            if (data.active_auction) {
                if (data.active_auction.status === 'RUNNING') {
                    document.querySelector('.live-auction-container').style.display = 'block';
                    document.getElementById('auction-countdown-overlay').style.display = 'none';
                    // Clear countdown timer when live
                    const timerEl = document.getElementById('countdownTimer');
                    if (timerEl) {
                        timerEl.style.display = 'none';
                        timerEl.textContent = '';
                    }
                    updateAuctionState(data.active_auction);
                } else if (data.active_auction.status === 'NOT_STARTED' && data.active_auction.start_time) {
                    // Show dashboard with countdown in the header
                    document.querySelector('.live-auction-container').style.display = 'block';
                    document.getElementById('auction-countdown-overlay').style.display = 'none'; // Hide overlay just in case

                    // Show countdown timer
                    const timerEl = document.getElementById('countdownTimer');
                    if (timerEl) {
                        timerEl.style.display = 'block';
                    }

                    document.getElementById('auctionStatus').textContent = 'Starting Soon';
                    document.getElementById('auctionStatus').className = 'auction-status status-not-started';
                    document.getElementById('auctionContent').innerHTML = `
                        <div class="waiting-message">
                            <h3>Auction Starts Soon</h3>
                            <p>Please wait for the event to begin.</p>
                        </div>
                    `;

                    const startTime = new Date(data.active_auction.start_time).getTime();
                    startCountdown(startTime);
                } else {
                    document.querySelector('.live-auction-container').style.display = 'block';
                    document.getElementById('auction-countdown-overlay').style.display = 'none'; // Hide overlay

                    // Reset/Hide countdown
                    const timerEl = document.getElementById('countdownTimer');
                    if (timerEl) {
                        timerEl.textContent = '--:--';
                        timerEl.style.display = 'block';
                    }

                    document.getElementById('auctionStatus').textContent = 'Waiting';
                    document.getElementById('auctionStatus').className = 'auction-status status-not-started';
                    document.getElementById('countdownTimer').textContent = '--:--';
                    document.getElementById('auctionContent').innerHTML = `
                        <div class="waiting-message">
                            <h3>Waiting for Auction</h3>
                            <p>The auction for your event has not started yet.</p>
                        </div>
                     `;
                }
            }
        } else {
            console.error('Failed to load team owner dashboard data');
            if (response.status === 401 || response.status === 403) {
                // Handle auth error
                window.location.href = 'index.html';
            }
        }
    } catch (error) {
        console.error('Error loading team owner data:', error);
    }
}

// Load and display squad
// Update auction state
function updateAuctionState(auctionData) {
    if (!auctionData) return;

    // Update local state
    currentAuction.id = auctionData.auction_id;
    currentAuction.eventId = auctionData.event_id;
    currentAuction.status = auctionData.status;
    currentAuction.currentBid = auctionData.current_bid;
    currentAuction.highestBidder = auctionData.highest_bidder;

    // Update player info
    if (auctionData.current_player) {
        currentAuction.currentPlayer = {
            id: auctionData.current_player.id,
            name: auctionData.current_player.name,
            sport: auctionData.current_player.sport,
            category: auctionData.current_player.category,
            basePrice: auctionData.current_player.basePrice,
            rating: auctionData.current_player.rating
        };

        // Update UI
        updateAuctionDisplay();
    } else {
        // No current player - might be waiting for next player
        currentAuction.currentPlayer = null;
        document.getElementById('auctionContent').innerHTML = `
            <div class="waiting-message">
                <h3>Auction is Live!</h3>
                <p>Waiting for the next player to be announced...</p>
            </div>
        `;
    }

    // Update status badge
    const statusEl = document.getElementById('auctionStatus');
    if (statusEl) {
        statusEl.textContent = 'Live Auction';
        statusEl.className = 'auction-status status-running';
    }

    // Clear countdown timer if exists to avoid 00:00 confusion
    const timerEl = document.getElementById('countdownTimer');
    if (timerEl) {
        timerEl.textContent = '';
    }
}

// Helper for UI Updates
function updateAuctionDisplay() {
    if (!currentAuction.currentPlayer) return;

    const player = currentAuction.currentPlayer;
    const isHigherBid = currentAuction.currentBid > 0;

    const html = `
        <div class="player-card-auction">
            <div class="player-header">
                <div class="player-avatar-large">
                    ${player.avatar ? `<img src="${player.avatar}" alt="${player.name}" style="width:100%;height:100%;border-radius:50%;object-fit:cover;">` : player.name.charAt(0)}
                </div>
                <div class="player-info-large">
                    <h3>${player.name}</h3>
                    <div class="player-tier-large tier-${player.category.toLowerCase()}">${player.category}</div>
                </div>
            </div>

            <div class="player-stats-large">
                <div class="stat-large">
                    <div class="stat-value-large">${player.rating}</div>
                    <div class="stat-label-large">Rating</div>
                </div>
                <div class="stat-large">
                    <div class="stat-value-large">${player.sport}</div>
                    <div class="stat-label-large">Sport</div>
                </div>
                <div class="stat-large">
                    <div class="stat-value-large">All-Rounder</div>
                    <div class="stat-label-large">Role</div>
                </div>
            </div>

            <div class="base-price-large">
                <div class="base-price-amount">₹${player.basePrice.toLocaleString()}</div>
                <div class="base-price-label">Base Price</div>
            </div>
        </div>

        <div class="bidding-panel">
            <div class="current-bid">
                <div class="current-bid-amount">₹${currentAuction.currentBid.toLocaleString()}</div>
                <div class="current-bid-label">Current Highest Bid (${currentAuction.highestBidder || 'None'})</div>
            </div>

            <div class="quick-bid-buttons">
                <button class="quick-bid-btn" onclick="placeQuickBid(${currentAuction.currentBid + 10000})">+ 10k</button>
                <button class="quick-bid-btn" onclick="placeQuickBid(${currentAuction.currentBid + 50000})">+ 50k</button>
                <button class="quick-bid-btn" onclick="placeQuickBid(${currentAuction.currentBid + 100000})">+ 1L</button>
            </div>

            <div class="custom-bid-section">
                <div class="bid-slider-container">
                    <div class="slider-value" id="sliderValue">₹${currentAuction.currentBid.toLocaleString()}</div>
                    <input type="range" min="${currentAuction.currentBid}" max="${parseInt(sessionStorage.getItem('walletBalance')) || 10000000}" step="10000" value="${currentAuction.currentBid}" class="slider" id="bidSlider">
                </div>
                <button class="place-bid-btn" id="placeBidBtn" onclick="placeCustomBid()">Place Bid</button>
            </div>
        </div>
    `;

    document.getElementById('auctionContent').innerHTML = html;

    // Re-bind slider events
    const slider = document.getElementById('bidSlider');
    const sliderValue = document.getElementById('sliderValue');
    const placeBidBtn = document.getElementById('placeBidBtn');
    const walletBalance = parseInt(sessionStorage.getItem('walletBalance')) || 0;

    if (slider) {
        slider.addEventListener('input', function () {
            sliderValue.textContent = `₹${parseInt(this.value).toLocaleString()}`;
            placeBidBtn.disabled = parseInt(this.value) > walletBalance;
        });
    }
}

// Load and display squad
function loadSquad() {
    // This is now triggered by loadTeamOwnerData or uses stored data
    const storedSquad = sessionStorage.getItem('squadData');
    if (storedSquad) {
        try {
            renderSquad(JSON.parse(storedSquad));
        } catch (e) {
            console.error('Error parsing squad data', e);
        }
    }
}

function renderSquad(squad) {
    const squadList = document.getElementById('squadList');
    if (!squadList) return;

    squadList.innerHTML = '';

    if (squad && squad.length > 0) {
        squad.forEach(player => {
            const squadPlayer = document.createElement('div');
            squadPlayer.className = 'squad-player';

            squadPlayer.innerHTML = `
                <div class="squad-player-avatar">
                   ${player.avatar ? `<img src="${player.avatar}" alt="${player.name}" style="width:100%;height:100%;object-fit:cover;border-radius:50%;">` : '<i class="fas fa-user"></i>'}
                </div>
                <div class="squad-player-info">
                    <div class="squad-player-name">${player.name}</div>
                    <div class="squad-player-price">₹${player.price.toLocaleString()}</div>
                </div>
            `;

            squadList.appendChild(squadPlayer);
        });
    } else {
        squadList.innerHTML = `
            <div class="empty-squad">
                <i class="fas fa-users" style="font-size: 3rem; color: #64748b; margin-bottom: 1rem;"></i>
                <p>Your squad is empty. Start bidding to acquire players!</p>
            </div>
        `;
    }
}

// Render participating players list
function renderParticipants(participants) {
    const participantsList = document.getElementById('participantsList');
    if (!participantsList) return;

    participantsList.innerHTML = '';

    if (participants && participants.length > 0) {
        participants.forEach(player => {
            const item = document.createElement('div');
            item.className = 'participant-item';

            item.innerHTML = `
                <div class="participant-avatar">
                   ${player.avatar ? `<img src="${player.avatar}" alt="${player.name}" style="width:100%;height:100%;object-fit:cover;">` : player.name.charAt(0)}
                </div>
                <div class="participant-info">
                    <div class="participant-name">${player.name}</div>
                    <div class="participant-rating">Rating: ${player.rating || 'N/A'}</div>
                </div>
            `;

            participantsList.appendChild(item);
        });
    } else {
        participantsList.innerHTML = `
            <div class="waiting-message" style="padding: 1rem; font-size: 0.9rem;">
                No participants registered yet.
            </div>
        `;
    }
}

// Initialize auction display
function initializeAuction() {
    fetchAuctionStatus();
    // Poll every 3 seconds for updates
    setInterval(fetchAuctionStatus, 3000);
}

// Fetch current auction status from backend
async function fetchAuctionStatus() {
    try {
        let url = '/api/team-owner/dashboard';
        if (currentTeamId) {
            url += `?team_id=${currentTeamId}`;
        }

        const response = await fetch(url, {
            headers: { 'Accept': 'application/json' },
            credentials: 'include'
        });

        if (response.ok) {
            const data = await response.json();

            // 1. Update Wallet Balance Live
            if (data.wallet_balance !== undefined) {
                const walletEl = document.getElementById('walletAmount');
                if (walletEl) {
                    walletEl.textContent = `₹${data.wallet_balance.toLocaleString()}`;
                }
                // Update session storage too
                sessionStorage.setItem('walletBalance', data.wallet_balance);
            }

            // 2. Handle Auction Status
            if (data.active_auction) {
                // Update countdown if running
                if (data.active_auction.status === 'RUNNING' && data.active_auction.current_player) {
                    const timeLeft = data.active_auction.current_player.time_left;
                    const timerEl = document.getElementById('countdownTimer');
                    if (timerEl) {
                        timerEl.style.display = 'block';
                        timerEl.textContent = formatTime(Math.ceil(timeLeft));
                        // Flash red if under 5 seconds
                        if (timeLeft < 5) {
                            timerEl.style.color = '#ef4444';
                            timerEl.style.animation = 'pulse 1s infinite';
                        } else {
                            timerEl.style.color = '#4F46E5';
                            timerEl.style.animation = 'none';
                        }
                    }
                }

                // Check if status changed from NOT_STARTED to RUNNING
                if (data.active_auction.status === 'RUNNING') {
                    // Ensure the UI switches to Live mode immediately
                    const liveContainer = document.querySelector('.live-auction-container');
                    if (liveContainer) liveContainer.style.display = 'block';

                    const overlay = document.getElementById('auction-countdown-overlay');
                    if (overlay) overlay.style.display = 'none';

                    // Call the state updater
                    if (typeof updateAuctionState === 'function') {
                        updateAuctionState(data.active_auction);
                    }
                } else if (data.active_auction.status === 'NOT_STARTED') {
                    // Just ensure the "Starting Soon" text is there if needed
                    const statusEl = document.getElementById('auctionStatus');
                    if (statusEl && statusEl.textContent !== 'Starting Soon') {
                        statusEl.textContent = 'Starting Soon';
                        statusEl.className = 'auction-status status-not-started';
                    }
                }
            }

            // 3. Update Participating Players
            if (data.participating_players) {
                renderParticipants(data.participating_players);
            }

            // 4. Update Squad if returned
            if (data.squad) {
                renderSquad(data.squad);
            }
        }
    } catch (error) {
        console.error('Error fetching auction status:', error);
    }
}

// Format seconds into MM:SS
function formatTime(seconds) {
    if (isNaN(seconds) || seconds < 0) return '00:00';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

// Update auction display based on current state
function updateAuctionDisplay() {
    const auctionContent = document.getElementById('auctionContent');
    const auctionStatus = document.getElementById('auctionStatus');
    const countdownTimer = document.getElementById('countdownTimer');

    // Update status
    let statusText = '';
    let statusClass = '';

    switch (currentAuction.status) {
        case 'NOT_STARTED':
            statusText = 'Auction Not Started';
            statusClass = 'status-not-started';
            countdownTimer.style.display = 'none';
            break;
        case 'RUNNING':
            statusText = 'Now Bidding';
            statusClass = 'status-running';
            countdownTimer.style.display = 'block';
            break;
        case 'PAUSED':
            statusText = 'Auction Paused';
            statusClass = 'status-paused';
            countdownTimer.style.display = 'none';
            break;
        case 'ENDED':
            statusText = 'Auction Ended';
            statusClass = 'status-ended';
            countdownTimer.style.display = 'none';
            break;
    }

    auctionStatus.textContent = statusText;
    auctionStatus.className = `auction-status ${statusClass}`;

    // Update countdown timer
    if (currentAuction.status === 'RUNNING') {
        countdownTimer.textContent = formatTime(currentAuction.timeLeft);
    }

    // Update content based on auction state
    if (currentAuction.status === 'NOT_STARTED' || currentAuction.status === 'ENDED') {
        auctionContent.innerHTML = `
            <div class="waiting-message">
                ${currentAuction.status === 'NOT_STARTED'
                ? 'Waiting for auction to start...'
                : 'The auction has concluded.'}
            </div>
        `;
    } else if (currentAuction.status === 'RUNNING' && currentAuction.currentPlayer) {
        displayPlayerCard();
    } else {
        auctionContent.innerHTML = `
            <div class="waiting-message">
                No player is currently being auctioned.
            </div>
        `;
    }
}

// Display current player card
function displayPlayerCard() {
    const auctionContent = document.getElementById('auctionContent');
    const player = currentAuction.currentPlayer;
    const walletBalance = parseInt(sessionStorage.getItem('walletBalance')) || 0;

    // Calculate stats (mocking Wins/Losses removed, using DB fallback 0)
    const wins = player.stats && player.stats.wins ? player.stats.wins : 0;
    const losses = player.stats && player.stats.losses ? player.stats.losses : 0;

    auctionContent.innerHTML = `
        <div class="player-card-premium" style="background: white; border-radius: 1rem; padding: 1.5rem; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); display: flex; flex-direction: column; align-items: center; max-width: 400px; margin: 0 auto;">
            <div class="player-header" style="text-align: center; margin-bottom: 1.5rem; width: 100%;">
                <div class="player-avatar-large" style="width: 100px; height: 100px; border-radius: 50%; background: #f3f4f6; margin: 0 auto 1rem; display: flex; align-items: center; justify-content: center; overflow: hidden; border: 3px solid #4f46e5;">
                    ${player.avatar
            ? `<img src="${player.avatar}" alt="${player.name}" style="width:100%;height:100%;object-fit:cover;">`
            : `<i class="fas fa-user" style="font-size: 3rem; color: #9ca3af;"></i>`}
                </div>
                <h3 style="font-size: 1.5rem; font-weight: 700; color: #111827; margin-bottom: 0.25rem;">${player.name}</h3>
                <span class="player-tier-badge" style="background: #4f46e5; color: white; padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; text-transform: uppercase;">
                    ${player.category || 'Standard'}
                </span>
            </div>

            <div class="player-stats-grid" style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; width: 100%; margin-bottom: 2rem; border-top: 1px solid #e5e7eb; border-bottom: 1px solid #e5e7eb; padding: 1rem 0;">
                <div class="stat-item" style="text-align: center;">
                    <div style="font-size: 1.25rem; font-weight: 700; color: #111827;">${player.rating || 'N/A'}</div>
                    <div style="font-size: 0.75rem; color: #6b7280; text-transform: uppercase; font-weight: 600;">Rating</div>
                </div>
                <div class="stat-item" style="text-align: center;">
                    <div style="font-size: 1.25rem; font-weight: 700; color: #111827;">${wins}</div>
                    <div style="font-size: 0.75rem; color: #6b7280; text-transform: uppercase; font-weight: 600;">Wins</div>
                </div>
                <div class="stat-item" style="text-align: center;">
                    <div style="font-size: 1.25rem; font-weight: 700; color: #111827;">${losses}</div>
                    <div style="font-size: 0.75rem; color: #6b7280; text-transform: uppercase; font-weight: 600;">Losses</div>
                </div>
            </div>

            <div class="bid-info" style="width: 100%; margin-bottom: 1.5rem;">
                <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
                    <span style="color: #6b7280;">Base Price</span>
                    <span style="font-weight: 600; color: #111827;">₹${(player.basePrice || 0).toLocaleString()}</span>
                </div>
                <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
                    <span style="color: #6b7280;">Current Bid</span>
                    <span style="font-weight: 600; color: #4f46e5; font-size: 1.1rem;">₹${(currentAuction.currentBid || 0).toLocaleString()}</span>
                </div>
            </div>

            <!-- Bidding Controls moved to wrapper but we can inject them here or keep separate -->
             <div class="custom-bid-section" style="width: 100%;">
                 <input type="range" min="${currentAuction.currentBid || player.basePrice}" max="${(currentAuction.currentBid || player.basePrice) * 2}" value="${currentAuction.currentBid || player.basePrice}" class="slider" id="bidSlider" oninput="updateSliderValue(this.value)" style="width: 100%; margin-bottom: 1rem;">
                 <div class="slider-value" id="sliderValue" style="text-align: center; font-size: 1.25rem; font-weight: 700; color: #4f46e5; margin-bottom: 1rem;">₹${(currentAuction.currentBid || player.basePrice).toLocaleString()}</div>
                 <button class="place-bid-btn" onclick="placeCustomBid()" style="width: 100%; padding: 0.875rem; background: #4f46e5; color: white; border: none; border-radius: 0.5rem; font-weight: 600; font-size: 1rem; cursor: pointer; transition: background 0.2s;">
                    Place Bid
                 </button>
            </div>
        </div>
    `;
}

// Update slider value display
function updateSliderValue(val) {
    const sliderValue = document.getElementById('sliderValue');
    if (sliderValue) {
        sliderValue.textContent = `₹${parseInt(val).toLocaleString()}`;
    }
}

// Place quick bid
function placeQuickBid(amount) {
    const walletBalance = parseInt(sessionStorage.getItem('walletBalance')) || 1500000;

    if (amount > walletBalance) {
        showModal('Insufficient Balance', 'You do not have enough balance to place this bid.');
        return;
    }

    // Log the quick bid attempt
    adminLogActivity('Team Owner Quick Bid', `Amount: ₹${amount.toLocaleString()}, Player: ${currentAuction.currentPlayer?.name || 'Unknown'} `, 'team_owner');

    showBidConfirmation(amount);
}

// Place custom bid
function placeCustomBid() {
    const slider = document.getElementById('bidSlider');
    const amount = parseInt(slider.value);
    const walletBalance = parseInt(sessionStorage.getItem('walletBalance')) || 1500000;

    if (amount > walletBalance) {
        showModal('Insufficient Balance', 'You do not have enough balance to place this bid.');
        return;
    }

    // Log the custom bid attempt
    adminLogActivity('Team Owner Custom Bid', `Amount: ₹${amount.toLocaleString()}, Player: ${currentAuction.currentPlayer?.name || 'Unknown'} `, 'team_owner');

    showBidConfirmation(amount);
}

// Show bid confirmation modal
function showBidConfirmation(amount) {
    const modal = document.getElementById('auctionModal');
    const bidConfirmation = document.getElementById('bidConfirmation');
    const player = currentAuction.currentPlayer;

    bidConfirmation.innerHTML = `
    < div style = "text-align: center;" >
            <h3 style="margin-bottom: 1rem; color: #ffffff;">Confirm Your Bid</h3>
            <div style="background-color: #1e293b; padding: 1rem; border-radius: 0.5rem; margin-bottom: 1rem;">
                <div style="font-size: 1.25rem; font-weight: 600; color: #f97316; margin-bottom: 0.5rem;">
                    ${player.name}
                </div>
                <div style="color: #94a3b8; margin-bottom: 1rem;">${player.sport} - ${player.category}</div>
                <div style="font-size: 1.5rem; font-weight: 600; color: #22c55e;">
                    ₹${amount.toLocaleString()}
                </div>
            </div>
            <p style="color: #94a3b8;">Are you sure you want to place this bid?</p>
        </div >
    `;

    modal.style.display = 'flex';
    document.body.style.overflow = 'hidden';

    // Store bid amount for confirmation
    sessionStorage.setItem('pendingBidAmount', amount);
}

// Confirm bid
// Confirm bid
async function confirmBid() {
    const amount = parseInt(sessionStorage.getItem('pendingBidAmount'));
    const walletBalance = parseInt(sessionStorage.getItem('walletBalance')) || 0;

    if (amount > walletBalance) {
        showModal('Insufficient Balance', 'You do not have enough balance to place this bid.');
        closeAuctionModal();
        return;
    }

    if (!currentAuction.eventId || !currentAuction.currentPlayer) {
        showModal('Error', 'No active auction or player found.');
        closeAuctionModal();
        return;
    }

    try {
        const response = await fetch(`/auction/${currentAuction.eventId}/bid/${currentAuction.currentPlayer.id}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ amount: amount }),
            credentials: 'include'
        });

        if (response.ok) {
            const result = await response.json();

            // Log the successful bid
            adminLogActivity('Team Owner Bid', `Placed bid of ₹${amount.toLocaleString()} for ${currentAuction.currentPlayer.name}`, 'team_owner');

            closeAuctionModal();
            showModal('Bid Placed!', `You successfully placed a bid of ₹${amount.toLocaleString()} !`);

            // Refresh dashboard data immediately
            loadTeamOwnerData();

        } else {
            const error = await response.json();
            closeAuctionModal();
            showModal('Bid Failed', error.detail || 'Failed to place bid. Please try again.');
        }
    } catch (error) {
        console.error('Error placing bid:', error);
        closeAuctionModal();
        showModal('Error', 'An error occurred while placing your bid.');
    }
}

// Add player to squad
// Add player to squad
function addPlayerToSquad(player, price) {
    const storedSquad = sessionStorage.getItem('squadData');
    let squad = [];
    try {
        squad = storedSquad ? JSON.parse(storedSquad) : [];
    } catch (e) {
        console.error('Error parsing squad data', e);
    }

    const newPlayer = {
        id: player.id,
        name: player.name,
        email: `${player.name.toLowerCase().replace(' ', '.')} @email.com`,
        sport: player.sport,
        rating: player.rating,
        category: player.category,
        price: price,
        avatar: player.avatar
    };

    squad.push(newPlayer);
    sessionStorage.setItem('squadData', JSON.stringify(squad));
    renderSquad(squad);
}

// Simulate next player (for demo purposes)
function simulateNextPlayer() {
    const players = [
        {
            id: 4,
            name: 'Sarah Johnson',
            sport: 'Basketball',
            rating: 8.5,
            category: 'Gold',
            basePrice: 150000,
            avatar: ''
        },
        {
            id: 5,
            name: 'Michael Chen',
            sport: 'Tennis',
            rating: 9.0,
            category: 'Platinum',
            basePrice: 300000,
            avatar: ''
        },
        {
            id: 6,
            name: 'Emma Davis',
            sport: 'Football',
            rating: 8.2,
            category: 'Silver',
            basePrice: 120000,
            avatar: ''
        }
    ];

    const randomPlayer = players[Math.floor(Math.random() * players.length)];
    currentAuction.currentPlayer = randomPlayer;
    currentAuction.currentBid = randomPlayer.basePrice;
    currentAuction.highestBidder = 'Starting Bid';

    // Use the bidding time preference
    const bidTimeLimit = currentAuction.bidTimeLimit || 20;
    currentAuction.timeLeft = bidTimeLimit;

    updateAuctionDisplay();
}

// Setup event listeners
function setupEventListeners() {
    // Contact support functionality
    // Contact support functionality
    window.contactSupport = function () {
        const teamName = sessionStorage.getItem('teamName') || 'Unknown Team';
        const modalId = 'contactSupportModal';

        // Remove existing modal if it exists to ensure fresh content
        const existingModal = document.getElementById(modalId);
        if (existingModal) {
            existingModal.remove();
        }

        // Create custom modal for contact support
        const modal = document.createElement('div');
        modal.id = modalId;
        modal.className = 'modal-overlay';
        modal.style.position = 'fixed';
        modal.style.top = '0';
        modal.style.left = '0';
        modal.style.width = '100%';
        modal.style.height = '100%';
        modal.style.backgroundColor = 'rgba(0, 0, 0, 0.7)';
        modal.style.display = 'flex';
        modal.style.justifyContent = 'center';
        modal.style.alignItems = 'center';
        modal.style.zIndex = '1000';

        modal.innerHTML = `
<div style="background-color: #1e293b; padding: 2rem; border-radius: 0.5rem; max-width: 500px; width: 90%; position: relative;">
    <h2 style="color: #ffffff; margin-top: 0; margin-bottom: 1rem;">Contact Admin</h2>
    <div style="margin-bottom: 1rem;">
        <label style="display: block; color: #94a3b8; margin-bottom: 0.5rem;">Subject</label>
        <input type="text" id="contactSubject" placeholder="e.g., Auction Issue" style="width: 100%; padding: 0.75rem; background-color: #0f172a; border: 1px solid #334155; color: white; border-radius: 0.25rem;">
    </div>
    <div style="margin-bottom: 1rem;">
        <label style="display: block; color: #94a3b8; margin-bottom: 0.5rem;">Message</label>
        <textarea id="contactMessage" rows="5" placeholder="Describe your issue..." style="width: 100%; padding: 0.75rem; background-color: #0f172a; border: 1px solid #334155; color: white; border-radius: 0.25rem;"></textarea>
    </div>
    <div style="display: flex; justify-content: flex-end; gap: 1rem;">
        <button onclick="document.getElementById('${modalId}').remove()" style="padding: 0.5rem 1rem; background: transparent; border: 1px solid #94a3b8; color: #94a3b8; border-radius: 0.25rem; cursor: pointer;">Cancel</button>
        <button onclick="submitContactMessage()" style="padding: 0.5rem 1rem; background-color: #f97316; border: none; color: white; border-radius: 0.25rem; cursor: pointer;">Send</button>
    </div>
</div>
`;
        document.body.appendChild(modal);
    };

    window.submitContactMessage = async function () {
        const subject = document.getElementById('contactSubject').value;
        const content = document.getElementById('contactMessage').value;
        const teamName = sessionStorage.getItem('teamName');
        const username = sessionStorage.getItem('username');

        if (!content) {
            alert('Please enter a message');
            return;
        }

        try {
            const response = await fetch('/api/messages', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    subject: subject || 'Support Request',
                    content: content,
                    team_name: teamName,
                    sender_name: username
                })
            });

            if (response.ok) {
                document.getElementById('contactSupportModal').style.display = 'none';
                document.getElementById('contactSubject').value = '';
                document.getElementById('contactMessage').value = '';
                showModal('Message Sent', 'Admin has been notified immediately.');
                adminLogActivity('Contact Admin', `Message sent: ${subject} `, 'team_owner');
            } else {
                throw new Error('Failed to send message');
            }
        } catch (error) {
            console.error('Error sending message:', error);
            showModal('Error', 'Failed to send message. Please try again.');
        }
    };

    // Download squad CSV
    window.downloadSquadCSV = function () {
        const teamName = sessionStorage.getItem('teamName') || 'My_Team';
        const squadDataStr = sessionStorage.getItem('squadData');
        let squad = [];
        
        try {
            squad = squadDataStr ? JSON.parse(squadDataStr) : [];
        } catch (e) {
            console.error('Error parsing squad data', e);
        }

        if (!squad || squad.length === 0) {
            showModal('No Data', 'Your squad is empty. No data to download.');
            return;
        }

        // Log the download action
        adminLogActivity('Team Owner Squad Download', `Team: ${teamName}, Players: ${squad.length} `, 'team_owner');

        // Create CSV content
        let csvContent = 'ID,Name,Email,Sport,Rating,Category,Price\n';

        squad.forEach(player => {
            csvContent += `${player.id},${player.name},${player.email},${player.sport},${player.rating},${player.category},${player.price} \n`;
        });

        // Create and download file
        const blob = new Blob([csvContent], { type: 'text/csv' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${teamName}_Squad.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);

        showModal('Download Complete', 'Your squad data has been downloaded successfully!');
    };

    // Close modal functions
    window.closeAuctionModal = function () {
        // Log the modal close action
        adminLogActivity('Bid Modal Closed', 'Team owner cancelled bid', 'team_owner');
        document.getElementById('auctionModal').style.display = 'none';
        document.body.style.overflow = '';
        sessionStorage.removeItem('pendingBidAmount');
    };
}

// Start auction polling (removed client-side simulation)
function startAuctionTimer() {
    setInterval(() => {
        if (currentTeamId) {
            loadTeamOwnerData(currentTeamId); // Poll the backend to get actual state
        }
    }, 5000);
}

// Simulate random bid from another team (Removed - driven by backend)
function simulateRandomBid() {
    // Removed client-side simulation
}

// Simulate next player (Removed - driven by backend)
function simulateNextPlayer() {
    // Removed client-side simulation
}

// Format time in MM:SS
function formatTime(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')} `;
}

// Show modal function
function showModal(title, message) {
    // Create modal if it doesn't exist
    let modal = document.querySelector('.modal-overlay');
    if (!modal) {
        modal = document.createElement('div');
        modal.className = 'modal-overlay';
        modal.style.display = 'none';
        modal.style.position = 'fixed';
        modal.style.top = '0';
        modal.style.left = '0';
        modal.style.width = '100%';
        modal.style.height = '100%';
        modal.style.backgroundColor = 'rgba(0, 0, 0, 0.7)';
        modal.style.display = 'flex';
        modal.style.justifyContent = 'center';
        modal.style.alignItems = 'center';
        modal.style.zIndex = '1000';

        // Create modal content
        const modalContent = document.createElement('div');
        modalContent.style.backgroundColor = '#1e293b';
        modalContent.style.padding = '2rem';
        modalContent.style.borderRadius = '0.5rem';
        modalContent.style.maxWidth = '500px';
        modalContent.style.width = '90%';
        modalContent.style.position = 'relative';

        // Create title element
        const titleElement = document.createElement('h2');
        titleElement.style.color = '#ffffff';
        titleElement.style.marginTop = '0';
        titleElement.style.marginBottom = '1rem';

        // Create message element
        const messageElement = document.createElement('div');
        messageElement.style.color = '#94a3b8';
        messageElement.style.lineHeight = '1.6';
        messageElement.style.marginBottom = '1.5rem';

        // Create OK button
        const okButton = document.createElement('button');
        okButton.textContent = 'OK';
        okButton.style.padding = '0.5rem 1.5rem';
        okButton.style.backgroundColor = '#f97316';
        okButton.style.color = 'white';
        okButton.style.border = 'none';
        okButton.style.borderRadius = '0.25rem';
        okButton.style.cursor = 'pointer';
        okButton.onclick = function () {
            modal.style.display = 'none';
        };

        // Assemble the modal
        modalContent.appendChild(titleElement);
        modalContent.appendChild(messageElement);
        modalContent.appendChild(okButton);
        modal.appendChild(modalContent);
        document.body.appendChild(modal);
    }

    // Update modal content
    const modalContent = modal.querySelector('div') || modal;
    let titleElement = modal.querySelector('h2');
    let messageElement = modal.querySelector('div:nth-child(2)');

    if (!titleElement) {
        titleElement = document.createElement('h2');
        titleElement.style.color = '#ffffff';
        titleElement.style.marginTop = '0';
        titleElement.style.marginBottom = '1rem';
        modalContent.insertBefore(titleElement, modalContent.firstChild);
    }

    if (!messageElement) {
        messageElement = document.createElement('div');
        messageElement.style.color = '#94a3b8';
        messageElement.style.lineHeight = '1.6';
        messageElement.style.marginBottom = '1.5rem';
        const okButton = modal.querySelector('button');
        if (okButton) {
            modalContent.insertBefore(messageElement, okButton);
        } else {
            modalContent.appendChild(messageElement);
        }
    }

    // Set the content
    titleElement.textContent = title;
    messageElement.innerHTML = message;

    // Show the modal
    modal.style.display = 'flex';

    // Close modal when clicking outside
    modal.onclick = function (event) {
        if (event.target === modal) {
            modal.style.display = 'none';
        }
    };

    return modal;
}

// Logout function
async function logout() {
    const userStr = localStorage.getItem('user');
    const user = userStr ? JSON.parse(userStr) : null;
    const username = user ? user.username : 'Unknown';

    // Log the logout action
    adminLogActivity('Team Owner Logout', `Username: ${username}`, 'team_owner');

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
    localStorage.removeItem('walletBalance');
    localStorage.removeItem('teamOwnerData');
    
    window.location.replace('/');
}
// Countdown Timer Logic
let countdownInterval;

function startCountdown(startTime) {
    // Inline timer elements
    const timerElement = document.getElementById('countdownTimer');
    const statusElement = document.getElementById('auctionStatus');
    const overlay = document.getElementById('auction-countdown-overlay');
    if (overlay) overlay.style.display = 'none'; // Ensure overlay is hidden

    clearInterval(countdownInterval);

    function updateTimer() {
        const now = new Date().getTime();
        const distance = startTime - now;

        if (distance < 0) {
            clearInterval(countdownInterval);
            if (statusElement) statusElement.textContent = 'Live!';
            if (timerElement) timerElement.textContent = '00:00:00';

            // Reload to fetch live auction data
            setTimeout(() => {
                window.location.reload();
            }, 2000);
            return;
        }

        const days = Math.floor(distance / (1000 * 60 * 60 * 24));
        const hours = Math.floor((distance % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
        const minutes = Math.floor((distance % (1000 * 60 * 60)) / (1000 * 60));
        const seconds = Math.floor((distance % (1000 * 60)) / 1000);

        if (timerElement) {
            timerElement.textContent = `${days > 0 ? days + 'd ' : ''}${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')} `;
        }
    }

    updateTimer(); // Run immediately
    countdownInterval = setInterval(updateTimer, 1000);
}

// Apply role-based UI permissions
function applyRolePermissions(user) {
    // Analyst shouldn't see wallet or perform bidding
    if (user.user_type === 'team_analyst') {
        const walletCards = document.querySelectorAll('.wallet-card');
        walletCards.forEach(card => card.style.display = 'none');
        
        // Hide bidding controls
        const bidControls = document.getElementById('bidControls');
        if (bidControls) bidControls.style.display = 'none';
        
        // Add a visual indicator of their role
        const headerTitle = document.querySelector('.header h2') || document.querySelector('.header .nav-logo span');
        if (headerTitle) {
            headerTitle.textContent = 'BidZone - Team Analyst Dashboard';
        }
    } 
    // Manager has bidding rights but maybe not wallet access
    else if (user.user_type === 'team_manager') {
        const walletCards = document.querySelectorAll('.wallet-card');
        walletCards.forEach(card => card.style.display = 'none');
        
        const headerTitle = document.querySelector('.header h2') || document.querySelector('.header .nav-logo span');
        if (headerTitle) {
            headerTitle.textContent = 'BidZone - Team Manager Dashboard';
        }
    }
}
