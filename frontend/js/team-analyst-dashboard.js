
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

    // Setup generic input listeners
    document.querySelectorAll('.saas-input').forEach(input => {
        input.addEventListener('focus', function () {
            this.parentElement.classList.add('focused');
        });
        input.addEventListener('blur', function () {
            this.parentElement.classList.remove('focused');
        });
    });
});
// ------------------------

// Team Owner Dashboard
// Authentication check
document.addEventListener('DOMContentLoaded', function () {


    // Check if user is authenticated via localStorage
    const userStr = sessionStorage.getItem('user');
    if (!userStr) {

        window.location.replace('/');
        return;
    }

    let user;
    try {
        user = JSON.parse(userStr);
    } catch (e) {
        console.error('[INIT] Failed to parse user from localStorage', e);
        window.location.replace('/');
        return;
    }


    // Check if user is team owner, manager, or analyst
    if (!['team_owner', 'team_manager', 'team_analyst'].includes(user.user_type)) {

        showModal('Access Denied', 'Please login as a team owner, manager, or analyst to access this page.');
        setTimeout(() => {
            window.location.replace('/');
        }, 2000);
        return;
    }


    // Apply role-based UI restrictions
    applyRolePermissions(user);

    // Verify session with backend single source of truth
    fetch('/api/me')
        .then(res => {
            if (!res.ok) throw new Error('Unauthenticated');
            return res.json();
        })
        .then(data => {
            const role = (data.user && data.user.user_type) ? data.user.user_type : data.user_type;
            if (!data.authenticated || !['team_owner', 'team_manager', 'team_analyst'].includes(role)) {
                console.warn('[AUTH] Session invalid or role mismatch:', role);
                sessionStorage.removeItem('user');
                sessionStorage.removeItem('session_token');
                sessionStorage.clear();
                window.location.replace('/');
            } else if (data.user) {
                sessionStorage.setItem('user', JSON.stringify(data.user));
                
                // Update User Dropdown
                const headerUserName = document.getElementById('headerUserName');
                const dropdownUserName = document.getElementById('dropdownUserName');
                const dropdownUserRole = document.getElementById('dropdownUserRole');
                if (headerUserName) headerUserName.textContent = data.user.username || 'Team Owner';
                if (dropdownUserName) dropdownUserName.textContent = data.user.username || 'Team Owner';
                if (dropdownUserRole) dropdownUserRole.textContent = (data.user.user_type || 'Owner').replace('_', ' ');
            }
        })
        .catch(err => {
            console.error('[AUTH] Server session check failed:', err);
            sessionStorage.removeItem('user');
            sessionStorage.removeItem('session_token');
            sessionStorage.clear();
            window.location.replace('/');
        });

    // Check if auction is in preparation phase
    const currentAuctionStatus = localStorage.getItem('currentAuctionStatus');
    const auctionStarting = localStorage.getItem('auctionStarting');

    // Load bidding time preference from team owner's selection or admin's decision
    const teamBidTime = localStorage.getItem('teamBidTimePreference');
    const adminBidTime = localStorage.getItem('auctionBidTime');

    if (adminBidTime) {
        currentAuction.bidTimeLimit = parseInt(adminBidTime);

    } else if (teamBidTime) {
        currentAuction.bidTimeLimit = parseInt(teamBidTime);

    }

    if (currentAuctionStatus === 'NOT_STARTED' && auctionStarting === 'true') {

        return;
    } else if (currentAuctionStatus === 'NOT_STARTED' && !auctionStarting) {

    }

    if (user.user_type === 'team_owner') {

        loadTeamOwnerData();

        loadSquad();

        loadAuctionPool();

        initTrainingCalendar();

        initializeAuction();

        startAuctionTimer();

        // As a superset role, Team Owner also needs Analyst and Manager data loaded

        if (typeof loadAnalystDashboard === 'function') loadAnalystDashboard();
    } else if (user.user_type === 'team_analyst') {

        if (typeof loadAnalystDashboard === 'function') loadAnalystDashboard();
        // Setup analyst specific initializations if needed
    } else if (user.user_type === 'team_manager') {

        loadTeamOwnerData();
        loadSquad();
        loadAuctionPool();
        initTrainingCalendar();
        initializeAuction();
        startAuctionTimer();
    }


    setupEventListeners();

    startHeartbeat();

    // Initial view rendering based on hash
    setTimeout(() => {
        let defaultHash = '#dashboard';
        if (user.user_type === 'team_analyst') defaultHash = '#analytics';
        else if (user.user_type === 'team_manager') defaultHash = '/dashboard/manager';
        const initialHash = window.location.hash || defaultHash;
        switchView(initialHash);
    }, 100);
});

// --- PRESENCE SYSTEM ---
let heartbeatInterval = null;

async function sendHeartbeat() {
    try {
        const res = await fetch('/api/presence/heartbeat', {
            method: 'POST',
            credentials: 'include'
        });
        if (res.status === 401 || res.status === 403) {
            // Session expired or revoked — stop heartbeat and force re-login
            clearInterval(heartbeatInterval);
            heartbeatInterval = null;
            sessionStorage.clear();
            window.location.replace('/');
        }
    } catch (err) {
        console.error('Heartbeat failed:', err);
    }
}

function startHeartbeat() {
    // Send immediately on load
    sendHeartbeat();
    // Then every 15 seconds
    if (!heartbeatInterval) {
        heartbeatInterval = setInterval(sendHeartbeat, 15000);
    }
}

window.addEventListener('beforeunload', () => {
    // Attempt to notify server of offline status during unload
    navigator.sendBeacon('/api/presence/offline');
});
// ------------------------

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

// --- VIEW LOADERS ---

async function loadPlayersView() {
    try {
        const response = await fetch('/api/team-owner/squad');
        if (!response.ok) throw new Error('Failed to load squad');
        const data = await response.json();
        window.currentSquadData = data.squad || [];

        const container = document.getElementById('playersFullList');
        if (!data.squad || data.squad.length === 0) {
            container.innerHTML = `
                <div class="empty-state" style="grid-column: 1 / -1;">
                    <i class="fas fa-users empty-icon" style="font-size: 3rem;"></i>
                    <p>You haven't acquired any players yet.</p>
                </div>
            `;
            return;
        }

        container.innerHTML = data.squad.map(player => `
            <div class="glass-card" style="padding: 1rem;">
                <div style="display: flex; align-items: center; gap: 1rem;">
                    <div style="width: 60px; height: 60px; border-radius: 50%; background: var(--accent-blue); display: flex; align-items: center; justify-content: center; overflow: hidden;">
                        ${player.avatar ? `<img src="${player.avatar}" style="width: 100%; height: 100%; object-fit: cover;">` : `<i class="fas fa-user" style="color: white; font-size: 1.5rem;"></i>`}
                    </div>
                    <div>
                        <h4 style="margin: 0; color: white;">${player.name}</h4>
                        <span class="badge" style="background: rgba(255,255,255,0.1); color: #94a3b8; font-size: 0.75rem; margin-top: 0.25rem; display: inline-block;">${player.category}</span>
                    </div>
                </div>
                <div style="margin-top: 1rem; padding-top: 1rem; border-top: 1px solid rgba(255,255,255,0.1); display: flex; justify-content: space-between;">
                    <div style="color: #94a3b8; font-size: 0.875rem;">Purchased For</div>
                    <div style="color: #10b981; font-weight: bold;">₹${player.price.toLocaleString()}</div>
                </div>
            </div>
        `).join('');

    } catch (err) {
        console.error('Error loading players:', err);
    }
}

let auctionPoolData = [];
let heatmapChartInstance = null;

async function loadAuctionPool() {
    try {
        const response = await fetch('/api/team-owner/auction-pool');
        if (!response.ok) throw new Error('Failed to load auction pool');
        const data = await response.json();

        auctionPoolData = data.pool || [];

        const tableBody = document.getElementById('scoutPoolTableBody');
        const select = document.getElementById('heatmapPlayerSelect');

        if (!tableBody || !select) return;

        if (auctionPoolData.length === 0) {
            tableBody.innerHTML = `<tr><td colspan="4" style="text-align: center; padding: 2rem; color: #64748b;">No registered players found.</td></tr>`;
            return;
        }

        // Populate Scout Pool Table
        tableBody.innerHTML = auctionPoolData.map(player => `
            <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
                <td style="padding: 0.75rem; color: white;">
                    <div style="display: flex; align-items: center; gap: 0.5rem;">
                        <div style="width: 32px; height: 32px; border-radius: 50%; background: var(--accent-blue); display: flex; align-items: center; justify-content: center; overflow: hidden;">
                            ${player.avatar ? `<img src="${player.avatar}" style="width: 100%; height: 100%; object-fit: cover;">` : `<i class="fas fa-user" style="color: white; font-size: 0.8rem;"></i>`}
                        </div>
                        ${player.name}
                    </div>
                </td>
                <td style="padding: 0.75rem; color: #cbd5e1;">${player.role}</td>
                <td style="padding: 0.75rem; text-align: center;">
                    <span class="badge" style="background: rgba(255,255,255,0.1); color: #94a3b8; font-size: 0.75rem;">${player.category}</span>
                </td>
                <td style="padding: 0.75rem; text-align: right; color: #10b981; font-weight: 500;">₹${player.base_price.toLocaleString()}</td>
            </tr>
        `).join('');

        // Populate Heatmap Dropdown
        select.innerHTML = '<option value="">Select a player...</option>' +
            auctionPoolData.map(p => `<option value="${p.id}">${p.name} (${p.role})</option>`).join('');

    } catch (err) {
        console.error('Error loading auction pool:', err);
    }
}

window.handleHeatmapSelectChange = function () {
    const select = document.getElementById('heatmapPlayerSelect');
    const playerId = parseInt(select.value);

    if (!playerId) {
        document.getElementById('heatmapEmptyState').style.display = 'flex';
        document.getElementById('heatmapCanvasContainer').style.display = 'none';
        return;
    }

    document.getElementById('heatmapEmptyState').style.display = 'none';
    document.getElementById('heatmapCanvasContainer').style.display = 'block';

    const player = auctionPoolData.find(p => p.id === playerId);
    if (player) {
        renderPlayerHeatmap(player);
    }
};

function renderPlayerHeatmap(player) {
    const ctx = document.getElementById('playerHeatmapChart').getContext('2d');

    if (heatmapChartInstance) {
        heatmapChartInstance.destroy();
    }

    // Configure axes based on role
    let labels = [];
    let data = [];

    const stats = player.stats || {};

    if (player.role.toLowerCase().includes('bowler')) {
        labels = ['Matches', 'Wickets', 'Economy', 'Avg', 'Strike Rate'];
        data = [stats.matches || 0, stats.wickets || 0, stats.economy || 0, stats.average || 0, stats.strike_rate || 0];
    } else if (player.role.toLowerCase().includes('all-rounder')) {
        labels = ['Runs', 'Strike Rate', 'Bat Avg', 'Wickets', 'Bowl Avg'];
        data = [stats.runs || 0, stats.strike_rate || 0, stats.average || 0, stats.wickets || 0, stats.economy || 0];
    } else {
        // Default to batsman
        labels = ['Runs', 'Strike Rate', 'Average', 'Highest Score', 'Matches'];
        data = [stats.runs || 0, stats.strike_rate || 0, stats.average || 0, stats.highest_score || 0, stats.matches || 0];
    }

    heatmapChartInstance = new Chart(ctx, {
        type: 'radar',
        data: {
            labels: labels,
            datasets: [{
                label: player.name + ' Performance',
                data: data,
                backgroundColor: 'rgba(34, 211, 238, 0.2)',
                borderColor: 'rgba(34, 211, 238, 1)',
                pointBackgroundColor: 'rgba(34, 211, 238, 1)',
                pointBorderColor: '#fff',
                pointHoverBackgroundColor: '#fff',
                pointHoverBorderColor: 'rgba(34, 211, 238, 1)',
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                r: {
                    angleLines: { color: 'rgba(255, 255, 255, 0.1)' },
                    grid: { color: 'rgba(255, 255, 255, 0.1)' },
                    pointLabels: { color: '#94a3b8', font: { size: 11, family: 'Inter' } },
                    ticks: { display: false }
                }
            },
            plugins: {
                legend: { labels: { color: '#fff', font: { family: 'Inter' } } }
            }
        }
    });
}

async function loadWalletView() {
    try {
        const response = await fetch('/api/team-owner/wallet');
        if (!response.ok) throw new Error('Failed to load wallet');
        const data = await response.json();

        document.getElementById('walletTotalBudget').textContent = `₹${data.total_budget.toLocaleString()}`;
        document.getElementById('walletSpent').textContent = `₹${data.spent.toLocaleString()}`;
        document.getElementById('walletAvailable').textContent = `₹${data.available.toLocaleString()}`;

        const list = document.getElementById('transactionHistoryList');
        if (!data.transactions || data.transactions.length === 0) {
            list.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-receipt empty-icon" style="font-size: 2rem;"></i>
                    <p>No transactions yet.</p>
                </div>
            `;
            return;
        }

        list.innerHTML = data.transactions.map(tx => `
            <div class="list-item" style="display: flex; justify-content: space-between; align-items: center; padding: 1rem; border-bottom: 1px solid rgba(255,255,255,0.05);">
                <div>
                    <div style="color: white; font-weight: 500;">${tx.description}: ${tx.player}</div>
                    <div style="color: #94a3b8; font-size: 0.875rem; margin-top: 0.25rem;">
                        <i class="fas fa-calendar-alt"></i> ${new Date(tx.date).toLocaleDateString()} | ${tx.event}
                    </div>
                </div>
                <div style="color: #ef4444; font-weight: bold;">-₹${tx.amount.toLocaleString()}</div>
            </div>
        `).join('');
    } catch (err) {
        console.error('Error loading wallet:', err);
    }
}

async function loadReportsView() {
    try {
        const response = await fetch('/api/team-owner/reports');
        if (!response.ok) throw new Error('Failed to load reports');
        const data = await response.json();

        // Auction Summary
        document.getElementById('reportAuctionSummary').innerHTML = `
            <div style="display: flex; justify-content: space-between;"><span>Total Auctions Participated:</span> <strong>${data.auction_summary.total_auctions}</strong></div>
            <div style="display: flex; justify-content: space-between;"><span>Players Purchased:</span> <strong>${data.auction_summary.players_purchased}</strong></div>
            <div style="display: flex; justify-content: space-between;"><span>Remaining Purse:</span> <strong style="color: #10b981;">₹${data.auction_summary.remaining_purse.toLocaleString()}</strong></div>
        `;

        // Spending Summary
        document.getElementById('reportSpendingSummary').innerHTML = `
            <div style="display: flex; justify-content: space-between;"><span>Total Spent:</span> <strong style="color: #ef4444;">₹${data.spending_summary.total.toLocaleString()}</strong></div>
            <div style="display: flex; justify-content: space-between;"><span>Avg. Player Price:</span> <strong>₹${data.spending_summary.avg_per_player.toLocaleString(undefined, { maximumFractionDigits: 2 })}</strong></div>
            <div style="display: flex; justify-content: space-between;"><span>Highest Purchase:</span> <strong>₹${data.auction_summary.highest_purchase.toLocaleString()}</strong></div>
            <div style="display: flex; justify-content: space-between;"><span>Lowest Purchase:</span> <strong>₹${data.auction_summary.lowest_purchase.toLocaleString()}</strong></div>
        `;

        // Auction History Table
        const historyContainer = document.getElementById('reportAuctionHistory');
        if (!data.auction_history || data.auction_history.length === 0) {
            historyContainer.innerHTML = '<div class="empty-state"><p>No auction history available.</p></div>';
        } else {
            let tableHTML = `
                <table style="width: 100%; text-align: left; border-collapse: collapse; color: white;">
                    <thead>
                        <tr style="border-bottom: 1px solid rgba(255,255,255,0.1);">
                            <th style="padding: 1rem;">Event Name</th>
                            <th style="padding: 1rem;">Date</th>
                            <th style="padding: 1rem;">Players Bought</th>
                            <th style="padding: 1rem;">Amount Spent</th>
                            <th style="padding: 1rem;">Status</th>
                        </tr>
                    </thead>
                    <tbody>
            `;

            data.auction_history.forEach(row => {
                tableHTML += `
                    <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
                        <td style="padding: 1rem;">${row.event_name}</td>
                        <td style="padding: 1rem; color: #94a3b8;">${new Date(row.date).toLocaleDateString()}</td>
                        <td style="padding: 1rem;">${row.players_purchased}</td>
                        <td style="padding: 1rem; color: #ef4444;">₹${row.amount_spent.toLocaleString()}</td>
                        <td style="padding: 1rem;"><span class="badge" style="background: rgba(255,255,255,0.1);">${row.status}</span></td>
                    </tr>
                `;
            });

            tableHTML += `</tbody></table>`;
            historyContainer.innerHTML = tableHTML;
        }
    } catch (err) {
        console.error('Error loading reports:', err);
    }
}

// --- STAFF SETTINGS LOGIC ---

async function loadStaffSettings() {
    try {

        const response = await fetch('/api/owner/staff');




        if (response.status === 401 || response.status === 403) return;

        const text = await response.text();


        let data;
        try {
            data = JSON.parse(text);
        } catch (err) {
            console.error('[STAFF DEBUG] Failed to parse JSON', err);
            return;
        }
        if (data.success) {



            const manager = data.manager;
            if (manager) {
                if (document.getElementById('manager-name')) {
                    document.getElementById('manager-name').value = manager.name || '';
                }
                if (document.getElementById('manager-email')) {
                    document.getElementById('manager-email').value = manager.email || '';
                }
            }

            const analyst = data.analyst;
            if (analyst) {
                if (document.getElementById('analyst-name')) {
                    document.getElementById('analyst-name').value = analyst.name || '';
                }
                if (document.getElementById('analyst-email')) {
                    document.getElementById('analyst-email').value = analyst.email || '';
                }
            }
        }
    } catch (e) {
        console.error("Error loading staff settings:", e);
    }
}

async function updateStaffDetails(e, role) {
    e.preventDefault();
    const btn = e.target.querySelector('button[type="submit"]');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Updating...';
    btn.disabled = true;

    let prefix = role === 'team_manager' ? 'manager' : 'analyst';

    const payload = {
        name: document.getElementById(`${prefix}-name`).value,
        email: document.getElementById(`${prefix}-email`).value,
        password: document.getElementById(`${prefix}-password`).value
    };

    try {
        const response = await fetch(`/api/owner/staff/${role}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await response.json();
        if (data.success) {
            showNotification(data.message || 'Details updated successfully', 'success');
            document.getElementById(`${prefix}-password`).value = ''; // clear password field
            loadStaffSettings(); // reload staff data
        } else {
            showNotification(data.error || 'Failed to update details', 'error');
        }
    } catch (err) {
        console.error(err);
        showNotification('Network error while updating details', 'error');
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

// --- ANALYST DASHBOARD LOGIC ---
// NOTE: Only the authoritative loadAnalystDashboard() is defined further below (near line 2568).
// This section intentionally left as a comment to avoid duplicate 403 API calls.

let playerHeatmapChartInstance = null;

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

                    const teamsHash = JSON.stringify(data.my_teams);
                    if (window.lastTeamsHash !== teamsHash) {
                        window.lastTeamsHash = teamsHash;
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
                    }
                } else {
                    teamSelector.style.display = 'none';
                }
            }

            // Set Event Title Header
            if (eventTitleEl) eventTitleEl.textContent = currentEventName;

            // Update wallet balance
            document.getElementById('walletAmount').textContent = `₹${data.wallet_balance.toLocaleString()}`;

            // Update stats
            const squadSizeEl = document.getElementById('squadSize');
            if (squadSizeEl) squadSizeEl.textContent = data.squad_size !== undefined ? data.squad_size : (data.squad ? data.squad.length : 0);

            const liveAuctionsEl = document.getElementById('liveAuctions');
            if (liveAuctionsEl) liveAuctionsEl.textContent = data.live_auctions_count !== undefined ? data.live_auctions_count : 0;

            const activeBidsEl = document.getElementById('activeBids');
            if (activeBidsEl) activeBidsEl.textContent = data.active_bids_count !== undefined ? data.active_bids_count : 0;

            // Manager Stats
            const managerAvailablePlayersEl = document.getElementById('managerAvailablePlayers');
            if (managerAvailablePlayersEl && (data.participants || data.participating_players)) {
                const parts = data.participants || data.participating_players;
                managerAvailablePlayersEl.textContent = parts.length;
            }

            const managerUpcomingMatchesEl = document.getElementById('managerUpcomingMatches');
            if (managerUpcomingMatchesEl && data.upcoming_events !== undefined) {
                managerUpcomingMatchesEl.textContent = data.upcoming_events.length;
            }

            // Trigger squad update
            window.currentSquadData = data.squad || [];
            renderSquad(data.squad);

            // Trigger participants update
            renderParticipants(data.participants || data.participating_players);

            // Trigger upcoming events update
            renderUpcomingEvents(data.upcoming_events);

            // Store current team owner data
            sessionStorage.setItem('teamName', data.team_name);
            sessionStorage.setItem('walletBalance', data.wallet_balance);
            sessionStorage.setItem('squadData', JSON.stringify(data.squad));

            // Handle auction status
            if (data.active_auction) {
                if (data.active_auction.status === 'RUNNING') {
                    document.querySelector('.live-auction-container').style.display = 'block';
                    document.getElementById('auction-countdown-overlay').style.display = 'none';
                    // Update countdown timer when live
                    const timerEl = document.getElementById('countdownTimer');
                    if (timerEl && data.active_auction.current_player && typeof data.active_auction.current_player.time_left !== 'undefined') {
                        timerEl.style.display = 'block';
                        const timeLeft = data.active_auction.current_player.time_left;
                        timerEl.textContent = formatTime(Math.ceil(timeLeft));
                        if (timeLeft < 5) {
                            timerEl.style.color = '#ef4444';
                            timerEl.style.animation = 'pulse 1s infinite';
                        } else {
                            timerEl.style.color = '#4F46E5';
                            timerEl.style.animation = 'none';
                        }
                    } else if (timerEl) {
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
                } else if (data.active_auction.status === 'LOBBY' || data.active_auction.status === 'lobby') {
                    localStorage.setItem('currentAuctionStatus', 'LOBBY');
                    // Removed continuous initializeAuction call to prevent interval duplication
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
                sessionStorage.removeItem('user');
                sessionStorage.removeItem('token');
                sessionStorage.clear();
                window.location.replace('/index.html');
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

let lastSquadHash = null;
function renderSquad(squad) {
    window.currentSquadData = squad || [];
    const squadList = document.getElementById('squadList');
    if (!squadList) return;

    const squadHash = JSON.stringify(squad || []);
    if (squadHash === lastSquadHash) return;
    lastSquadHash = squadHash;

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

let lastParticipantsHash = null;
// Render participating players list
function renderParticipants(participants) {
    const participantsList = document.getElementById('participantsList');
    if (!participantsList) return;

    const partHash = JSON.stringify(participants || []);
    if (partHash === lastParticipantsHash) return;
    lastParticipantsHash = partHash;

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

let lastUpcomingHash = null;
function renderUpcomingEvents(events) {
    const eventsList = document.getElementById('upcomingEventsList');
    if (!eventsList) return;

    const eventsHash = JSON.stringify(events || []);
    if (eventsHash === lastUpcomingHash) return;
    lastUpcomingHash = eventsHash;

    eventsList.innerHTML = '';

    if (events && events.length > 0) {
        events.forEach(ev => {
            const item = document.createElement('div');
            item.className = 'list-item';

            // Format dates
            let startDateStr = 'TBD';
            if (ev.start_date) {
                const d = new Date(ev.start_date);
                startDateStr = d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            }

            let iconClass = 'fa-calendar-check';
            let iconColor = 'var(--accent-purple)';
            let iconBg = 'rgba(139, 92, 246, 0.1)';

            item.innerHTML = `
                <div class="avatar-circle" style="background: ${iconBg}; color: ${iconColor}; width: 40px; height: 40px; font-size: 1rem;"><i class="fas ${iconClass}"></i></div>
                <div class="item-details">
                    <div class="item-name">${ev.title}</div>
                    <div class="item-meta"><span>${startDateStr}</span></div>
                </div>
            `;
            eventsList.appendChild(item);
        });
    } else {
        eventsList.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-calendar-times empty-icon" style="font-size: 2rem;"></i>
                <p>No upcoming events.</p>
            </div>
        `;
    }
}

// Initialize auction display
function initializeAuction() {
    // Polling is strictly handled by startAuctionTimer().
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

            // 1. Update Wallet Balance and Stats Live
            if (data.wallet_balance !== undefined) {
                const walletEl = document.getElementById('walletAmount');
                if (walletEl) {
                    walletEl.textContent = `₹${data.wallet_balance.toLocaleString()}`;
                }
                sessionStorage.setItem('walletBalance', data.wallet_balance);
            }

            const squadSizeEl = document.getElementById('squadSize');
            if (squadSizeEl && data.squad_size !== undefined) {
                squadSizeEl.textContent = data.squad_size;
            }

            const liveAuctionsEl = document.getElementById('liveAuctions');
            if (liveAuctionsEl && data.live_auctions_count !== undefined) {
                liveAuctionsEl.textContent = data.live_auctions_count;
            }

            const activeBidsEl = document.getElementById('activeBids');
            if (activeBidsEl && data.active_bids_count !== undefined) {
                activeBidsEl.textContent = data.active_bids_count;
            }

            // Manager Stats
            const managerAvailablePlayersEl = document.getElementById('managerAvailablePlayers');
            if (managerAvailablePlayersEl && data.participating_players) {
                // Determine available players by subtracting squad size or just total participants.
                // Assuming data.participants returns everyone, or maybe just available ones depending on backend.
                managerAvailablePlayersEl.textContent = data.participating_players.length;
            }

            const managerUpcomingMatchesEl = document.getElementById('managerUpcomingMatches');
            if (managerUpcomingMatchesEl && data.upcoming_events !== undefined) {
                managerUpcomingMatchesEl.textContent = data.upcoming_events.length;
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
            break;
    }
    const auctionStatusEl = document.getElementById('auctionStatus');
    const dedicatedAuctionStatus = document.getElementById('dedicatedAuctionStatus');
    const currentEventTitle = document.getElementById('currentEventTitle');
    const dedicatedEventTitle = document.getElementById('dedicatedEventTitle');

    if (auctionStatus) {
        auctionStatus.textContent = currentAuction.status;
        auctionStatus.className = `auction-status status-${currentAuction.status.toLowerCase().replace('_', '-')}`;
    }
    if (dedicatedAuctionStatus) {
        dedicatedAuctionStatus.textContent = currentAuction.status;
        dedicatedAuctionStatus.className = `auction-status status-${currentAuction.status.toLowerCase().replace('_', '-')}`;
    }

    if (currentEventTitle && window.currentEventName) {
        currentEventTitle.textContent = window.currentEventName;
    }
    if (dedicatedEventTitle && window.currentEventName) {
        dedicatedEventTitle.textContent = window.currentEventName;
    }

    // Update countdown timer
    if (currentAuction.status === 'RUNNING') {
        countdownTimer.textContent = formatTime(currentAuction.timeLeft);
    }

    // Update content based on auction state
    let contentHTML = '';
    if (currentAuction.status === 'NOT_STARTED' || currentAuction.status === 'ENDED') {
        contentHTML = `
            <div class="waiting-message">
                ${currentAuction.status === 'NOT_STARTED'
                ? 'Waiting for auction to start...'
                : 'The auction has concluded.'}
            </div>
        `;
        document.getElementById('auctionContent').innerHTML = contentHTML;
        document.getElementById('dedicatedAuctionContent').innerHTML = contentHTML;
    } else if (currentAuction.status === 'RUNNING' && currentAuction.currentPlayer) {
        displayPlayerCard();
    } else {
        contentHTML = `
            <div class="waiting-message">
                No player is currently being auctioned.
            </div>
        `;
        document.getElementById('auctionContent').innerHTML = contentHTML;
        document.getElementById('dedicatedAuctionContent').innerHTML = contentHTML;
    }
}

// Display current player card
function displayPlayerCard() {
    const player = currentAuction.currentPlayer;
    const walletBalance = parseInt(sessionStorage.getItem('walletBalance')) || 0;

    // Calculate stats
    const wins = player.stats && player.stats.wins ? player.stats.wins : 0;
    const losses = player.stats && player.stats.losses ? player.stats.losses : 0;

    const htmlContent = `
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

             <div class="custom-bid-section" style="width: 100%;">
                 <input type="range" min="${currentAuction.currentBid || player.basePrice}" max="${(currentAuction.currentBid || player.basePrice) * 2}" value="${currentAuction.currentBid || player.basePrice}" class="slider" oninput="updateSliderValue(this.value)" style="width: 100%; margin-bottom: 1rem;">
                 <div class="slider-value" style="text-align: center; font-size: 1.25rem; font-weight: 700; color: #4f46e5; margin-bottom: 1rem;">₹${(currentAuction.currentBid || player.basePrice).toLocaleString()}</div>
                 <button class="place-bid-btn" onclick="placeCustomBid()" style="width: 100%; padding: 0.875rem; background: #4f46e5; color: white; border: none; border-radius: 0.5rem; font-weight: 600; font-size: 1rem; cursor: pointer; transition: background 0.2s;">
                    Place Bid
                 </button>
            </div>
        </div>
    `;

    const auctionContent = document.getElementById('auctionContent');
    const dedicatedAuctionContent = document.getElementById('dedicatedAuctionContent');

    if (auctionContent) auctionContent.innerHTML = htmlContent;
    if (dedicatedAuctionContent) dedicatedAuctionContent.innerHTML = htmlContent;
}

// Update slider value display
function updateSliderValue(val) {
    document.querySelectorAll('.slider-value').forEach(el => {
        el.textContent = `₹${parseInt(val).toLocaleString()}`;
    });
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

// --- VIEW SWITCHING LOGIC ---
window.switchView = function (hashOrPath) {
    let user;
    try { user = JSON.parse(sessionStorage.getItem('user')); } catch (e) { }
    const role = user ? (user.role || user.user_type) : null;

    // Use default views if not provided
    if (!hashOrPath) {
        if (role === 'team_analyst') hashOrPath = '#analytics';
        else if (role === 'team_manager') hashOrPath = '/dashboard/manager';
        else hashOrPath = '#dashboard';
    }

    // Extract hash part
    let viewName = 'dashboard';
    if (hashOrPath.includes('#')) {
        viewName = hashOrPath.split('#')[1];
    }

    const validViews = ['dashboard', 'players', 'auction', 'wallet', 'reports', 'squad', 'analytics', 'performance', 'predictions', 'settings'];
    if (!validViews.includes(viewName)) {
        if (role === 'team_analyst') viewName = 'analytics';
        else viewName = 'dashboard';
    }

    // Squad alias to players
    if (viewName === 'squad') viewName = 'players';

    // We no longer hide .view-section here because we want them all visible for scrolling
    // We only hide role panels
    document.querySelectorAll('.role-panel').forEach(el => {
        el.style.display = 'none';
    });

    let targetElement = null;
    let targetPanel = null;
    let isRolePanel = false;

    // Use currentPath to determine if Team Owner or Manager is trying to view a sub-panel
    const currentPath = (hashOrPath && hashOrPath.includes('/')) ? hashOrPath : (window.location.pathname + hashOrPath);


    // Show target view or panel based strictly on user role (and path for superset owner role)
    if (role === 'team_analyst' || (role === 'team_owner' && currentPath.includes('/dashboard/analyst'))) {
        isRolePanel = true;
        targetPanel = document.getElementById('analyst-panel');
        if (targetPanel) {
            targetPanel.style.display = 'grid'; // Analyst panel uses display: grid

            // Map analyst sidebar nav names to section IDs in the analyst panel
            const analystSectionMap = {
                'analytics': 'section-analytics',
                'performance': 'section-performance',
                'reports': 'section-reports',
                'predictions': 'section-predictions',
                'settings': 'section-analyst-settings'
            };

            const sectionId = analystSectionMap[viewName] || `section-${viewName}`;
            targetElement = document.getElementById(sectionId);
            if (!targetElement) targetElement = targetPanel;
        }
    } else if (currentPath.startsWith('/dashboard/manager') || (role === 'team_manager' && !currentPath.includes('/dashboard/'))) {
        isRolePanel = true;

        // If team manager is navigating to a shared view (players, auction, squad, reports), show that view in owner panel
        if (['players', 'auction', 'squad', 'reports'].includes(viewName) && hashOrPath.includes('#')) {
            const ownerPanel = document.getElementById('owner-panel');
            if (ownerPanel) {
                ownerPanel.style.display = 'grid';
                ownerPanel.classList.add('scroll-mode');

                // First, remove active-view from ALL view-sections (fix: prevents multiple sections showing)
                ownerPanel.querySelectorAll('.view-section').forEach(v => {
                    v.classList.remove('active-view');
                    v.style.display = 'none';
                });

                // Always hide owner-only views from manager
                const ownerOnlyViews = ['view-dashboard', 'view-wallet', 'view-settings'];
                ownerOnlyViews.forEach(id => {
                    const el = document.getElementById(id);
                    if (el) {
                        el.style.display = 'none';
                        el.classList.remove('active-view');
                        el.classList.add('hidden-for-role');
                    }
                });
            }

            const targetView = document.getElementById(`view-${viewName}`);
            if (targetView) {
                targetView.style.display = 'grid';
                targetView.classList.add('active-view');
                targetView.classList.remove('hidden-for-role');
                targetElement = targetView;
            }
            isRolePanel = false; // Treat it as an owner panel view
        } else {
            targetPanel = document.getElementById('manager-panel');
            if (targetPanel) {
                targetPanel.style.display = 'grid';
                targetElement = document.getElementById(`section-${viewName}`);
                if (!targetElement) targetElement = targetPanel;
            }
        }
    } else {
        const ownerPanel = document.getElementById('owner-panel');
        if (ownerPanel) {
            ownerPanel.style.display = 'grid';
            ownerPanel.classList.add('scroll-mode');

            // Hide other view sections in owner panel
            ownerPanel.querySelectorAll('.view-section').forEach(v => {
                v.classList.remove('active-view');
                v.style.display = 'none';
            });

            // Ensure dashboard view is visible for owner
            const dashView = document.getElementById('view-dashboard');
            if (dashView) dashView.classList.remove('hidden-for-role');
        }

        const targetView = document.getElementById(`view-${viewName}`);
        if (targetView) {
            targetView.style.display = 'grid';
            targetView.classList.add('active-view');
            targetElement = targetView;
        }
    }

    if (targetElement || (isRolePanel && targetPanel)) {
        // Synchronize sidebar active state
        document.querySelectorAll('.sidebar-item').forEach(item => {
            item.classList.remove('active');
            const itemPath = item.getAttribute('data-path');
            if (itemPath) {
                if (itemPath === currentPath) {
                    item.classList.add('active');
                } else if (currentPath.includes('#') && itemPath.endsWith('#' + viewName)) {
                    item.classList.add('active');
                } else if (!currentPath.includes('#') && itemPath === currentPath.split('#')[0]) {
                    item.classList.add('active');
                }
            }
        });

        // Trigger specific loads based on view
        if (isRolePanel && targetPanel && targetPanel.id === 'analyst-panel') {
            if (typeof loadAnalystDashboard === 'function' && !window._analystDashboardLoaded) {
                window._analystDashboardLoaded = true;
                loadAnalystDashboard();
            }
        } else if (isRolePanel && targetPanel && targetPanel.id === 'manager-panel') {
            if (typeof initTrainingCalendar === 'function') initTrainingCalendar();
        }


        if (viewName === 'players') {
            loadPlayersView();
        } else if (viewName === 'wallet') {
            loadWalletView();
        } else if (viewName === 'reports') {
            loadReportsView();
        } else if (viewName === 'settings') {
            if (typeof loadStaffSettings === 'function') loadStaffSettings();
            if (isRolePanel && targetPanel && targetPanel.id === 'analyst-panel') {
                loadAnalystProfileSettings();
            }
        } else if (viewName === 'auction') {
            // Already updated via polling, but could force refresh
        }

        // Scroll smoothly to the target section, accounting for the header
        setTimeout(() => {
            if (targetElement) {
                const headerOffset = 80;
                const elementPosition = targetElement.getBoundingClientRect().top;
                const offsetPosition = elementPosition + window.pageYOffset - headerOffset;
                window.scrollTo({
                    top: offsetPosition,
                    behavior: "smooth"
                });
            }
        }, 50);
    }
};

// Setup event listeners
function setupEventListeners() {
    // Listen for custom viewChanged event from rbac-router.js
    window.addEventListener('viewChanged', (e) => {
        if (e.detail && e.detail.path) {
            switchView(e.detail.path);
        }
    });

    // Setup Scroll Spy (IntersectionObserver) for Team Owner dashboard
    const ownerSections = document.querySelectorAll('#owner-panel .view-section');
    if (ownerSections.length > 0) {
        const ownerObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const id = entry.target.id;
                    const viewName = id.replace('view-', '');

                    // Update active sidebar item
                    document.querySelectorAll('.sidebar-item').forEach(item => {
                        item.classList.remove('active');
                        const path = item.getAttribute('data-path');
                        if (path && path.includes('#' + viewName)) {
                            item.classList.add('active');
                        }
                    });
                }
            });
        }, {
            root: null,
            rootMargin: '-20% 0px -60% 0px',
            threshold: 0
        });

        ownerSections.forEach(section => {
            ownerObserver.observe(section);
        });
    }

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
let dashboardPollInterval = null;
function startAuctionTimer() {
    if (dashboardPollInterval) clearInterval(dashboardPollInterval);
    dashboardPollInterval = setInterval(() => {
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

// Show toast notification (used by Settings update, Training forms, etc.)
function showNotification(message, type = 'info') {
    const existingNotif = document.getElementById('toastNotification');
    if (existingNotif) existingNotif.remove();

    const notif = document.createElement('div');
    notif.id = 'toastNotification';

    const bgColor = type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : '#3b82f6';
    notif.style.cssText = `
        position: fixed;
        bottom: 2rem;
        right: 2rem;
        background: ${bgColor};
        color: white;
        padding: 0.875rem 1.5rem;
        border-radius: 0.5rem;
        font-size: 0.9rem;
        font-weight: 500;
        z-index: 9999;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        transition: opacity 0.3s ease;
        opacity: 1;
        max-width: 350px;
    `;
    notif.textContent = message;
    document.body.appendChild(notif);

    // Auto-dismiss after 3.5s
    setTimeout(() => {
        notif.style.opacity = '0';
        setTimeout(() => { if (notif.parentNode) notif.remove(); }, 300);
    }, 3500);
}

// Logout function
async function logout() {
    const userStr = sessionStorage.getItem('user');
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
    sessionStorage.removeItem('user');
    sessionStorage.removeItem('session_token');
    sessionStorage.removeItem('userType');
    sessionStorage.removeItem('username');
    sessionStorage.removeItem('teamName');
    sessionStorage.removeItem('walletBalance');
    sessionStorage.removeItem('teamOwnerData');

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

            // Dynamically fetch live auction data instead of reloading the entire page
            setTimeout(() => {
                if (typeof fetchAuctionStatus === 'function') {
                    fetchAuctionStatus();
                } else if (typeof loadAuctionData === 'function') {
                    loadAuctionData();
                }
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
            headerTitle.textContent = 'JamRig - Team Analyst Dashboard';
        }
    }
    // Manager has bidding rights but maybe not wallet access
    else if (user.user_type === 'team_manager') {
        const walletCards = document.querySelectorAll('.wallet-card');
        walletCards.forEach(card => card.style.display = 'none');

        const headerTitle = document.querySelector('.header h2') || document.querySelector('.header .nav-logo span');
        if (headerTitle) {
            headerTitle.textContent = 'JamRig - Team Manager Dashboard';
        }
    }
}

// --- SOCKET.IO & LOBBY (PHASE 3 + LIVE BIDDING PHASE 4) ---
let socket;

function initializeLobbySocket(auctionId, teamId) {
    if (!socket) {
        socket = io({ transports: ['polling'], upgrade: false }); // Connects to the host using polling only

        socket.on('connect', () => {

            socket.emit('join_lobby', {
                auction_id: auctionId,
                team_id: teamId
            });
        });

        socket.on('team_status_update', (data) => {

            if (data.team_id == teamId && data.status === 'READY') {
                const btn = document.getElementById('btn-team-ready');
                if (btn) {
                    btn.textContent = 'Ready! Waiting for Admin...';
                    btn.classList.add('disabled');
                    btn.disabled = true;
                }
            }
        });

        socket.on('auction_update', (data) => {

            if (data.status === 'RUNNING') {
                // Transition from lobby to live auction UI
                const lobbyContainer = document.getElementById('auction-lobby-container');
                if (lobbyContainer) lobbyContainer.style.display = 'none';

                const liveContainer = document.querySelector('.live-auction-container');
                if (liveContainer) liveContainer.style.display = 'block';

                if (data.current_player) {
                    const nameEl = document.getElementById('currentPlayerName') || document.querySelector('.player-info h3');
                    if (nameEl) nameEl.textContent = data.current_player.name;

                    const roleEl = document.getElementById('currentPlayerRole') || document.querySelector('.player-info p');
                    if (roleEl) roleEl.textContent = `${data.current_player.role} • ${data.current_player.category}`;

                    const bidAmountEl = document.getElementById('currentBidAmount') || document.getElementById('currentBid');
                    if (bidAmountEl) bidAmountEl.textContent = `₹${data.current_bid || data.current_player.base_price}`;

                    const imgEl = document.getElementById('currentPlayerImage') || document.querySelector('.player-photo-lg');
                    if (imgEl) imgEl.src = data.current_player.photo || '/static/images/default-avatar.png';
                }

                const timerEl = document.getElementById('countdownTimer');
                if (timerEl) timerEl.textContent = data.time_left;
            } else if (data.status === 'PAUSED') {
                const timerEl = document.getElementById('countdownTimer');
                if (timerEl) timerEl.textContent = 'PAUSED';
            } else if (data.status === 'COMPLETED') {
                const timerEl = document.getElementById('countdownTimer');
                if (timerEl) timerEl.textContent = 'COMPLETED';
            }
        });

        socket.on('bid_placed', (data) => {

            const bidAmountEl = document.getElementById('currentBidAmount') || document.getElementById('currentBid');
            if (bidAmountEl) bidAmountEl.textContent = `₹${data.amount}`;

            const timerEl = document.getElementById('countdownTimer');
            if (timerEl) timerEl.textContent = data.time_left;
        });
    }
}

window.placeBid = function (amount) {
    const userStr = sessionStorage.getItem('user');
    if (!userStr || !socket) return;
    const user = JSON.parse(userStr);

    const teamSelector = document.getElementById('teamSelector');
    const auctionId = teamSelector ? teamSelector.value : localStorage.getItem('currentAuctionId');

    if (auctionId && user.team_id) {
        // analysts cannot bid

    }
};

window.markTeamReady = function () {
    const userStr = sessionStorage.getItem('user');
    if (!userStr) return;
    const user = JSON.parse(userStr);

    const teamSelector = document.getElementById('teamSelector');
    const auctionId = teamSelector ? teamSelector.value : null;

    const finalAuctionId = auctionId || localStorage.getItem('currentAuctionId');
    if (socket && finalAuctionId && user.team_id) {
        socket.emit('team_ready', {
            auction_id: parseInt(finalAuctionId),
            team_id: user.team_id
        });
    }
};

const originalInitAuction = window.initializeAuction || function () { };
window.initializeAuction = async function () {
    const currentAuctionStatus = localStorage.getItem('currentAuctionStatus');
    if (currentAuctionStatus === 'LOBBY' || currentAuctionStatus === 'lobby') {
        const liveContainer = document.querySelector('.live-auction-container');
        if (liveContainer) liveContainer.style.display = 'none';

        const lobbyContainer = document.getElementById('auction-lobby-container');
        if (lobbyContainer) lobbyContainer.style.display = 'block';

        const user = JSON.parse(sessionStorage.getItem('user'));
        const teamSelector = document.getElementById('teamSelector');
        const auctionId = teamSelector ? teamSelector.value : localStorage.getItem('currentAuctionId');
        if (auctionId && user && user.team_id) {
            initializeLobbySocket(auctionId, user.team_id);
        }
    } else {
        originalInitAuction();
    }
};

// ==========================================
// TRAINING CALENDAR MODULE
// ==========================================

let currentCalendarDate = new Date();
let currentTrainingSessions = [];

const MOCK_HOLIDAYS = [
    { id: "holiday-1", title: "New Year's Day", date: "2026-01-01", type: "Holiday", start_time: "00:00", end_time: "23:59", status: "Scheduled", isHoliday: true },
    { id: "holiday-2", title: "Republic Day", date: "2026-01-26", type: "Holiday", start_time: "00:00", end_time: "23:59", status: "Scheduled", isHoliday: true },
    { id: "holiday-3", title: "Maha Shivratri", date: "2026-02-15", type: "Festival", start_time: "00:00", end_time: "23:59", status: "Scheduled", isHoliday: true },
    { id: "holiday-4", title: "Holi", date: "2026-03-04", type: "Festival", start_time: "00:00", end_time: "23:59", status: "Scheduled", isHoliday: true },
    { id: "holiday-5", title: "Good Friday", date: "2026-04-03", type: "Holiday", start_time: "00:00", end_time: "23:59", status: "Scheduled", isHoliday: true },
    { id: "holiday-6", title: "Eid ul-Fitr", date: "2026-03-20", type: "Festival", start_time: "00:00", end_time: "23:59", status: "Scheduled", isHoliday: true },
    { id: "holiday-7", title: "Independence Day", date: "2026-08-15", type: "Holiday", start_time: "00:00", end_time: "23:59", status: "Scheduled", isHoliday: true },
    { id: "holiday-8", title: "Raksha Bandhan", date: "2026-08-28", type: "Festival", start_time: "00:00", end_time: "23:59", status: "Scheduled", isHoliday: true },
    { id: "holiday-9", title: "Janmashtami", date: "2026-09-04", type: "Festival", start_time: "00:00", end_time: "23:59", status: "Scheduled", isHoliday: true },
    { id: "holiday-10", title: "Ganesh Chaturthi", date: "2026-09-14", type: "Festival", start_time: "00:00", end_time: "23:59", status: "Scheduled", isHoliday: true },
    { id: "holiday-11", title: "Gandhi Jayanti", date: "2026-10-02", type: "Holiday", start_time: "00:00", end_time: "23:59", status: "Scheduled", isHoliday: true },
    { id: "holiday-12", title: "Dussehra", date: "2026-10-20", type: "Festival", start_time: "00:00", end_time: "23:59", status: "Scheduled", isHoliday: true },
    { id: "holiday-13", title: "Diwali", date: "2026-11-08", type: "Festival", start_time: "00:00", end_time: "23:59", status: "Scheduled", isHoliday: true },
    { id: "holiday-14", title: "Christmas", date: "2026-12-25", type: "Holiday", start_time: "00:00", end_time: "23:59", status: "Scheduled", isHoliday: true }
];

function initTrainingCalendar() {
    if (document.getElementById('manager-panel')) {
        fetchTrainingSessions();
    }
}

function fetchTrainingSessions() {
    const year = currentCalendarDate ? currentCalendarDate.getFullYear() : new Date().getFullYear();
    const holidaysUrl = `https://date.nager.at/api/v3/PublicHolidays/${year}/IN`;

    Promise.all([
        fetch('/api/manager/training', { headers: { 'Content-Type': 'application/json' } })
            .then(res => res.json())
            .catch(() => ({ success: false, sessions: [] })),
        fetch(holidaysUrl)
            .then(res => res.json())
            .catch(() => null)
    ]).then(([trainingData, holidayData]) => {
        let holidaysMap = new Map();

        // 1. Always load Indian Festival & Holiday Calendar with accurate dates (Ganesh Chaturthi on Sept 14)
        MOCK_HOLIDAYS.forEach(h => {
            const adjustedDate = `${year}${h.date.substring(4)}`;
            holidaysMap.set(h.title.toLowerCase(), { ...h, date: adjustedDate });
        });

        // 2. Supplement with any additional live public holidays
        if (holidayData && Array.isArray(holidayData)) {
            holidayData.forEach((h, i) => {
                const key = (h.name || h.localName || '').toLowerCase();
                if (!holidaysMap.has(key)) {
                    holidaysMap.set(key, {
                        id: `holiday-api-${i}`,
                        title: h.name,
                        date: h.date,
                        type: (h.types && h.types.includes('Observance')) ? "Festival" : "Holiday",
                        start_time: "00:00",
                        end_time: "23:59",
                        status: "Scheduled",
                        isHoliday: true
                    });
                }
            });
        }

        const allHolidays = Array.from(holidaysMap.values());

        if (trainingData && trainingData.success && Array.isArray(trainingData.sessions)) {
            currentTrainingSessions = [...trainingData.sessions, ...allHolidays];
        } else {
            currentTrainingSessions = [...allHolidays];
        }

        renderCalendar();
        renderAgenda();
        updateTrainingStats();
    }).catch(err => {
        console.error("Error fetching calendar data:", err);
        currentTrainingSessions = [...MOCK_HOLIDAYS];
        renderCalendar();
        renderAgenda();
        updateTrainingStats();
    });
}

function updateTrainingStats() {
    const now = new Date();
    // Use substring to ensure safe comparison
    const todayStr = now.toISOString().substring(0, 10);
    const upcoming = currentTrainingSessions.filter(s => s.date >= todayStr && s.status !== 'Cancelled');
    const statEl = document.getElementById('managerTraining');
    if (statEl) statEl.textContent = upcoming.length;
}

function changeCalendarMonth(offset) {
    currentCalendarDate.setMonth(currentCalendarDate.getMonth() + offset);
    fetchTrainingSessions();
}

function resetCalendarToToday() {
    currentCalendarDate = new Date();
    fetchTrainingSessions();
}

function toggleTrainingView(view) {
    if (view === 'calendar') {
        document.getElementById('trainingCalendarGrid').style.display = 'grid';
        document.getElementById('trainingAgendaList').style.display = 'none';
        document.getElementById('btnViewCalendar').classList.replace('btn-outline-primary', 'btn-primary');
        document.getElementById('btnViewAgenda').classList.replace('btn-primary', 'btn-outline-primary');
    } else {
        document.getElementById('trainingCalendarGrid').style.display = 'none';
        document.getElementById('trainingAgendaList').style.display = 'flex';
        document.getElementById('btnViewAgenda').classList.replace('btn-outline-primary', 'btn-primary');
        document.getElementById('btnViewCalendar').classList.replace('btn-primary', 'btn-outline-primary');
    }
}

function renderCalendar() {
    const grid = document.getElementById('trainingCalendarGrid');
    const monthLabel = document.getElementById('calendarCurrentMonth');
    if (!grid || !monthLabel) return;

    const year = currentCalendarDate.getFullYear();
    const month = currentCalendarDate.getMonth();

    monthLabel.textContent = new Date(year, month).toLocaleString('default', { month: 'long', year: 'numeric' });

    grid.innerHTML = `
        <div style="background: rgba(255,255,255,0.05); padding: 0.5rem; text-align: center; font-weight: 600;">Sun</div>
        <div style="background: rgba(255,255,255,0.05); padding: 0.5rem; text-align: center; font-weight: 600;">Mon</div>
        <div style="background: rgba(255,255,255,0.05); padding: 0.5rem; text-align: center; font-weight: 600;">Tue</div>
        <div style="background: rgba(255,255,255,0.05); padding: 0.5rem; text-align: center; font-weight: 600;">Wed</div>
        <div style="background: rgba(255,255,255,0.05); padding: 0.5rem; text-align: center; font-weight: 600;">Thu</div>
        <div style="background: rgba(255,255,255,0.05); padding: 0.5rem; text-align: center; font-weight: 600;">Fri</div>
        <div style="background: rgba(255,255,255,0.05); padding: 0.5rem; text-align: center; font-weight: 600;">Sat</div>
    `;

    const firstDay = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const today = new Date();

    for (let i = 0; i < firstDay; i++) {
        grid.innerHTML += `<div style="background: rgba(0,0,0,0.2); min-height: 80px;"></div>`;
    }

    const typeFilter = document.getElementById('calendarTypeFilter') ? document.getElementById('calendarTypeFilter').value : "";

    for (let day = 1; day <= daysInMonth; day++) {
        const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;

        let dayEventsHtml = '';
        currentTrainingSessions.forEach(session => {
            if (session.date === dateStr && (!typeFilter || session.type === typeFilter)) {
                let badgeClass = 'badge';
                if (session.status === 'Cancelled') badgeClass = 'badge badge-danger';
                else if (session.status === 'Completed') badgeClass = 'badge badge-success';

                let bgColor = 'rgba(16, 185, 129, 0.2)';
                let borderColor = 'rgba(16, 185, 129, 0.5)';
                let icon = '';
                let clickAction = session.isHoliday ? 'void(0)' : `viewTrainingDetails('${session.id}')`;
                let cursorStyle = session.isHoliday ? 'default' : 'pointer';

                if (session.type === 'Holiday' || session.type === 'Festival') {
                    bgColor = 'rgba(245, 158, 11, 0.2)';
                    borderColor = 'rgba(245, 158, 11, 0.5)';
                    icon = '✨ ';
                } else if (session.type === 'Match') {
                    bgColor = 'rgba(59, 130, 246, 0.2)';
                    borderColor = 'rgba(59, 130, 246, 0.5)';
                }

                dayEventsHtml += `
                    <div onclick="${clickAction}" style="font-size: 0.75rem; background: ${bgColor}; border: 1px solid ${borderColor}; border-radius: 4px; padding: 0.25rem 0.4rem; margin-top: 0.25rem; cursor: ${cursorStyle}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: flex; align-items: center; gap: 0.3rem;" title="${session.title}">
                        <span>${icon}</span>
                        <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${session.isHoliday ? session.title : (session.start_time.substring(0, 5) + ' ' + session.type)}</span>
                    </div>
                `;
            }
        });

        const isToday = today.getFullYear() === year && today.getMonth() === month && today.getDate() === day;
        const bg = isToday ? 'rgba(6, 182, 212, 0.1)' : 'transparent';
        const numColor = isToday ? 'color: var(--accent-cyan); font-weight: bold;' : 'color: #94a3b8;';

        grid.innerHTML += `
            <div style="background: ${bg}; min-height: 80px; padding: 0.5rem; border-top: 1px solid rgba(255,255,255,0.05); border-left: 1px solid rgba(255,255,255,0.05);">
                <div style="text-align: right; font-size: 0.8rem; ${numColor}">${day}</div>
                ${dayEventsHtml}
            </div>
        `;
    }
}

function renderAgenda() {
    const list = document.getElementById('trainingAgendaList');
    if (!list) return;

    const typeFilter = document.getElementById('calendarTypeFilter') ? document.getElementById('calendarTypeFilter').value : "";

    const filtered = currentTrainingSessions.filter(s => !typeFilter || s.type === typeFilter).sort((a, b) => new Date(a.date) - new Date(b.date));

    if (filtered.length === 0) {
        list.innerHTML = `<div class="empty-state" style="padding: 2rem;"><p>No training sessions found.</p></div>`;
        return;
    }

    let html = '';
    filtered.forEach(session => {
        let borderStyle = 'border-left: 4px solid var(--accent-emerald);';
        let icon = '';
        let btnHtml = `<button class="btn-outline-primary" style="padding: 0.3rem 0.6rem; font-size: 0.8rem;" onclick="viewTrainingDetails(${session.id})">Details</button>`;

        if (session.type === 'Holiday' || session.type === 'Festival') {
            borderStyle = 'border-left: 4px solid #f59e0b;'; // Amber color
            icon = '✨ ';
            btnHtml = ''; // No details button for mock holidays
        }

        html += `
            <div class="glass-card" style="padding: 1rem; display: flex; justify-content: space-between; align-items: center; ${borderStyle}">
                <div>
                    <h4 style="margin: 0 0 0.5rem 0; color: white;">${icon}${session.title} <span style="font-size: 0.8rem; font-weight: normal; margin-left: 0.5rem; color: #94a3b8;">${session.type}</span></h4>
                    <p style="margin: 0; font-size: 0.85rem; color: #cbd5e1;">
                        <i class="fas fa-calendar-day"></i> ${session.date} | 
                        <i class="fas fa-clock"></i> ${session.start_time.substring(0, 5)} - ${session.end_time.substring(0, 5)} | 
                        <i class="fas fa-map-marker-alt"></i> ${session.location || 'TBD'}
                    </p>
                </div>
                <div>
                    <span class="badge" style="margin-right: 1rem;">${session.status}</span>
                    ${btnHtml}
                </div>
            </div>
        `;
    });
    list.innerHTML = html;
}

async function openScheduleTrainingModal() {
    const playersList = document.getElementById('trainPlayersList');
    playersList.innerHTML = '<div style="color: #94a3b8; font-size: 0.85rem; padding: 0.5rem;"><i class="fas fa-spinner fa-spin"></i> Loading squad...</div>';

    // Auto-fill fully updated current date and time
    const now = new Date();
    document.getElementById('trainDate').value = now.toISOString().split('T')[0];
    const hours = String(now.getHours()).padStart(2, '0');
    const mins = String(now.getMinutes()).padStart(2, '0');
    document.getElementById('trainStart').value = `${hours}:${mins}`;

    // Default end time to 2 hours later
    now.setHours(now.getHours() + 2);
    const endHours = String(now.getHours()).padStart(2, '0');
    const endMins = String(now.getMinutes()).padStart(2, '0');
    document.getElementById('trainEnd').value = `${endHours}:${endMins}`;

    document.getElementById('scheduleTrainingModal').style.display = 'flex';

    // 1. Check window.currentSquadData
    let squad = window.currentSquadData;

    // 2. Check sessionStorage
    if (!squad || squad.length === 0) {
        const stored = sessionStorage.getItem('squadData');
        if (stored) {
            try { squad = JSON.parse(stored); } catch (e) { }
        }
    }

    // 3. If still empty, fetch from API
    if (!squad || squad.length === 0) {
        try {
            const res = await fetch('/api/team-owner/squad', { credentials: 'include' });
            if (res.ok) {
                const data = await res.json();
                squad = data.squad || [];
                window.currentSquadData = squad;
                sessionStorage.setItem('squadData', JSON.stringify(squad));
            }
        } catch (e) {
            console.warn('Could not fetch squad:', e);
        }
    }

    let checkboxes = '';
    if (squad && squad.length > 0) {
        squad.forEach((player, idx) => {
            const pid = player.id || player.player_id || (idx + 1);
            const name = player.name || player.player_name || ('Player #' + pid);
            const category = player.category || player.role || '';
            checkboxes += `
                <label style="display: flex; align-items: center; justify-content: space-between; padding: 0.4rem 0.6rem; border-radius: 6px; background: rgba(255,255,255,0.03); margin-bottom: 0.35rem; cursor: pointer; transition: background 0.15s;" onmouseover="this.style.background='rgba(255,255,255,0.08)'" onmouseout="this.style.background='rgba(255,255,255,0.03)'">
                    <span style="display: flex; align-items: center; gap: 0.6rem; font-size: 0.88rem; color: #f1f5f9;">
                        <input type="checkbox" name="trainingPlayer" value="${pid}" style="accent-color: var(--accent-cyan, #06b6d4); width: 16px; height: 16px; cursor: pointer;">
                        <span>${name}</span>
                    </span>
                    ${category ? `<span style="font-size: 0.72rem; color: #94a3b8; background: rgba(255,255,255,0.08); padding: 0.15rem 0.5rem; border-radius: 4px;">${category}</span>` : ''}
                </label>
            `;
        });
    }

    if (checkboxes) {
        playersList.innerHTML = checkboxes;
    } else {
        playersList.innerHTML = '<p style="color: #94a3b8; font-size: 0.85rem; margin: 0; padding: 0.75rem; text-align: center;">No players in squad yet. Acquire players in auction to assign them to training.</p>';
    }
}

function selectAllTrainingPlayers() {
    const cbs = document.querySelectorAll('input[name="trainingPlayer"]');
    const allChecked = Array.from(cbs).every(cb => cb.checked);
    cbs.forEach(cb => cb.checked = !allChecked);
}

function closeScheduleTrainingModal() {
    document.getElementById('scheduleTrainingModal').style.display = 'none';
    document.getElementById('scheduleTrainingForm').reset();
}

function submitTrainingForm(e) {
    e.preventDefault();

    const players = [];
    document.querySelectorAll('input[name="trainingPlayer"]:checked').forEach(cb => {
        if (cb.value && cb.value !== 'undefined') players.push(parseInt(cb.value));
    });

    const data = {
        title: document.getElementById('trainTitle').value,
        type: document.getElementById('trainType').value,
        date: document.getElementById('trainDate').value,
        start_time: document.getElementById('trainStart').value + ":00",
        end_time: document.getElementById('trainEnd').value + ":00",
        location: document.getElementById('trainLocation').value,
        coach: document.getElementById('trainCoach').value,
        description: document.getElementById('trainDescription').value,
        players: players
    };

    fetch('/api/manager/training', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    })
        .then(res => res.json())
        .then(res => {
            if (res.success) {
                closeScheduleTrainingModal();
                fetchTrainingSessions();
                showNotification('Success', 'Training session scheduled successfully.');
            } else {
                alert("Error: " + res.error);
            }
        })
        .catch(err => console.error(err));
}

let activeTrainingSessionId = null;

function viewTrainingDetails(id) {
    activeTrainingSessionId = id;
    fetch(`/api/manager/training/${id}`)
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                const s = data.session;
                document.getElementById('detailsTrainTitle').textContent = s.title;
                document.getElementById('detailsTrainStatus').textContent = s.status;
                document.getElementById('detailsTrainType').textContent = s.type;
                document.getElementById('detailsTrainTime').textContent = `${s.date} | ${s.start_time.substring(0, 5)} - ${s.end_time.substring(0, 5)}`;
                document.getElementById('detailsTrainLocation').textContent = s.location || 'TBD';
                document.getElementById('detailsTrainDesc').textContent = s.description || 'No description provided.';

                let phtml = '';
                s.players.forEach(p => {
                    phtml += `
                    <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
                        <td style="padding: 0.5rem; color: white;">${p.name}</td>
                        <td style="padding: 0.5rem;">
                            <select class="form-input att-status" data-pid="${p.player_id}" style="padding: 0.2rem; font-size: 0.8rem; height: auto;">
                                <option value="Pending" ${p.status === 'Pending' ? 'selected' : ''}>Pending</option>
                                <option value="Present" ${p.status === 'Present' ? 'selected' : ''}>Present</option>
                                <option value="Absent" ${p.status === 'Absent' ? 'selected' : ''}>Absent</option>
                                <option value="Late" ${p.status === 'Late' ? 'selected' : ''}>Late</option>
                                <option value="Excused" ${p.status === 'Excused' ? 'selected' : ''}>Excused</option>
                            </select>
                        </td>
                        <td style="padding: 0.5rem;">
                            <input type="text" class="form-input att-remarks" data-pid="${p.player_id}" value="${p.remarks || ''}" placeholder="Remarks" style="padding: 0.2rem; font-size: 0.8rem;">
                        </td>
                    </tr>
                `;
                });
                document.getElementById('detailsTrainPlayers').innerHTML = phtml;

                document.getElementById('trainingDetailsModal').style.display = 'flex';
            }
        });
}

function closeTrainingDetailsModal() {
    document.getElementById('trainingDetailsModal').style.display = 'none';
    activeTrainingSessionId = null;
}

function saveTrainingAttendance() {
    if (!activeTrainingSessionId) return;

    const updates = [];
    const rows = document.querySelectorAll('#detailsTrainPlayers tr');
    rows.forEach(row => {
        const statSelect = row.querySelector('.att-status');
        const remInput = row.querySelector('.att-remarks');
        if (statSelect && remInput) {
            updates.push({
                player_id: parseInt(statSelect.getAttribute('data-pid')),
                status: statSelect.value,
                remarks: remInput.value
            });
        }
    });

    fetch(`/api/manager/training/${activeTrainingSessionId}/attendance`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ attendance: updates })
    })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                showNotification('Success', 'Attendance saved successfully.');
            } else {
                alert('Error: ' + data.error);
            }
        });
}

function updateTrainingStatus(status) {
    if (!activeTrainingSessionId) return;
    if (!confirm(`Are you sure you want to mark this training as ${status}?`)) return;

    fetch(`/api/manager/training/${activeTrainingSessionId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: status })
    })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                closeTrainingDetailsModal();
                fetchTrainingSessions();
                showNotification('Success', `Training ${status.toLowerCase()} successfully.`);
            }
        });
}

// ==========================================
// ANALYST DASHBOARD FUNCTIONS
// ==========================================


// ---- Analyst Profile Settings ----
async function loadAnalystProfileSettings() {
    try {
        const res = await fetch('/api/me', { credentials: 'include' });
        if (!res.ok) return;
        const data = await res.json();
        const nameEl = document.getElementById('analyst-profile-name');
        const emailEl = document.getElementById('analyst-profile-email');
        if (nameEl && data.username) nameEl.value = data.username;
        if (emailEl && data.email) emailEl.value = data.email;
    } catch (e) {
        console.warn('Could not load analyst profile:', e);
    }
}

window.saveAnalystProfile = async function (e) {
    e.preventDefault();
    const btn = e.target.querySelector('button[type="submit"]');
    const originalText = btn ? btn.innerHTML : '';
    if (btn) { btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...'; btn.disabled = true; }

    const name = document.getElementById('analyst-profile-name')?.value;
    const email = document.getElementById('analyst-profile-email')?.value;
    const password = document.getElementById('analyst-profile-password')?.value;

    const payload = {};
    if (name) payload.username = name;
    if (email) payload.email = email;
    if (password) payload.password = password;

    try {
        const res = await fetch('/api/analyst/update_profile', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(payload)
        });
        if (res.ok) {
            const data = await res.json();
            if (data.success) {
                showNotification('Profile updated successfully!', 'success');
                document.getElementById('analyst-profile-password').value = '';
            } else {
                showNotification(data.error || 'Failed to update profile.', 'error');
            }
        } else {
            showNotification('Server error updating profile.', 'error');
        }
    } catch (err) {
        showNotification('Network error.', 'error');
    } finally {
        if (btn) { btn.innerHTML = originalText; btn.disabled = false; }
    }
};

let analystHeatmapChart = null;

let analystPoolData = [];

async function loadAnalystDashboard() {
    try {
        // 1. Fetch Dashboard Stats
        const dashboardRes = await fetch('/api/analyst/dashboard_data');
        if (dashboardRes.ok) {
            const data = await dashboardRes.json();
            if (data.success && data.stats) {
                const elWinProb = document.getElementById('analystWinProb');
                if (elWinProb) elWinProb.textContent = data.stats.win_probability || 'N/A';

                const elTeamRank = document.getElementById('analystTeamRank');
                if (elTeamRank) elTeamRank.textContent = data.stats.team_rank || 'N/A';

                const elPerfTrend = document.getElementById('analystPerfTrend');
                if (elPerfTrend) elPerfTrend.textContent = data.stats.performance_trend || 'N/A';

                const elValuePicks = document.getElementById('analystValuePicks');
                if (elValuePicks) elValuePicks.textContent = data.stats.value_picks || 'N/A';
            }
        } else {
            console.error(`[ANALYST API ERROR] /api/analyst/dashboard_data failed with status: ${dashboardRes.status}`);
            const errText = await dashboardRes.text();
            console.error(`[ANALYST API RESPONSE] ${errText}`);
        }

        // 2. Fetch Analyst Players for Scout Pool & Radar
        const playersRes = await fetch('/api/analyst/players');
        if (playersRes.ok) {
            const pData = await playersRes.json();
            if (pData.success && pData.players) {
                analystPoolData = pData.players;
                const tbody = document.getElementById('scoutPoolTableBody');
                const radarSelect = document.getElementById('radarPlayerSelect');

                if (tbody) {
                    if (analystPoolData.length === 0) {
                        tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; padding: 2rem; color: #64748b;">No players found</td></tr>';
                    } else {
                        tbody.innerHTML = analystPoolData.map(p => `
                            <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
                                <td style="padding: 0.75rem;">${p.name || 'Unknown'}</td>
                                <td style="padding: 0.75rem;">${p.role || 'Player'}</td>
                                <td style="padding: 0.75rem; text-align: center;"><span class="badge category-${(p.category || 'Standard').toLowerCase()}">${p.category || 'Standard'}</span></td>
                                <td style="padding: 0.75rem; text-align: right;">₹${(p.base_price || 0).toLocaleString()}</td>
                            </tr>
                        `).join('');
                    }
                }

                if (radarSelect) {
                    radarSelect.innerHTML = '<option value="">Select a player...</option>' +
                        analystPoolData.map(p => `<option value="${p.id}">${p.name}</option>`).join('');
                }
            }
        } else {
            console.error(`[ANALYST API ERROR] /api/analyst/players failed with status: ${playersRes.status}`);
            const errText = await playersRes.text();
            console.error(`[ANALYST API RESPONSE] ${errText}`);
        }

        // 3. Setup Scroll Spy (IntersectionObserver)
        const analystSections = document.querySelectorAll('#analyst-panel > .center-panel, #analyst-panel > .dashboard-grid');
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const id = entry.target.id;
                    const viewName = id.replace('section-', '');

                    // Update active sidebar item
                    document.querySelectorAll('.sidebar-item').forEach(item => {
                        item.classList.remove('active');
                        const path = item.getAttribute('data-path');
                        if (path && path.includes('#' + viewName)) {
                            item.classList.add('active');
                        }
                    });
                }
            });
        }, {
            root: null,
            rootMargin: '-20% 0px -60% 0px',
            threshold: 0
        });

        analystSections.forEach(section => {
            observer.observe(section);
        });

    } catch (error) {
        console.error('Error loading analyst dashboard:', error);
    }
}

window.handleRadarSelectChange = async function () {
    const select = document.getElementById('radarPlayerSelect');
    if (!select) return;

    const playerId = select.value;
    const emptyState = document.getElementById('radarEmptyState');
    const canvasContainer = document.getElementById('radarCanvasContainer');

    if (!playerId) {
        if (emptyState) {
            emptyState.style.display = 'flex';
            emptyState.innerHTML = '<i class="fas fa-chart-pie empty-icon"></i><p>Select a player to view performance radar.</p>';
        }
        if (canvasContainer) canvasContainer.style.display = 'none';
        return;
    }

    // Fetch stats for the selected player
    try {
        const res = await fetch(`/api/analyst/player_stats/${playerId}`);
        if (res.ok) {
            const data = await res.json();
            if (data.success && data.stats && data.stats.length > 0) {
                if (emptyState) emptyState.style.display = 'none';
                if (canvasContainer) canvasContainer.style.display = 'block';
                renderRadarMap(data.player.name, data.stats);
            } else {
                if (emptyState) {
                    emptyState.style.display = 'flex';
                    emptyState.innerHTML = '<i class="fas fa-chart-pie empty-icon"></i><p>No performance data available for this player.</p>';
                }
                if (canvasContainer) canvasContainer.style.display = 'none';
            }
        } else {
            console.error(`[ANALYST API ERROR] /api/analyst/player_stats/${playerId} failed with status: ${res.status}`);
        }
    } catch (error) {
        console.error('Error fetching player stats:', error);
    }
}

function renderRadarMap(playerName, stats) {
    const ctx = document.getElementById('playerRadarChart');
    if (!ctx) return;

    // Use default radar labels since backend currently returns an array of values
    const labels = ['Batting', 'Bowling', 'Fielding', 'Consistency', 'Form', 'Value'];
    const data = stats;

    if (analystHeatmapChart) {
        analystHeatmapChart.destroy();
    }

    // Check if Chart.js is loaded
    if (typeof Chart === 'undefined') {
        console.error('Chart.js is not loaded.');
        return;
    }

    analystHeatmapChart = new Chart(ctx, {
        type: 'radar',
        data: {
            labels: labels,
            datasets: [{
                label: `${playerName} Performance`,
                data: data,
                backgroundColor: 'rgba(56, 189, 248, 0.2)',
                borderColor: 'rgba(56, 189, 248, 1)',
                pointBackgroundColor: 'rgba(56, 189, 248, 1)',
                pointBorderColor: '#fff',
                pointHoverBackgroundColor: '#fff',
                pointHoverBorderColor: 'rgba(56, 189, 248, 1)',
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                r: {
                    angleLines: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    pointLabels: {
                        color: '#94a3b8',
                        font: {
                            size: 12
                        }
                    },
                    ticks: {
                        display: false,
                        min: 0,
                        max: 100
                    }
                }
            },
            plugins: {
                legend: {
                    labels: {
                        color: '#fff'
                    }
                }
            }
        }
    });
}

window.generateAnalystReport = async function () {
    try {
        const btn = document.querySelector('button[onclick="generateAnalystReport()"]');
        const originalText = btn ? btn.innerHTML : '<i class="fas fa-file-csv"></i> Generate Report';
        if (btn) {
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Generating...';
            btn.disabled = true;
        }

        // Extract dashboard stats directly from UI to match exactly what is displayed
        const winProb = document.getElementById('analystWinProb') ? document.getElementById('analystWinProb').textContent : 'N/A';
        const teamRank = document.getElementById('analystTeamRank') ? document.getElementById('analystTeamRank').textContent : 'N/A';
        const perfTrend = document.getElementById('analystPerfTrend') ? document.getElementById('analystPerfTrend').textContent : 'N/A';
        const valuePicks = document.getElementById('analystValuePicks') ? document.getElementById('analystValuePicks').textContent : 'N/A';

        let csvContent = "Section,Metric,Value\n";

        csvContent += `Summary,Win Probability,${winProb}\n`;
        csvContent += `Summary,Team Rank,${teamRank}\n`;
        csvContent += `Summary,Performance Trend,${perfTrend}\n`;
        csvContent += `Summary,Value Picks,${valuePicks}\n`;

        csvContent += "\nPlayer,Role,Category,Base Price\n";
        // Use analystPoolData which populates the Analyst Scout Pool table
        if (typeof analystPoolData !== 'undefined' && analystPoolData && analystPoolData.length > 0) {
            analystPoolData.forEach(p => {
                const name = (p.name || 'Unknown').replace(/,/g, '');
                const role = (p.role || 'Player').replace(/,/g, '');
                const category = (p.category || 'Standard').replace(/,/g, '');
                const basePrice = p.base_price !== undefined ? p.base_price : '0';
                csvContent += `${name},${role},${category},${basePrice}\n`;
            });
        }

        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.setAttribute("href", url);
        const dateStr = new Date().toISOString().split('T')[0];
        link.setAttribute("download", `jamrig-analyst-report-${dateStr}.csv`);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);

        if (btn) {
            btn.innerHTML = originalText;
            btn.disabled = false;
        }

        showNotification('Analyst Report generated successfully.', 'success');

    } catch (error) {
        console.error('Error generating report:', error);
        alert('Failed to generate report.');
        const btn = document.querySelector('button[onclick="generateAnalystReport()"]');
        if (btn) {
            btn.innerHTML = '<i class="fas fa-file-csv"></i> Generate Report';
            btn.disabled = false;
        }
    }
};

// Handle smooth scrolling for Analyst dashboard sections
window.addEventListener('viewChanged', (e) => {
    const path = e.detail.path;
    if (path.startsWith('/dashboard/analyst')) {
        const hash = path.includes('#') ? path.split('#')[1] : '';
        const analystSectionMap = {
            'analytics': 'section-analytics',
            'performance': 'section-performance',
            'reports': 'section-reports',
            'predictions': 'section-predictions',
            'settings': 'section-analyst-settings'
        };
        const sectionId = analystSectionMap[hash] || (hash ? `section-${hash}` : null);
        if (sectionId) {
            document.getElementById(sectionId)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        } else {
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }
    }
});

// User Menu Toggle Logic
window.toggleUserMenu = function() {
    const menu = document.getElementById('userDropdownMenu');
    if (menu) {
        menu.style.display = menu.style.display === 'none' || menu.style.display === '' ? 'block' : 'none';
    }
};

document.addEventListener('click', function(event) {
    const container = document.querySelector('.user-dropdown-container');
    const menu = document.getElementById('userDropdownMenu');
    if (container && menu && !container.contains(event.target)) {
        menu.style.display = 'none';
    }
});
